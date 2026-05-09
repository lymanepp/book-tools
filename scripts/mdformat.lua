-- mdformat.lua
--
-- Unified Lua filter for DOCX + EPUB/HTML pipelines.
--
-- Print layout is now owned entirely by the Typst pipeline.
-- This filter no longer implements odd-page logic.
--
-- Chapter structure is driven semantically by H1 headers:
--
--     # Chapter Title
--
-- H1 headers receive:
--   DOCX      → simple page break before chapter
--   EPUB/HTML → CSS page break before chapter
--
-- Legacy \newpage directives are ignored and may be safely removed
-- from Markdown source files.
--
-- Remaining supported directives:
--
--   \pagebreak
--   \clearpage
--       Manual intra-chapter page break.
--
--   \toc
--       Native Word TOC field insertion.
--
-- Blockquote behavior:
--
--   Bare >
--       Uses Pandoc's built-in "Block Text" style in DOCX.
--
--   Scripture quotations:
--
--       ::: {custom-style="Scripture Quote"}
--       > Scripture text...
--       :::
--
--   This preserves a distinction between ordinary block quotes and
--   intentionally styled Scripture quotations.

----------------------------------------------------------------------
-- Helpers
----------------------------------------------------------------------

local function is_tex_command(raw, cmd)
  return raw.format:match("tex") and raw.text == cmd
end

local function is_newpage_tex(raw)
  return is_tex_command(raw, "\\newpage")
end

local function is_pagebreak_tex(raw)
  return is_tex_command(raw, "\\pagebreak")
end

local function is_clearpage_tex(raw)
  return is_tex_command(raw, "\\clearpage")
end

local function is_manual_break_tex(raw)
  return is_pagebreak_tex(raw) or is_clearpage_tex(raw)
end

local function is_toc_tex(raw)
  return is_tex_command(raw, "\\toc")
end

----------------------------------------------------------------------
-- DOCX helpers
----------------------------------------------------------------------

local function page_break_docx()
  return pandoc.RawBlock("openxml", table.concat({
    '<w:p>',
      '<w:r>',
        '<w:br w:type="page"/>',
      '</w:r>',
    '</w:p>',
  }))
end

local function toc_docx()
  return pandoc.RawBlock("openxml", table.concat({

    '<w:sdt>',

      '<w:sdtPr>',
        '<w:docPartObj>',
          '<w:docPartGallery w:val="Table of Contents"/>',
          '<w:docPartUnique/>',
        '</w:docPartObj>',
      '</w:sdtPr>',

      '<w:sdtContent>',

        '<w:p>',
          '<w:pPr>',
            '<w:pStyle w:val="TOCHeading"/>',
          '</w:pPr>',
          '<w:r>',
            '<w:t xml:space="preserve">Table of Contents</w:t>',
          '</w:r>',
        '</w:p>',

        '<w:p>',
          '<w:r>',
            '<w:fldChar w:fldCharType="begin" w:dirty="true"/>',
            '<w:instrText xml:space="preserve">TOC \\o "1-1" \\h \\z \\u</w:instrText>',
            '<w:fldChar w:fldCharType="separate"/>',
            '<w:fldChar w:fldCharType="end"/>',
          '</w:r>',
        '</w:p>',

      '</w:sdtContent>',

    '</w:sdt>',
  }))
end

----------------------------------------------------------------------
-- Header handling
----------------------------------------------------------------------

local seen_first_h1 = false

function Header(el)
  -- H1 headers define chapter boundaries.
  -- Typst owns all real print pagination.
  --
  -- DOCX gets simple page breaks between chapters.
  -- EPUB/HTML gets no forced breaks to avoid blank pages
  -- and broken TOC navigation.

  if el.level ~= 1 then
    return el
  end

  --------------------------------------------------------------------
  -- DOCX
  --------------------------------------------------------------------

  if FORMAT:match("docx") then

    -- Do not insert a break before the first chapter.
    if not seen_first_h1 then
      seen_first_h1 = true
      return el
    end

    return {
      page_break_docx(),
      el,
    }
  end

  --------------------------------------------------------------------
  -- EPUB / HTML
  --------------------------------------------------------------------

  return el
end

----------------------------------------------------------------------
-- RawBlock handling
----------------------------------------------------------------------

function RawBlock(el)

  --------------------------------------------------------------------
  -- Ignore legacy \newpage directives entirely.
  --
  -- Structural chapter pagination is now driven by H1 headers.
  --------------------------------------------------------------------

  if is_newpage_tex(el) then
    return {}
  end

  --------------------------------------------------------------------
  -- Manual intra-chapter page breaks.
  --------------------------------------------------------------------

  if is_manual_break_tex(el) then

    if FORMAT:match("docx") then
      return page_break_docx()
    end

    return nil
  end

  --------------------------------------------------------------------
  -- Native Word TOC insertion.
  --------------------------------------------------------------------

  if is_toc_tex(el) then

    if FORMAT:match("docx") then
      return toc_docx()
    end

    return nil
  end

  return nil
end
