#!/usr/bin/env python3
"""
build-template.py — Build the shared pandoc reference-template.docx.

Merges the best of both ecosystems:
  - Scripture book:   style_by_id() correctness fix, configure_document(),
                      configure_normal(), configure_header_footer_styles(),
                      configure_header_footer_parts(), configure_headings(),
                      configure_paragraph_styles(), configure_character_styles(),
                      pandoc default.docx as the seed document.
  - Counseling book:  configure_quotes() (Block Quote + Scripture Quote),
                      configure_lists(), configure_table_paragraph_styles(),
                      set_style_shading(), set_style_border(), set_run_font().

Usage:
    python3 build-template.py [output-path]
    Default output: reference-template.docx (in cwd)
"""

from __future__ import annotations

import io
import subprocess
from pathlib import Path

from docx import Document
from docx.enum.section import WD_SECTION_START
from docx.enum.style import WD_STYLE_TYPE
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor
from docx.styles.style import StyleFactory

# ---------------------------------------------------------------------------
# Palette
# ---------------------------------------------------------------------------

PALATINO   = "Palatino Linotype"

# Grayscale palette used throughout — KDP-safe, print-friendly.
_BLACK     = RGBColor(0, 0, 0)
_DARK      = RGBColor(34, 34, 34)
_MUTED     = RGBColor(88, 96, 105)
_WHITE     = RGBColor(255, 255, 255)

QUOTE_FILL  = "F3F3F3"   # light grey background on block quotes
QUOTE_RULE  = "B8B8B8"   # left-border accent on block quotes


# ---------------------------------------------------------------------------
# Style lookup — bypasses python-docx BabelFish name translation
# ---------------------------------------------------------------------------

def style_by_id(doc: Document, style_id: str):
    """Look up a style by XML styleId.

    python-docx lowercases style names on lookup, which breaks 'Heading1',
    'BodyText', etc. against pandoc's reference.docx.  We go through the
    element tree directly and fall back to lowercase as a secondary check
    (add_style() lowercases its output).
    """
    el = doc.styles._element.get_by_id(style_id)
    if el is None:
        el = doc.styles._element.get_by_id(style_id.lower())
    if el is None:
        raise KeyError(f"No style with styleId {style_id!r}")
    return StyleFactory(el)


def ensure_style(doc: Document, name: str, style_type: WD_STYLE_TYPE,
                 base_id: str | None = None):
    """Get or create a style by styleId (name with spaces removed).

    Always uses styleId lookup to avoid BabelFish translation issues.
    Clears all inherited formatting so the style starts from a clean slate.
    """
    style_id = name.replace(" ", "")
    el = doc.styles._element.get_by_id(style_id)
    if el is not None:
        style = StyleFactory(el)
    else:
        style = doc.styles.add_style(name, style_type)
    clear_style_formatting(style)
    if base_id is not None:
        style.base_style = style_by_id(doc, base_id)
    return style


# ---------------------------------------------------------------------------
# XML helpers
# ---------------------------------------------------------------------------

def get_or_add_child(parent, tag: str):
    child = parent.find(qn(tag))
    if child is None:
        child = OxmlElement(tag)
        parent.append(child)
    return child


def remove_child(parent, tag: str) -> None:
    child = parent.find(qn(tag))
    if child is not None:
        parent.remove(child)


def clear_style_formatting(style) -> None:
    """Strip all formatting XML from a style element so it starts fresh."""
    style_el = style.element
    for tag in (
        "w:pPr", "w:rPr", "w:basedOn", "w:next", "w:link",
        "w:uiPriority", "w:qFormat", "w:semiHidden", "w:unhideWhenUsed",
        "w:hidden", "w:autoRedefine", "w:rsid", "w:aliases",
    ):
        remove_child(style_el, tag)


def set_style_ui(style, *, hidden: bool | None = None,
                 quick: bool | None = None, priority: int | None = None) -> None:
    style.hidden = hidden
    style.quick_style = quick
    style.priority = priority


def set_next(doc: Document, style, next_style_id: str) -> None:
    style.next_paragraph_style = style_by_id(doc, next_style_id)


