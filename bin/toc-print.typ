// toc-print.typ — Table of Contents page (p5, recto) + blank verso (p6)
// #include'd by pdf-typst.sh after front-matter-print.typ.
// Must be in the same compilation unit as the chapter body so outline() works.
#import "book.typ" as book

// ── Page 5: Table of Contents (recto) ────────────────────────────────────────
#pagebreak(to: "odd")
#book._suppress.update(true)
#book._chapter_open_page.update(0)

#v(39.4pt)
#{
  set text(font: book._body-font, size: 16pt, weight: "bold")
  set par(justify: false, leading: book._leading, spacing: 0pt,
          first-line-indent: (amount: 0pt, all: true))
  align(center)[Table of Contents]
}
#v(28.3pt)
#{
  set text(font: book._body-font, size: book._body-size)
  set par(justify: false, leading: 8.9pt, spacing: 0pt,
          first-line-indent: (amount: 0pt, all: true))
  show outline.entry: it => {
    let eloc = it.element.location()
    let pg = counter(page).at(eloc).first()
    let pg-fmt = numbering(eloc.page-numbering(), pg)
    let entry = if it.element.numbering != none {
      let n = numbering(it.element.numbering, ..counter(heading).at(eloc))
      [#n#h(0.5em)#it.element.body]
    } else {
      it.element.body
    }
    // Level-2 outline entries are reserved by book-tools for major Part
    // dividers. Ordinary Markdown H2/H3 headings are rendered semantically
    // by book.section/subsection and therefore never enter the native outline.
    let styled-entry = if it.element.level == 2 { strong(entry) } else { entry }
    block(above: 0pt, below: 0pt,
      grid(columns: (1fr, auto), gutter: 0pt,
        [#styled-entry #box(width: 1fr, repeat[.])], [#h(4pt)#pg-fmt],
      )
    )
    v(8.9pt)
  }
  outline(title: none, indent: 0pt, depth: 2)
}

// Body begins on the next recto. A single parity-aware break works whether
// the TOC occupies one page or several; do not manufacture a fixed blank
// verso first, because a two-page TOC would then create two blank pages.
#pagebreak(to: "odd")
#book._suppress.update(true)
#book._chapter_open_page.update(0)
#counter(page).update(1)
