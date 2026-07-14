-- typst-markup.lua
-- Markdown -> Typst semantic markup filter for What Scripture Says book production.
--
-- Contract:
--   * Lua emits semantic structure and a few intentional book-production blocks.
--   * book.typ owns layout, vertical rhythm, indentation, footnotes, headers, and tables.
--   * Paragraphs and footnotes remain native except for explicit lead-in/run-in cases.
--
-- Usage:
--   pandoc -f markdown+smart+footnotes+pipe_tables+raw_tex \
--     -t typst \
--     --lua-filter typst-markup.lua \
--     -o 01-salvation.typ \
--     01-salvation.md

local stringify = pandoc.utils.stringify

traverse = "topdown"

local next_para_kind = "first"
local previous_block_was_quote = false

local function raw_block(s)
  return pandoc.RawBlock("typst", s)
end

local function raw_inline(s)
  return pandoc.RawInline("typst", s)
end

local function esc_attr(s)
  if s == nil then return "" end
  s = tostring(s)
  s = s:gsub("\\", "\\\\")
  s = s:gsub('"', '\\"')
  return s
end

local function trim(s)
  return tostring(s or ""):gsub("^%s+", ""):gsub("%s+$", "")
end

-- Escape plain text injected into raw Typst content.
local function esc_typst_text(s)
  s = tostring(s or "")
  s = s:gsub("\\", "\\\\")
  s = s:gsub("#", "\\#")
  s = s:gsub("@", "\\@")
  s = s:gsub("~", "\\~")
  s = s:gsub("%[", "\\[")
  s = s:gsub("%]", "\\]")
  s = s:gsub("%$", "\\$")
  s = s:gsub("%*", "\\*")
  s = s:gsub("_", "\\_")
  s = s:gsub("`", "\\`")
  return s
end

local function blocks_between(opening, blocks, closing)
  local out = { raw_block(opening) }
  for _, b in ipairs(blocks or {}) do table.insert(out, b) end
  table.insert(out, raw_block(closing))
  return out
end

local function inlines_between(opening, inlines, closing)
  local out = { raw_inline(opening) }
  for _, i in ipairs(inlines or {}) do table.insert(out, i) end
  table.insert(out, raw_inline(closing))
  return out
end

local function table_len(t)
  local n = 0
  for _ in ipairs(t or {}) do n = n + 1 end
  return n
end

local function cell_blocks(cell)
  if cell == nil then return {} end
  if cell.contents ~= nil then return cell.contents end
  if cell[1] ~= nil then return cell end
  return {}
end

local function table_rows_from_head(head)
  if head == nil then return {} end
  if head.rows ~= nil then return head.rows end
  return {}
end

local function table_body_rows(body)
  if body == nil then return {} end
  if body.body ~= nil then return body.body end
  if body.rows ~= nil then return body.rows end
  return {}
end

local function row_cells(row)
  if row == nil then return {} end
  if row.cells ~= nil then return row.cells end
  return row
end

local function table_col_count(el)
  if el.colspecs ~= nil then return table_len(el.colspecs) end
  local head_rows = table_rows_from_head(el.head)
  if head_rows[1] ~= nil then return table_len(row_cells(head_rows[1])) end
  if el.bodies ~= nil and el.bodies[1] ~= nil then
    local body_rows = table_body_rows(el.bodies[1])
    if body_rows[1] ~= nil then return table_len(row_cells(body_rows[1])) end
  end
  return 1
end

local function concat_inlines(...)
  local out = {}
  for _, xs in ipairs({...}) do
    for _, x in ipairs(xs or {}) do
      table.insert(out, x)
    end
  end
  return out
end

local function clone_inlines(src, first, last)
  local out = {}
  for i = first, last do table.insert(out, src[i]) end
  return out
end

local function is_space(el)
  return el and (el.t == "Space" or el.t == "SoftBreak" or el.t == "LineBreak")
end

local function strong_text_ends_runin(s)
  s = trim(s)
  return s:match("[%.:]$") ~= nil