def set_outline_level(style, level: int | None) -> None:
    pPr = get_or_add_child(style.element, "w:pPr")
    remove_child(pPr, "w:outlineLvl")
    if level is not None:
        outline = OxmlElement("w:outlineLvl")
        outline.set(qn("w:val"), str(level))
        pPr.append(outline)


def set_font(style, *, name: str | None = None, size_pt: float | None = None,
             bold: bool | None = None, italic: bool | None = None,
             all_caps: bool | None = None, superscript: bool | None = None,
             color: RGBColor | None = None) -> None:
    """Set character formatting on a style.

    Works at both the python-docx font layer and the raw rPr XML layer so
    that theme-font overrides cannot clobber explicit font assignments.
    """
    font = style.font
    font.name = name
    font.size = Pt(size_pt) if size_pt is not None else None
    font.bold = bold
    font.italic = italic
    font.all_caps = all_caps
    if color is not None:
        font.color.rgb = color

    rPr = get_or_add_child(style.element, "w:rPr")
    if name is not None:
        rFonts = get_or_add_child(rPr, "w:rFonts")
        for attr in ("ascii", "hAnsi", "cs", "eastAsia"):
            rFonts.set(qn(f"w:{attr}"), name)
        # Strip theme-font overrides that would take precedence over explicit name.
        for attr in ("asciiTheme", "hAnsiTheme", "cstheme", "eastAsiaTheme"):
            rFonts.attrib.pop(qn(f"w:{attr}"), None)
    else:
        remove_child(rPr, "w:rFonts")
    if size_pt is not None:
        sz = get_or_add_child(rPr, "w:sz")
        sz.set(qn("w:val"), str(int(round(size_pt * 2))))
    else:
        remove_child(rPr, "w:sz")
    if bold is True:
        get_or_add_child(rPr, "w:b")
    elif bold is False:
        remove_child(rPr, "w:b")
    if italic is True:
        get_or_add_child(rPr, "w:i")
    elif italic is False:
        remove_child(rPr, "w:i")
    if superscript is True:
        vert = get_or_add_child(rPr, "w:vertAlign")
        vert.set(qn("w:val"), "superscript")
    elif superscript is False:
        remove_child(rPr, "w:vertAlign")


# Paragraph-level decoration helpers (from counseling book).

def set_style_shading(style, fill: str) -> None:
    pPr = get_or_add_child(style.element, "w:pPr")
    shd = pPr.find(qn("w:shd"))
    if shd is None:
        shd = OxmlElement("w:shd")
        pPr.append(shd)
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), fill)


def set_style_border(style, *, side: str, color: str, size: int,
                     space: int = 0, val: str = "single") -> None:
    pPr = get_or_add_child(style.element, "w:pPr")
    pBdr = pPr.find(qn("w:pBdr"))
    if pBdr is None:
        pBdr = OxmlElement("w:pBdr")
        pPr.append(pBdr)
    edge = pBdr.find(qn(f"w:{side}"))
    if edge is None:
        edge = OxmlElement(f"w:{side}")
        pBdr.append(edge)
    edge.set(qn("w:val"), val)
    edge.set(qn("w:sz"), str(size))
    edge.set(qn("w:space"), str(space))
    edge.set(qn("w:color"), color)


def clear_style_borders_and_shading(style) -> None:
    pPr = get_or_add_child(style.element, "w:pPr")
    for tag in ("w:pBdr", "w:shd"):
        node = pPr.find(qn(tag))
        if node is not None:
            pPr.remove(node)


# ---------------------------------------------------------------------------
# Document-level configuration
# ---------------------------------------------------------------------------

