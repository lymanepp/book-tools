-- scripts/md2ssml.lua
-- Pandoc Lua filter: Markdown -> SSML (via pandoc -t html)
-- Goal: preserve structure (headings/lists/quotes) but emit speech-friendly SSML.

local PARA_BREAK   = "<break time='550ms'/>"
local SECTION_BREAK= "<break time='900ms'/>"
local LIST_BREAK   = "<break time='250ms'/>"
local QUOTE_BREAK  = "<break time='350ms'/>"

local function raw(s)
  return pandoc.RawInline('html', s)
end

local function rawb(s)
  return pandoc.RawBlock('html', s)
end

local function txt(inlines)
  -- stringify inlines (Pandoc handles smart punctuation); keep content only.
  return pandoc.utils.stringify(inlines)
end

-- Strip URLs but keep link text
function Link(el)
  return el.content
end

-- Map *italic* → moderate emphasis (Polly-supported)
function Emph(el)
  local out = { raw("<emphasis level='moderate'>") }
  for i = 1, #el.content do
    out[#out + 1] = el.content[i]
  end
  out[#out + 1] = raw("</emphasis>")
  return out
end

-- Map **bold** → strong emphasis (Polly-supported)
function Strong(el)
  local out = { raw("<emphasis level='strong'>") }
  for i = 1, #el.content do
    out[#out + 1] = el.content[i]
  end
  out[#out + 1] = raw("</emphasis>")
  return out
end

-- Drop images entirely (or change to alt text if you want)
function Image(el)
  -- return el.caption  -- uncomment if you want to read captions/alt-ish text
  return {}           -- default: omit
end

-- Inline code: keep it but without backticks; optionally prefix "code"
function Code(el)
  return pandoc.Str(el.text)
end

-- Code blocks: for narration, best is to omit or summarize
function CodeBlock(el)
  -- If you want to read it, replace {} with:
  -- return pandoc.Para({pandoc.Str("Code block omitted.")})
  return {} -- omit
end

-- Headings: turn into spoken section titles + longer pause
function Header(el)
  local title = txt(el.content)
  if title == "" then return {} end
  return pandoc.Para({
    pandoc.Str(title .. "."),
    raw(SECTION_BREAK)
  })
end

-- Block quotes: preserve content but add a slight pause before/after
function BlockQuote(el)
  local blocks = el.content
  -- Add a short lead-in pause
  table.insert(blocks, 1, pandoc.Para({ raw(QUOTE_BREAK) }))
  -- Add a short trailing pause
  table.insert(blocks, pandoc.Para({ raw(QUOTE_BREAK) }))
  return blocks
end

-- Bullet lists: each item becomes its own paragraph line with short pause
function BulletList(el)
  local out = {}
  for _, item in ipairs(el.content) do
    -- item is a list of Blocks
    local s = pandoc.utils.stringify(pandoc.Div(item))
    s = s:gsub("%s+", " "):gsub("^%s+", ""):gsub("%s+$", "")
    if s ~= "" then
      table.insert(out, pandoc.Para({ pandoc.Str(s .. "."), raw(LIST_BREAK) }))
    end
  end
  table.insert(out, pandoc.Para({ raw(PARA_BREAK) }))
  return out
end

-- Ordered lists: keep numbering spoken
function OrderedList(el)
  local out = {}
  local n = 1
  for _, item in ipairs(el.content) do
    local s = pandoc.utils.stringify(pandoc.Div(item))
    s = s:gsub("%s+", " "):gsub("^%s+", ""):gsub("%s+$", "")
    if s ~= "" then
      table.insert(out, pandoc.Para({
        pandoc.Str(tostring(n) .. ". " .. s .. "."),
        raw(LIST_BREAK)
      }))
    end
    n = n + 1
  end
  table.insert(out, pandoc.Para({ raw(PARA_BREAK) }))
  return out
end

-- Tables: narration-friendly default is to omit (tables are awful read aloud)
function Table(el)
  return {} -- omit
end

-- Horizontal rule: treat as a section pause
function HorizontalRule(el)
  return pandoc.Para({ raw(SECTION_BREAK) })
end

-- Paragraph breaks: add a medium pause after paragraphs
function Para(el)
  -- Avoid double pauses if the paragraph already ends with a break raw inline
  local inl = el.content
  if #inl > 0 then
    local last = inl[#inl]
    if last.t == "RawInline" and (last.text:find("<break") ~= nil) then
      return el
    end
  end
  table.insert(inl, raw(PARA_BREAK))
  return pandoc.Para(inl)
end

-- Wrap entire document in <speak> ... </speak>
function Pandoc(doc)
  local blocks = doc.blocks
  table.insert(blocks, 1, rawb("<speak>"))
  table.insert(blocks, rawb("</speak>"))
  return pandoc.Pandoc(blocks, doc.meta)
end
