#!/usr/bin/env python3
"""Build a local, CPU-only Kokoro proof-listening audiobook.

This is intentionally separate from the publication pipeline.  It reuses the
same Markdown-to-speech cleanup as the ElevenLabs builder, caches generated
speech by text/settings hash, and writes one proof-listening M4A or MP3 per chapter.

Kokoro dependencies are optional; see tools/requirements-audio-kokoro.txt.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import shutil
import subprocess
import sys
import time
import wave
from pathlib import Path

from audiobook_text import discover_chapters, split_into_chunks, strip_markdown
from book_tools_common import load_env, repo_root, resolve_under

SAMPLE_RATE = 24_000
DEFAULT_VOICE = "af_heart"
DEFAULT_SPEED = 1.0
DEFAULT_CHUNK_CHARS = 900
DEFAULT_FORMAT = "m4a"
DEFAULT_AAC_BITRATE = "96k"
DEFAULT_MP3_BITRATE = "128k"
DEFAULT_GAP_MS = 120
DEFAULT_INTERNAL_GAP_MS = 90
LANG_CODE = "a"  # American English


def fail(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def parse_float(value: str, name: str) -> float:
    try:
        result = float(value)
    except ValueError as exc:
        raise SystemExit(f"ERROR: {name} must be a number; got {value!r}.") from exc
    if result <= 0:
        raise SystemExit(f"ERROR: {name} must be greater than zero; got {value!r}.")
    return result


def parse_int(value: str, name: str) -> int:
    try:
        result = int(value)
    except ValueError as exc:
        raise SystemExit(f"ERROR: {name} must be an integer; got {value!r}.") from exc
    if result <= 0:
        raise SystemExit(f"ERROR: {name} must be greater than zero; got {value!r}.")
    return result


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def package_version(name: str) -> str:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return "not-installed"


def select_chapters(book_dir: Path, prefixes: list[str] | None) -> list[tuple[str, Path]]:
    chapters = discover_chapters(book_dir)
    if prefixes:
        chapters = [
            item for item in chapters
            if any(item[0].startswith(prefix) for prefix in prefixes)
        ]
    if not chapters:
        fail(f"no chapters found in {book_dir}")
    return chapters


def chapter_title(plain: str, slug: str) -> str:
    first = next((line.strip() for line in plain.splitlines() if line.strip()), "")
    return first.rstrip(".") or slug


def cache_key(text: str, voice: str, speed: float, kokoro_version: str) -> str:
    payload = json.dumps(
        {
            "engine": "kokoro-82m",
            "kokoro_version": kokoro_version,
            "lang": LANG_CODE,
            "voice": voice,
            "speed": speed,
            "text": text,
        },
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return sha256_text(payload)


def cache_path(cache_dir: Path, key: str) -> Path:
    return cache_dir / key[:2] / f"{key}.wav"


def require_generation_dependencies() -> tuple[object, object, object]:
    try:
        import numpy as np
        import soundfile as sf
        import torch
        from kokoro import KPipeline
    except ImportError as exc:
        fail(
            "Kokoro generation dependencies are missing. Install them with:\n"
            "  python3 -m pip install -r tools/requirements-audio-kokoro.txt\n"
            f"Underlying import error: {exc}"
        )
    return np, sf, (torch, KPipeline)


def build_pipeline(threads: int):
    np, sf, (torch, KPipeline) = require_generation_dependencies()
    if threads > 0:
        torch.set_num_threads(threads)
        try:
            torch.set_num_interop_threads(1)
        except RuntimeError:
            # PyTorch only allows this before parallel work has begun.  A reused
            # interpreter may already have initialized its inter-op pool.
            pass
    print(f"Loading Kokoro on CPU (torch threads: {torch.get_num_threads()}) …", flush=True)
    pipeline = KPipeline(lang_code=LANG_CODE, device="cpu")
    return np, sf, pipeline


def render_chunk(
    pipeline,
    np,
    sf,
    text: str,
    destination: Path,
    voice: str,
    speed: float,
    internal_gap_ms: int,
) -> None:
    parts = []
    gap = np.zeros(int(SAMPLE_RATE * internal_gap_ms / 1000), dtype=np.float32)

    # Let Kokoro do its own phoneme-aware sub-chunking inside our cache-sized
    # chunk. Newlines preserve paragraph/heading boundaries.
    for result in pipeline(text, voice=voice, speed=speed, split_pattern=r"\n+"):
        audio = result.audio
        if audio is None:
            continue
        if hasattr(audio, "detach"):
            audio = audio.detach()
        if hasattr(audio, "cpu"):
            audio = audio.cpu()
        if hasattr(audio, "numpy"):
            audio = audio.numpy()
        audio = np.asarray(audio, dtype=np.float32).reshape(-1)
        if audio.size:
            if parts:
                parts.append(gap)
            parts.append(audio)

    if not parts:
        fail(f"Kokoro produced no audio for chunk: {text[:100]!r}")

    destination.parent.mkdir(parents=True, exist_ok=True)
    tmp = destination.with_suffix(".tmp.wav")
    sf.write(tmp, np.concatenate(parts), SAMPLE_RATE, subtype="PCM_16")
    tmp.replace(destination)


def concatenate_wavs(paths: list[Path], destination: Path, gap_ms: int) -> None:
    if not paths:
        fail("cannot concatenate an empty chapter")

    destination.parent.mkdir(parents=True, exist_ok=True)
    tmp = destination.with_suffix(".tmp.wav")
    silence_frames = int(SAMPLE_RATE * gap_ms / 1000)
    silence = b"\x00\x00" * silence_frames

    with wave.open(str(tmp), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(SAMPLE_RATE)
        for index, path in enumerate(paths):
            with wave.open(str(path), "rb") as src:
                if (src.getnchannels(), src.getsampwidth(), src.getframerate()) != (1, 2, SAMPLE_RATE):
                    fail(f"unexpected WAV format in cache file: {path}")
                while frames := src.readframes(64 * 1024):
                    out.writeframes(frames)
            if index + 1 < len(paths) and gap_ms:
                out.writeframes(silence)

    tmp.replace(destination)


def encode_audio(
    wav_path: Path,
    output_path: Path,
    audio_format: str,
    bitrate: str,
    book_title: str,
    author: str,
    title: str,
) -> None:
    if not shutil.which("ffmpeg"):
        fail("ffmpeg is required to create M4A/MP3 files. Install ffmpeg or use --wav-only.")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = output_path.with_name(f"{output_path.stem}.tmp{output_path.suffix}")
    command = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(wav_path),
        "-vn", "-ac", "1", "-ar", str(SAMPLE_RATE),
    ]
    if audio_format == "m4a":
        command += [
            "-codec:a", "aac", "-profile:a", "aac_low", "-b:a", bitrate,
            "-movflags", "+faststart",
        ]
    elif audio_format == "mp3":
        command += ["-codec:a", "libmp3lame", "-b:a", bitrate]
    else:
        fail(f"unsupported audio format: {audio_format}")

    command += [
        "-metadata", f"title={title}",
        "-metadata", f"album={book_title}",
        "-metadata", f"artist={author}",
        str(tmp),
    ]
    result = subprocess.run(command, check=False)
    if result.returncode:
        fail(f"ffmpeg failed while encoding {output_path.name}")
    tmp.replace(output_path)


def output_duration(path: Path) -> float | None:
    if not shutil.which("ffprobe"):
        return None
    result = subprocess.run(
        [
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", str(path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode:
        return None
    try:
        return float(result.stdout.strip())
    except ValueError:
        return None


def manifest_matches(path: Path, expected: dict) -> bool:
    if not path.is_file():
        return False
    try:
        actual = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return False
    return all(actual.get(key) == value for key, value in expected.items())


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Build a free local Kokoro proof-listening audiobook (CPU only)."
    )
    p.add_argument("book_dir", help="Book directory containing book.env and chapter Markdown")
    p.add_argument("--voice", help=f"Kokoro voice (default: book.env or {DEFAULT_VOICE})")
    p.add_argument("--speed", type=float, help=f"Narration speed (default: {DEFAULT_SPEED})")
    p.add_argument("--chunk-chars", type=int, help=f"Outer cache chunk size (default: {DEFAULT_CHUNK_CHARS})")
    p.add_argument("--format", choices=("m4a", "mp3"), help=f"Compressed output format (default: book.env or {DEFAULT_FORMAT})")
    p.add_argument("--bitrate", help="Compressed audio bitrate (default: 96k for M4A, 128k for MP3)")
    p.add_argument("--threads", type=int, default=0, help="PyTorch CPU threads; 0 uses PyTorch default")
    p.add_argument("--chapters", nargs="+", metavar="PREFIX", help="Only slugs beginning with PREFIX")
    p.add_argument("--output-dir", help="Final chapter output directory")
    p.add_argument("--build-dir", help="Cache/narration-text directory")
    p.add_argument("--wav-only", action="store_true", help="Keep chapter WAV instead of compressed M4A/MP3")
    p.add_argument("--force", action="store_true", help="Regenerate cached audio and final files")
    p.add_argument("--dry-run", action="store_true", help="Show narration/chunk plan without loading Kokoro")
    return p


def main() -> None:
    args = parser().parse_args()
    root = repo_root()
    book_dir = resolve_under(root, args.book_dir)
    env_path = book_dir / "book.env"
    if not env_path.is_file():
        fail(f"missing book metadata: {env_path}")

    env = load_env(env_path)
    basename = env.get("BOOK_OUTPUT_BASENAME") or book_dir.name
    book_title = env.get("BOOK_TITLE") or basename
    author = env.get("BOOK_AUTHOR") or ""

    voice = args.voice or env.get("BOOK_AUDIO_KOKORO_VOICE") or DEFAULT_VOICE
    speed = args.speed if args.speed is not None else parse_float(
        env.get("BOOK_AUDIO_KOKORO_SPEED", str(DEFAULT_SPEED)), "BOOK_AUDIO_KOKORO_SPEED"
    )
    chunk_chars = args.chunk_chars if args.chunk_chars is not None else parse_int(
        env.get("BOOK_AUDIO_KOKORO_CHUNK_CHARS", str(DEFAULT_CHUNK_CHARS)),
        "BOOK_AUDIO_KOKORO_CHUNK_CHARS",
    )
    audio_format = args.format or env.get("BOOK_AUDIO_KOKORO_FORMAT") or DEFAULT_FORMAT
    if audio_format not in {"m4a", "mp3"}:
        fail("BOOK_AUDIO_KOKORO_FORMAT/--format must be m4a or mp3")
    default_bitrate = DEFAULT_AAC_BITRATE if audio_format == "m4a" else DEFAULT_MP3_BITRATE
    bitrate_env = (
        env.get("BOOK_AUDIO_KOKORO_AAC_BITRATE")
        if audio_format == "m4a"
        else env.get("BOOK_AUDIO_KOKORO_MP3_BITRATE")
    )
    bitrate = args.bitrate or bitrate_env or default_bitrate

    if speed <= 0:
        fail("--speed must be greater than zero")
    if chunk_chars < 300:
        fail("--chunk-chars should be at least 300")
    if args.threads < 0:
        fail("--threads cannot be negative")

    build_dir = resolve_under(
        root,
        args.build_dir or Path("build") / "audiobook-kokoro" / basename,
    )
    output_dir = resolve_under(
        root,
        args.output_dir or Path("dist") / f"{basename}-audio-proof",
    )
    cache_dir = build_dir / "cache"
    text_dir = build_dir / "text"
    manifest_dir = build_dir / "manifests"

    chapters = select_chapters(book_dir, args.chapters)
    narration: list[tuple[str, Path, str, list[str]]] = []
    total_chars = 0
    total_words = 0
    total_chunks = 0
    for slug, path in chapters:
        plain = strip_markdown(path.read_text(encoding="utf-8"))
        chunks = split_into_chunks(plain, chunk_chars)
        narration.append((slug, path, plain, chunks))
        total_chars += len(plain)
        total_words += len(plain.split())
        total_chunks += len(chunks)

    print(f"\nBook          : {book_title}")
    print(f"Book dir      : {book_dir}")
    print(f"Voice         : {voice}")
    print(f"Speed         : {speed:g}x")
    print(f"Device        : CPU only")
    print(f"Chapters      : {len(chapters)}")
    print(f"Narration     : {total_words:,} words / {total_chars:,} chars")
    print(f"Outer chunks  : {total_chunks:,} (target <= {chunk_chars} chars)")
    print(f"Est. audio    : ~{total_words / 160 / 60 / speed:.1f} hours at ~160 wpm")
    print(f"Build cache   : {build_dir}")
    print(f"Final output  : {output_dir}")
    if args.wav_only:
        print("Format        : 24 kHz mono WAV")
    elif audio_format == "m4a":
        print(f"Format        : 24 kHz mono M4A / AAC-LC @ {bitrate}")
    else:
        print(f"Format        : 24 kHz mono MP3 @ {bitrate}")
    if args.threads:
        print(f"Torch threads : {args.threads}")

    if args.dry_run:
        print("\nDRY RUN — Kokoro will not be loaded.\n")
        for slug, _path, plain, chunks in narration:
            print(f"  {slug:<42} {len(plain):>7,} chars  {len(chunks):>4} chunks")
        return

    kokoro_version = package_version("kokoro")
    if kokoro_version == "not-installed":
        fail(
            "Kokoro is not installed. Run:\n"
            "  python3 -m pip install -r tools/requirements-audio-kokoro.txt"
        )
    print(f"Kokoro        : {kokoro_version}")

    np, sf, pipeline = build_pipeline(args.threads)
    output_dir.mkdir(parents=True, exist_ok=True)
    text_dir.mkdir(parents=True, exist_ok=True)
    manifest_dir.mkdir(parents=True, exist_ok=True)

    started = time.time()
    generated = reused = 0
    outputs: list[Path] = []

    for chapter_index, (slug, source_path, plain, chunks) in enumerate(narration, 1):
        print(f"\n[{chapter_index}/{len(narration)}] {slug}")
        text_path = text_dir / f"{slug}.txt"
        text_path.write_text(plain + "\n", encoding="utf-8")

        source_hash = sha256_text(source_path.read_text(encoding="utf-8"))
        narration_hash = sha256_text(plain)
        extension = ".wav" if args.wav_only else f".{audio_format}"
        final = output_dir / f"{slug}{extension}"
        manifest_path = manifest_dir / f"{slug}.json"
        expected = {
            "source_sha256": source_hash,
            "narration_sha256": narration_hash,
            "voice": voice,
            "speed": speed,
            "chunk_chars": chunk_chars,
            "format": "wav" if args.wav_only else audio_format,
            "bitrate": None if args.wav_only else bitrate,
            "wav_only": args.wav_only,
            "kokoro_version": kokoro_version,
        }

        if final.is_file() and manifest_matches(manifest_path, expected) and not args.force:
            print("  unchanged — final audio already current")
            outputs.append(final)
            continue

        chunk_paths: list[Path] = []
        for index, chunk in enumerate(chunks, 1):
            key = cache_key(chunk, voice, speed, kokoro_version)
            wav = cache_path(cache_dir, key)
            chunk_paths.append(wav)
            if wav.is_file() and not args.force:
                reused += 1
                print(f"  chunk {index:03d}/{len(chunks)} — cache", flush=True)
                continue

            print(
                f"  chunk {index:03d}/{len(chunks)} — render {len(chunk):,} chars … ",
                end="",
                flush=True,
            )
            t0 = time.time()
            render_chunk(
                pipeline, np, sf, chunk, wav, voice, speed, DEFAULT_INTERNAL_GAP_MS
            )
            generated += 1
            print(f"{time.time() - t0:.1f}s")

        chapter_wav = build_dir / "chapters" / f"{slug}.wav"
        concatenate_wavs(chunk_paths, chapter_wav, DEFAULT_GAP_MS)
        title = chapter_title(plain, slug)
        if args.wav_only:
            final.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(chapter_wav, final)
        else:
            encode_audio(chapter_wav, final, audio_format, bitrate, book_title, author, title)
            chapter_wav.unlink(missing_ok=True)

        manifest = {
            **expected,
            "source": str(source_path.relative_to(root)),
            "title": title,
            "chunks": [cache_key(chunk, voice, speed, kokoro_version) for chunk in chunks],
            "output": str(final.relative_to(root)),
        }
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        outputs.append(final)

        duration = output_duration(final)
        size_mb = final.stat().st_size / (1024 * 1024)
        suffix = f", {duration / 60:.1f} min" if duration is not None else ""
        print(f"  -> {final.name} ({size_mb:.1f} MB{suffix})")

    elapsed = time.time() - started
    total_duration = sum(filter(None, (output_duration(path) for path in outputs)))
    print("\nDone.")
    print(f"  Rendered chunks : {generated:,}")
    print(f"  Reused chunks   : {reused:,}")
    print(f"  Wall time       : {elapsed / 60:.1f} min")
    if total_duration:
        print(f"  Audio duration  : {total_duration / 3600:.2f} hours")
        print(f"  Overall RTF     : {elapsed / total_duration:.3f}")
    print(f"  Output          : {output_dir}")


if __name__ == "__main__":
    main()