end

local function has_class(el, class_name)
  for _, cls in ipairs(el.classes or {}) do
    if cls == class_name then return true end
  end
  return false
end


function Pandoc(doc)
  -- pdf-typst.sh writes the Typst preamble itself so it can inject
  -- generated book-level front matter before the chapter body. Keep the
  -- old standalone behavior for direct pandoc usage.
  if os.getenv("SUPPRESS_TYPST_PREAMBLE") ~= "1" then
    table.insert(doc.blocks, 1, raw_block('#import "book.typ" as book\n#show: book.setup\n'))
  end
  return doc
end

function RawBlock(el)
  previous_block_was_quote = false
  if el.format == "tex" then
    if el.text:match("\\\\newpage") or el.text:match("\\\\pagebreak") or el.text:match("\\\\clearpage") then
      return {}
    end
  end
  return nil
end

function Header(el)
  previous_block_was_quote = false
  local title = stringify(el.content)
  local id = el.identifier or ""
  next_para_kind = "first"

  if el.level == 1 then
    local n, t = title:match("^(%d+)%.%s+(.+)$")
    if n then
      return raw_block('#book.chapter(number: "' .. esc_attr(n) .. '", title: "' .. esc_attr(t) .. '", id: "' .. esc_attr(id) .. '")')
    end
    return raw_block('#book.front_chapter(title: "' .. esc_attr(title) .. '", id: "' .. esc_attr(id) .. '")')
  end

  if el.level == 2 then return raw_block('#book.section(title: "' .. esc_attr(title) .. '", id: "' .. esc_attr(id) .. '")') end
  if el.level == 3 then return raw_block('#book.subsection(title: "' .. esc_attr(title) .. '", id: "' .. esc_attr(id) .. '")') end

  return raw_block('#book.heading(level: ' .. tostring(el.level) .. ', title: "' .. esc_attr(title) .. '", id: "' .. esc_attr(id) .. '")')
end

