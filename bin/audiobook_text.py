"""Shared Markdown-to-speech preparation for audiobook tools."""

from __future__ import annotations

import re
from pathlib import Path

_NUMBER_WORDS = [
    "", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight",
    "Nine", "Ten", "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen",
    "Sixteen", "Seventeen", "Eighteen", "Nineteen", "Twenty",
    "Twenty-One", "Twenty-Two", "Twenty-Three", "Twenty-Four", "Twenty-Five",
    "Twenty-Six", "Twenty-Seven", "Twenty-Eight", "Twenty-Nine", "Thirty",
]

_EXCLUDED_STEMS = {
    "front-matter-print",
    "front-matter-submission",
    "metadata-submission",
}


def chapter_number_to_words(number: int) -> str:
    return _NUMBER_WORDS[number] if 1 <= number < len(_NUMBER_WORDS) else str(number)


def heading_to_spoken(line: str) -> str:
    match = re.match(r"^(#{1,6})\s+(.*)", line)
    if not match:
        return line.strip()

    text = match.group(2).strip()
    if len(match.group(1)) == 1:
        numbered = re.match(r"^(\d+)\.\s+(.*)", text)
        if numbered:
            number = chapter_number_to_words(int(numbered.group(1)))
            title = numbered.group(2).strip().replace("—", ". ")
            return f"Chapter {number}. {title}."
        return f"{text.replace('—', '. ')}."

    text = text.replace("—", ". ")
    return text if text.endswith(".") else f"{text}."


def strip_markdown(text: str) -> str:
    """Convert manuscript Markdown to the prose sent to the TTS service."""
    output: list[str] = []
    for line in text.splitlines():
        if re.match(r"^:::\s*(?:\{[^}]*\}|[A-Za-z0-9_-]+)?\s*$", line):
            continue
        if re.match(r"^\[\^[^\]]+\]:", line):
            continue
        if re.match(r"^[-*_]{3,}\s*$", line):
            output.append("")
            continue
        if re.match(r"^#{1,6}\s", line):
            output.extend(("", heading_to_spoken(line), ""))
            continue

        line = re.sub(r"<!--\s*pdf-?br\s*-->", "", line)
        line = re.sub(r"^>\s?", "", line)
        line = re.sub(r"\[\^[^\]]+\]", "", line)
        line = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", line)
        line = re.sub(r"https?://\S+", "", line)
        line = re.sub(r"\*\*([^*]+)\*\*", r"\1", line)
        line = re.sub(r"\*([^*\s][^*]*[^*\s])\*", r"\1", line)
        line = re.sub(r"\*([^*\s])\*", r"\1", line)
        line = re.sub(r"^—\s*", "", line).replace("—", ", ")
        output.append(line)

    return re.sub(r"\n{3,}", "\n\n", "\n".join(output)).strip()


def discover_chapters(book_dir: Path) -> list[tuple[str, Path]]:
    return [
        (path.stem, path)
        for path in sorted(book_dir.glob("*.md"))
        if not any(path.stem == stem or path.stem.startswith(stem) for stem in _EXCLUDED_STEMS)
    ]
