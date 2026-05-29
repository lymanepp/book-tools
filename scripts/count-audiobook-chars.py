#!/usr/bin/env python3
"""
count-chars.py
==============
Count post-stripped characters across one or more book directories.
This is the actual character count ElevenLabs will charge against —
markdown syntax, footnotes, URLs, and heading markers are all removed
before counting, matching exactly what the narration script sends to the API.

USAGE
-----
  # One book
  python count-chars.py book1/

  # Multiple books (all three at once)
  python count-chars.py book1/ book2/ book3/

  # Show per-chapter breakdown
  python count-chars.py book1/ --verbose
"""

import re
import sys
import argparse
from pathlib import Path

# ---------------------------------------------------------------------------
# Markdown stripping — must match build-audiobook-elevenlabs.py exactly
# ---------------------------------------------------------------------------

ROMAN = [
    "", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight",
    "Nine", "Ten", "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen",
    "Sixteen", "Seventeen", "Eighteen", "Nineteen", "Twenty",
    "Twenty-One", "Twenty-Two", "Twenty-Three", "Twenty-Four", "Twenty-Five",
    "Twenty-Six", "Twenty-Seven", "Twenty-Eight", "Twenty-Nine", "Thirty",
]


def chapter_number_to_words(n: int) -> str:
    if 1 <= n <= len(ROMAN) - 1:
        return ROMAN[n]
    return str(n)


def heading_to_spoken(line: str) -> str:
    m = re.match(r'^(#{1,6})\s+(.*)', line)
    if not m:
        return line.strip()
    text = m.group(2).strip()
    if len(m.group(1)) == 1:
        num_m = re.match(r'^(\d+)\.\s+(.*)', text)
        if num_m:
            num   = int(num_m.group(1))
            title = num_m.group(2).strip().replace('—', '. ')
            return f"Chapter {chapter_number_to_words(num)}. {title}."
        return f"{text.replace('—', '. ')}."
    text = text.replace('—', '. ')
    return text if text.endswith('.') else text + '.'


def strip_markdown(text: str) -> str:
    lines = text.splitlines()
    out   = []
    for line in lines:
        if re.match(r'^\[\^[^\]]+\]:', line):
            continue
        if re.match(r'^[-*_]{3,}\s*$', line):
            out.append('')
            continue
        if re.match(r'^#{1,6}\s', line):
            out.extend(['', heading_to_spoken(line), ''])
            continue
        line = re.sub(r'^>\s?',                    '',    line)
        line = re.sub(r'\[\^[^\]]+\]',             '',    line)
        line = re.sub(r'\[([^\]]+)\]\([^)]+\)',    r'\1', line)
        line = re.sub(r'https?://\S+',             '',    line)
        line = re.sub(r'\*\*([^*]+)\*\*',          r'\1', line)
        line = re.sub(r'\*([^*\s][^*]*[^*\s])\*', r'\1', line)
        line = re.sub(r'\*([^*\s])\*',             r'\1', line)
        line = line.replace('—', ', ')
        out.append(line)
    return re.sub(r'\n{3,}', '\n\n', '\n'.join(out)).strip()


# ---------------------------------------------------------------------------
# File discovery
# ---------------------------------------------------------------------------

EXCLUDE = {'front-matter-print', 'front-matter-submission', 'metadata-submission'}


def discover_chapters(book_dir: Path) -> list[tuple[str, Path]]:
    return [
        (f.stem, f) for f in sorted(book_dir.glob('*.md'))
        if not any(f.stem == ex or f.stem.startswith(ex) for ex in EXCLUDE)
    ]


# ---------------------------------------------------------------------------
# Pricing reference
# ---------------------------------------------------------------------------

PLANS = [
    ("Starter",  22_000,    22.00),
    ("Creator", 100_000,    59.00),   # ~$0.59/1k at 100k
    ("Pro",     500_000,    99.00),
    ("Scale",  2_000_000,  330.00),   # per elevenlabs.io/pricing
]

