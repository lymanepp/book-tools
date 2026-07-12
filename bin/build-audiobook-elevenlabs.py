#!/usr/bin/env python3
"""Build ElevenLabs audiobook chapters and master them for ACX."""

import os
import re
import sys
import time
import argparse
import textwrap
from pathlib import Path


from audiobook_text import discover_chapters, split_into_chunks, strip_markdown
from book_tools_common import load_env

# Configuration — Generation

BOOK_DIR  = Path(__file__).parent / "book1"
OUTPUT_DIR = Path(__file__).parent / "audiobook"

# ElevenLabs model
# eleven_v3              — highest naturalness; explicit audiobook recommendation
# eleven_multilingual_v2 — excellent quality, cheaper, 10k char limit per chunk
MODEL    = "eleven_v3"

# Voice ID — replace with your chosen voice (use --list-voices to find IDs)
# Audition voices at: https://elevenlabs.io/voice-library
VOICE_ID = "JBFqnCBsd6RMkjVDRZzb"

# ID                    Name                      Category
# -------------------------------------------------------------
# hpp4J3VqNfWAUOO0d1Us  Bella - Professional, Bright, Warm premade
# N2lVS1w4EtoT3dr4eOWO  Callum - Husky Trickster  premade
# IKne3meq5aSn9XLyUdCD  Charlie - Deep, Confident, Energetic premade
# JBFqnCBsd6RMkjVDRZzb  George - Warm, Captivating Storyteller premade
# SOYHLrjzK2X1ezoPC6cr  Harry - Fierce Warrior    premade
# FGY2WhTYpPnrIDTdsKH5  Laura - Enthusiast, Quirky Attitude premade
# TX3LPaxmHKxFdv7VOQHJ  Liam - Energetic, Social Media Creator premade
# SAz9YHcvj6GT2YYXdXww  River - Relaxed, Neutral, Informative premade
# CwhRBWXzGAHq8TQ4Fs17  Roger - Laid-Back, Casual, Resonant premade
# EXAVITQu4vr4xnSDxMaL  Sarah - Mature, Reassuring, Confident premade

# ElevenLabs output format (Pro plan or above required for 192 kbps)
EL_FORMAT = "mp3_44100_192"

# Voice character settings — tuned for authoritative nonfiction narration
STABILITY        = 0.60   # 0.55–0.65: consistent but not robotic
SIMILARITY_BOOST = 0.80   # 0.75–0.85: faithful to chosen voice
STYLE            = 0.10   # keep low for nonfiction; higher = over-dramatic
SPEAKER_BOOST    = True   # recommended for final renders

# Seconds between API chunk calls (burst throttle)
CHUNK_DELAY = 0.5

# Character limits per model (hard limits minus safety headroom)
CHUNK_LIMITS = {
    "eleven_v3":              2800,   # hard limit 3,000
    "eleven_multilingual_v2": 9500,   # hard limit 10,000
    "eleven_flash_v2_5":     38000,   # hard limit 40,000
}

# Configuration — Post-processing (ACX mastering)
# These can be adjusted and --master re-run at no API cost.

ACX_TARGET_RMS_DBFS   = -20.0   # aim for centre of ACX window (-23 to -18)
ACX_PEAK_CEILING_DBFS =  -3.0   # lower to -3.5 if ACX rejects on true peaks
ACX_RMS_MIN_DBFS      = -23.0   # ACX floor  (do not change)
ACX_RMS_MAX_DBFS      = -18.0   # ACX ceiling (do not change)
HEAD_SILENCE_MS       =   500   # 0.5 s — ACX minimum is 0.5 s
TAIL_SILENCE_MS       =  1000   # 1.0 s — ACX minimum is 1.0 s

# File layout

def raw_dir(output_dir: Path, slug: str) -> Path:
    """Directory where raw chunk files for a chapter are stored."""
    return output_dir / "raw" / slug


def final_path(output_dir: Path, slug: str) -> Path:
    """Path of the final ACX-mastered chapter MP3."""
    return output_dir / f"{slug}.mp3"


# Credit / cost estimation

def estimate_credits(chapters: list[tuple[str, Path]], model: str) -> tuple:
    total = sum(
        len(strip_markdown(p.read_text(encoding='utf-8')))
        for _, p in chapters
    )
    multiplier = 0.5 if 'flash' in model else 1.0
    credits    = int(total * multiplier)
    if 'v3' in model:
        cost = (total / 1000) * 0.24
    elif 'multilingual' in model:
        cost = (total / 1000) * 0.15
    else:
        cost = (total / 1000) * 0.08
    return total, credits, f"~${cost:.2f}"


