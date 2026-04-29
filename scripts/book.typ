// book.typ — What Scripture Says book template
// Target: 6×9 print PDF, Typst 0.14.x
// Contract: Pandoc/Lua emits semantic structure; this file owns layout.

#let _b-emph     = emph
#let _b-strong   = strong
#let _b-strike   = strike
#let _b-super    = super
#let _b-sub      = sub
#let _b-sc       = smallcaps
#let _b-link     = link
#let _b-image    = image
#let _b-raw      = raw
#let _b-line     = line
#let _b-lbreak   = linebreak

// Typography
#let _body-font     = "TeX Gyre Pagella"
#let _mono-font     = "TeX Gyre Cursor"
#let _body-size     = 11pt
#let _fn-size       = 9pt
#let _hdr-size      = 9pt
#let _ch-num-size   = 24pt
#let _ch-title-size = 18pt
#let _h2-size       = 13pt
#let _h3-size       = 11.5pt
#let _hyphenate     = false

// Page geometry
#let _page-width  = 6in
#let _page-height = 9in
#let _margin-top  = 0.70in
#let _margin-bot  = 0.82in
#let _margin-in   = 0.90in
#let _margin-out  = 0.625in

// Vertical rhythm and indents
#let _leading        = 6.3pt
#let _para-spacing   = 0pt
#let _indent         = 0.25in
#let _quote-indent   = 0.375in
#let _quote-before   = 4.5pt
#let _quote-after    = 4.5pt
#let _list-spacing   = 0.45em
#let _list-before    = 12pt
#let _list-after     = 12pt
#let _heading-keep   = 2.15em
#let _chapter-top-space    = 0.82in
#let _chapter-number-after = 0.32in
#let _chapter-title-after  = 0.16in

#let _book-title = "What Scripture Says, Volume 2"
#let _ch-title   = state("book-current-chapter-title", "")
#let _suppress   = state("book-suppress-running-head", true)
#let _chapter_open_page = state("book-current-chapter-opening-page", 0)
#let _noind      = state("book-next-paragraph-no-indent", false)

#let _body-par() = {
  set par(
    justify: true,
    leading: _leading,
    spacing: _para-spacing,
    first-line-indent: (amount: _indent, all: false),
  )
}

#let _noindent-par(justify: true) = {
  set par(
    justify: justify,
    leading: _leading,
    spacing: 0pt,
    first-line-indent: (amount: 0pt, all: true),
  )
}

#let _plain-par() = _noindent-par(justify: false)

#let _reset-book-text(size: _body-size) = {
  set text(font: _body-font, size: size, lang: "en", hyphenate: _hyphenate)
}

#let _book-text(body, size: _body-size, weight: "regular", style: "normal") = {
  text(font: _body-font, size: size, weight: weight, style: style, lang: "en", hyphenate: _hyphenate)[#body]
}

#let _mono-text(body, size: 9pt) = {
  text(font: _mono-font, size: size, lang: "en", hyphenate: false)[#body]
}