def configure_document(doc: Document) -> None:
    """6×9″ trade trim, mirror margins, twoside headers."""
    section = doc.sections[0]
    section.page_width    = Inches(6)
    section.page_height   = Inches(9)
    section.top_margin    = Inches(0.75)
    section.bottom_margin = Inches(0.75)
    section.left_margin   = Inches(0.75)   # inner (recto)
    section.right_margin  = Inches(0.5)    # outer (recto)
    section.header_distance = Inches(0.375)
    section.footer_distance = Inches(0.375)
    section.gutter       = Inches(0)
    section.start_type   = WD_SECTION_START.NEW_PAGE
    section.different_first_page_header_footer = True

    doc.settings.odd_and_even_pages_header_footer = True

    settings = doc.settings.element
    compat = settings.find(qn("w:compat"))
    if compat is None:
        compat = OxmlElement("w:compat")
        settings.append(compat)
    for name, val in (
        ("compatibilityMode",                              "14"),
        ("overrideTableStyleFontSizeAndJustification",     "1"),
        ("enableOpenTypeFeatures",                         "1"),
        ("doNotFlipMirrorIndents",                         "1"),
    ):
        found = next(
            (el for el in compat.findall(qn("w:compatSetting"))
             if el.get(qn("w:name")) == name),
            None,
        )
        if found is None:
            found = OxmlElement("w:compatSetting")
            compat.append(found)
        found.set(qn("w:name"), name)
        found.set(qn("w:uri"), "http://schemas.microsoft.com/office/word")
        found.set(qn("w:val"), val)


# ---------------------------------------------------------------------------
# Style configuration
# ---------------------------------------------------------------------------

def configure_normal(doc: Document) -> None:
    s = style_by_id(doc, "Normal")
    clear_style_formatting(s)
    set_style_ui(s, hidden=False, quick=True, priority=None)
    set_font(s, name=PALATINO, size_pt=11)
    pf = s.paragraph_format
    pf.alignment          = WD_ALIGN_PARAGRAPH.JUSTIFY
    pf.left_indent        = None
    pf.right_indent       = None
    pf.first_line_indent  = Inches(0.25)
    pf.space_before       = Pt(0)
    pf.space_after        = Pt(5)
    pf.line_spacing_rule  = WD_LINE_SPACING.SINGLE
    pf.line_spacing       = 1.0
    pf.keep_together      = None
    pf.keep_with_next     = None
    pf.page_break_before  = None


def configure_header_footer_styles(doc: Document) -> None:
    for name in ("Header", "Footer"):
        s = ensure_style(doc, name, WD_STYLE_TYPE.PARAGRAPH, base_id="Normal")
        set_style_ui(s, hidden=None, quick=False, priority=99)
        set_font(s, name=PALATINO, size_pt=9, color=_MUTED)
        pf = s.paragraph_format
        pf.alignment         = WD_ALIGN_PARAGRAPH.LEFT
        pf.left_indent       = None
        pf.right_indent      = None
        pf.first_line_indent = None
        pf.space_before      = None
        pf.space_after       = Pt(0)
        pf.line_spacing_rule = WD_LINE_SPACING.SINGLE
        pf.line_spacing      = 1.0


def configure_headings(doc: Document) -> None:
    definitions = {
        "Heading1": dict(size=16, align=WD_ALIGN_PARAGRAPH.CENTER, before=24, after=12),
        "Heading2": dict(size=13, align=WD_ALIGN_PARAGRAPH.LEFT,   before=18, after=10),
        "Heading3": dict(size=12, align=WD_ALIGN_PARAGRAPH.LEFT,   before=14, after=8),
    }
    for style_id, cfg in definitions.items():
        s = style_by_id(doc, style_id)
        clear_style_formatting(s)
        s.base_style = style_by_id(doc, "Normal")
        set_next(doc, s, "BodyText")
        set_style_ui(s, hidden=False, quick=True, priority=9)
        set_font(s, name=PALATINO, size_pt=cfg["size"], bold=True)
        pf = s.paragraph_format
        pf.alignment         = cfg["align"]
        pf.left_indent       = None
        pf.right_indent      = None
        pf.first_line_indent = Inches(0)
        pf.space_before      = Pt(cfg["before"])
        pf.space_after       = Pt(cfg["after"])
        pf.line_spacing_rule = WD_LINE_SPACING.SINGLE
        pf.line_spacing      = 1.0
        pf.keep_together     = True
        pf.keep_with_next    = True
        pf.page_break_before = None


