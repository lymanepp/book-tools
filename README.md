# Unified Book Build Ecosystem

## How to share the scripts without keeping two copies

The scripts directory is the single source of truth. The question is how
it reaches both book repos without copying it. There are three options.
The recommendation is at the top.

---

### Option 1 — Git submodule (recommended)

Create a third repository: `book-tools`. It contains only the `scripts/`
directory and `.devcontainer/`. Both book repos (`what-scripture-says` and
the counseling repo) add it as a submodule pinned to a specific commit.

**Repo layout:**

```
book-tools/                 ← shared repo (this directory)
  scripts/
    build-template.py
    postprocess-pandoc.py
    docx.sh
    mdformat.lua
    md2ssml.lua
    epub.sh
    docx2pdf.py
    docx2pdf.sh
    download
    Makefile.book
  .devcontainer/
    devcontainer.json
    post-create

what-scripture-says/        ← your existing repo
  scripts/                  ← submodule pointing to book-tools/scripts/
  book1/
    book.env
    front-matter-print.md
    front-matter-submission.md
    metadata-print.yaml
    metadata-submission.yaml
    header.tex
    Makefile                ← copy of Makefile.book (or symlink)
    00-introduction.md
    01-*.md ...
  book2/
    (same layout as book1)
  .devcontainer/ → submodule or copy of book-tools/.devcontainer/
  .github/workflows/build-books.yml

counseling-book/            ← your wife's existing repo
  scripts/                  ← same submodule, same commit
  counseling/
    book.env
    front-matter-print.md
    front-matter-submission.md
    metadata-print.yaml
    metadata-submission.yaml
    header.tex              ← if PDF output is needed; omit otherwise
    Makefile                ← copy of Makefile.book
    ch00-10-preface.md      ← rename to 00-preface.md (see Markdown changes)
    ch01-*.md ...           ← rename to 01-*.md etc.
  .devcontainer/ → submodule or copy
  .github/workflows/build-books.yml
```

**Setup (one time per consuming repo):**

```bash
# Inside what-scripture-says or counseling-book:
git submodule add https://github.com/you/book-tools scripts
git submodule update --init --recursive
```

**Updating the scripts:**

```bash
# Inside book-tools:
git commit -am "fix: table width clamping for 4-col tables"
git push

# Inside each consuming repo — update the pinned commit:
cd scripts && git pull origin main && cd ..
git add scripts
git commit -m "chore: update book-tools submodule"
git push
```

**Why submodule instead of subtree:**
Subtree embeds the scripts history into the consuming repo, making it
impossible to pull changes selectively. Submodule keeps them separate
and pinned — a script change does not silently affect a book build until
you explicitly update the pin.

**CI:**
The workflow file included in this directory uses `submodules: true` on
the checkout step. That is the only CI change required.

**VS Code devcontainer:**
Both repos' `.devcontainer/` directories can themselves be submodules of
`book-tools/.devcontainer/`, or simply copied once and kept in sync
manually (the devcontainer changes rarely).

---

### Option 2 — Monorepo

Combine everything into one repository:

```
epp-books/
  scripts/          ← one copy, shared by all books
  .devcontainer/
  .github/workflows/build-books.yml
  book1/
  book2/
  counseling/
```

**Advantages:** Dead simple. One `git clone`, one CI job, no submodule
mechanics, no pinning.

**Disadvantages:** Your wife's counseling book is in your repo (or vice
versa). Commit history is interleaved. Access control is all-or-nothing.
If either of you ever publishes to a platform that expects a clean repo
per book, you're restructuring later.

Use this if access and history separation are not concerns and you want
the simplest possible setup.

---

### Option 3 — Package install (overkill for now)

Publish `book-tools/scripts/` as a Python package to PyPI or a private
index. Each repo installs it via `pip install book-tools==x.y.z`. This
is the correct answer for a team of ten. For two authors it is not worth
the overhead.

---

## What is in scripts/

