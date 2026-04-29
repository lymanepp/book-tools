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
  s = s:gsub("%[", "\\[")
  s = s:gsub("%]", "\\]")
  s = s:gsub("%$", "\\$")
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

local function para_ends_with_colon(el)
  local s = trim(stringify(el.content))
  if s == "" then return false end
  if s:match("^https?://") then return false end
  return s:match(":$") ~= nil
end

function Pandoc(doc)
  -- pdf-typst.sh writes the Typst preamble itself so it can inject
  -- generated book-level front matter before the chapter body. Keep the
  -- old standalone behavior for direct pandoc usage.
  if os.getenv("WSS_SUPPRESS_TYPST_PREAMBLE") ~= "1" then
    table.insert(doc.blocks, 1, raw_block('#import "book.typ" as book\n#show: book.setup\n'))
  end
  return doc
end

function RawBlock(el)
  if el.format == "tex" then
    if el.text:match("\\\\newpage") or el.text:match("\\\\pagebreak") or el.text:match("\\\\clearpage") then
      return {}
    end
  end
  return nil
end

function Header(el)
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

function Plain(el) return nil end

function Note(el)
  -- Flatten notes into a single inline footnote. Do NOT run paragraph
  -- wrappers inside footnotes; that caused markers to sit on a separate line.
  local parts = {}
  for _, b in ipairs(el.content or {}) do
    local s = trim(stringify(b))
    if s ~= "" then table.insert(parts, s) end
  end
  local text = table.concat(parts, " ")
  return raw_inline("#footnote[" .. esc_typst_text(text) .. "]")
end

function BlockQuote(el)
  local out = blocks_between("#book.quote[", el.content, "]")
  next_para_kind = "normal"   -- consume the "first" set by the preceding header
  return out
end

function HorizontalRule() return raw_block("#book.hr[]") end

function LineBlock(el)
  local out = { raw_block("#book.lineblock[") }
  for _, line in ipairs(el.content or {}) do
    table.insert(out, raw_block("#book.line["))
    table.insert(out, pandoc.Plain(line))
    table.insert(out, raw_block("]"))
  end
  table.insert(out, raw_block("]"))
  return out
end

function BulletList(el) return nil end
function OrderedList(el) return nil end
function DefinitionList(el) return nil end

function CodeBlock(el)
  return raw_block('#book.codeblock(language: "' .. esc_attr(el.classes and el.classes[1] or "") .. '")[' .. el.text .. ']')
end

local function cell_text_len(cell)
  local s = trim(stringify(cell_blocks(cell)))
  -- Count wide punctuation and spaces lightly; keep signal from actual words.
  s = s:gsub("%s+", " ")
  return #s
end

local function dynamic_col_spec(el, cols)
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

  local total = 0.0
  for i = 1, cols do
    weights[i] = math.max(0.72, math.min(weights[i], 2.35))
    total = total + weights[i]
  end

  -- Extremely narrow middle columns are useful for Greek terms or short labels,
  -- but avoid making any column too small to hold ordinary prose.
  local parts = {}
  for i = 1, cols do table.insert(parts, string.format("%.2ffr", weights[i])) end
  return "(" .. table.concat(parts, ", ") .. ")"
end

function Table(el)
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

function Figure(el) return blocks_between("#book.figure[", el.content, "]") end

function Div(el)
  local classes = table.concat(el.classes or {}, " ")
  return blocks_between('#book.div(classes: "' .. esc_attr(classes) .. '")[', el.content, "]")
end

function Emph(el) return inlines_between("#book.emph[", el.content, "]") end
function Strong(el) return inlines_between("#book.strong[", el.content, "]") end
function Strikeout(el) return inlines_between("#book.strike[", el.content, "]") end
function Superscript(el) return inlines_between("#book.sup[", el.content, "]") end
function Subscript(el) return inlines_between("#book.sub[", el.content, "]") end
function SmallCaps(el) return inlines_between("#book.smallcaps[", el.content, "]") end

function Quoted(el)
  local kind = "double"
  if el.quotetype == "SingleQuote" then kind = "single" end
  return inlines_between('#book.quoted(kind: "' .. kind .. '")[', el.content, "]")
end

function Code(el) return raw_inline("#book.code[" .. el.text .. "]") end
function Link(el) return inlines_between('#book.link(url: "' .. esc_attr(el.target) .. '")[', el.content, "]") end

function Image(el)
  local alt = stringify(el.content)
  return raw_inline('#book.image(src: "' .. esc_attr(el.src) .. '", alt: "' .. esc_attr(alt) .. '")')
end

function LineBreak() return raw_inline("#book.linebreak[]") end
function Str(el) return el end
