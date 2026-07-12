"""Small shared helpers for the book build scripts."""
from __future__ import annotations

import re
import shlex
import subprocess
from pathlib import Path

_ENV_KEY = re.compile(r"[A-Za-z_][A-Za-z0-9_]*$")


def repo_root(start: Path | None = None) -> Path:
    """Return the enclosing Git worktree, falling back to the tools parent."""
    cwd = (start or Path.cwd()).resolve()
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=cwd,
            capture_output=True,
            text=True,
            check=True,
        )
        return Path(result.stdout.strip()).resolve()
    except (FileNotFoundError, subprocess.CalledProcessError):
        return Path(__file__).resolve().parents[2]


def load_env(path: Path) -> dict[str, str]:
    """Parse the simple shell-style KEY=value files used by the build."""
    values: dict[str, str] = {}
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        if "=" not in line:
            continue
        key, raw = (part.strip() for part in line.split("=", 1))
        if not _ENV_KEY.fullmatch(key):
            raise SystemExit(f"ERROR: Invalid env key in {path}:{lineno}: {key}")
        try:
            parts = shlex.split(raw, comments=False, posix=True)
        except ValueError as exc:
            raise SystemExit(f"ERROR: Could not parse {path}:{lineno}: {exc}") from exc
        values[key] = parts[0] if parts else ""
    return values


def resolve_under(root: Path, value: str | Path) -> Path:
    path = Path(value).expanduser()
    return (path if path.is_absolute() else root / path).resolve()