# Stage 1 — Generation

def get_client(api_key: str):
    try:
        from elevenlabs.client import ElevenLabs
    except ImportError as exc:
        raise SystemExit("elevenlabs is required for generation. Install it with: pip install elevenlabs") from exc
    return ElevenLabs(api_key=api_key)


def list_voices(client) -> None:
    response = client.voices.search()
    print(f"\n{'ID':<32} {'Name':<25} Category")
    print('-' * 72)
    for v in sorted(response.voices, key=lambda x: x.name):
        print(f"{v.voice_id:<32} {v.name:<25} {getattr(v, 'category', '')}")


def api_narrate_chunk(client, text: str, voice_id: str, model: str,
                      el_format: str) -> bytes:
    try:
        from elevenlabs import VoiceSettings
    except ImportError as exc:
        raise SystemExit("elevenlabs is required for generation. Install it with: pip install elevenlabs") from exc

    audio_iter = client.text_to_speech.convert(
        text=text,
        voice_id=voice_id,
        model_id=model,
        output_format=el_format,
        voice_settings=VoiceSettings(
            stability=STABILITY,
            similarity_boost=SIMILARITY_BOOST,
            style=STYLE,
            use_speaker_boost=SPEAKER_BOOST,
        ),
    )
    return b''.join(audio_iter)


def generate_chapter(client, slug: str, md_path: Path, output_dir: Path,
                     voice_id: str, model: str, el_format: str,
                     dry_run: bool, force: bool) -> bool:
    raw     = md_path.read_text(encoding='utf-8')
    plain   = strip_markdown(raw)
    max_ch  = CHUNK_LIMITS.get(model, 2800)
    chunks  = split_into_chunks(plain, max_ch)
    rdir    = raw_dir(output_dir, slug)
    total_chars = sum(len(c) for c in chunks)

    print(f"  generate: {len(chunks)} chunk(s), {total_chars:,} chars")

    if dry_run:
        for i, chunk in enumerate(chunks, 1):
            print(f"    chunk {i:03d} ({len(chunk):,} chars): "
                  f"{chunk[:72].replace(chr(10), ' ')}…")
        return False

    rdir.mkdir(parents=True, exist_ok=True)
    any_generated = False

    for i, chunk in enumerate(chunks, 1):
        cpath = rdir / f"chunk-{i:03d}.mp3"

        if cpath.exists() and not force:
            print(f"    chunk {i:03d}/{len(chunks)} — exists, skipping")
            continue

        if cpath.exists() and force:
            print(f"    chunk {i:03d}/{len(chunks)} — exists, --force re-generating")

        print(f"    chunk {i:03d}/{len(chunks)} ({len(chunk):,} chars)…",
              end='', flush=True)
        audio = api_narrate_chunk(client, chunk, voice_id, model, el_format)
        cpath.write_bytes(audio)
        print(" ✓")
        any_generated = True

        if i < len(chunks):
            time.sleep(CHUNK_DELAY)

    # Warn if chunk count on disk doesn't match expected (interrupted prior run)
    existing = sorted(rdir.glob("chunk-*.mp3"))
    if len(existing) != len(chunks):
        print(f"    WARNING: {len(existing)} chunk file(s) on disk, "
              f"expected {len(chunks)}. Run --generate again to complete.")

    return any_generated


# Stage 2 — Post-processing / ACX mastering

def master_for_acx(audio):
    import numpy as np
    from pydub import AudioSegment

    audio = audio.set_channels(1)

    audio = audio.set_frame_rate(44100)

    if audio.rms > 0:
        current_dbfs = 20 * np.log10(audio.rms / 32768.0)
        gain = ACX_TARGET_RMS_DBFS - current_dbfs
        audio = audio.apply_gain(gain)

    if audio.max_dBFS > ACX_PEAK_CEILING_DBFS:
        audio = audio.apply_gain(ACX_PEAK_CEILING_DBFS - audio.max_dBFS)

    if audio.rms > 0:
        final_rms = 20 * np.log10(audio.rms / 32768.0)
        if not (ACX_RMS_MIN_DBFS <= final_rms <= ACX_RMS_MAX_DBFS):
            print(f"\n    WARNING: post-limit RMS {final_rms:.1f} dBFS is outside "
                  f"ACX window ({ACX_RMS_MIN_DBFS} to {ACX_RMS_MAX_DBFS} dBFS). "
                  f"Adjust ACX_TARGET_RMS_DBFS or ACX_PEAK_CEILING_DBFS and re-run --master.")

    head = AudioSegment.silent(duration=HEAD_SILENCE_MS, frame_rate=44100).set_channels(1)
    tail = AudioSegment.silent(duration=TAIL_SILENCE_MS, frame_rate=44100).set_channels(1)
    return head + audio + tail


