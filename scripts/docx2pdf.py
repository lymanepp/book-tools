import sys
from pathlib import Path

import pythoncom
import win32com.client


# Word constants
WD_EXPORT_FORMAT_PDF = 17
WD_DO_NOT_SAVE_CHANGES = 0


def strip_trailing_odd_page_section(doc) -> bool:
    if doc.Sections.Count < 2:
        return False

    prev_section = doc.Sections(doc.Sections.Count - 1)
    last_section = doc.Sections(doc.Sections.Count)

    # A trailing odd-page artifact typically creates a final empty section.
    last_text = last_section.Range.Text.replace("\r", "").replace("\x07", "").strip()
    if last_text != "":
        return False

    # The section break is the final character of the previous section's range.
    rng = prev_section.Range.Duplicate
    rng.Collapse(0)   # start
    rng.SetRange(prev_section.Range.End - 1, prev_section.Range.End)
    rng.Delete()
    return True

def convert_docx_to_pdf(docx_path: str, pdf_path: str | None = None) -> Path:
    """
    Open a DOCX in Microsoft Word, update TOCs/fields, repaginate,
    and export to PDF using Word's native rendering engine.

    Requires:
      - Windows
      - Microsoft Word installed
      - pywin32
    """
    pythoncom.CoInitialize()

    word = None
    doc = None

    try:
        input_path = Path(docx_path).resolve()
        if not input_path.exists():
            raise FileNotFoundError(f"Input file not found: {input_path}")

        if pdf_path is None:
            output_path = input_path.with_suffix(".pdf")
        else:
            output_path = Path(pdf_path).resolve()

        word = win32com.client.DispatchEx("Word.Application")
        word.Visible = False
        word.DisplayAlerts = 0

        # Open read/write so Word can fully update fields and pagination.
        doc = word.Documents.Open(
            str(input_path),
            ConfirmConversions=False,
            ReadOnly=False,
            AddToRecentFiles=False,
            Visible=False,
        )

        # Update every TOC explicitly.
        # TableOfContents.Update updates the entries;
        # UpdatePageNumbers exists separately, but Update is the more complete operation.
        for i in range(1, doc.TablesOfContents.Count + 1):
            toc = doc.TablesOfContents(i)
            toc.Update()

        if strip_trailing_odd_page_section(doc):
            print("Removed trailing odd-page end section")

        # Update all remaining fields as well
        # (cross-references, page refs, etc.).
        doc.Fields.Update()

        # Force pagination to settle before PDF export.
        doc.Repaginate()

        # Export as PDF with Word's own engine.
        doc.ExportAsFixedFormat(
            OutputFileName=str(output_path),
            ExportFormat=WD_EXPORT_FORMAT_PDF,
            OpenAfterExport=False,
            OptimizeFor=0,          # print
            Range=0,                # whole document
            Item=0,                 # document content
            IncludeDocProps=True,
            KeepIRM=True,
            CreateBookmarks=1,      # headings/bookmarks where possible
            DocStructureTags=True,
            BitmapMissingFonts=True,
            UseISO19005_1=False,    # PDF, not PDF/A
        )

        return output_path

    finally:
        if doc is not None:
            doc.Close(SaveChanges=WD_DO_NOT_SAVE_CHANGES)
        if word is not None:
            word.Quit()
        pythoncom.CoUninitialize()


def main() -> int:
    if len(sys.argv) not in (2, 3):
        print("Usage: py docx2pdf_word.py input.docx [output.pdf]")
        return 1

    input_file = sys.argv[1]
    output_file = sys.argv[2] if len(sys.argv) == 3 else None

    try:
        pdf = convert_docx_to_pdf(input_file, output_file)
        print(f"Created: {pdf}")
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
