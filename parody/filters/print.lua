-- Print-target pandoc filter: markdown -> LaTeX environments.
--
-- Ported per-environment from rtc-book common/filter.lua (2,803 lines),
-- keeping the LaTeX emission for the environments and semantic spans the
-- seed plan inventories. Deliberately NOT ported (book-private or Phase 4
-- plugin territory): book-defs/book-json lookups, hardware versioning
-- (ts/ds spans, version_params), apocrypha/video machinery, the meta-site
-- HTML branches, and the MIT Press \lab/\resource section commands.
--
-- The emitted commands/environments are defined by the generic profile
-- (profiles/print/parody-print.sty): exercise/solution (xsim), example,
-- theorem/definition/lemma/corollary/proposition (tcolorbox), infobox,
-- listingsbox(float) (minted), algorithm, \figcaption/\tabcaption,
-- \keyword, \myindex/\indexc, \mykeys, \menu, \path, \myurl(inline),
-- \lref, \unicoder, formattedoutput, mintedwrapper.

local function isempty(s)
  return s == nil or s == '' or next(s) == nil
end

local function starts_with(start, str)
  return str:sub(1, #start) == start
end

local function has_value(tab, val)
  for _, value in ipairs(tab) do
    if value == val then
      return true
    end
  end
  return false
end

local function delimiter_dollar(text)
  text = string.gsub(text, "\\%(", "$")
  text = string.gsub(text, "\\%)", "$")
  return text
end

local function is_latex()
  return FORMAT:match 'latex' or FORMAT:match 'beamer'
end

-- Forward declarations so the interior filter late-binds to the handlers.
local coder_latex, citer, pandoccrossrefer
local moving_code_to_latex -- safe rendering of inline code in moving arguments
local resolve_asset -- defined in the notebook-includes section below

-- Walks content nested inside environments so spans/code/cites inside
-- exercise bodies etc. get the same treatment as top-level content.
local interior_filter
interior_filter = {
  Math = function(el) return Math(el) end,
  RawInline = function(el) return RawInline(el) end,
  RawBlock = function(el) return RawBlock(el) end,
  Span = function(el) return Span(el) end,
  Link = function(el) return Link(el) end,
  Code = function(el)
    if is_latex() then return coder_latex(el) else return Code(el) end
  end,
  CodeBlock = function(el)
    if is_latex() then return coder_latex(el) else return CodeBlock(el) end
  end,
  Cite = function(el)
    local first_id = el.citations[1].id
    if is_latex() then
      if first_id:match('^[Ss]ec:') or first_id:match('^[Ee]q:')
          or first_id:match('^[Tt]bl:') or first_id:match('^[Ff]ig:')
          or first_id:match('^[Ll]st:') then
        return pandoccrossrefer(el)
      else
        return Cite(el)
      end
    else
      return Cite(el)
    end
  end,
  OrderedList = function(el) return OrderedList(el) end,
  Table = function(el) return Table(el) end,
  Figure = function(el) return Figure(el) end,
  -- Only cloze blocks: returning nil for every other class leaves the bespoke
  -- nested-Div handling inside the environment handlers untouched. Late-binds
  -- to the global Div, like the other entries here.
  Div = function(el)
    if el.classes:includes('cloze') or el.classes:includes('blank') then
      return Div(el)
    end
    return nil
  end,
}

-- Bare-image fallback. Walked separately AFTER interior_filter: within a
-- single walk table inlines run before blocks, so registering Image
-- alongside Figure would hand Figure an already-converted RawInline.
local image_filter = { Image = function(el) return Image(el) end }

local inline_filter = {
  Math = function(el) return Math(el) end,
  Code = function(el)
    if is_latex() then return coder_latex(el) else return Code(el) end
  end,
  RawInline = function(el) return RawInline(el) end,
  Cite = function(el) return Cite(el) end,
  Span = function(el) return Span(el) end,
  Link = function(el) return Link(el) end,
}

local function walk_to_latex(el)
  local el_walked = pandoc.walk_block(el, interior_filter)
  el_walked = pandoc.walk_block(el_walked, image_filter)
  local content_doc = pandoc.Pandoc(el_walked.content)
  return pandoc.write(content_doc, 'latex')
end

local function inlines_to_latex(content)
  local walked = pandoc.Para(content)
  -- inline code in a moving argument (section title, figure/table caption)
  -- can't be verbatim \mintinline; swap it for a \texttt form first
  walked = pandoc.walk_block(walked, { Code = moving_code_to_latex })
  walked = pandoc.walk_block(walked, inline_filter)
  local doc = pandoc.Pandoc(walked)
  local tex = pandoc.write(doc, 'latex')
  return (tex:gsub("\n$", ""))
end

-- ---- cloze (fill-in-the-blank) -------------------------------------------
-- Print emits the profile-contract macros in every mode and lets TeX branch on
-- \clozemode: only LaTeX can measure the hidden box (\settowidth), so widths
-- are exact, and the discarded measuring box never enters the PDF content
-- stream — a `blank` PDF cannot be mined for answers. Named sizes are resolved
-- here so the profile always receives a real length. See filter.lua for the
-- web side, which must strip the answer instead.
-- Figure variants are the one thing print resolves in Lua, not TeX: asset
-- resolution and svg conversion already live here.
local CLOZE_MODE = os.getenv('PARODY_CLOZE_MODE') or 'blank'
local CLOZE_SIZES = { sm = '2em', md = '5em', lg = '10em', xl = '20em' }

local function cloze_manual_width(el)
  local w = el.attributes and el.attributes.width
  if w and w ~= '' then return w end
  local size = (el.attributes and el.attributes.size) or 'md'
  return CLOZE_SIZES[size] or CLOZE_SIZES.md
end

-- Incomplete artwork for `blank` mode: an explicit cloze="…" attribute, else a
-- <stem>-cloze.<ext> sibling in the chapter source dir. Absence means the
-- figure isn't part of the exercise, so it renders complete in every mode.
-- Only the referenced file is staged into media/, so in `blank` mode the
-- complete artwork is never published.
local function cloze_variant_src(el)
  if CLOZE_MODE ~= 'blank' then return nil end
  local explicit = el.attributes and el.attributes.cloze
  if explicit and explicit ~= '' then return explicit end
  local stem, ext = el.src:match('^(.*)%.(%w+)$')
  if not stem then return nil end
  local candidate = stem .. '-cloze.' .. ext
  local dir = os.getenv('PARODY_CHAPTER_DIR')
  if not dir then return nil end
  local f = io.open(dir .. '/' .. candidate, 'r')
  if f then f:close() return candidate end
  return nil
end

local function clozer_latex(el)
  return pandoc.RawInline('tex',
    '\\cloze{' .. inlines_to_latex(el.content) .. '}')
end

local function blanker_latex(el)
  return pandoc.RawInline('tex', '\\clozeblank{' .. cloze_manual_width(el) .. '}')
end

local function cloze_div_latex(el)
  local content = pandoc.write(pandoc.Pandoc(el.content), 'latex')
  return pandoc.RawBlock('tex',
    '\\begin{clozeblock}\n' .. content .. '\n\\end{clozeblock}')
end

local function blank_div_latex(el)
  local n = tonumber(el.attributes and el.attributes.lines) or 4
  return pandoc.RawBlock('tex',
    string.format('\\clozelines{%d}', math.max(1, math.floor(n))))
end

-- Inline code in a moving argument (section title, figure/table caption) must
-- not use verbatim \mintinline: those arguments are written to the .toc/.lof
-- and re-read by hyperref's \pdfstringdef for PDF bookmarks, and verbatim
-- catcodes break there ("Argument of \FV@... has an extra }" -> Emergency
-- stop). Render it as an escaped \texttt instead, with a plain \texorpdfstring
-- fallback for the bookmark text. Body inline code keeps \mintinline (minted
-- highlighting). Assigned to the forward-declared upvalue so inlines_to_latex,
-- defined above, can reach it.
local function latex_escape_tt(s)
  local repl = {
    ['\\'] = '\\textbackslash{}',
    ['{'] = '\\{', ['}'] = '\\}', ['$'] = '\\$', ['&'] = '\\&',
    ['#'] = '\\#', ['_'] = '\\_', ['%'] = '\\%',
    ['~'] = '\\textasciitilde{}', ['^'] = '\\textasciicircum{}',
  }
  return (s:gsub('[\\{}%$&#_%%~%^]', repl))
end

moving_code_to_latex = function(el)
  local content = pandoc.utils.stringify(el.text)
  local safe = '\\texttt{' .. latex_escape_tt(content) .. '}'
  return pandoc.RawInline('latex',
    '\\texorpdfstring{' .. safe .. '}{' .. content .. '}')
end

-- A subfigures div's caption is a block. When the source caption starts with a
-- fancy-list marker like "(a) ...", pandoc parses the whole paragraph as a
-- one-item OrderedList; emitting it verbatim yields \figcaption{\begin{enumerate}
-- ...}, and a list environment inside that moving argument breaks lualatex
-- ("Incomplete \iffalse ... Emergency stop"). Flatten any list caption back to
-- a single Plain, re-prefixing each item with its reconstructed marker.
local function list_marker(style, delim, n)
  local num
  if style == 'LowerAlpha' and n >= 1 and n <= 26 then
    num = string.char(96 + n)
  elseif style == 'UpperAlpha' and n >= 1 and n <= 26 then
    num = string.char(64 + n)
  else
    num = tostring(n) -- Decimal / Roman / Example all fall back to the number
  end
  if delim == 'TwoParens' then return '(' .. num .. ')' end
  if delim == 'OneParen' then return num .. ')' end
  return num .. '.'
end

local function delist_caption(block)
  if block.t ~= 'OrderedList' and block.t ~= 'BulletList' then
    return block
  end
  local la = block.listAttributes or {}
  local style = la.style and tostring(la.style) or 'Decimal'
  local delim = la.delimiter and tostring(la.delimiter) or 'Period'
  local start = la.start or 1
  local out = {}
  for i, item in ipairs(block.content) do
    if #out > 0 then out[#out + 1] = pandoc.Space() end
    if block.t == 'OrderedList' then
      out[#out + 1] = pandoc.Str(list_marker(style, delim, start + i - 1))
      out[#out + 1] = pandoc.Space()
    end
    for _, x in ipairs(pandoc.utils.blocks_to_inlines(item, { pandoc.Space() })) do
      out[#out + 1] = x
    end
  end
  return pandoc.Plain(out)
end

-- Headers: standard LaTeX sectioning (the ancestor's custom
-- \section[][v][wherein]{shortid}{hash} commands are MIT-class-private).
local function headerer_latex(el)
  local l = el.level
  if l > 3 then return el end
  local content = ''
  if el.content then
    content = inlines_to_latex(el.content)
  end
  local cmds = { 'section', 'subsection', 'subsubsection' }
  local star = el.classes:includes('unnumbered') and '*' or ''
  local label = el.attr.attributes['shortid'] or el.identifier
  -- Lab sections render via the MIT-class-private \lab command (each print
  -- profile styles it); other levels/sections use the standard sectioning.
  local sec_tex
  if el.classes:includes('lab') then
    sec_tex = '\\lab{' .. content .. '}'
  else
    sec_tex = '\\' .. cmds[l] .. star .. '{' .. content .. '}'
  end
  if label and label ~= '' then
    sec_tex = sec_tex .. '\n\\label{' .. label .. '}'
  end
  -- short hashes are cross-ref keys: [h]{.hashref} -> \cref{h} needs a
  -- label at the heading carrying that hash
  local h = el.attr.attributes['h'] or el.attr.attributes['hash']
  if h and h ~= '' and h ~= label then
    sec_tex = sec_tex .. '\n\\label{' .. h .. '}'
  end
  -- Companion QR at each top-level section heading: the profile's \parodyqr
  -- (if defined) drops a QR of companion_url/<hash> in the margin, matching the
  -- original book. Guarded so profiles without it (and books without a
  -- companion_url, whose build pre-renders no qr-<hash>.png) simply no-op.
  if l == 1 and h and h ~= '' and not el.classes:includes('lab') then
    sec_tex = sec_tex ..
      '\n\\ifcsname parodyqr\\endcsname\\parodyqr{' .. h .. '}\\fi'
  end
  return { pandoc.RawBlock('latex', sec_tex) }
end

-- Semantic spans -------------------------------------------------------

local function keyer(el)
  if not is_latex() then return el end
  local text = ''
  if el.content then
    text = pandoc.utils.stringify(el.content)
  end
  if el.classes:includes('folder') then
    text = '\\faFolder'
  elseif el.classes:includes('windows') then
    text = '\\faWindows'
  elseif el.classes:includes('enter') then
    text = 'ENTR'
  elseif el.classes:includes('return') then
    text = '\\return'
  elseif el.classes:includes('leftarrow') or el.classes:includes('left')
      or el.classes:includes('backspace') then
    text = '$\\leftarrow$'
  elseif el.classes:includes('uparrow') or el.classes:includes('up') then
    text = 'UP'
  elseif el.classes:includes('downarrow') or el.classes:includes('down') then
    text = 'DWN'
  elseif el.classes:includes('play') then
    text = '\\faPlay'
  end
  return pandoc.RawInline('latex', '\\mykeys{' .. text .. '}')
end

local function menuer_latex(el)
  local content = pandoc.utils.stringify(el.content)
  return pandoc.RawInline('latex', '\\menu{' .. content .. '}')
end

local function pather(el)
  local path
  if el.t == 'Code' then
    path = pandoc.utils.stringify(el.text)
  else
    path = pandoc.utils.stringify(el.content)
  end
  if not is_latex() or path == nil then return el end
  return pandoc.RawInline('latex', '\\path{' .. path .. '}')
end

local function keyworder(el)
  if not is_latex() then return el end
  local content = pandoc.utils.stringify(el.content)
  return pandoc.RawInline('latex', '\\keyword{' .. content .. '}')
end

local function unicoder(el)
  if not is_latex() then return el end
  local text = pandoc.utils.stringify(el.content)
  return pandoc.RawInline('latex', '\\unicoder{' .. text .. '}')
end

local function hashrefer(el)
  local text = pandoc.utils.stringify(el.content)
  local cap = el.classes:includes('Hashref') or el.classes:includes('Href')
  if not is_latex() then return el end
  -- capitalized typed refs ([Fig:x]{.hashref}) mean "capitalize the name":
  -- labels are lowercase; the capitalization belongs to \Cref
  local prefix, rest = text:match('^(%u%l*):(.+)$')
  if prefix and (prefix == 'Fig' or prefix == 'Tbl' or prefix == 'Eq'
      or prefix == 'Sec' or prefix == 'Lst') then
    text = prefix:lower() .. ':' .. rest
    cap = true
  end
  if cap then
    return pandoc.RawInline('latex', '\\Cref{' .. text .. '}')
  end
  return pandoc.RawInline('latex', '\\cref{' .. text .. '}')
end

local function linerefer(el)
  if not is_latex() then return el end
  local text = pandoc.utils.stringify(el.content)
  return pandoc.RawInline('latex', '\\lref{' .. text .. '}')
end

local function labeler(el)
  if not is_latex() then return el end
  local text = pandoc.utils.stringify(el.content)
  if el.classes:includes('component') then
    return pandoc.RawInline('latex', '\\label[componentitem]{' .. text .. '}')
  end
  return pandoc.RawInline('latex', '\\label{' .. text .. '}')
end

local function plainciter(el)
  if not is_latex() then return el end
  local text = pandoc.utils.stringify(el.content or '')
  local pre = el.attr.attributes['pre'] or ''
  local post = el.attr.attributes['post'] or ''
  local postpost = el.attr.attributes['postpost']
  if postpost then postpost = ', ' .. postpost else postpost = '' end
  return pandoc.RawInline('latex',
    '{\\textcite[{' .. pre .. '}][{' .. post .. '}]{' .. text .. '}' .. postpost .. '}')
end

-- Web-pipeline bibliography spans: [key]{.cite}, [key|note]{.cite},
-- [k1,k2]{.cite}. The homepage filter turns these into Django {% cite %}
-- tags; for print they map to biblatex (\textcite when .plain or
-- .no-parentheses requests no parentheses).
local function spanciter(el)
  if not is_latex() then return el end
  local text = pandoc.utils.stringify(el.content or '')
  text = text:match('^%s*(.-)%s*$') or ''
  local note = ''
  local pipe_pos = text:find('|')
  if pipe_pos then
    note = text:sub(pipe_pos + 1):match('^%s*(.-)%s*$') or ''
    text = text:sub(1, pipe_pos - 1):match('^%s*(.-)%s*$') or ''
  end
  local keys = text:gsub('%s*,%s*', ',')
  local cmd = '\\autocite'
  if el.classes:includes('plain') or el.classes:includes('no-parentheses') then
    cmd = '\\textcite'
  end
  return pandoc.RawInline('latex', cmd .. '[{' .. note .. '}]{' .. keys .. '}')
end

-- Index entries: \myindex (prose) and \indexc (code), with the ancestor's
-- special-class vocabulary kept verbatim so existing sources port cleanly.
local indexer_special = {
  'cop', 'ccon', 'cfun', 'ctype', 'cmacro', 'cheader', 'cstruct',
  'myriocon', 'myrioheader', 'myriofun', 'myriotype', 'myriostruct',
  'myriomacro', 'tcon', 'ttype', 'tmacro', 'tstruct', 'theader', 'tfun',
  'ucon', 'utype', 'umacro', 'ustruct', 'uheader',
  'ufunl0', 'ufunl1', 'ufunl2', 'ufunl3', 'ufunl4', 'ufunl5', 'ufunl6',
  'ufunl7', 'ufunl8', 'matlab', 'cqual', 'cspec', 'ufun', 'linuxheader',
  'posixfun',
}

local function indexer(el)
  if not FORMAT:match 'latex' then
    return pandoc.RawInline(FORMAT, '')
  end
  local ss, fun, lab, post, under, show = '[]', '[]', '[]', '[]', '[]', '[]'
  local primary, lang = '', ''
  local code = false
  local function has_special()
    for _, item in ipairs(indexer_special) do
      if el.classes:includes(item) then return true end
    end
    return false
  end
  if el.classes:includes('cfun') or el.classes:includes('myriofun')
      or el.classes:includes('ufun') then
    el.classes:insert('function')
  else
    for i = 0, 8 do
      if el.classes:includes('ufunl' .. i) then
        el.classes:insert('function')
        break
      end
    end
  end
  if has_special() or el.classes:includes('c') or el.classes:includes('matlab')
      or el.classes:includes('bash') or el.classes:includes('function') then
    el.classes:insert('code')
  end
  if has_special() and not el.classes:includes('matlab')
      and not el.classes:includes('bash') then
    el.classes:insert('c')
  end
  if el.classes:includes('start') then
    ss = '[start]'
  elseif el.classes:includes('stop') then
    ss = '[stop]'
  end
  if el.classes:includes('function') then fun = '[true]' end
  if el.attr.attributes['under'] then
    under = '[' .. el.attr.attributes['under'] .. ']'
  end
  if el.classes:includes('lab') then lab = '[L]' end
  if el.classes:includes('primary') or el.classes:includes('bold') then
    primary = '*'
  end
  if el.classes:includes('code') or el.classes:includes('c')
      or el.classes:includes('matlab') or el.classes:includes('bash') then
    code = true
  end
  if el.classes:includes('c') then
    lang = 'c'
  elseif el.classes:includes('matlab') then
    lang = 'matlab'
  elseif el.classes:includes('bash') then
    lang = 'bash'
  end
  for _, posti in ipairs(indexer_special) do
    if el.classes:includes(posti) then
      post = '[' .. posti .. ']'
    end
  end
  if el.attr.attributes['show'] then
    show = '[' .. el.attr.attributes['show'] .. ']'
  end
  local content = pandoc.utils.stringify(el.content)
  -- code index entries carry TeX specials (%, #, &, _): escape or the
  -- emitted argument swallows its own closing brace / breaks on .ind re-read
  content = content:gsub('([%%#&_])', '\\%1')
  if not code then
    return pandoc.RawInline('latex',
      '\\myindex' .. primary .. ss .. lab .. show .. under .. '{' .. content .. '}')
  end
  return pandoc.RawInline('latex',
    '\\indexc' .. primary .. ss .. lab .. post .. fun .. under
    .. '{' .. lang .. '}{' .. content .. '}')
end

local function mathspaner(el)
  if not is_latex() then return el end
  if el.content[1].mathtype == 'InlineMath' then
    return pandoc.RawInline('tex', '$' .. el.content[1].text .. '$')
  end
  local identifier = el.identifier or ''
  local content = el.content[1].text or ''
  return pandoc.RawInline('latex',
    '\n\\begin{align*}' .. content
    .. '\\numberthis \\label{' .. identifier .. '}\n\\end{align*}\n')
end

-- Citations ------------------------------------------------------------

citer = function(el)
  if not is_latex() then return el end
  local citeraw = '\\autocite['
  for i, c in ipairs(el.citations) do
    local citekey = c.id
    local citesuffix = pandoc.utils.stringify(c.suffix)
    citesuffix = string.gsub(citesuffix, ',', '', 1)
    if not citesuffix then citesuffix = '' end
    if i == 1 then
      citeraw = citeraw .. citesuffix .. ']{' .. citekey
    else
      citeraw = citeraw .. ',' .. citekey
    end
  end
  return pandoc.RawInline('latex', citeraw .. '}')
end

pandoccrossrefer = function(el)
  if not is_latex() then return el end
  local citeids = ''
  for index, value in ipairs(el.citations) do
    citeids = citeids .. value.id
    if index ~= #el.citations then citeids = citeids .. ',' end
  end
  local cref = '\\cref{'
  if citeids:sub(1, 1):upper() == citeids:sub(1, 1) then
    cref = '\\Cref{'
  end
  local citeids_lower = citeids:sub(1, 1):lower() .. citeids:sub(2)
  return pandoc.RawInline('latex', cref .. citeids_lower .. '}')
end

-- URLs ------------------------------------------------------------------

local function myurler(el)
  if not is_latex() then return el end
  local url = pandoc.utils.stringify(el.target)
  local hash = el.attr.attributes['h'] or el.attr.attributes['hash'] or ''
  local punctuation = el.attr.attributes['punctuation'] or ''
  local safety = el.attr.attributes['safe'] or ''
  local noid = ''
  if el.classes:includes('noid') or el.classes:includes('star') then
    noid = '*'
  end
  if not el.classes:includes('inline') then
    if el.classes:includes('bottom') then
      return pandoc.RawInline('latex',
        '\\myurlbottom' .. noid .. '[' .. punctuation .. '][' .. safety .. ']{'
        .. url .. '}{' .. hash .. '}')
    end
    return pandoc.RawInline('latex',
      '\\myurl' .. noid .. '[' .. punctuation .. '][' .. safety .. ']{'
      .. url .. '}{' .. hash .. '}')
  end
  return pandoc.RawInline('latex',
    '\\myurlinline' .. noid .. '{' .. url .. '}{' .. hash .. '}')
end

-- Code ------------------------------------------------------------------

local function code_shorthand(el)
  if el.classes:includes('py') then
    el.classes[#el.classes + 1] = 'python'
  end
  return el
end

-- Pygments has no lexer for some language tags authors use; map them to the
-- closest lexer minted/pygments knows so the print build doesn't abort with
-- "Pygments lexer ... is unknown". (Mirrors the migrate step, which already
-- rewrites inline \mintinline{arm} -> nasm.)
local lexer_alias = { arm = 'nasm' }

coder_latex = function(el)
  local language
  if not isempty(el.classes) then
    language = el.classes[1]
  else
    language = 'text'
  end
  language = lexer_alias[language] or language
  if el.t == 'CodeBlock' then
    local content = pandoc.utils.stringify(el.text)
    local samepage = el.classes:includes('nosamepage') and '' or ',samepage'
    local linenos = el.classes:includes('linenos') and ',linenos' or ''
    return pandoc.RawBlock('latex',
      '\\begin{mintedwrapper}\\nointerlineskip\\nointerlineskip\\begin{minted}[autogobble'
      .. samepage .. linenos .. ']{' .. language .. '}\n'
      .. content .. '\n\\end{minted}\n\\end{mintedwrapper}\n')
  elseif el.t == 'Code' then
    local content = pandoc.utils.stringify(el.text)
    -- the delimiter must not occur in the content (code spans can print `|`)
    for delim in string.gmatch('|!=+^~;?', '.') do
      if not content:find(delim, 1, true) then
        return pandoc.RawInline('latex',
          '\\mintinline{' .. language .. '}' .. delim .. content .. delim)
      end
    end
    return pandoc.RawInline('latex',
      '\\mintinline{' .. language .. '}{' .. content .. '}')
  end
  return el
end

-- Numbered div environments ---------------------------------------------

local function infoboxer(el)
  local content = walk_to_latex(el)
  local title = el.attr.attributes['title']
  local identifier = el.identifier
  if not is_latex() then return el end
  if title == nil then title = '{}' else title = '{' .. title .. '}' end
  if identifier == nil or identifier == '' then
    identifier = ''
  else
    identifier = '[label=' .. el.identifier .. ']'
  end
  return pandoc.RawBlock('latex',
    '\\begin{infobox}' .. identifier .. title .. '\n' .. content .. '\n\\end{infobox}')
end

-- A ::: {.freadinglist} div is a comma-separated list of cited further-reading
-- items ([key]{.plaincite ...} spans). The profile's \freadinglist macro wraps
-- them in a numbered "Further Reading" infobox via \docsvlist, so route the
-- walked content (plaincite already \textcite, each brace-grouped so its inner
-- commas don't split the list) through the macro — matching raw \freadinglist{}
-- blocks already in the source.
local function freadinglister(el)
  if not is_latex() then return el end
  local content = walk_to_latex(el):gsub('%s+$', '')
  local identifier = ''
  if el.identifier ~= nil and el.identifier ~= '' then
    identifier = '[' .. el.identifier .. ']'
  end
  return pandoc.RawBlock('latex',
    '\\freadinglist' .. identifier .. '{' .. content .. '}')
end

-- pandoc-crossref reference prefix per environment; a div whose id lacks
-- the prefix (e.g. {#magnitude-criterion .definition} referenced as
-- def:magnitude-criterion) needs the prefixed label emitted too.
local crossref_prefix = {
  definition = 'def', theorem = 'thm', lemma = 'lem',
  corollary = 'cor', proposition = 'prp',
}

local function typed_labels(envtype, identifier)
  if identifier == nil or identifier == '' then return '' end
  local prefix = crossref_prefix[envtype]
  if not prefix or identifier:match('^%a+:') then
    return ''  -- already prefixed, or no convention
  end
  return '\\label{' .. prefix .. ':' .. identifier .. '}'
end

local function theoremer(el)
  local content = walk_to_latex(el)
  local title = el.attr.attributes['title'] or ''
  local identifier = el.identifier or ''
  if not is_latex() then return el end
  local envtype
  if el.classes:includes('theorem') then
    envtype = 'theorem'
  elseif el.classes:includes('definition') then
    envtype = 'definition'
  elseif el.classes:includes('lemma') then
    envtype = 'lemma'
  elseif el.classes:includes('corollary') then
    envtype = 'corollary'
  elseif el.classes:includes('proposition') then
    envtype = 'proposition'
  end
  return pandoc.RawBlock('latex',
    '\\begin{' .. envtype .. '}{' .. title .. '}{' .. identifier .. '}\n'
    .. typed_labels(envtype, identifier)
    .. content .. '\n\\end{' .. envtype .. '}\n')
end

local function definitioner(el)
  local content = walk_to_latex(el)
  local title = el.attr.attributes['title'] or ''
  local identifier = el.identifier or ''
  if not is_latex() then return el end
  return pandoc.RawBlock('latex',
    '\\begin{definition}{' .. title .. '}{' .. identifier .. '}\n'
    .. typed_labels('definition', identifier)
    .. content .. '\n\\end{definition}\n')
end

local function exercise_solution(el)
  local content = delimiter_dollar(walk_to_latex(el))
  if el.classes:includes('lab') then
    return pandoc.RawBlock('latex',
      '\\end{labexercise}\n\\begin{labsolution}\n' .. content .. '\n\\end{labsolution}')
  end
  return pandoc.RawBlock('latex',
    '\\end{exercise}\n\\begin{solution}\n' .. content .. '\n\\end{solution}')
end

local function exerciser(el)
  if not is_latex() then return el end
  local el_walked = pandoc.walk_block(el, {
    Div = function(inner)
      if inner.classes:includes('exercise-solution') or inner.classes:includes('solution') then
        return exercise_solution(inner)
      end
      return inner
    end,
    Header = function(inner) -- demote and unnumber headers inside exercises
      inner.level = inner.level + 2
      inner.classes[#inner.classes + 1] = 'unnumbered'
      return inner
    end,
  })
  el_walked = pandoc.walk_block(el_walked, interior_filter)
  el_walked = pandoc.walk_block(el_walked, image_filter)
  local content_doc = pandoc.Pandoc(el_walked.content)
  local content = delimiter_dollar(pandoc.write(content_doc, 'latex'))
  local hash = el.attr.attributes['h'] or el.attr.attributes['hash']
  if not hash then
    -- Content repos use #exe:... identifiers rather than rtc hashes.
    hash = el.identifier or ''
  end
  local env = el.classes:includes('lab') and 'labexercise' or 'exercise'
  -- labels for the id and hash so hashrefs to exercises resolve
  local labels = ''
  local id = el.identifier or ''
  if id ~= '' then labels = labels .. '\\label{' .. id .. '}' end
  if hash ~= '' and hash ~= id then
    labels = labels .. '\\label{' .. hash .. '}'
  end
  return pandoc.RawBlock('latex',
    '\\begin{' .. env .. '}[ID=' .. hash .. ',hash=' .. hash .. ']\n'
    .. labels .. '\n' .. content)
end

local function example_solution(el)
  local content = delimiter_dollar(walk_to_latex(el))
  if el.classes:includes('example-solution') then
    return pandoc.RawBlock('latex', '\\tcblower\n' .. content)
  end
  return pandoc.RawBlock('latex', content)
end

local function exampler(el)
  if not is_latex() then return el end
  local identifier = el.identifier or ''
  local el_walked = pandoc.walk_block(el, {
    Div = function(inner) return example_solution(inner) end,
  })
  el_walked = pandoc.walk_block(el_walked, interior_filter)
  el_walked = pandoc.walk_block(el_walked, image_filter)
  local content_doc = pandoc.Pandoc(el_walked.content)
  local content = delimiter_dollar(pandoc.write(content_doc, 'latex'))
  local hash = el.attr.attributes['h'] or el.attr.attributes['hash'] or identifier
  return pandoc.RawBlock('latex',
    '\\begin{myexample}[]{' .. identifier .. '}{' .. hash .. '}\n\\noindent '
    .. content .. '\n\\end{myexample}')
end

local function listinger(el)
  local code_block = el.content[1]
  local id = pandoc.utils.stringify(el.identifier)
  local caption = el.attr.attributes['caption']
  if not is_latex() then return el end
  if caption then
    local caption_pre = pandoc.read(caption, 'markdown').blocks[1]
    -- listing captions float (moving argument): keep inline code out of verbatim
    caption_pre = pandoc.walk_block(caption_pre, { Code = moving_code_to_latex })
    local caption_walked = pandoc.walk_block(caption_pre, interior_filter)
    local caption_doc = pandoc.Pandoc(caption_walked)
    caption = pandoc.write(caption_doc, 'latex')
  else
    caption = ''
  end
  local content = pandoc.utils.stringify(code_block.text)
  local language = code_block.classes and code_block.classes[1] or ''
  local mynewminted
  if language == 'c' then
    local long = el.classes:includes('long')
    local texcomments = el.classes:includes('texcomments')
    if long and texcomments then
      mynewminted = 'clistinglongtexcomments'
    elseif el.classes:includes('linenos') then
      mynewminted = long and 'clistinglonglinenos' or 'clistinglinenos'
    elseif long then
      mynewminted = 'clistinglong'
    elseif texcomments then
      mynewminted = 'clistingtexcomments'
    else
      mynewminted = 'clisting'
    end
  elseif language == 'arm' then
    mynewminted = 'armlisting'
  elseif language == 'python' or language == 'py' then
    mynewminted = 'pythonlisting'
  else
    mynewminted = 'textlisting'
  end
  local position
  if el.classes:includes('nofloat') then
    position = 'nofloat'
  else
    position = el.attr.attributes['position'] or 'htbp'
  end
  local ifsolution_beg, ifsolution_end = '', ''
  if el.classes:includes('solutions-only') then
    ifsolution_beg = '\n\\ifdefined\\issolution\n'
    ifsolution_end = '\n\\fi\n'
  end
  if position == 'nofloat' then
    return pandoc.RawInline('latex',
      ifsolution_beg .. '\\begin{listingsbox}{' .. mynewminted .. '}{' .. caption
      .. '}{' .. id .. '}\n' .. content .. '\n\\end{listingsbox}' .. ifsolution_end)
  end
  return pandoc.RawInline('latex',
    ifsolution_beg .. '\\begin{listingsboxfloat}{' .. mynewminted .. '}{' .. caption
    .. '}{' .. id .. '}{' .. position .. '}\n' .. content
    .. '\n\\end{listingsboxfloat}' .. ifsolution_end)
end

local function outputer(el)
  if not is_latex() then return el end
  if el.classes:includes('output') and el.classes:includes('execute_result') then
    local content = walk_to_latex(el)
    return pandoc.RawBlock('latex',
      '\\begin{formattedoutput}\n' .. content .. '\n\\end{formattedoutput}\n')
  end
  return el
end

local function only_htmler(el)
  if FORMAT:match 'html' then return el end
  return pandoc.RawBlock(FORMAT, '')
end

-- Figures ----------------------------------------------------------------

-- A standalone/pgf/subfigure src written in the MEDIA hierarchy
-- (notebooks/<slug>/<name>) is a web-side path. In print it is handed to
-- kpathsea, which searches TEXINPUTS (the chapter dirs + assets) for that
-- literal relative path and never finds it — silently, so the figure is just
-- absent from the PDF (\includestandalone is \providecommand'd to
-- \includegraphics, so most failures raise no distinct error). The web path
-- resolves such refs by BASENAME against the source tree; do the same, which
-- is all TEXINPUTS needs.
--
-- Conservative on purpose: rewrite only when the file really is in this
-- chapter, so srcs that already resolve (rtc, math) are untouched. Task #587.
local function resolve_media_src(src)
  local media_rel = src:match('^notebooks/[^/]+/(.*)$')
  local chapter_dir = os.getenv('PARODY_CHAPTER_DIR')
  if not (media_rel and chapter_dir) then return src end
  -- '' first: some refs already carry their extension (…/sources-real.pdf),
  -- and appending another would find nothing.
  for _, ext in ipairs({'', '.pdf', '.tex', '.pgf'}) do
    -- io.open, not file_exists(): that helper is defined further down in the
    -- notebook-includes section and is still nil at this point.
    local f = io.open(chapter_dir .. '/' .. media_rel .. ext, 'r')
    if f then
      f:close()
      return media_rel
    end
  end
  -- Left as-is rather than dropped: it might still resolve through another
  -- TEXINPUTS entry (assets/), and removing a figure is worse than keeping a
  -- suspect one. But say so — this shape silently produced ~70 missing
  -- figures in the electronics book before #587.
  io.stderr:write(
    '⚠️  standalone figure src is a media path with no file in this chapter '
    .. '(may be missing from the PDF): ' .. src .. '\n')
  return src
end

function imager(el)
  if not is_latex() then return el end
  -- Notebook print builds (PARODY_PROJECT_DIR set): map media-hierarchy and
  -- chapter-relative srcs to source-tree files, converting svg as needed.
  -- pgf/standalone sources are LaTeX inputs with their own commands and
  -- src conventions (extensionless); they never go through asset resolution.
  local is_pgf_or_standalone = el.classes:includes('standalone')
    or el.classes:includes('pgf') or el.src:match('%.pgf$')
  local notebook_ctx = os.getenv('PARODY_PROJECT_DIR') ~= nil
  if notebook_ctx and is_pgf_or_standalone then
    el.src = resolve_media_src(el.src)
  end
  if notebook_ctx and not is_pgf_or_standalone then
    local resolved = resolve_asset(el.src, nil)
    if resolved == nil then
      return pandoc.RawInline('latex', '')
    end
    el.src = resolved
  end
  local width = el.attr.attributes['figwidth']
  if width == nil then
    -- notebook figures: natural size capped at the text width
    width = notebook_ctx and 'width=\\maxwidth' or ''
  else
    width = 'width=' .. pandoc.utils.stringify(width)
  end
  local graphics_command
  if el.classes:includes('standalone') then
    graphics_command = '\\noindent\\includestandalone[' .. width .. ']{' .. el.src .. '}'
  elseif el.classes:includes('pgf') or el.src:match('%.pgf$') then
    -- \inputpgf appends .pgf; rtc srcs omit the extension, math srcs carry
    -- it (and sometimes omit the class — includegraphics can't load .pgf)
    graphics_command = '\\noindent\\inputpgf{' .. el.src:gsub('%.pgf$', '') .. '}'
  else
    graphics_command = '\\noindent\\includegraphics[' .. width .. ']{' .. el.src .. '}'
  end
  return pandoc.RawInline('latex', graphics_command)
end

local figcaption_keys = {
  'color', 'format', 'credit', 'permission', 'reprint', 'territory',
  'language', 'edition', 'fair', 'publicity', 'size', 'permissioncomment',
  'layoutcomment',
}

function figurer(el, nofloat)
  if not is_latex() then return el end
  local image = el.content[1] and el.content[1].content and el.content[1].content[1]
  local el_walked = pandoc.walk_block(el, {
    Image = function(img) return imager(img) end,
  })
  local content_doc = pandoc.Pandoc(el_walked.content)
  local content = pandoc.write(content_doc, 'latex')
  local graphics_list_reset = '\\gdef\\graphicslist{}%\n'
  local fig_begin, fig_end
  if nofloat then
    fig_begin = '\\begin{figure}[H]%\n\\centering\n'
    fig_end = '\\end{figure}%\n\n'
  else
    local position = el.attr.attributes['position'] or 'H'
    fig_begin = '\\begin{figure}[' .. position .. ']\n\\centering\n'
    fig_end = '\\end{figure}\n'
  end
  local attributes = (image and image.attr and image.attr.attributes) or {}
  local options = '['
  local i = 0
  for key, value in pairs(attributes) do
    if has_value(figcaption_keys, key) then
      options = options .. (i == 0 and '' or ',') .. key .. '={' .. value .. '}'
      i = i + 1
    end
  end
  options = options .. ']'
  local caption = image and image.caption
  if caption == nil then
    caption = ''
  else
    caption = inlines_to_latex(caption)
  end
  -- A tbl:-prefixed identifier marks an image that is a *table* in the book's
  -- numbering (e.g. a rendered execution grid or instruction breakdown). Emit a
  -- genuine table float so it counts and captions as "Table N.M" (caption above,
  -- table convention), not a figure — even though the content is an image.
  if el.identifier:match('^[Tt]bl:') then
    return pandoc.RawInline('latex',
      graphics_list_reset .. '\\begin{table}[H]%\n'
      .. '\\tabcaption[][nofloat]{' .. el.identifier .. '}{' .. caption .. '}%\n'
      .. '\\centering\n' .. content .. '\n\\end{table}%\n\n')
  end
  -- Notebook sources use unprefixed figure ids (#foo) but reference them
  -- either way ([foo]{.hashref} -> \cref{foo} OR @fig:foo). Emit both the
  -- bare and fig:-prefixed labels so either resolves.
  local label = el.identifier
  local extra_label = ''
  if os.getenv('PARODY_PROJECT_DIR') and label ~= ''
      and not label:match('^%a+:') then
    extra_label = '\\label{' .. label .. '}'
    label = 'fig:' .. label
  end
  local fig_tex = graphics_list_reset .. fig_begin .. content
    .. '\n\\figcaption' .. options .. '[]{' .. label .. '}{' .. caption .. '}\n'
    .. extra_label .. fig_end
  return pandoc.RawInline('latex', fig_tex)
end

local function figurediver(el)
  -- Subfigure Divs: ::: {#fig:foo .figure .subfigures rows=2}
  if not FORMAT:match 'latex' then return el end
  local rows = tonumber(el.attr.attributes['rows'] or 1)
  local last_el = el.content[#el.content].content[1]
  local n_subfigures, caption
  if last_el.t == 'Image' then
    n_subfigures = #el.content
    caption = pandoc.Para {}
  else
    n_subfigures = #el.content - 1
    -- a "(a) ... (b) ..." caption pandoc misread as a list would otherwise
    -- emit \figcaption{\begin{enumerate}...}, fatal in a moving argument
    caption = delist_caption(el.content[#el.content])
  end
  local subfigures = {}
  for i = 1, n_subfigures do
    subfigures[i] = el.content[i].content[1]
  end
  -- Subfigures default to native size; a div- or image-level scale=/width=
  -- opts a figure into scaling (e.g. third-party art too wide to sit side by
  -- side at 1:1 — a uniform scale= preserves the panels' relative sizes).
  local div_attrs = el.attr.attributes or {}
  local caps, srcs, labels, classes, sizes = {}, {}, {}, {}, {}
  for i = 1, #subfigures do
    local img = subfigures[i].t == 'Image' and subfigures[i] or subfigures[i].content[1]
    local cap = img.caption
    if cap == nil or isempty(cap) then
      caps[i] = ''
    else
      -- caption is an Inlines list; Pandoc(cap) would coerce each inline
      -- to its own block (a \par between every word, fatal inside
      -- \subcaptionbox)
      caps[i] = inlines_to_latex(cap)
    end
    srcs[i] = img.src or ''
    -- pandoc 3 puts ![cap](src){#id} 's id on the Figure block wrapper,
    -- not the inner Image; read the wrapper's id when the image's is empty
    labels[i] = img.identifier
    if (labels[i] == nil or labels[i] == '')
        and el.content[i].identifier then
      labels[i] = el.content[i].identifier
    end
    if labels[i] == nil or labels[i] == '' then
      labels[i] = 'fig:sub-' .. i
    end
    classes[i] = img.classes or {}
    local a = (img.attr and img.attr.attributes) or {}
    sizes[i] = { width = a['width'] or div_attrs['width'],
                 scale = a['scale'] or div_attrs['scale'] }
  end
  local fig_tex = '\\begin{figure}[H]\n\\centering\n'
  local cols = math.ceil(n_subfigures / rows)
  local current_row = 1
  fig_tex = fig_tex .. '% Row 1\n'
  for i = 1, #subfigures do
    if math.fmod(i - 1, cols) == 0 and i ~= 1 then
      current_row = current_row + 1
      fig_tex = fig_tex .. '\\\\\n% Row ' .. current_row .. '\n'
    end
    -- optional scale=/width= (native when neither is set)
    local w, s = sizes[i].width, sizes[i].scale
    local opt = ''
    if w and w ~= '' then opt = '[width=' .. w .. ']'
    elseif s and s ~= '' then opt = '[scale=' .. s .. ']' end
    local graphics_command
    -- Subfigures build their own graphics command instead of going through
    -- imager, so they need the same media-path resolution (#587).
    local src = os.getenv('PARODY_PROJECT_DIR') and resolve_media_src(srcs[i])
      or srcs[i]
    if classes[i]:includes('pgf') or src:match('%.pgf$') then
      local pgf = '\\inputpgf{' .. src:gsub('%.pgf$', '') .. '}'
      if w and w ~= '' then pgf = '\\resizebox{' .. w .. '}{!}{' .. pgf .. '}'
      elseif s and s ~= '' then pgf = '\\scalebox{' .. s .. '}{' .. pgf .. '}' end
      graphics_command = '\\noindent' .. pgf
    else
      graphics_command = '\\noindent\\includegraphics' .. opt .. '{' .. src .. '}'
    end
    local filler_after = ''
    if math.fmod(i, cols) == 0 then
      filler_after = '\\hspace*{\\fill}%\n'
    end
    -- Each subfigure keeps its NATIVE size (the art is drawn to fit the text
    -- measure at 1:1 — no scaling, so its internal fonts stay correct); the
    -- \hspace*{\fill}s distribute the row across the text width. Forcing a fixed
    -- 1/cols column instead made wide subfigures overflow the column (spilling
    -- into the margin or onto their neighbour).
    fig_tex = fig_tex .. '\\hspace*{\\fill}%\n'
      .. '\\subcaptionbox{' .. caps[i] .. '\\label{' .. labels[i] .. '}}\n'
      .. '{' .. graphics_command .. '}\n' .. filler_after
  end
  local caption_tex = pandoc.write(pandoc.Pandoc(caption), 'latex')
  -- carry rights/credit metadata (color, permission, permissioncomment, …) from
  -- the subfigures div onto its \figcaption, same as single figures (figurer)
  local sf_options, j = '[', 0
  for key, value in pairs(el.attr.attributes or {}) do
    if has_value(figcaption_keys, key) then
      sf_options = sf_options .. (j == 0 and '' or ',') .. key .. '={' .. value .. '}'
      j = j + 1
    end
  end
  sf_options = sf_options .. ']'
  fig_tex = fig_tex .. '\\figcaption' .. sf_options .. '{' .. el.identifier
    .. '}{' .. caption_tex .. '}\n' .. '\\end{figure}\n'
  return pandoc.RawBlock('latex', fig_tex)
end

local function table_to_tabular(tbl)
  -- pandoc's table writer emits a page-breaking longtable; for a \subcaptionbox
  -- we want a plain {tabular}. Rebuild it cell-by-cell from the AST.
  local ncol = #tbl.colspecs
  local function row_latex(row)
    local cells = {}
    for _, cell in ipairs(row.cells) do
      cells[#cells + 1] = (pandoc.write(pandoc.Pandoc(cell.contents), 'latex')
        :gsub('\n', ' '):gsub('%s+$', ''))
    end
    return table.concat(cells, ' & ')
  end
  local lines = {}
  for _, row in ipairs(tbl.head and tbl.head.rows or {}) do
    lines[#lines + 1] = row_latex(row)
  end
  for _, body in ipairs(tbl.bodies or {}) do
    for _, row in ipairs(body.body) do lines[#lines + 1] = row_latex(row) end
  end
  return '\\begin{tabular}{' .. string.rep('l', ncol) .. '}\n'
    .. table.concat(lines, ' \\\\\n') .. ' \\\\\n\\end{tabular}'
end

local function subtablesdiver(el)
  -- ::: {#tbl:main .subtables} of markdown tables (each with a sub-caption) →
  -- one \begin{table} of side-by-side \subcaptionbox{subcap}{tabular}, mirroring
  -- the print book's table-of-tables. The web build has its own .subtables path.
  if not FORMAT:match 'latex' then return el end
  local subs, caption = {}, pandoc.Para {}
  for _, block in ipairs(el.content) do
    if block.t == 'Table' then
      local subcap = block.caption and block.caption.long or {}
      subs[#subs + 1] = {
        cap = pandoc.write(pandoc.Pandoc(subcap), 'latex'):gsub('%s+$', ''),
        id = block.identifier or '',
        tabular = table_to_tabular(block),
      }
    elseif block.t ~= 'Para' or #block.content > 0 then
      caption = block
    end
  end
  -- table caption goes above (the original \tabcaption preceded the subtables)
  local tex = '\\begin{table}[htbp]\\centering\n\\tabcaption{'
    .. (el.identifier or '') .. '}{'
    .. pandoc.write(pandoc.Pandoc({caption}), 'latex'):gsub('%s+$', '')
    .. '}\n\\hfil\n'
  for _, s in ipairs(subs) do
    tex = tex .. '\\subcaptionbox{' .. s.cap .. '\\label{' .. s.id .. '}}{'
      .. s.tabular .. '}\n\\hfil\n'
  end
  tex = tex .. '\\end{table}\n'
  return pandoc.RawBlock('latex', tex)
end

local function algorithmer_latex(el)
  -- Figure whose image is a standalone .tex algorithm: splice in the body.
  -- The build converts from build/print/sections/<ch>/, so resolve the
  -- asset against the real chapter dir (PARODY_CHAPTER_DIR).
  local image = el.content[1].content[1]
  local src = image.src:gsub('%.tex$', '') .. '.tex'
  src = resolve_asset(src, nil) or src
  local f = io.open(src, 'r')
  if not f then
    error('algorithm source not found: ' .. src)
  end
  local content = f:read('*all')
  f:close()
  content = content:gsub('.*\\begin{document}', ''):gsub('\\end{document}.*', '')
  local caption = image.caption
  if caption == nil then
    caption = ''
  else
    caption = inlines_to_latex(caption)
  end
  local id = el.identifier or ''
  local width = image.attr.attributes['width'] or '\\linewidth'
  return pandoc.RawBlock('latex',
    '\\begin{algorithmcenter}\n\\begin{minipage}{' .. width
    .. '}\n\\begin{algorithm}[H]\n'
    .. '\\algcaption{' .. id .. '}{' .. caption .. '}\n' .. content
    .. '\\end{algorithm}\n\\end{minipage}\n\\end{algorithmcenter}')
end

-- Tables -----------------------------------------------------------------

local function get_table_id(el)
  -- Pandoc assigns a caption's trailing {#id} to the Table's own identifier;
  -- prefer that, falling back to scraping a literal {#id} out of the caption
  -- text for inputs where it survives there instead.
  if el.t == 'Table' then
    if el.identifier ~= nil and el.identifier ~= '' then
      return el.identifier
    end
    el = pandoc.utils.to_simple_table(el)
  end
  local caption = pandoc.utils.stringify(el.caption)
  local id = string.match(caption, '%{.*%}$')
  if id == nil then id = '' end
  return string.sub(id, 3, -2)
end

-- ── Grouped-header tables ─────────────────────────────────────────────────
-- Raw-HTML tables tagged `grouped-header` carry colspan/rowspan headers and
-- `cmid`/`cmid-l`/`cmid-r` rule groups (e.g. tbl:steadystateerror). These can't
-- survive to_simple_table (it drops spans and rules), so render them straight
-- from the pandoc Table AST: \multicolumn column groups, \multirow flankers,
-- \cmidrule from the cmid classes, and 2-line \makecell wrapping of wide
-- headers so they don't overrun the text width.

local function cell_to_latex(cell)
  return (pandoc.write(pandoc.Pandoc(cell.contents), 'latex')
    :gsub('\n', ' '):gsub('%s+$', ''))
end

-- split latex on spaces outside $...$ and {...}
local function top_level_words(s)
  local words, buf, depth, math = {}, {}, 0, false
  for i = 1, #s do
    local ch = s:sub(i, i)
    if ch == '$' then math = not math
    elseif ch == '{' then depth = depth + 1
    elseif ch == '}' then depth = depth - 1 end
    if ch == ' ' and depth == 0 and not math then
      words[#words + 1] = table.concat(buf); buf = {}
    else
      buf[#buf + 1] = ch
    end
  end
  words[#words + 1] = table.concat(buf)
  return words
end

-- wrap a wide multi-word header into two balanced \makecell lines
local function wrap_header(s)
  local words = top_level_words(s)
  if #words < 2 or #s < 11 then return s end  -- leave short headers on one line
  local len, split = 0, 1
  for i = 1, #words - 1 do
    len = len + #words[i] + 1; split = i
    if len >= #s / 2 then break end
  end
  local a, b = {}, {}
  for i = 1, split do a[#a + 1] = words[i] end
  for i = split + 1, #words do b[#b + 1] = words[i] end
  return '\\makecell{' .. table.concat(a, ' ') .. '\\\\' .. table.concat(b, ' ') .. '}'
end

local function is_grouped_header(el)
  if el.attr.classes:includes('grouped-header') then return true end
  for _, row in ipairs(el.head.rows) do
    for _, cell in ipairs(row.cells) do
      if cell.col_span > 1 or cell.row_span > 1 then return true end
    end
  end
  return false
end

-- Header rows -> LaTeX, with \multicolumn/\multirow and \cmidrule per cmid
-- group. A rowspan cell's rule is deferred to the row where its span ends.
local function grouped_header_rows(head_rows, ncols)
  local occupied, deferred, out = {}, {}, {}
  for ri, row in ipairs(head_rows) do
    local cells, col, group_start = {}, 1, nil
    for _, cell in ipairs(row.cells) do
      while (occupied[col] or 0) > 0 do
        occupied[col] = occupied[col] - 1; cells[#cells + 1] = ''; col = col + 1
      end
      local span, a = cell.col_span, col
      local b = col + span - 1
      local cls = cell.attr.classes
      if cls:includes('cmid-l') or (cls:includes('cmid') and group_start == nil) then
        group_start = a
      end
      if cls:includes('cmid-r') and group_start ~= nil then
        local after = ri + cell.row_span - 1
        -- (r) for a group flush to the left edge, (lr) for interior groups, so
        -- adjacent rules don't touch and the leftmost reaches the margin.
        local trim = (group_start > 1 and 'l' or '') .. 'r'
        deferred[after] = deferred[after] or {}
        deferred[after][#deferred[after] + 1] =
          '\\cmidrule(' .. trim .. '){' .. group_start .. '-' .. b .. '}'
        group_start = nil
      end
      local content = wrap_header(cell_to_latex(cell))
      if cell.row_span > 1 then
        content = '\\multirow{' .. cell.row_span .. '}{*}{' .. content .. '}'
        for k = a, b do occupied[k] = cell.row_span - 1 end
      end
      if span > 1 then content = '\\multicolumn{' .. span .. '}{c}{' .. content .. '}' end
      cells[#cells + 1] = content
      col = col + span
    end
    while col <= ncols do
      if (occupied[col] or 0) > 0 then occupied[col] = occupied[col] - 1 end
      cells[#cells + 1] = ''; col = col + 1
    end
    out[#out + 1] = table.concat(cells, ' & ') .. ' \\\\'
    if deferred[ri] then out[#out + 1] = table.concat(deferred[ri], ' ') end
  end
  return table.concat(out, '\n')
end

local function grouped_body_rows(bodies, strut)
  local out = {}
  for _, body in ipairs(bodies) do
    for _, row in ipairs(body.body) do
      local cells = {}
      for _, cell in ipairs(row.cells) do
        local content = cell_to_latex(cell)
        if cell.col_span > 1 then
          content = '\\multicolumn{' .. cell.col_span .. '}{c}{' .. content .. '}'
        end
        cells[#cells + 1] = content
      end
      out[#out + 1] = strut .. table.concat(cells, ' & ') .. ' \\\\'
    end
  end
  return table.concat(out, '\n')
end

local function grouped_table_latex(el, identifier)
  local ncols = 0
  for _, cell in ipairs(el.head.rows[1].cells) do ncols = ncols + cell.col_span end
  local spec = {}
  for c = 1, ncols do spec[c] = (c == 1) and 'l' or 'c' end
  local strut = '\\rule[-1ex]{0pt}{3.2ex}'
  local tabular = '\\begin{tabular}{@{}' .. table.concat(spec) .. '@{}}\n\\toprule\n'
    .. grouped_header_rows(el.head.rows, ncols) .. '\n'
    .. grouped_body_rows(el.bodies, strut) .. '\n\\bottomrule\n\\end{tabular}'
  local caption_text = pandoc.write(pandoc.Pandoc(el.caption.long), 'latex')
    :gsub('\n', ' '):gsub('%s+$', ''):gsub('%s*{#.*}$', '')
  local caption_latex = ''
  if #caption_text > 0 or identifier ~= '' then
    caption_latex = '\\tabcaption[][nofloat]{' .. identifier .. '}{' .. caption_text .. '}\n'
  end
  return pandoc.RawBlock('latex',
    '\\begin{table}\n' .. caption_latex .. '\\centering\n' .. tabular .. '\n\\end{table}')
end

local function tabler_latex(el)
  local identifier = get_table_id(el)
  if is_grouped_header(el) then return grouped_table_latex(el, identifier) end
  local simple = pandoc.utils.to_simple_table(el)

  local function render_row(row)
    local cells = {}
    for _, cell in ipairs(row) do
      local doc = pandoc.Pandoc(cell)
      cells[#cells + 1] = (pandoc.write(doc, 'latex'):gsub('\n$', ''))
    end
    return table.concat(cells, ' & ') .. ' \\\\'
  end

  local function render_tabular(header, rows)
    if rows == nil or #rows == 0 then return '' end
    local lines = { '\\toprule', render_row(header), '\\midrule' }
    for _, row in ipairs(rows) do
      lines[#lines + 1] = render_row(row)
    end
    lines[#lines + 1] = '\\bottomrule'
    return '\\begin{tabular}{' .. string.rep('l', #rows[1]) .. '}\n'
      .. table.concat(lines, '\n') .. '\n\\end{tabular}'
  end

  -- Render caption inlines to LaTeX, not stringify: stringify flattens Math and
  -- markup to plain text, so \(x\) math in a caption would vanish. Unwrap the
  -- newlines pandoc.write inserts so the \tabcaption argument stays one line.
  local caption_text = pandoc.write(
    pandoc.Pandoc({ pandoc.Plain(simple.caption) }), 'latex')
  caption_text = caption_text:gsub('\n', ' '):gsub('%s+$', '')
  caption_text = string.gsub(caption_text, '%s*{#.*}$', '')
  local content_latex = render_tabular(simple.headers, simple.rows)
  if string.len(caption_text) > 0 or identifier ~= '' then
    local caption_latex = '\\tabcaption[][nofloat]{' .. identifier .. '}{'
      .. caption_text .. '}'
    return pandoc.RawBlock('latex',
      '\\begin{table}\n' .. caption_latex .. '\n' .. content_latex .. '\n\\end{table}')
  end
  return pandoc.RawBlock('latex', content_latex)
end

-- Notebook includes + asset resolution --------------------------------------
--
-- Notebook content repos inline executed jupytext output via
-- ```{.include-py path="x.py"} and reference figures with bare names or
-- media-hierarchy paths (notebooks/<slug>/<chapter>/...). The PDF build
-- (writers/latex.py) sets PARODY_PROJECT_DIR / PARODY_CHAPTER_DIR /
-- PARODY_SVG_CACHE so these can be resolved against the SOURCE tree (pandoc
-- runs from the build dir). Without those env vars (rtc-style projects)
-- everything below is inert.

local function read_file(path)
  local f = io.open(path, 'r')
  if not f then return nil end
  local content = f:read('*all')
  f:close()
  return content
end

local function file_exists(path)
  local f = io.open(path, 'r')
  if f then f:close(); return true end
  return false
end

-- Convert an .svg to .pdf in the build's svg cache; returns the pdf path.
local function svg_to_pdf(svg_path)
  local cache = os.getenv('PARODY_SVG_CACHE')
  if not cache then return svg_path end
  local key = svg_path:gsub('[/\\]', '__')
  local out = cache .. '/' .. key:gsub('%.svg$', '') .. '.pdf'
  if not file_exists(out) then
    os.execute('mkdir -p "' .. cache .. '"')
    local ok = os.execute('rsvg-convert -f pdf -o "' .. out .. '" "' .. svg_path
      .. '" 2>/dev/null')
    if not ok and not file_exists(out) then
      ok = os.execute('inkscape "' .. svg_path .. '" --export-type=pdf '
        .. '--export-filename="' .. out .. '" 2>/dev/null')
    end
    if not file_exists(out) then
      io.stderr:write('⚠️  svg conversion failed (need rsvg-convert or '
        .. 'inkscape): ' .. svg_path .. '\n')
      return svg_path
    end
  end
  return out
end

-- Resolve an image src to an absolute file path. base_stem is the include's
-- file stem (jupytext outputs live in <stem>_files/).
resolve_asset = function(src, base_stem)
  local project_dir = os.getenv('PARODY_PROJECT_DIR')
  local chapter_dir = os.getenv('PARODY_CHAPTER_DIR')
  local resolved = nil
  local media_rel = src:match('^notebooks/[^/]+/(.*)$')
  if media_rel and project_dir then
    -- media-hierarchy path: maps directly onto the source layout
    local candidate = project_dir .. '/' .. media_rel
    if file_exists(candidate) then
      resolved = candidate
    elseif chapter_dir then
      -- ...except where the book keeps the file beside its section instead of
      -- at the project root (electronics). The media path is flat, so the
      -- basename is what identifies it — the same rule the web staging uses.
      candidate = chapter_dir .. '/' .. media_rel
      if file_exists(candidate) then resolved = candidate end
    end
  elseif not src:match('^/') and chapter_dir then
    local candidates = {}
    if base_stem then
      candidates[#candidates + 1] = chapter_dir .. '/' .. base_stem .. '_files/' .. src
    end
    candidates[#candidates + 1] = chapter_dir .. '/' .. src
    for _, candidate in ipairs(candidates) do
      if file_exists(candidate) then resolved = candidate; break end
    end
  elseif src:match('^/') and file_exists(src) then
    resolved = src
  end
  if not resolved then
    if project_dir then
      io.stderr:write('⚠️  unresolved figure (omitting): ' .. src .. '\n')
      return nil
    end
    return src -- rtc projects: leave untouched
  end
  if resolved:match('%.svg$') then
    resolved = svg_to_pdf(resolved)
  end
  return resolved
end

-- Resolve srcs in a tree of parsed blocks (with include-stem context).
local function resolve_images(blocks, base_stem)
  local out = {}
  for _, b in ipairs(blocks) do
    local walked = pandoc.walk_block(b, {
      Image = function(img)
        local resolved = resolve_asset(img.src, base_stem)
        if resolved == nil then return {} end -- drop unresolvable image
        img.src = resolved
        return img
      end,
    })
    -- a bare top-level Image arrives wrapped in Para/Plain/Figure, so the
    -- child walk above covers it
    out[#out + 1] = walked
  end
  return out
end

-- Apply this filter's top-level handlers to freshly parsed blocks (returned
-- blocks are not re-walked by earlier passes in the filter chain).
local function latexify_blocks(blocks)
  local out = {}
  for _, b in ipairs(blocks) do
    local r
    if b.t == 'Figure' then
      r = Figure(b)
    elseif b.t == 'CodeBlock' then
      r = CodeBlock(b)
    elseif b.t == 'Table' then
      r = Table(b)
    elseif b.t == 'Header' then
      r = headerer_latex(b)
    elseif b.t == 'Div' then
      r = Div(b)
    else
      r = pandoc.walk_block(b, interior_filter)
    end
    if r == nil then r = b end
    if type(r) ~= 'table' or r.t then r = { r } end
    for _, item in ipairs(r) do
      if item.t and (item.t == 'RawInline' or item.t == 'Str'
          or item.t == 'Span') then
        item = pandoc.Plain { item }
      end
      out[#out + 1] = item
    end
  end
  return out
end

local function include_py_print(el)
  local path = el.attr.attributes['path']
  if not path then return el end
  local chapter_dir = os.getenv('PARODY_CHAPTER_DIR')
  local md_path = path:gsub('%.py$', '.md')
  local content = chapter_dir and read_file(chapter_dir .. '/' .. md_path)
    or read_file(md_path)
  if not content then
    io.stderr:write('⚠️  include-py: ' .. md_path .. ' not found\n')
    return {}
  end
  local base_stem = path:gsub('%.py$', ''):match('([^/]+)$')
  local parsed = pandoc.read(content, 'markdown-smart')
  local blocks = resolve_images(parsed.blocks, base_stem)
  return latexify_blocks(blocks)
end

local function include_code_print(el)
  local path = el.attr.attributes['path']
  if not path then return el end
  local chapter_dir = os.getenv('PARODY_CHAPTER_DIR')
  local content = chapter_dir and read_file(chapter_dir .. '/' .. path)
    or read_file(path)
  if not content then
    io.stderr:write('⚠️  include-code: ' .. path .. ' not found\n')
    return {}
  end
  local lang = ({ py = 'python', m = 'matlab', jl = 'julia', c = 'c' })
    [path:match('%.([A-Za-z]+)$') or ''] or 'text'
  return coder_latex(pandoc.CodeBlock(content, { class = lang }))
end

local function download_code_print(el)
  -- Web-only download affordance; print gets a pointer to the file.
  local path = el.attr.attributes['path'] or ''
  local filename = path:match('([^/]+)$') or path
  local label = el.attr.attributes['label'] or ('Download ' .. filename)
  return pandoc.RawBlock('latex',
    '\\noindent\\textit{' .. label .. ' (web version): \\path{'
    .. filename .. '}}')
end

-- Top-level dispatchers ----------------------------------------------------

function Code(el)
  el = code_shorthand(el)
  if el.classes:includes('path') then
    return pather(el)
  end
  if is_latex() then
    return coder_latex(el)
  end
  return el
end

function CodeBlock(el)
  if is_latex() then
    if el.classes:includes('include-py') then
      return include_py_print(el)
    elseif el.classes:includes('include-code') then
      return include_code_print(el)
    elseif el.classes:includes('link-code')
        or el.classes:includes('download-code') then
      return download_code_print(el)
    end
  end
  el = code_shorthand(el)
  if is_latex() then
    return coder_latex(el)
  end
  return el
end

function Link(el)
  if el.classes:includes('myurl') then
    return myurler(el)
  end
  return el
end

function RawBlock(el)
  if is_latex() then
    if el.format:match 'html' then
      -- tex_math_single_backslash so \(...\)/\[...\] math in raw-HTML table
      -- cells parses as math too (not just $...$); otherwise the backslashes
      -- get escaped to \textbackslash( and the math leaks as literal text.
      local html_read = pandoc.read(
        el.text, 'html+tex_math_dollars+tex_math_single_backslash').blocks
      local html_reads = {}
      for i = 1, #html_read do
        html_reads[i] = pandoc.walk_block(html_read[i], interior_filter)
        html_reads[i] = pandoc.walk_block(html_reads[i], {
          Table = function(t)
            return pandoc.RawBlock('latex', pandoc.write(pandoc.Pandoc({ t }), 'latex'))
          end,
        })
      end
      return html_reads
    end
  end
  return el
end

function RawInline(el)
  return el
end

-- A solution div OUTSIDE any exercise: no handler ever claimed it, so it
-- rendered as ordinary body text in the public PDF. It cannot go through
-- exercise_solution — that emits \end{exercise} to close an enclosing
-- environment which, here, does not exist — so gate it like .solutions-only.
local function orphan_solutioner(el)
  if not is_latex() then return {} end
  local content = delimiter_dollar(walk_to_latex(el))
  return pandoc.RawBlock('latex',
    '\n\\ifdefined\\issolution\n' .. content .. '\n\\fi\n')
end

function Div(el)
  if el.classes:includes('section') then
    return el -- section-divs pass through; versioning filters are Phase 4
  end
  if el.classes:includes('exercise-solution')
      and not el.classes:includes('in-exercise') then
    return orphan_solutioner(el)
  end
  if el.classes:includes('cloze') then
    return cloze_div_latex(el)
  elseif el.classes:includes('blank') then
    return blank_div_latex(el)
  end
  if el.classes:includes('infobox') then
    return infoboxer(el)
  elseif el.classes:includes('freadinglist') then
    return freadinglister(el)
  elseif el.classes:includes('listing') then
    return listinger(el)
  elseif el.classes:includes('output') then
    return outputer(el)
  elseif el.classes:includes('exercise') then
    return exerciser(el)
  elseif el.classes:includes('subtables') then
    -- untested-in-CI LaTeX path: never let a bug here break the print build
    local ok, res = pcall(subtablesdiver, el)
    return ok and res or el
  elseif el.classes:includes('figure') then
    return figurediver(el)
  elseif el.classes:includes('example') then
    return exampler(el)
  elseif el.classes:includes('theorem') or el.classes:includes('lemma')
      or el.classes:includes('corollary') or el.classes:includes('proposition') then
    return theoremer(el)
  elseif el.classes:includes('definition') then
    return definitioner(el)
  elseif el.classes:includes('only-html') then
    return only_htmler(el)
  end
  return el
end

-- Images outside .figure divs fall through to pandoc's writer, whose
-- \includegraphics cannot load .pgf; route those through \inputpgf.
function Image(el)
  if not is_latex() then return el end
  local variant = cloze_variant_src(el)
  if variant then el.src = variant end
  if el.classes:includes('pgf') or el.src:match('%.pgf$') then
    return imager(el)
  end
  -- An identified figure image that pandoc left bare because its caption is
  -- empty (![](src){#fig:x .figure}) renders as a plain \includegraphics
  -- with no \label, so \cref{fig:x} dangles. Wrap it in a figure float so
  -- it gets a number and label (bare + fig:-prefixed, like figurer).
  if el.identifier and el.identifier ~= ''
      and (el.classes:includes('figure') or el.classes:includes('standalone')) then
    local graphics = imager(el)
    -- tbl:-prefixed id -> genuine table float (see figurer), even bare
    if el.identifier:match('^[Tt]bl:') then
      return pandoc.RawInline('latex',
        '\\begin{table}[H]%\n\\tabcaption[][nofloat]{' .. el.identifier .. '}{}%\n'
        .. '\\centering\n' .. graphics.text .. '\n\\end{table}%\n\n')
    end
    local label = el.identifier
    local extra = ''
    if os.getenv('PARODY_PROJECT_DIR') and not label:match('^%a+:') then
      extra = '\\label{' .. label .. '}'
      label = 'fig:' .. label
    end
    return pandoc.RawInline('latex',
      '\\begin{figure}[H]\\centering\n' .. graphics.text
      .. '\n\\figcaption[]{' .. label .. '}{}\n' .. extra .. '\\end{figure}')
  end
  -- No identifier: no float wrapper, but a MEDIA-HIERARCHY src still needs
  -- resolving. A captionless, id-less
  -- ![](notebooks/<slug>/<name>){.standalone} used to fall off the end of this
  -- function, leaving pandoc's default writer to emit \includegraphics with
  -- the web media path — which kpathsea cannot find, so the figure vanished
  -- from the PDF without a distinct error (\includestandalone is
  -- \providecommand'd to \includegraphics). ~70 refs in the electronics book
  -- rendered as missing figures this way (#587).
  --
  -- Restricted to the notebooks/ form on purpose. A BARE src (rtc's shape,
  -- e.g. ![](gate-not){.figure}) already resolves: kpathsea searches TEXINPUTS
  -- and tries extensions. resolve_asset instead demands an exact filename
  -- match and returns nil, so sending bare srcs down this path DROPS the
  -- figure — an earlier attempt at #587 blanked the logic-gate images in three
  -- rtc sections that way.
  if os.getenv('PARODY_PROJECT_DIR') and el.src:match('^notebooks/[^/]+/') then
    return imager(el)
  end
end

-- `[answer]{.solutions-only}` — the inline form of the listing-box gate a few
-- hundred lines up. Wrap the run in \ifdefined\issolution…\fi so a non-solutions
-- build typesets nothing.
--
-- Both {} matter. Without the one after \issolution the true branch would start
-- by gobbling nothing in particular; without the one after \fi, TeX eats the
-- space that follows the control word and the span runs into the next word
-- ("4.2 secondsfor this design"). Any non-LaTeX format drops the run instead of
-- passing it through — print.lua only ever runs for latex, and a gate that
-- fails open is how this class leaked onto the web in the first place.
local function solutions_onlyer(el)
  if not is_latex() then return {} end
  local out = pandoc.List({ pandoc.RawInline('latex', '\\ifdefined\\issolution{}') })
  out:extend(el.content)
  out:insert(pandoc.RawInline('latex', '\\fi{}'))
  return out
end

function Span(el)
  if el.classes:includes('solutions-only') then
    return solutions_onlyer(el)
  elseif el.classes:includes('key') or el.classes:includes('keys') then
    return keyer(el)
  elseif el.classes:includes('menu') then
    if is_latex() then return menuer_latex(el) end
    return el
  elseif el.classes:includes('unicode') then
    return unicoder(el)
  elseif el.classes:includes('path') then
    return pather(el)
  elseif el.classes:includes('hashref') or el.classes:includes('Hashref')
      or el.classes:includes('href') or el.classes:includes('Href') then
    return hashrefer(el)
  elseif el.classes:includes('lref') then
    return linerefer(el)
  elseif el.classes:includes('cloze') then
    return clozer_latex(el)
  elseif el.classes:includes('blank') then
    return blanker_latex(el)
  elseif el.classes:includes('label') then
    return labeler(el)
  elseif el.classes:includes('plaincite') then
    return plainciter(el)
  elseif el.classes:includes('cite') then
    return spanciter(el)
  elseif el.classes:includes('keyword') then
    return keyworder(el)
  elseif el.classes:includes('index') then
    return indexer(el)
  elseif starts_with('eq:', el.identifier) then
    return mathspaner(el)
  end
  return el
end

function Cite(el)
  local first_id = el.citations[1].id
  if first_id:match('^[Ss]ec:') or first_id:match('^[Ee]q:')
      or first_id:match('^[Tt]bl:') or first_id:match('^[Ff]ig:')
      or first_id:match('^[Ll]st:') then
    return el -- handled by pandoc-crossref downstream
  end
  return citer(el)
end

function Header(el)
  if FORMAT:match 'latex' then
    return headerer_latex(el)
  end
  return el
end

function Math(el)
  if is_latex() and el.mathtype == 'InlineMath' then
    return pandoc.RawInline('tex', '$' .. el.text .. '$')
  end
  return el
end

function Figure(el)
  local first = el.content[1]
  local image = first and first.content and first.content[1]
  if image and image.src then
    local variant = cloze_variant_src(image)
    if variant then image.src = variant end
  end
  if image and image.classes and image.classes:includes('algorithm') then
    if is_latex() then
      return algorithmer_latex(el)
    end
    return el
  end
  return figurer(el, true) -- all figures nofloat, per ancestor behavior
end

function Table(el)
  if is_latex() then
    return tabler_latex(el)
  end
  return el
end

function OrderedList(el)
  if is_latex() then
    return pandoc.walk_block(el, interior_filter)
  end
  return el
end

-- Marks `.exercise-solution` divs that live inside an .exercise, so the Div
-- pass can tell them from orphans. It has to be its own earlier pass: pandoc
-- walks bottom-up, so by the time Div sees a solution div its exercise has not
-- been visited yet and the div cannot look upward for itself. Marking from the
-- exercise DOWN sidesteps the ordering entirely.
local function mark_nested_solutions(el)
  if not el.classes:includes('exercise') then return nil end
  return pandoc.walk_block(el, {
    Div = function(inner)
      if inner.classes:includes('exercise-solution')
          or inner.classes:includes('solution') then
        inner.classes:insert('in-exercise')
      end
      return inner
    end,
  })
end

return {
  { Div = mark_nested_solutions },
  { Div = Div },
  { Header = Header },
  { RawBlock = RawBlock },
  { OrderedList = OrderedList },
  -- Figure runs before Code (like Header) so figurer sees its caption's
  -- inline code as a Code element and routes it through inlines_to_latex,
  -- which renders it moving-argument-safe (\texttt, not verbatim
  -- \mintinline — fatal in a \figcaption, a moving argument). If Code ran
  -- first, the caption would already hold a \mintinline RawInline and the
  -- print build would die with an "Emergency stop". figurer self-converts
  -- all its caption inlines, so it does not depend on the later passes.
  { Figure = Figure },
  { Code = Code },
  { CodeBlock = CodeBlock },
  { RawInline = RawInline },
  { Cite = Cite },
  { Span = Span },
  { Link = Link },
  { Math = Math },
  -- After Figure: Figure consumes its own images via figurer; this pass
  -- catches only bare images that no block handler claimed.
  { Image = Image },
  { Table = Table },
}