def configure_paragraph_styles(doc: Document) -> None:
    # Body Text — pandoc default style
    s = ensure_style(doc, "BodyText", WD_STYLE_TYPE.PARAGRAPH, base_id="Normal")
    set_style_ui(s, hidden=None, quick=False, priority=99)
    pf = s.paragraph_format
    pf.space_after = Pt(6)

    # First Paragraph — pandoc default style (no first-line indent)
    s = ensure_style(doc, "FirstParagraph", WD_STYLE_TYPE.PARAGRAPH, base_id="Normal")
    pf = s.paragraph_format
    pf.first_line_indent = Inches(0)

    # Compact — pandoc default style (tight list-like paragraphs)
    s = ensure_style(doc, "Compact", WD_STYLE_TYPE.PARAGRAPH, base_id="BodyText")
    set_next(doc, s, "Compact")
    pf = s.paragraph_format
    pf.first_line_indent = Inches(0)
    pf.space_before      = Pt(0)
    pf.space_after       = Pt(0)

    # Captioned Figure — pandoc default style
    s = ensure_style(doc, "CaptionedFigure", WD_STYLE_TYPE.PARAGRAPH, base_id="Normal")
    pf = s.paragraph_format
    pf.alignment         = WD_ALIGN_PARAGRAPH.CENTER
    pf.first_line_indent = Inches(0)
    pf.space_before      = Pt(6)
    pf.space_after       = Pt(3)

    # Image Caption — pandoc default style
    s = ensure_style(doc, "ImageCaption", WD_STYLE_TYPE.PARAGRAPH, base_id="Normal")
    set_font(s, name=PALATINO, size_pt=10, italic=True)
    pf = s.paragraph_format
    pf.alignment         = WD_ALIGN_PARAGRAPH.CENTER
    pf.first_line_indent = Inches(0)
    pf.space_before      = Pt(0)
    pf.space_after       = Pt(6)

    # TOC Heading — pandoc default style
    s = ensure_style(doc, "TOCHeading", WD_STYLE_TYPE.PARAGRAPH, base_id="Normal")
    set_next(doc, s, "Normal")
    set_style_ui(s, hidden=True, quick=True, priority=39)
    set_outline_level(s, 9)
    set_font(s, name=PALATINO, size_pt=16, bold=True)
    pf = s.paragraph_format
    pf.alignment         = WD_ALIGN_PARAGRAPH.CENTER
    pf.first_line_indent = Inches(0)
    pf.space_before      = Pt(24)
    pf.space_after       = Pt(12)
    pf.keep_together     = True
    pf.keep_with_next    = True

    # Footnote Text — pandoc default style
    s = ensure_style(doc, "FootnoteText", WD_STYLE_TYPE.PARAGRAPH, base_id="Normal")
    set_next(doc, s, "FootnoteText")
    set_style_ui(s, hidden=True, quick=False, priority=99)
    set_font(s, name=PALATINO, size_pt=9)
    pf = s.paragraph_format
    pf.alignment         = WD_ALIGN_PARAGRAPH.JUSTIFY
    pf.first_line_indent = Inches(0)
    pf.space_before      = Pt(0)
    pf.space_after       = Pt(3)
    pf.line_spacing_rule = WD_LINE_SPACING.SINGLE
    pf.line_spacing      = 1.0