def master_chapter(slug: str, output_dir: Path,
                   book_title: str, force: bool) -> bool:
    fp    = final_path(output_dir, slug)
    rdir  = raw_dir(output_dir, slug)
    cpaths = sorted(rdir.glob("chunk-*.mp3"))

    if not cpaths:
        print(f"  master: no chunks found in {rdir} — run --generate first")
        return False

    if fp.exists() and not force:
        print(f"  master: final MP3 exists, skipping "
              f"(use --force to re-master with new parameters)")
        return False

    if fp.exists() and force:
        print(f"  master: --force re-mastering {fp.name}")

    from pydub import AudioSegment

    print(f"  master: merging {len(cpaths)} chunk(s)…", end='', flush=True)
    combined = AudioSegment.empty()
    for cp in cpaths:
        combined += AudioSegment.from_mp3(str(cp))
    print(" ✓")

    print(f"  master: applying ACX mastering "
          f"(RMS target {ACX_TARGET_RMS_DBFS} dBFS, "
          f"peak ≤ {ACX_PEAK_CEILING_DBFS} dBFS)…", end='', flush=True)
    mastered = master_for_acx(combined)
    print(" ✓")

    print(f"  master: exporting → {fp.name}…", end='', flush=True)
    mastered.export(
        str(fp),
        format='mp3',
        bitrate='192k',
        parameters=['-q:a', '0'],
        tags={
            'title':  slug,
            'album':  book_title,
            'artist': 'Lyman Epp',
        },
    )
    print(" ✓")

    # Inline ACX verification
    m = acx_check(fp)
    rms_ok  = '✓' if m['pass_rms']   else '✗'
    peak_ok = '✓' if m['pass_peak']  else '✗'
    ns_ok   = '✓' if m['pass_noise'] else '✗'
    print(f"  master: ACX check — "
          f"{rms_ok}RMS {m['rms_dbfs']:.1f}  "
          f"{peak_ok}peak {m['peak_dbfs']:.1f}  "
          f"{ns_ok}noise {m['noise_dbfs']:.1f}")

    return True


# ACX compliance checker