function Para(el)
  previous_block_was_quote = false
  local c = el.content

  if c[1] and c[1].t == "Strong" and strong_text_ends_runin(stringify(c[1].content)) and c[2] ~= nil then
    local label = c[1].content
    local rest_start = 2
    if is_space(c[rest_start]) then rest_start = rest_start + 1 end
    local rest = clone_inlines(c, rest_start, #c)
    next_para_kind = "normal"
    return {
      raw_block('#book.para(kind: "normal")['),
      pandoc.Plain(concat_inlines(
        { raw_inline("#book.strong[") },
        label,
        { raw_inline("] ") },
        rest
      )),
      raw_block(']')
    }
  end

  if c[1] and c[1].t == "RawInline" and c[1].format == "typst" and c[1].text == "#book.strong[" then
    local close = nil
    for i = 2, #c do
      if c[i].t == "RawInline" and c[i].format == "typst" and c[i].text == "]" then close = i; break end
    end
    if close and close < #c then
      local label = clone_inlines(c, 2, close - 1)
      if strong_text_ends_runin(stringify(label)) then
        local rest_start = close + 1
        if is_space(c[rest_start]) then rest_start = rest_start + 1 end
        local rest = clone_inlines(c, rest_start, #c)
        next_para_kind = "normal"
        return {
          raw_block('#book.para(kind: "normal")['),
          pandoc.Plain(concat_inlines(
            { raw_inline("#book.strong[") },
            label,
            { raw_inline("] ") },
            rest
          )),
          raw_block(']')
        }
      end
    end
  end

  local kind = next_para_kind or "normal"
  next_para_kind = "normal"
  return { raw_block('#book.para(kind: "' .. kind .. '")['), pandoc.Plain(c), raw_block(']') }
end

-- Footnote serialization is defined after the inline serializer helpers.
-- Notes must stay inline, but their internal inline markup must survive.

function BlockQuote(el)
  local adjacent = previous_block_was_quote
  previous_block_was_quote = true
  local opening = adjacent and '#book.quote(adjacent: true)[' or '#book.quote['
  local out = blocks_between(opening, el.content, "]")
  next_para_kind = "normal"   -- consume the "first" set by the preceding header
  return out
end

local function cell_text_len(cell)
  local s = trim(stringify(cell_blocks(cell)))
  -- Count wide punctuation and spaces lightly; keep signal from actual words.
  s = s:gsub("%s+", " ")
  return #s
end

local function table_header_texts(el, cols)
  local out = {}
  local rows = table_rows_from_head(el.head)
  local first = rows and rows[1]
  local cells = first and row_cells(first) or {}
  for i = 1, cols do
    out[i] = string.lower(trim(stringify(cell_blocks(cells[i]))))
  end
  return out
end

local function is_two_col_definition_table(el, cols)
  if cols ~= 2 then return false end
  local h = table_header_texts(el, cols)
  return h[2] == "definition"
end

local function dynamic_col_spec(el, cols)
  -- Two-column definition tables that occur near one another should share the
  -- same visual grammar.  Content-derived widths made Term/Definition and
  -- Type of Call/Definition tables choose slightly different dividers, which
  -- looked accidental when stacked.  Keep this semantic table shape stable
  -- without imposing equal widths or flattening wider analytical tables.
  if is_two_col_definition_table(el, cols) then
    return "(1.60fr, 2.40fr)"
  end

  local weights = {}
  for i = 1, cols do weights[i] = 0.0 end

  local function add_rows(rows, head)
    for _, row in ipairs(rows or {}) do
      local cells = row_cells(row)
      for i = 1, cols do
        local len = cell_text_len(cells[i])
        local score = 0.70 + math.sqrt(math.max(len, 1)) / 3.0
        if head then score = score * 0.95 end
        if score > weights[i] then weights[i] = score end
      end
    end
  end

  add_rows(table_rows_from_head(el.head), true)
  for _, body in ipairs(el.bodies or {}) do add_rows(table_body_rows(body), false) end

  for i = 1, cols do
    weights[i] = math.max(0.72, math.min(weights[i], 2.35))
  end

  -- Extremely narrow middle columns are useful for Greek terms or short labels,
  -- but avoid making any column too small to hold ordinary prose.
  local parts = {}
  for i = 1, cols do table.insert(parts, string.format("%.2ffr", weights[i])) end
  return "(" .. table.concat(parts, ", ") .. ")"
end

function Table(el)
  previous_block_was_quote = false
  local cols = table_col_count(el)
  local out = {}

  table.insert(out, raw_block("#book.table_block["))
  table.insert(out, raw_block("#{"))
  table.insert(out, raw_block("let _cells = ("))

  local function add_rows(rows, is_head)
    for _, row in ipairs(rows or {}) do
      for _, cell in ipairs(row_cells(row)) do
        if is_head then
          table.insert(out, raw_block("book.table_cell(head: true)["))
          for _, b in ipairs(cell_blocks(cell)) do table.insert(out, b) end
          table.insert(out, raw_block("],"))
        else
          table.insert(out, raw_block("book.table_cell["))
          for _, b in ipairs(cell_blocks(cell)) do table.insert(out, b) end
          table.insert(out, raw_block("],"))
        end
      end
    end
  end

  add_rows(table_rows_from_head(el.head), true)
  for _, body in ipairs(el.bodies or {}) do add_rows(table_body_rows(body), false) end

  table.insert(out, raw_block(
    ");" ..
    "table(" ..
    "columns: " .. dynamic_col_spec(el, cols) .. "," ..
    "stroke: (x, y) => (" ..
      "top: if y == 0 { 0.75pt } else { 0.35pt }," ..
      "bottom: 0.35pt," ..
      "left: 0.35pt," ..
      "right: 0.35pt," ..
    ")," ..
    ".._cells," ..
    ");" ..
    "}"
  ))
  table.insert(out, raw_block("]"))
  return out
end

-- Protect em-dashes from line-break decisions by injecting a zero-width
-- no-break hint before each one at the Pandoc AST level.  Typst's line
-- breaker operates on text runs assembled after this filter runs, so the
-- show-rule approach in book.typ is unreliable; this layer owns the fix.
local function protect_emdashes_in_text(s)
  s = tostring(s or "")
  -- U+2060 WORD JOINER: zero-width, no break opportunity. h(0pt) is a glue
  -- element and remains a break point; U+2060 is the correct Unicode primitive.
  local protected = s:gsub("\xe2\x80\x94", "\xe2\x81\xa0\xe2\x80\x94")
  return protected
end

function Str(el)
  if not el.text:find("\xe2\x80\x94", 1, true) then
    return nil
  end
  local out = {}
  local pos = 1
  while true do
    local i, j = el.text:find("\xe2\x80\x94", pos, true)
    if not i then
      if pos <= #el.text then
        table.insert(out, pandoc.Str(el.text:sub(pos)))
      end
      break
    end
    if i > pos then
      table.insert(out, pandoc.Str(el.text:sub(pos, i - 1)))
    end
    table.insert(out, pandoc.Str("\xe2\x81\xa0\xe2\x80\x94"))  -- U+2060 word-joiner + em-dash
    pos = j + 1
  end
  return out
end

-- Serialize a single inline element to a Typst raw string.
-- Mirrors the inline handlers (Emph, Strong, Quoted, Note) defined below.
local inlines_to_typst      -- forward declaration; defined after inline_to_typst
local note_blocks_to_typst  -- forward declaration; defined after inlines_to_typst

local function attr_to_typst_string(s)
  -- Escape for Typst quoted strings, not Typst content blocks.
  s = tostring(s or "")
  s = s:gsub("\\", "\\\\")
  s = s:gsub('"', '\\"')
  s = s:gsub("\r\n", "\n")
  s = s:gsub("\r", "\n")
  s = s:gsub("\n", "\\n")
  return s
end

local function inline_to_typst(el)
  if el.t == "Str" then
    return esc_typst_text(protect_emdashes_in_text(el.text))
  elseif el.t == "Space" or el.t == "SoftBreak" then
    return " "
  elseif el.t == "LineBreak" then
    -- Keep footnotes/list-produced raw Typst inline. Hard Markdown breaks are
    -- converted to an explicit Typst inline break, not a block paragraph.
    return "#linebreak()"
  elseif el.t == "Emph" then
    return "#book.emph[" .. inlines_to_typst(el.content) .. "]"
  elseif el.t == "Strong" then
    return "#book.strong[" .. inlines_to_typst(el.content) .. "]"
  elseif el.t == "Quoted" then
    local kind = el.quotetype == "SingleQuote" and "single" or "double"
    return '#book.quoted(kind: "' .. kind .. '")[' .. inlines_to_typst(el.content) .. "]"
  elseif el.t == "Note" then
    return "#footnote[" .. note_blocks_to_typst(el.content or {}) .. "]"
  elseif el.t == "RawInline" and el.format == "html"
      and el.text:match("^%s*<!%-%-%s*pdf%-?br%s*%-%->%s*$") then
    -- PDF-only manual line-break control. In Markdown source, insert
    -- <!--pdfbr--> inside an epigraph where the print/PDF line should break.
    -- Pandoc drops or hides the HTML comment in non-PDF outputs; the audiobook
    -- scripts strip it explicitly.
    return "#linebreak()"
  elseif el.t == "RawInline" and el.format == "typst" then
    return el.text
  elseif el.t == "Code" then
    return "#raw(\"" .. attr_to_typst_string(el.text) .. "\")"
  elseif el.t == "Math" then
    return "$" .. el.text .. "$"
  elseif el.t == "Link" then
    -- Print-friendly: preserve the visible link text.  URLs are usually
    -- already given in prose/citations in this project, and raw link styling
    -- would be a typography change.
    return inlines_to_typst(el.content or {})
  elseif el.t == "Span" then
    return inlines_to_typst(el.content or {})
  elseif el.t == "SmallCaps" then
    return "#smallcaps[" .. inlines_to_typst(el.content or {}) .. "]"
  elseif el.t == "Superscript" then
    return "#super[" .. inlines_to_typst(el.content or {}) .. "]"
  elseif el.t == "Subscript" then
    return "#sub[" .. inlines_to_typst(el.content or {}) .. "]"
  elseif el.t == "Strikeout" then
    return "#strike[" .. inlines_to_typst(el.content or {}) .. "]"
  else
    -- Fallback: stringify and escape. This loses unknown semantic markup, but
    -- remains Typst-safe and avoids reintroducing block wrappers in footnotes.
    return esc_typst_text(stringify(el))
  end
end

-- Serialize a list of inlines. Defined after inline_to_typst so both can
-- call each other (inline_to_typst calls inlines_to_typst for children).
inlines_to_typst = function(inlines)  -- assigns the forward-declared local
  local parts = {}
  for _, il in ipairs(inlines or {}) do
    table.insert(parts, inline_to_typst(il))
  end
  return table.concat(parts, "")
end

local function list_item_to_note_typst(item)
  local parts = {}
  for _, b in ipairs(item or {}) do
    local s = nil
    if b.t == "Para" or b.t == "Plain" then
      s = inlines_to_typst(b.content or {})
    else
      s = note_blocks_to_typst({ b })
    end
    if trim(s) ~= "" then table.insert(parts, s) end
  end
  return table.concat(parts, " ")
end

local function block_to_note_typst(b)
  if b.t == "Para" or b.t == "Plain" then
    return inlines_to_typst(b.content or {})
  elseif b.t == "BlockQuote" then
    local parts = {}
    for _, qb in ipairs(b.content or {}) do
      local s = block_to_note_typst(qb)
      if trim(s) ~= "" then table.insert(parts, s) end
    end
    return table.concat(parts, " ")
  elseif b.t == "BulletList" then
    local items = {}
    for _, item in ipairs(b.content or {}) do
      local s = list_item_to_note_typst(item)
      if trim(s) ~= "" then table.insert(items, "• " .. s) end
    end
    return table.concat(items, "; ")
  elseif b.t == "OrderedList" then
    local items = {}
    local start = 1
    if b.start ~= nil then start = tonumber(b.start) or 1 end
    for i, item in ipairs(b.content or {}) do
      local s = list_item_to_note_typst(item)
      if trim(s) ~= "" then table.insert(items, tostring(start + i - 1) .. ". " .. s) end
    end
    return table.concat(items, "; ")
  elseif b.t == "LineBlock" then
    local lines = {}
    for _, line in ipairs(b.content or {}) do
      local s = inlines_to_typst(line)
      if trim(s) ~= "" then table.insert(lines, s) end
    end
    return table.concat(lines, "#linebreak()")
  elseif b.t == "CodeBlock" then
    return "#raw(\"" .. attr_to_typst_string(b.text) .. "\")"
  elseif b.t == "HorizontalRule" then
    return ""
  else
    return esc_typst_text(trim(stringify(b)))
  end
end

note_blocks_to_typst = function(blocks)
  -- Deliberately collapse multiple block-level items into inline content.
  -- This preserves the old marker-layout fix while keeping inline markup.
  local parts = {}
  for _, b in ipairs(blocks or {}) do
    local s = block_to_note_typst(b)
    if trim(s) ~= "" then table.insert(parts, s) end
  end
  return table.concat(parts, " ")
end

function Note(el)
  -- Keep notes as a single inline Typst footnote so the marker remains in
  -- the paragraph. Do not run ordinary book.para()/block wrappers inside
  -- notes; that was the source of the earlier marker-on-separate-line bug.
  -- Also do not use stringify() for ordinary note text, because it discards
  -- Emph/Strong/Quoted and similar inline formatting.
  return raw_inline("#footnote[" .. note_blocks_to_typst(el.content or {}) .. "]")
end


function Div(el)
  if not has_class(el, "epigraph") then
    return nil
  end

  previous_block_was_quote = false
  local parts = {}
  for _, b in ipairs(el.content or {}) do
    if b.t == "Para" or b.t == "Plain" then
      table.insert(parts, inlines_to_typst(b.content or {}))
    elseif b.t == "BlockQuote" then
      for _, qb in ipairs(b.content or {}) do
        if qb.t == "Para" or qb.t == "Plain" then
          table.insert(parts, inlines_to_typst(qb.content or {}))
        end
      end
    else
      local s = trim(stringify(b))
      if s ~= "" then table.insert(parts, esc_typst_text(s)) end
    end
  end

  -- Do not consume next_para_kind. The first real paragraph after an
  -- epigraph should still be treated as the first paragraph after the heading.
  if #parts >= 2 then
    local quote_parts = {}
    for i = 1, #parts - 1 do
      table.insert(quote_parts, parts[i])
    end
    local quote = table.concat(quote_parts, "#linebreak()")
    local attribution = parts[#parts]
    return raw_block("#book.epigraph_parts([" .. quote .. "], attribution: [" .. attribution .. "])")
  end
  return raw_block("#book.epigraph[" .. table.concat(parts, "#linebreak()") .. "]")
end

-- Serialize a paragraph's inlines to a book.para() call.
local function para_to_typst(inlines, kind)
  -- Handle run-in strong (bold label ending in period/colon followed by body)
  local c = inlines
  if c[1] and c[1].t == "Strong" and strong_text_ends_runin(stringify(c[1].content)) and c[2] ~= nil then
    local label = inlines_to_typst(c[1].content)
    local rest_start = 2
    if is_space(c[rest_start]) then rest_start = rest_start + 1 end
    local rest_inlines = {}
    for i = rest_start, #c do table.insert(rest_inlines, c[i]) end
    local rest = inlines_to_typst(rest_inlines)
    return '#book.para(kind: "' .. kind .. '")[#book.strong[' .. label .. "] " .. rest .. "]"
  end
  return '#book.para(kind: "' .. kind .. '")[' .. inlines_to_typst(c) .. "]"
end

local function render_list(items, marker)
  local out = {}
  for _, item in ipairs(items or {}) do
    local parts = {}
    local first_para = true
    for _, b in ipairs(item or {}) do
      if b.t == "Para" or b.t == "Plain" then
        local kind = first_para and "first" or "normal"
        local line = para_to_typst(b.content or {}, kind)
        if first_para then
          table.insert(parts, marker .. " " .. line)
        else
          -- Continuation paragraphs: 2-space indent so Typst keeps them in the item
          table.insert(parts, "  " .. line)
        end
        first_para = false
      elseif b.t == "BlockQuote" then
        local inner = {}
        for _, qb in ipairs(b.content or {}) do
          if qb.t == "Para" or qb.t == "Plain" then
            table.insert(inner, inlines_to_typst(qb.content or {}))
          end
        end
        local line = "#book.quote[" .. table.concat(inner, " ") .. "]"
        table.insert(parts, (first_para and (marker .. " ") or "  ") .. line)
        first_para = false
      else
        local line = esc_typst_text(stringify(b))
        table.insert(parts, (first_para and (marker .. " ") or "  ") .. line)
        first_para = false
      end
    end
    table.insert(out, raw_block(table.concat(parts, "\n")))
  end
  return out
end

function BulletList(el)
  previous_block_was_quote = false
  return render_list(el.content, "-")
end

function OrderedList(el)
  previous_block_was_quote = false
  return render_list(el.content, "+")
end

function Emph(el)
  return raw_inline("#book.emph[" .. inlines_to_typst(el.content or {}) .. "]")
end

function Strong(el)
  return raw_inline("#book.strong[" .. inlines_to_typst(el.content or {}) .. "]")
end

function Quoted(el)
  local kind = "double"
  if el.quotetype == "SingleQuote" then kind = "single" end
  return raw_inline('#book.quoted(kind: "' .. kind .. '")[' .. inlines_to_typst(el.content or {}) .. "]")
end

