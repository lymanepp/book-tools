#!/usr/bin/env python3
"""Generate and validate reproducible publication metadata for one book target."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

SEMVER_RE = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
TAG_RE = re.compile(r"^(?P<slug>[a-z0-9][a-z0-9-]*)-v(?P<version>\d+\.\d+\.\d+)$")


def run_git(root: Path, *args: str, check: bool = True) -> str:
    p = subprocess.run(["git", *args], cwd=root, text=True, capture_output=True)
    if check and p.returncode:
        raise SystemExit((p.stderr or p.stdout).strip() or f"git {' '.join(args)} failed")
    return p.stdout.strip()


def load_env(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        if s.startswith("export "):
            s = s[7:].lstrip()
        if "=" not in s:
            continue
        key, raw = (part.strip() for part in s.split("=", 1))
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
            raise SystemExit(f"Invalid key in {path}:{n}: {key}")
        try:
            parts = shlex.split(raw, comments=False, posix=True)
        except ValueError as exc:
            raise SystemExit(f"Could not parse {path}:{n}: {exc}") from exc
        out[key] = parts[0] if parts else ""
    return out


def typst_string(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def iso_from_epoch(epoch: int) -> str:
    return dt.datetime.fromtimestamp(epoch, dt.timezone.utc).date().isoformat()


def human_date(value: str) -> str:
    parsed = dt.date.fromisoformat(value)
    return f"{parsed.strftime('%B')} {parsed.day}, {parsed.year}"


def git_state(root: Path) -> dict[str, object]:
    sha = run_git(root, "rev-parse", "HEAD")
    short = run_git(root, "rev-parse", "--short=12", "HEAD")
    epoch = int(run_git(root, "show", "-s", "--format=%ct", "HEAD"))
    dirty = bool(run_git(root, "status", "--porcelain", "--untracked-files=normal"))
    tools_sha = ""
    tools = root / "tools"
    if tools.exists():
        tools_sha = run_git(tools, "rev-parse", "HEAD", check=False)
    return {"commit": sha, "shortCommit": short, "commitEpoch": epoch, "dirty": dirty, "toolsCommit": tools_sha}


def exact_tags(root: Path) -> list[str]:
    value = run_git(root, "tag", "--points-at", "HEAD", check=False)
    return sorted(t for t in value.splitlines() if t)


def resolve_context(root: Path, target: Path, cfg: dict[str, str], requested_tag: str | None,
                    requested_date: str | None, release: bool, require_clean: bool) -> dict[str, object]:
    for key in ("BOOK_TITLE", "BOOK_OUTPUT_BASENAME"):
        if not cfg.get(key):
            raise SystemExit(f"{target / 'book.env'} must define {key}")
    cfg = dict(cfg)
    cfg.setdefault("BOOK_PUBLICATION_CODE", re.sub(r"[^A-Za-z0-9]+", "-", cfg["BOOK_OUTPUT_BASENAME"]).strip("-").upper())
    cfg.setdefault("BOOK_RELEASE_SLUG", target.name)
    cfg.setdefault("BOOK_EDITION_LABEL", "First edition")

    state = git_state(root)
    tag = requested_tag or os.environ.get("BOOK_RELEASE_TAG", "")
    if not tag and release:
        matches = [t for t in exact_tags(root) if t.startswith(cfg["BOOK_RELEASE_SLUG"] + "-v")]
        if len(matches) != 1:
            raise SystemExit(f"Release build requires exactly one {cfg['BOOK_RELEASE_SLUG']}-vX.Y.Z tag at HEAD; found {matches}")
        tag = matches[0]

    version = ""
    kind = "draft"
    if tag:
        m = TAG_RE.fullmatch(tag)
        if not m:
            raise SystemExit(f"Invalid release tag {tag!r}; expected <slug>-vMAJOR.MINOR.PATCH")
        if m.group("slug") != cfg["BOOK_RELEASE_SLUG"]:
            raise SystemExit(f"Tag {tag!r} does not belong to target slug {cfg['BOOK_RELEASE_SLUG']!r}")
        version = m.group("version")
        if not SEMVER_RE.fullmatch(version):
            raise SystemExit(f"Invalid version in tag: {tag}")
        kind = "release"
        if tag not in exact_tags(root):
            raise SystemExit(f"Release tag {tag!r} does not point at HEAD")

    if release and kind != "release":
        raise SystemExit("--release requires a valid release tag")
    if (release or require_clean) and state["dirty"]:
        raise SystemExit("Release build requires a clean main repository and submodule state")

    if kind == "release":
        release_date = requested_date or os.environ.get("BOOK_RELEASE_DATE") or iso_from_epoch(int(state["commitEpoch"]))
        dt.date.fromisoformat(release_date)
        publication_id = f"{cfg['BOOK_PUBLICATION_CODE']}-{version}"
        display_revision = version
    else:
        release_date = requested_date or iso_from_epoch(int(state["commitEpoch"]))
        dirty_suffix = ".dirty" if state["dirty"] else ""
        publication_id = f"{cfg['BOOK_PUBLICATION_CODE']}-dev.{state['shortCommit']}{dirty_suffix}"
        display_revision = f"draft {state['shortCommit']}{dirty_suffix}"

    return {
        "schemaVersion": 1,
        "publication": {
            "code": cfg["BOOK_PUBLICATION_CODE"],
            "slug": cfg["BOOK_RELEASE_SLUG"],
            "title": cfg["BOOK_TITLE"],
            "subtitle": cfg.get("BOOK_SUBTITLE", ""),
            "editionLabel": cfg["BOOK_EDITION_LABEL"],
            "revision": version or display_revision,
            "publicationId": publication_id,
            "releaseDate": release_date,
            "releaseDateDisplay": human_date(release_date),
            "kind": kind,
            "tag": tag,
            "outputBasename": cfg["BOOK_OUTPUT_BASENAME"],
        },
        "source": {
            "repository": os.environ.get("GITHUB_REPOSITORY", ""),
            **state,
        },
        "build": {
            "sourceDateEpoch": int(state["commitEpoch"]),
            "generatedAt": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
            "githubRunId": os.environ.get("GITHUB_RUN_ID", ""),
            "githubRunAttempt": os.environ.get("GITHUB_RUN_ATTEMPT", ""),
        },
        "artifacts": [],
    }


def write_typst(path: Path, ctx: dict[str, object]) -> None:
    p = ctx["publication"]
    s = ctx["source"]
    lines = [
        "// Generated by tools/bin/publication.py. Do not edit.",
        "#let publication = (",
        f"  kind: {typst_string(str(p['kind']))},",
        f"  edition: {typst_string(str(p['editionLabel']))},",
        f"  revision: {typst_string(str(p['revision']))},",
        f"  date: {typst_string(str(p['releaseDateDisplay']))},",
        f"  iso_date: {typst_string(str(p['releaseDate']))},",
        f"  id: {typst_string(str(p['publicationId']))},",
        f"  tag: {typst_string(str(p['tag']))},",
        f"  git_sha: {typst_string(str(s['commit']))},",
        f"  git_short_sha: {typst_string(str(s['shortCommit']))},",
        f"  tools_sha: {typst_string(str(s['toolsCommit']))},",
        f"  dirty: {'true' if s['dirty'] else 'false'},",
        ")",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def artifact_paths(root: Path, cfg: dict[str, str]) -> list[Path]:
    base = cfg["BOOK_OUTPUT_BASENAME"]
    return sorted(p for p in (root / "dist").glob(f"{base}*") if p.is_file() and p.name not in {f"{base}-publication-manifest.json", f"{base}-SHA256SUMS"})


def finalize(root: Path, target: Path, cfg: dict[str, str], context_path: Path) -> tuple[Path, Path]:
    ctx = json.loads(context_path.read_text(encoding="utf-8"))
    artifacts = artifact_paths(root, cfg)
    if not artifacts:
        raise SystemExit("No publication artifacts found to finalize")
    ctx["artifacts"] = [{"file": p.name, "bytes": p.stat().st_size, "sha256": sha256(p)} for p in artifacts]
    manifest = root / "dist" / f"{cfg['BOOK_OUTPUT_BASENAME']}-publication-manifest.json"
    sums = root / "dist" / f"{cfg['BOOK_OUTPUT_BASENAME']}-SHA256SUMS"
    manifest.write_text(json.dumps(ctx, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    sum_lines = [f"{a['sha256']}  {a['file']}" for a in ctx["artifacts"]]
    sum_lines.append(f"{sha256(manifest)}  {manifest.name}")
    sums.write_text("\n".join(sum_lines) + "\n", encoding="utf-8")
    return manifest, sums


def verify_pdf(root: Path, cfg: dict[str, str], context_path: Path) -> None:
    ctx = json.loads(context_path.read_text(encoding="utf-8"))
    pdf = root / "dist" / f"{cfg['BOOK_OUTPUT_BASENAME']}-print.pdf"
    if not pdf.is_file():
        raise SystemExit(f"Missing interior PDF: {pdf}")
    p = subprocess.run(["pdftotext", str(pdf), "-"], text=True, capture_output=True)
    if p.returncode:
        raise SystemExit(p.stderr.strip() or "pdftotext failed")
    text = p.stdout
    expected = [ctx["publication"]["editionLabel"], ctx["publication"]["revision"], ctx["publication"]["publicationId"]]
    missing = [item for item in expected if item and item not in text]
    if ctx["publication"]["kind"] == "release" and "DRAFT" in text:
        missing.append("absence of DRAFT marker")
    if missing:
        raise SystemExit("PDF publication metadata verification failed: " + ", ".join(missing))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["prepare", "finalize", "verify"])
    parser.add_argument("target")
    parser.add_argument("--tag")
    parser.add_argument("--date")
    parser.add_argument("--release", action="store_true")
    parser.add_argument("--require-clean", action="store_true")
    args = parser.parse_args()

    root = Path(run_git(Path.cwd(), "rev-parse", "--show-toplevel")).resolve()
    target = (root / args.target).resolve()
    cfg = load_env(target / "book.env")
    build_dir = root / "build" / args.target
    build_dir.mkdir(parents=True, exist_ok=True)
    context_path = build_dir / "publication-context.json"

    if args.command == "prepare":
        ctx = resolve_context(root, target, cfg, args.tag, args.date, args.release, args.require_clean)
        context_path.write_text(json.dumps(ctx, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        write_typst(build_dir / "publication-info.typ", ctx)
        print(json.dumps(ctx["publication"], indent=2))
    elif args.command == "finalize":
        manifest, sums = finalize(root, target, cfg, context_path)
        print(manifest)
        print(sums)
    else:
        verify_pdf(root, cfg, context_path)
        print("Publication metadata verified in PDF")


if __name__ == "__main__":
    main()