def configure_quotes(doc: Document) -> None:
    """Style pandoc's block-quote and scripture-quote styles.

    Pandoc maps bare Markdown blockquotes (>) to the "Block Text" style in DOCX
    output — this is a built-in pandoc style name, not configurable.  We style
    it here with a shaded background and left accent border.

    Scripture quotations should use a fenced div to apply the distinct style:

        ::: {custom-style="Scripture Quote"}
        > For God so loved the world… (John 3:16)
        :::

    Bare > blockquotes (Block Text) are for non-scripture prose citations,
    extended quotes, pull quotes, etc.
    """
    # Block Text — pandoc built-in name for bare > blockquotes.
    # Styled with shading + left border, italic, indented.
    block_text = ensure_style(doc, "BlockText", WD_STYLE_TYPE.PARAGRAPH, base_id="Normal")
    block_text.name = "Block Text"
    set_font(block_text, name=PALATINO, size_pt=10.5, italic=True, color=_DARK)
    pf = block_text.paragraph_format
    pf.left_indent       = Inches(0.35)
    pf.right_indent      = Inches(0.25)
    pf.first_line_indent = Inches(0)
    pf.space_before      = Pt(8)
    pf.space_after       = Pt(12)
    pf.line_spacing_rule = WD_LINE_SPACING.MULTIPLE
    pf.line_spacing      = 1.08
    set_style_shading(block_text, QUOTE_FILL)
    set_style_border(block_text, side="left", color=QUOTE_RULE, size=14)

    # Scripture Quote — applied via fenced div custom-style attribute.
    # Derived from Block Text; Palatino italic in muted tone, tighter spacing.
    scripture = ensure_style(doc, "ScriptureQuote", WD_STYLE_TYPE.PARAGRAPH,
                             base_id="BlockText")
    scripture.name = "Scripture Quote"
    set_font(scripture, name=PALATINO, size_pt=10.5, italic=True, color=_MUTED)
    pf = scripture.paragraph_format
    pf.left_indent  = Inches(0.42)
    pf.right_indent = Inches(0.18)
    pf.space_before = Pt(12)
    pf.space_after  = Pt(14)
    pf.line_spacing_rule = WD_LINE_SPACING.MULTIPLE
    pf.line_spacing = 1.08


def configure_lists(doc: Document) -> None:
    s = style_by_id(doc, "ListParagraph")
    clear_style_formatting(s)
    set_font(s, name=PALATINO, size_pt=11, color=_DARK)
    pf = s.paragraph_format
    pf.space_before      = Pt(2)
    pf.space_after       = Pt(5)
    pf.left_indent       = Inches(0.25)
    pf.first_line_indent = Inches(-0.18)
    pf.line_spacing_rule = WD_LINE_SPACING.MULTIPLE
    pf.line_spacing      = 1.08


def configure_table_styles(doc: Document) -> None:
    """Table Text, Table Header Text, and a Compact alias for table cells."""
    # Table Text — body cells; Georgia at 9.9pt for density.
    table_text = ensure_style(doc, "TableText", WD_STYLE_TYPE.PARAGRAPH, base_id="Normal")
    table_text.name = "Table Text"
    clear_style_borders_and_shading(table_text)
    set_font(table_text, name="Georgia", size_pt=9.9, color=_DARK)
    pf = table_text.paragraph_format
    pf.alignment         = WD_ALIGN_PARAGRAPH.LEFT
    pf.left_indent       = Inches(0)
    pf.right_indent      = Inches(0)
    pf.first_line_indent = Inches(0)
    pf.space_before      = Pt(0)
    pf.space_after       = Pt(1)
    pf.line_spacing_rule = WD_LINE_SPACING.SINGLE
    pf.line_spacing      = 1.0
    pf.keep_together     = True
    pf.keep_with_next    = False

    # Table Header Text — header row; Arial bold white on dark fill.
    table_header = ensure_style(doc, "TableHeaderText", WD_STYLE_TYPE.PARAGRAPH,
                                base_id="TableText")
    table_header.name = "Table Header Text"
    clear_style_borders_and_shading(table_header)
    set_font(table_header, name="Arial", size_pt=10, bold=True, color=_WHITE)
    pf = table_header.paragraph_format
    pf.alignment         = WD_ALIGN_PARAGRAPH.CENTER
    pf.space_before      = Pt(0)
    pf.space_after       = Pt(1)
    pf.line_spacing_rule = WD_LINE_SPACING.SINGLE
    pf.line_spacing      = 1.0
    pf.keep_together     = True