# Pay-as-you-go: eleven_v3 ~$0.24/1k chars
PAYG_RATE_PER_1K = 0.24


def plan_recommendation(total_chars: int) -> None:
    print("\nElevenLabs plan options:")
    print(f"  {'Plan':<10} {'Credits':>12}  {'$/mo':>7}  {'Covers?'}")
    print(f"  {'-'*10} {'-'*12}  {'-'*7}  {'-'*20}")
    for name, credits, price in PLANS:
        covers = "✓ yes" if credits >= total_chars else f"✗ short by {total_chars - credits:,}"
        print(f"  {name:<10} {credits:>12,}  ${price:>6.2f}  {covers}")

    payg = (total_chars / 1000) * PAYG_RATE_PER_1K
    print(f"\n  Pay-as-you-go (eleven_v3): ~${payg:.2f} total")

    # Find cheapest single-month plan that covers it
    fits = [(n, c, p) for n, c, p in PLANS if c >= total_chars]
    if fits:
        name, credits, price = fits[0]
        surplus = credits - total_chars
        print(f"\n  Cheapest single-month plan: {name} (${price:.2f}/mo, "
              f"{surplus:,} credits to spare)")
    else:
        # Needs multiple months of the largest plan or overage
        name, credits, price = PLANS[-1]
        months = -(-total_chars // credits)   # ceiling division
        print(f"\n  Requires {months} month(s) of {name} "
              f"(${price * months:.2f} total) or pay-as-you-go (${payg:.2f})")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def parse_args():
    p = argparse.ArgumentParser(
        description='Count post-stripped characters for ElevenLabs credit estimation',
    )
    p.add_argument('book_dirs', nargs='+', metavar='DIR',
                   help='One or more book directories containing chapter .md files')
    p.add_argument('--verbose', '-v', action='store_true',
                   help='Show per-chapter character counts')
    return p.parse_args()


def main():
    args = parse_args()
    grand_total_raw    = 0
    grand_total_stripped = 0

    for dir_arg in args.book_dirs:
        book_dir = Path(dir_arg)
        if not book_dir.exists():
            print(f"ERROR: directory not found: {book_dir}", file=sys.stderr)
            sys.exit(1)

        chapters = discover_chapters(book_dir)
        if not chapters:
            print(f"WARNING: no chapter .md files found in {book_dir}")
            continue

        book_raw      = 0
        book_stripped = 0

        print(f"\n{book_dir}/  ({len(chapters)} chapters)")
        if args.verbose:
            print(f"  {'Chapter':<50} {'Raw':>8}  {'Stripped':>10}  {'Saved':>6}")
            print(f"  {'-'*50} {'-'*8}  {'-'*10}  {'-'*6}")

        for slug, path in chapters:
            raw_text      = path.read_text(encoding='utf-8')
            stripped_text = strip_markdown(raw_text)
            raw_chars     = len(raw_text)
            stripped_chars = len(stripped_text)
            saved         = raw_chars - stripped_chars

            book_raw      += raw_chars
            book_stripped += stripped_chars

            if args.verbose:
                print(f"  {slug:<50} {raw_chars:>8,}  {stripped_chars:>10,}  "
                      f"{saved:>5,} ({100*saved//raw_chars}%)")

        reduction = 100 * (book_raw - book_stripped) // book_raw if book_raw else 0
        print(f"  Raw markdown chars    : {book_raw:>12,}")
        print(f"  Post-strip chars      : {book_stripped:>12,}  "
              f"({reduction}% reduction)")

        grand_total_raw      += book_raw
        grand_total_stripped += book_stripped

    if len(args.book_dirs) > 1:
        reduction = 100 * (grand_total_raw - grand_total_stripped) // grand_total_raw
        print(f"\n{'='*55}")
        print(f"  TOTAL raw markdown    : {grand_total_raw:>12,}")
        print(f"  TOTAL post-strip      : {grand_total_stripped:>12,}  "
              f"({reduction}% reduction)")

    plan_recommendation(grand_total_stripped)
    print()


if __name__ == '__main__':
    main()
