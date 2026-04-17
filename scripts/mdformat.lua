-- mdformat.lua — unified Lua filter for all output formats.
--
-- Handles:
--   \newpage    → odd-page section break (DOCX) / \newpage (LaTeX) / CSS break (EPUB)
--   \pagebreak  → plain page break       (DOCX) / \newpage (LaTeX) / CSS break (EPUB)
--   \toc        → native Word TOC field  (DOCX) / \tableofcontents (LaTeX)
--   BlockQuote  → "Block Text" style by default (pandoc built-in, styled by reference.docx)
--                 Fenced div with custom-style="Scripture Quote" → Scripture Quote style
--
-- Blockquote mapping:
--   Bare >    → pandoc emits "Block Text" in DOCX (built-in pandoc style name).
--               configure_paragraph_styles() in build-template.py styles it with
--               left indent and no first-line indent — appropriate for poetry / prose
--               block quotes that are NOT scripture.
--
--   Scripture quotations should use the fenced div form to get the distinct style:
--
--       ::: {custom-style="Scripture Quote"}
--       > For God so loved the world… (John 3:16)
--       :::
--
--   This keeps bare > available for non-scripture block quotes and lets the
--   Scripture Quote style carry the shading, left border, and Palatino italic
--   applied by build-template.py.

local function is_tex_command(raw, cmd)
  return raw.format:match("tex") and raw.text == cmd
end

local function is_newpage_tex(raw)
  return is_tex_command(raw, "\\newpage")
end

local function is_pagebreak_tex(raw)
  return is_tex_command(raw, "\\pagebreak")
end

local function is_break_tex(raw)
  return is_newpage_tex(raw) or is_pagebreak_tex(raw)
end

local function is_toc_tex(raw)
  return is_tex_command(raw, "\\toc")
end

local function odd_page_section_break_docx()
  -- Odd-page section break in OOXML.
  --
  -- Rules:
  -- 1. sectPr must be inside <w:pPr> of an empty paragraph.
  -- 2. Full layout properties must be repeated.
  -- 3. Do NOT include <w:titlePg/>.
  return pandoc.RawBlock("openxml", table.concat({
    '<w:p>',
      '<w:pPr>',
        '<w:sectPr>',
          '<w:type w:val="oddPage"/>',
          '<w:pgSz w:w="8640" w:h="12960"/>',
          '<w:pgMar w:top="1080" w:right="720" w:bottom="1080" w:left="1080" w:header="540" w:footer="540" w:gutter="0"/>',
          '<w:cols w:space="720"/>',
          '<w:docGrid w:linePitch="360"/>',
          '<w:mirrorMargins/>',
        '</w:sectPr>',
      '</w:pPr>',
    '</w:p>',
  }))
end

local function toc_docx()
  -- Insert a native Word TOC content control + field.
  -- Word will usually update/populate it on open or field update.
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

local function toc_latex()
  return pandoc.RawBlock("latex", "\\tableofcontents")
end

local function toc_html()
  -- No-op for now. Pandoc won't build a real HTML TOC from here
  -- unless you want to add custom handling later.
  return nil
end

local function plain_page_break_docx()
  -- A simple page break (not section-aware) for use within a chapter.
  -- Use \pagebreak in Markdown for intra-chapter breaks.
  -- Use \newpage for chapter boundaries (odd-page section break).
  return pandoc.RawBlock("openxml", table.concat({
    '<w:p>',
      '<w:r>',
        '<w:br w:type="page"/>',
      '</w:r>',
    '</w:p>',
  }))
end

local function html_page_break()
  return pandoc.RawBlock("html",
    "<div style=\"break-before: page; page-break-before: always;\"></div>"
  )
end

function RawBlock(el)
  -- \newpage → odd-page section break (chapter boundary)
  if is_newpage_tex(el) then
    if FORMAT:match("docx") then
      return odd_page_section_break_docx()
    elseif FORMAT:match("latex") or FORMAT:match("pdf") then
      return pandoc.RawBlock("latex", "\\newpage")
    elseif FORMAT:match("epub") or FORMAT:match("html") then
      return html_page_break()
    end
    return nil
  end

  -- \pagebreak → plain page break (within a chapter)
  if is_pagebreak_tex(el) then
    if FORMAT:match("docx") then
      return plain_page_break_docx()
    elseif FORMAT:match("latex") or FORMAT:match("pdf") then
      return pandoc.RawBlock("latex", "\\newpage")
    elseif FORMAT:match("epub") or FORMAT:match("html") then
      return html_page_break()
    end
    return nil
  end

  -- \toc → native Word TOC field / LaTeX table of contents
  if is_toc_tex(el) then
    if FORMAT:match("docx") then
      return toc_docx()
    elseif FORMAT:match("latex") or FORMAT:match("pdf") then
      return toc_latex()
    elseif FORMAT:match("epub") or FORMAT:match("html") then
      return toc_html()
    end
    return nil
  end

  return nil
end