#let setup(doc, title: "") = {
  let _effective-title = if title != "" { title } else { _book-title }
  set document(title: _effective-title)

  set page(
    width: _page-width,
    height: _page-height,
    margin: (top: _margin-top, bottom: _margin-bot, inside: _margin-in, outside: _margin-out),
    header-ascent: 28%,
    // Gives chapter-opening footnotes and the centered footer page number
    // enough separation without changing the rest of the running-header logic.
    footer-descent: 38%,

    header: context {
      let pg = counter(page).at(here()).first()
      // _suppress is set to true before the pagebreak that opens each chapter,
      // so the opening page reliably sees it as true. It is cleared to false
      // after the chapter title content, so subsequent pages get their header.
      if _suppress.at(here()) { [] } else {
        set text(font: _body-font, size: _hdr-size)
        _plain-par()
        if calc.even(pg) {
          // Even (left-hand) pages: page number on the outside/left edge.
          grid(columns: (auto, 1fr), gutter: 0pt, str(pg), align(right)[#_effective-title])
        } else {
          // Odd (right-hand) pages: page number on the outside/right edge.
          grid(columns: (1fr, auto), gutter: 0pt, _ch-title.at(here()), align(right)[#str(pg)])
        }
      }
    },

    footer: context {
      // First page of each chapter: no running header, but do show the
      // page number centered in the footer. Non-opening pages keep their
      // page number in the outside edge of the running header.
      let pg = counter(page).at(here()).first()
      if pg == _chapter_open_page.at(here()) {
        set text(font: _body-font, size: _hdr-size)
        _plain-par()
        align(center)[#str(pg)]
      } else { [] }
    },
  )

  set page(numbering: "1")
  counter(page).update(1)

  _reset-book-text()
  _body-par()

  // Ordinary Markdown paragraphs are emitted by the Lua filter as book.para.
  // This avoids relying on Typst's global paragraph state to infer whether a
  // paragraph is the first paragraph after a heading.

  // Lists must inherit body typography and use normal book text, not a fallback font.
  // The item spacing is deliberately a little larger than Typst's compact default
  // so numbered and bulleted lists read with the same visual rhythm as body text.
  set list(indent: 0.28in, body-indent: 0.16in, spacing: _list-spacing)
  set enum(indent: 0.28in, body-indent: 0.16in, spacing: _list-spacing)
  show list: it => {
    v(_list-before, weak: true)
    block(width: 100%)[
      #_reset-book-text()
      #set par(
        justify: true,
        leading: _leading,
        spacing: 0pt,
        first-line-indent: (amount: 0pt, all: true),
        hanging-indent: 0pt,
      )
      #_book-text(it)
    ]
    v(_list-after, weak: true)
    _noind.update(true)
  }
  show enum: it => {
    v(_list-before, weak: true)
    block(width: 100%)[
      #_reset-book-text()
      #set par(
        justify: true,
        leading: _leading,
        spacing: 0pt,
        first-line-indent: (amount: 0pt, all: true),
        hanging-indent: 0pt,
      )
      #_book-text(it)
    ]
    v(_list-after, weak: true)
    _noind.update(true)
  }

  // Native Pandoc footnotes stay native. This styles only the footnote area.
  // No first-line, hanging, or footnote-entry indentation is applied inside notes.
  set footnote.entry(indent: 0pt, gap: 0.45em)
  set footnote(numbering: n => super(typographic: false, text(size: 8.5pt, str(n))))
  show footnote.entry: it => {
    set footnote(numbering: n => super(typographic: false, text(size: 8.5pt, str(n))))
    set text(font: _body-font, size: _fn-size, lang: "en", hyphenate: _hyphenate)
    set par(
      justify: true,
      leading: 5.0pt,
      spacing: 0pt,
      first-line-indent: (amount: 0pt, all: true),
      hanging-indent: 0pt,
    )
    _book-text(it, size: _fn-size)
  }

  // chapter() emits an invisible heading(outlined: true) so that outline()
  // can collect chapter titles and page numbers for the TOC. The show rule
  // suppresses all visual rendering of those headings.
  show heading: it => none

  doc
}

// ── Structural headings ──────────────────────────────────────────────────────
#let chapter(number: "", title: "", id: "") = {
  // Suppress the running header before the page break so the opening page
  // never inherits a stale "false" from the previous chapter's final page.
  _suppress.update(true)
  pagebreak(weak: true, to: "odd")
  // Record the physical opening page for footer logic.
  context { _chapter_open_page.update(counter(page).get().first()) }
  // Running heads use the chapter title only, not the printed chapter number.
  _ch-title.update(title)

  v(_chapter-top-space)
  if number != "" {
    {
      set text(font: _body-font, size: _ch-num-size, weight: "bold")
      _plain-par()
      align(center)[#number]
    }
    v(_chapter-number-after)
  }
  {
    set text(font: _body-font, size: _ch-title-size, weight: "bold")
    _plain-par()
    align(center)[#title]
  }
  // Emit an invisible level-1 heading so outline() can build the TOC.
  // numbering is set so outline.entry can render "N.   Title" format.
  // The show heading: none rule in setup() suppresses visual rendering.
  heading(level: 1, outlined: true, numbering: "1.")[#title]

  v(_chapter-title-after)
  // Clear suppression so the second page of each chapter gets its running head.
  _suppress.update(false)
  _noind.update(true)
}

#let front_chapter(title: "", id: "") = {
  _suppress.update(true)
  pagebreak(weak: true, to: "odd")
  context { _chapter_open_page.update(counter(page).get().first()) }
  _ch-title.update(title)
  v(_chapter-top-space)
  {
    set text(font: _body-font, size: _ch-title-size, weight: "bold")
    _plain-par()
    align(center)[#title]
  }
  heading(level: 1, outlined: true)[#title]
  v(_chapter-title-after)
  _suppress.update(false)
  _noind.update(true)
}

// ── Front matter (title page + copyright + TOC) ──────────────────────────────
// SUPERSEDED for print builds: pdf-typst.sh now #include's each book's
// front-matter-print.typ directly, which gives per-book control over layout,
// ISBNs, and page structure while keeping the auto-generated outline() TOC.
// This function is retained for standalone/submission builds that do not have
// a front-matter-print.typ, and as a fallback for new books.
#let front_matter(
  title: "",
  subtitle: "",
  author: "",
  copyright_year: "",
  hardcover_isbn: "",
  paperback_isbn: "",
) = {
  // ── Title page (recto) ──
  _suppress.update(true)
  context { _chapter_open_page.update(counter(page).get().first()) }
  v(1.8in)
  {
    set text(font: _body-font, size: _ch-title-size, weight: "bold")
    _plain-par()
    align(center)[#title]
  }
  if subtitle != "" {
    v(0.18in)
    set text(font: _body-font, size: _h2-size, weight: "regular", style: "italic")
    _plain-par()
    align(center)[#subtitle]
  }
  v(0.40in)
  {
    set text(font: _body-font, size: _body-size)
    _plain-par()
    align(center)[#author]
  }

  // ── Copyright page (verso) ──
  pagebreak(to: "even")
  _suppress.update(true)
  context { _chapter_open_page.update(counter(page).get().first()) }
  v(1fr)
  {
    set text(font: _body-font, size: _fn-size)
    set par(justify: false, leading: 5pt, spacing: 4pt,
            first-line-indent: (amount: 0pt, all: true))
    [*#title*]
    if subtitle != "" { linebreak(); _b-emph[#subtitle] }
    v(6pt)
    [© #copyright_year #author]
    v(2pt)
    [All rights reserved.]
    v(6pt)
    [No part of this publication may be reproduced, stored in a retrieval system, or transmitted in any form or by any means—electronic, mechanical, photocopying, recording, or otherwise—without the prior written permission of the author, except for brief quotations used in reviews or scholarly works.]
    v(6pt)
    [Scripture quotations are from the ESV® Bible (The Holy Bible, English Standard Version®), copyright © 2001 by Crossway, a publishing ministry of Good News Publishers. Used by permission. All rights reserved.]
    if hardcover_isbn != "" { v(6pt); [ISBN: #hardcover_isbn (hardcover)] }
    if paperback_isbn != "" { linebreak(); [ISBN: #paperback_isbn (paperback)] }
    v(4pt)
    [Printed in the United States of America.]
  }

  // ── Table of contents (recto) ──
  pagebreak(to: "odd")
  _suppress.update(true)
  context { _chapter_open_page.update(counter(page).get().first()) }
  v(0.60in)
  {
    set text(font: _body-font, size: _h2-size, weight: "bold")
    _plain-par()
    align(center)[Contents]
  }
  v(0.30in)
  {
    set text(font: _body-font, size: _body-size)
    set par(justify: false, leading: _leading, spacing: 4pt,
            first-line-indent: (amount: 0pt, all: true))
    outline(title: none, indent: 0pt, depth: 1)
  }

  // Body begins on next recto; _suppress cleared by the first chapter() call.
  pagebreak(to: "odd")
  _suppress.update(true)
}

#let _kept-heading(title, size: _body-size, italic: false, before: 12pt, after: 5pt) = {
  v(before, weak: true)
  block(breakable: false, sticky: true)[
    #set text(font: _body-font, size: size, weight: "bold", style: if italic { "italic" } else { "normal" })
    #set par(justify: false, first-line-indent: (amount: 0pt, all: true), spacing: 0pt)
    #title
    #v(after, weak: true)
  ]
  _noind.update(true)
}

#let section(title: "", id: "") = _kept-heading(title, size: _h2-size, italic: false, before: 18pt, after: 6pt)
#let subsection(title: "", id: "") = _kept-heading(title, size: _h3-size, italic: true, before: 13pt, after: 5pt)
#let heading(level: 4, title: "", id: "") = _kept-heading(title, size: _body-size, italic: false, before: 11pt, after: 4pt)

#let leadin(body) = {
  v(5pt, weak: true)
  block(breakable: false, sticky: true)[
    #_reset-book-text()
    #_noindent-par(justify: true)
    #_book-text(body)
    #v(3pt, weak: true)
  ]
  _noind.update(true)
}

#let runin(body, label: none) = {
  block[
    #_reset-book-text()
    #_noindent-par(justify: true)
    #_book-text([#strong[#label] #body])
  ]
}

// ── Block quote ──────────────────────────────────────────────────────────────
#let quote(body) = {
  v(_quote-before)
  block(width: 100%, inset: (left: _quote-indent, right: 0pt, top: 0pt, bottom: 0pt), breakable: true)[
    #set text(font: _body-font, size: _body-size, style: "normal", lang: "en", hyphenate: _hyphenate)
    #set par(
      justify: false,
      leading: _leading,
      spacing: 0pt,
      first-line-indent: (amount: 0pt, all: true),
      hanging-indent: 0pt,
    )
    #_book-text(body)
  ]
  v(_quote-after)
}
#let scripture_quote = quote

// ── Horizontal rule ──────────────────────────────────────────────────────────
#let hr(body: none) = {
  v(12pt, weak: true)
  _b-line(length: 100%, stroke: 0.4pt)
  v(12pt, weak: true)
  _noind.update(true)
}

// ── Line blocks ──────────────────────────────────────────────────────────────
#let lineblock(body) = {
  v(5pt, weak: true)
  block[
    #_reset-book-text()
    #set par(first-line-indent: (amount: 0pt, all: true), spacing: 0pt)
    #_book-text(body)
  ]
  v(5pt, weak: true)
  _noind.update(true)
}
#let line(body) = { body; _b-lbreak() }

// ── Code blocks ──────────────────────────────────────────────────────────────
#let codeblock(body, language: "") = {
  v(6pt, weak: true)
  block(fill: luma(245), inset: 8pt, radius: 3pt, width: 100%)[
    #set text(font: _mono-font, size: 9pt)
    #set par(first-line-indent: (amount: 0pt, all: true), justify: false, spacing: 0pt)
    #_mono-text(if language != "" { _b-raw(body, lang: language) } else { _b-raw(body) })
  ]
  v(6pt, weak: true)
  _noind.update(true)
}

// ── Tables ───────────────────────────────────────────────────────────────────
#let table_block(body) = {
  v(8pt, weak: true)
  // Keep each table as a single unit so rows do not split across pages.
  // If there is not enough space remaining, Typst moves the whole table.
  block(width: 100%, breakable: false)[
    #_reset-book-text(size: 9.6pt)
    #set par(justify: false, leading: 2.4pt, spacing: 0pt, first-line-indent: (amount: 0pt, all: true))
    // Keep the table in an unbreakable container. The outer block controls
    // vertical layout; the inner box prevents the table itself from splitting.
    #box(width: 100%)[#_book-text(body, size: 9.6pt)]
  ]
  v(8pt, weak: true)
  _noind.update(true)
}

#let table_cell(body, head: false) = {
  if head {
    table.cell(fill: luma(92%), inset: (x: 5.5pt, y: 4pt), align: left + horizon)[
      #set text(font: _body-font, size: 9.6pt, weight: "bold", lang: "en", hyphenate: _hyphenate)
      #set par(justify: false, leading: 2.2pt, spacing: 0pt, first-line-indent: (amount: 0pt, all: true))
      #_book-text(body, size: 9.6pt, weight: "bold")
    ]
  } else {
    table.cell(inset: (x: 5.5pt, y: 4pt), align: left + horizon)[
      #set text(font: _body-font, size: 9.6pt, lang: "en", hyphenate: _hyphenate)
      #set par(justify: false, leading: 2.2pt, spacing: 0pt, first-line-indent: (amount: 0pt, all: true))
      #_book-text(body, size: 9.6pt)
    ]
  }
}

// ── Figure / Div ─────────────────────────────────────────────────────────────
#let figure(body) = { v(8pt, weak: true); align(center)[#_book-text(body)]; v(8pt, weak: true); _noind.update(true) }
#let div(body, classes: "") = body

// ── Explicit paragraph wrapper ──────────────────────────────────────────────
#let para(body, kind: "normal") = {
  block(width: 100%)[
    #_reset-book-text()
    #set par(
      justify: true,
      leading: _leading,
      spacing: 0pt,
      first-line-indent: (amount: 0pt, all: true),
      hanging-indent: 0pt,
    )
    #if kind == "normal" { h(_indent) }
    #_book-text(body)
  ]
}

// ── Compatibility wrappers retained for older generated .typ files ──────────
#let p(body, kind: "normal") = para(body, kind: kind)
#let bullets(body) = { v(5pt, weak: true); body; v(5pt, weak: true); _noind.update(true) }
#let ordered(body) = { v(5pt, weak: true); body; v(5pt, weak: true); _noind.update(true) }
#let item(body) = body
#let deflist(body) = body
#let defterm(body) = { strong(body) }
#let defitem(body) = { pad(left: _indent)[#_book-text(body)] }
#let thead(body) = body
#let tbody(body) = body
#let row(body) = body
#let cell(body) = body

// ── Inline wrappers ──────────────────────────────────────────────────────────
#let emph(body)      = _b-emph[#body]
#let strong(body)    = _b-strong[#body]
#let strike(body)    = _b-strike[#body]
#let sup(body)       = _b-super[#body]
#let sub(body)       = _b-sub[#body]
#let smallcaps(body) = _b-sc[#body]
#let quoted(body, kind: "double") = {
  if kind == "single" { ['#body'] } else { ["#body"] }
}
#let code(body) = {
  _mono-text(_b-raw(body), size: 0.9em)
}
#let link(body, url: "") = _b-link(url)[#body]
#let image(src: "", alt: "") = _b-image(src, alt: alt)
#let linebreak() = _b-lbreak()