def acx_check(path: Path) -> dict:
    """Measure a file against all ACX specifications."""
    import numpy as np
    from pydub import AudioSegment

    audio      = AudioSegment.from_mp3(str(path))
    audio_mono = audio.set_channels(1)

    rms_dbfs  = (20 * np.log10(audio_mono.rms / 32768.0)
                 if audio_mono.rms > 0 else -96.0)
    peak_dbfs = audio_mono.max_dBFS

    # Noise floor: minimum RMS over 0.5 s windows
    samples = np.array(audio_mono.get_array_of_samples(), dtype=np.float32)
    window  = int(44100 * 0.5)
    noise_dbfs = -96.0
    if len(samples) >= window:
        rms_vals = [
            np.sqrt(np.mean(samples[i:i+window] ** 2))
            for i in range(0, len(samples) - window, window // 4)
        ]
        min_rms = min((r for r in rms_vals if r > 0), default=1.0)
        noise_dbfs = 20 * np.log10(min_rms / 32768.0)

    return {
        "rms_dbfs":   rms_dbfs,
        "peak_dbfs":  peak_dbfs,
        "noise_dbfs": noise_dbfs,
        "channels":   audio.channels,
        "frame_rate": audio.frame_rate,
        "pass_rms":   ACX_RMS_MIN_DBFS <= rms_dbfs <= ACX_RMS_MAX_DBFS,
        "pass_peak":  peak_dbfs <= ACX_PEAK_CEILING_DBFS,
        "pass_noise": noise_dbfs <= -60.0,
        "pass_mono":  audio.channels == 1,
        "pass_rate":  audio.frame_rate == 44100,
    }


def print_acx_report(path: Path) -> None:
    m = acx_check(path)

    def row(label, value, passing, unit='dBFS', target=''):
        tick = '✓' if passing else '✗'
        return f"  {tick} {label:<22} {value:>7.1f} {unit}  {target}"

    print(f"\nACX check: {path.name}")
    print(row("RMS loudness",  m['rms_dbfs'],  m['pass_rms'],
              target="(ACX: -23 to -18 dBFS)"))
    print(row("Peak level",    m['peak_dbfs'], m['pass_peak'],
              target="(ACX: ≤ -3 dBFS)"))
    print(row("Noise floor",   m['noise_dbfs'], m['pass_noise'],
              target="(ACX: ≤ -60 dBFS)"))
    ch_ok = m['channels'] == 1
    sr_ok = m['frame_rate'] == 44100
    print(f"  {'✓' if ch_ok else '✗'} {'Channels':<22} {m['channels']:>7}        "
          f"(ACX: 1 — mono)")
    print(f"  {'✓' if sr_ok else '✗'} {'Sample rate':<22} {m['frame_rate']:>7} Hz     "
          f"(ACX: 44,100 Hz)")
    all_pass = all([m['pass_rms'], m['pass_peak'], m['pass_noise'],
                    m['pass_mono'], m['pass_rate']])
    print(f"\n  {'PASS — ACX submission ready' if all_pass else 'FAIL — see issues above'}\n")


# CLI

def parse_args():
    p = argparse.ArgumentParser(
        description='ElevenLabs audiobook builder — two-stage, ACX/Audible compliant',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""
        Stage flags (at least one required except for --check / --list-voices):
          --generate   Call ElevenLabs API; save raw chunk MP3s
          --master     Merge chunks; apply ACX mastering; write final MP3

        Examples:
          python build-audiobook-elevenlabs.py --generate --master
          python build-audiobook-elevenlabs.py --generate --dry-run
          python build-audiobook-elevenlabs.py --generate --chapters 01 02
          python build-audiobook-elevenlabs.py --master
          python build-audiobook-elevenlabs.py --master --force
          python build-audiobook-elevenlabs.py --check audiobook/01-chapter.mp3
          python build-audiobook-elevenlabs.py --list-voices
        """)
    )

    # Stage selection
    p.add_argument('--generate',  action='store_true',
                   help='Stage 1: call ElevenLabs API and save raw chunks')
    p.add_argument('--master',    action='store_true',
                   help='Stage 2: merge chunks and apply ACX mastering')

    # Paths / identity
    p.add_argument('--book-dir',   default=str(BOOK_DIR))
    p.add_argument('--output-dir', default=str(OUTPUT_DIR))
    p.add_argument('--book-title',
                   help='Book title written into MP3 metadata; defaults to BOOK_TITLE in book.env')
    p.add_argument('--voice-id',   default=VOICE_ID)
    p.add_argument('--model',      default=MODEL,
                   choices=['eleven_v3', 'eleven_multilingual_v2',
                            'eleven_flash_v2_5'])
    p.add_argument('--chapters',   nargs='+', metavar='PREFIX',
                   help='Process only chapters whose slug starts with PREFIX')

    # Control
    p.add_argument('--dry-run', action='store_true',
                   help='Preview generation chunking without calling the API')
    p.add_argument('--force',   action='store_true',
                   help='Overwrite existing chunks (--generate) or final MP3s (--master)')

    # Utilities
    p.add_argument('--list-voices', action='store_true',
                   help='List voices in your ElevenLabs library and exit')
    p.add_argument('--check', metavar='FILE',
                   help='Run ACX compliance check on an existing MP3 and exit')

    return p.parse_args()


def load_api_key() -> str | None:
    if key := os.environ.get('ELEVENLABS_API_KEY'):
        return key
    env_path = Path(__file__).parent / '.env'
    if not env_path.exists():
        return None
    for line in env_path.read_text().splitlines():
        if line.strip().startswith('ELEVENLABS_API_KEY='):
            return line.split('=', 1)[1].strip().strip('"\'')
    return None


def fail(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def select_chapters(book_dir: Path, prefixes: list[str] | None):
    if not book_dir.exists():
        fail(f"book directory not found: {book_dir}")
    chapters = discover_chapters(book_dir)
    if not chapters:
        fail(f"no .md files found in {book_dir}")
    if prefixes:
        chapters = [
            chapter for chapter in chapters
            if any(chapter[0].startswith(prefix) for prefix in prefixes)
        ]
        if not chapters:
            fail(f"no chapters matched prefixes: {prefixes}")
    return chapters


def print_run_summary(args, book_dir: Path, output_dir: Path, chapters) -> None:
    stages = ' + '.join(
        stage for stage, enabled in (
            ('generate', args.generate), ('master', args.master)
        ) if enabled
    )
    print(f"\nBook           : {args.book_title}")
    print(f"Stages         : {stages}")
    print(f"Book dir       : {book_dir}")
    print(f"Output dir     : {output_dir}")
    print(f"Chapters       : {len(chapters)}")

    if args.generate:
        total_chars, credits, est_cost = estimate_credits(chapters, args.model)
        print(f"Voice ID       : {args.voice_id}")
        print(f"Model          : {args.model}")
        print(f"EL format      : {EL_FORMAT}")
        print(f"Total chars    : {total_chars:,}")
        print(f"Credits        : ~{credits:,}  (est. pay-as-you-go {est_cost})")
        print("Chunk safety   : existing chunks skipped unless --force")

    if args.master:
        print(f"ACX RMS target : {ACX_TARGET_RMS_DBFS} dBFS  "
              f"(window: {ACX_RMS_MIN_DBFS} to {ACX_RMS_MAX_DBFS})")
        print(f"ACX peak ceil  : {ACX_PEAK_CEILING_DBFS} dBFS")
        print(f"Head / tail    : {HEAD_SILENCE_MS} ms / {TAIL_SILENCE_MS} ms")
        print("Final MP3      : existing files skipped unless --force")

    if args.force:
        print("Force          : ON — existing files will be overwritten")
    if args.dry_run:
        print("\n*** DRY RUN — no API calls will be made ***")


def generation_client(args, api_key: str | None):
    if not args.generate or args.dry_run:
        return None
    if args.voice_id == "REPLACE_WITH_YOUR_VOICE_ID":
        fail("VOICE_ID not set. Run --list-voices, then set VOICE_ID or pass --voice-id <id>.")
    if not api_key:
        fail("ELEVENLABS_API_KEY not set. Export it or add it to tools/bin/.env.")
    return get_client(api_key)


def require_master_dependencies() -> None:
    try:
        import numpy, pydub  # noqa: F401
    except ImportError:
        fail("pip install pydub numpy")


def print_outputs(output_dir: Path) -> None:
    finals = sorted(output_dir.glob('*.mp3'))
    if finals:
        print(f"\nFinal MP3s ({len(finals)}):")
        for path in finals:
            print(f"  {path.name}  ({path.stat().st_size / (1024*1024):.1f} MB)")
    raw_root = output_dir / "raw"
    if raw_root.exists():
        raw_count = sum(1 for _ in raw_root.rglob("chunk-*.mp3"))
        print(f"Raw chunks     : {raw_count} files in {raw_root}")
    print("\nRun --check <file> on any final MP3 to verify ACX compliance.")


def main():
    args = parse_args()
    api_key = load_api_key()

    if args.check:
        path = Path(args.check)
        if not path.exists():
            fail(f"file not found: {path}")
        print_acx_report(path)
        return

    if args.list_voices:
        if not api_key:
            fail("ELEVENLABS_API_KEY not set.")
        list_voices(get_client(api_key))
        return

    if not (args.generate or args.master):
        fail("specify at least one stage: --generate and/or --master\n  Run with --help for usage.")

    book_dir = Path(args.book_dir)
    output_dir = Path(args.output_dir)
    if args.book_title is None:
        env_path = book_dir / 'book.env'
        if not env_path.is_file():
            fail(f'book metadata not found: {env_path}')
        args.book_title = load_env(env_path).get('BOOK_TITLE')
        if not args.book_title:
            fail(f'BOOK_TITLE is not set in {env_path}')
    chapters = select_chapters(book_dir, args.chapters)
    print_run_summary(args, book_dir, output_dir, chapters)
    client = generation_client(args, api_key)
    if args.master:
        require_master_dependencies()
    output_dir.mkdir(parents=True, exist_ok=True)

    print()
    start = time.time()
    for index, (slug, md_path) in enumerate(chapters, 1):
        print(f"[{index}/{len(chapters)}] {slug}")
        if args.generate:
            generate_chapter(
                client, slug, md_path, output_dir, args.voice_id,
                args.model, EL_FORMAT, args.dry_run, args.force,
            )
        if args.master and not args.dry_run:
            master_chapter(slug, output_dir, args.book_title, args.force)

    print(f"\nDone in {time.time() - start:.1f}s")
    if not args.dry_run:
        print_outputs(output_dir)


if __name__ == '__main__':
    main()