| File | Purpose |
|---|---|
| `build-template.py` | Builds `reference-template.docx` from pandoc's default seed. Run automatically by `docx.sh` before every print build. |
| `postprocess-pandoc.py` | Injects running headers/footers, wires sections, splits chapter headings, fixes blockquote styles, processes copyright page, normalises fonts, lays out all tables. |
| `docx.sh` | Main build driver. Sources `book.env`, renders front matter, calls pandoc, calls postprocessor. Accepts `print` (default) or `submission`. |
| `mdformat.lua` | Pandoc Lua filter. Maps `\newpage` → odd-page section break (DOCX) / `\newpage` (LaTeX) / CSS page break (EPUB/HTML). Maps `\toc` → native Word TOC field. |
| `md2ssml.lua` | Pandoc Lua filter for SSML (audiobook/TTS) output. |
| `epub.sh` | Builds a full-book EPUB from submission front matter. Strips LaTeX commands and footnotes for TTS compatibility. |
| `docx2pdf.py` | Windows-only: converts DOCX to PDF via Word COM automation. |
| `docx2pdf.sh` | Wrapper for `docx2pdf.py` using the `py` launcher. |
| `download` | Downloads the latest CI artifact and converts to PDF. |
| `Makefile.book` | Per-book Makefile for PDF/EPUB/SSML targets. Copy to each book directory as `Makefile`. |

---

## Required per-book files (not in scripts/)

Each book directory must contain:

```
book.env                    ← identity and ISBNs
front-matter-print.md       ← title page, copyright, \toc marker
front-matter-submission.md  ← minimal front matter for submission
metadata-print.yaml         ← pandoc metadata for print build
metadata-submission.yaml    ← pandoc metadata for submission build
header.tex                  ← LaTeX header (ragged right, microtype, em-dash)
Makefile                    ← copy of scripts/Makefile.book
NN-chapter-name.md          ← chapter files (must match [0-9][0-9]-*.md)
```

---

## Markdown changes required when adopting the unified ecosystem

### Counseling book chapters

**1. Rename chapter files.**
The `docx.sh` glob is `[0-9][0-9]-*.md`. Counseling files use
`chNN-NN-title.md`. Rename to `NN-title.md`:

```
ch00-10-preface.md       → 00-preface.md
ch01-governing-framework.md → 01-governing-framework.md
```

**2. Replace implicit H2 page breaks with explicit `\newpage` or `\pagebreak`.**
The counseling book's old `content-layout.lua` injected a page break
before every H2 automatically. The unified `mdformat.lua` does not —
breaks are explicit. For a chapter that starts on an odd page (which
all chapters should), prefix the H1 with `\newpage`. For a section
heading within a chapter that should start on a new page (not
odd-page), use `\pagebreak`:

```markdown
\newpage

# Chapter 1: The Governing Framework

...body...

\pagebreak

## The Three-Domain Model
```

If a section heading should not force a page break (most of them
should not), add no marker — the H2 spacing handles visual separation.

**3. Scripture quotations — use fenced div for `Scripture Quote` style.**
Pandoc maps bare `>` blockquotes to the `Block Text` style in DOCX. `Block
Text` is styled with a shaded background and left accent border — appropriate
for general prose citations. Scripture quotations should use the fenced div
form to get the distinct `Scripture Quote` style:

```markdown
::: {custom-style="Scripture Quote"}
> For God so loved the world… (John 3:16)
:::
```

Leave bare `>` for non-scripture quotations. This is a per-instance change.

**4. Add `book.env`.**
Create `counseling/book.env`:

```bash
BOOK_TITLE='Counseling Toward Wholeness'
BOOK_SUBTITLE='A Practitioner'\''s Theological Framework'
BOOK_OUTPUT_BASENAME='counseling-toward-wholeness'
```

### Scripture book chapters

No changes required. The Scripture books already use explicit `\newpage`
markers (which produce odd-page section breaks, as before) and the correct
`NN-*.md` filename convention. The `\pagebreak` command is now also
available for intra-chapter plain page breaks if ever needed.

Bare `>` blockquotes in Scripture chapters land in `Block Text` (shaded,
left border, italic). If you want them in `Scripture Quote` style instead,
wrap with the fenced div. If the current rendering is acceptable, no change.