def configure_character_styles(doc: Document) -> None:
    # ChapterTitleOnly — invisible marker used by STYLEREF in running headers.
    ensure_style(doc, "ChapterTitleOnly", WD_STYLE_TYPE.CHARACTER)

    # Footnote Text Char — character counterpart to FootnoteText.
    s = ensure_style(doc, "FootnoteTextChar", WD_STYLE_TYPE.CHARACTER)
    set_font(s, name=PALATINO, size_pt=9)

    # Footnote Reference — superscript citation mark.
    s = ensure_style(doc, "FootnoteReference", WD_STYLE_TYPE.CHARACTER)
    set_font(s, name=PALATINO, size_pt=9, superscript=True)


def configure_header_footer_parts(doc: Document) -> None:
    """Initialise all six header/footer XML parts on section[0].

    The postprocessor (postprocess-pandoc.py) populates content into these
    slots after the pandoc build.  We create them here so the reference.docx
    contains the correct part relationships from the start.
    """
    section = doc.sections[0]
    for story, style_id in (
        (section.header,             "Header"),
        (section.first_page_header,  "Header"),
        (section.even_page_header,   "Header"),
        (section.footer,             "Footer"),
        (section.first_page_footer,  "Footer"),
        (section.even_page_footer,   "Footer"),
    ):
        element = story._element
        for child in list(element):
            element.remove(child)
        p = story.add_paragraph()
        p.style = style_by_id(doc, style_id)


# ---------------------------------------------------------------------------
# Reference document assembly
# ---------------------------------------------------------------------------

def add_style_samples(doc: Document) -> None:
    """Populate body with one paragraph per style for visual inspection."""
    samples = [
        ("Heading 1",          "1. Chapter Title"),
        ("Heading 2",          "Section Heading"),
        ("Heading 3",          "Subsection Heading"),
        ("Body Text",          "Body text paragraph with first-line indent."),
        ("First Paragraph",    "First paragraph after heading (no indent)."),
        ("Block Text",         "Sample block quote — general prose citation."),
        ("Scripture Quote",    "For God so loved the world… (John 3:16)"),
        ("List Paragraph",     "• List item sample"),
        ("Table Text",         "Table body cell text sample."),
        ("Table Header Text",  "TABLE HEADER"),
        ("Compact",            "Compact / tight paragraph sample."),
        ("Footnote Text",      "Footnote text sample at 9pt."),
    ]
    for style_name, text in samples:
        try:
            doc.add_paragraph(text, style=style_name)
        except KeyError:
            doc.add_paragraph(f"[missing style: {style_name}] {text}")


def strip_body_for_reference(doc: Document) -> None:
    """Remove all body content, keeping only the section properties."""
    body   = doc._body._element
    sectPr = body.find(qn("w:sectPr"))
    for child in list(body):
        body.remove(child)
    if sectPr is not None:
        body.append(sectPr)


def build_reference_docx(output_path: str | Path = "reference-template.docx",
                         include_samples: bool = False) -> Path:
    """Build and save the unified reference template.

    Args:
        output_path:     Destination path for the .docx file.
        include_samples: When True, populate the body with style sample
                         paragraphs so the template can be reviewed in Word
                         before stripping.  Set False (default) for production.
    """
    output_path = Path(output_path)

    # Seed from pandoc's own default reference.docx so built-in style IDs
    # (Heading1, FootnoteText, etc.) are present and correctly wired.
    result = subprocess.run(
        ["pandoc", "--print-default-data-file", "reference.docx"],
        capture_output=True, check=True,
    )
    doc = Document(io.BytesIO(result.stdout))

    configure_document(doc)
    configure_normal(doc)
    configure_header_footer_styles(doc)
    configure_headings(doc)
    configure_quotes(doc)           # defines Block Text and Scripture Quote
    configure_paragraph_styles(doc) # defines remaining pandoc built-in styles
    configure_lists(doc)
    configure_table_styles(doc)
    configure_character_styles(doc)
    configure_header_footer_parts(doc)

    if include_samples:
        add_style_samples(doc)

    strip_body_for_reference(doc)
    doc.save(output_path)
    return output_path


if __name__ == "__main__":
    import sys
    out  = sys.argv[1] if len(sys.argv) > 1 else "reference-template.docx"
    path = build_reference_docx(out)
    print(f"Created {path.resolve()}")
