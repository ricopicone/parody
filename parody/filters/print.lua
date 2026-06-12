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
  walked = pandoc.walk_block(walked, inline_filter)
  local doc = pandoc.Pandoc(walked)
  local tex = pandoc.write(doc, 'latex')
  return (tex:gsub("\n$", ""))
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
  local sec_tex = '\\' .. cmds[l] .. star .. '{' .. content .. '}'
  if label and label ~= '' then
    sec_tex = sec_tex .. '\n\\label{' .. label .. '}'
  end
  -- short hashes are cross-ref keys: [h]{.hashref} -> \cref{h} needs a
  -- label at the heading carrying that hash
  local h = el.attr.attributes['h'] or el.attr.attributes['hash']
  if h and h ~= '' and h ~= label then
    sec_tex = sec_tex .. '\n\\label{' .. h .. '}'
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

coder_latex = function(el)
  local language
  if not isempty(el.classes) then
    language = el.classes[1]
  else
    language = 'text'
  end
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
    .. content .. '\n\\end{' .. envtype .. '}\n')
end

local function definitioner(el)
  local content = walk_to_latex(el)
  local title = el.attr.attributes['title'] or ''
  local identifier = el.identifier or ''
  if not is_latex() then return el end
  return pandoc.RawBlock('latex',
    '\\begin{definition}{' .. title .. '}{' .. identifier .. '}\n'
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

function imager(el)
  if not is_latex() then return el end
  -- Notebook print builds (PARODY_PROJECT_DIR set): map media-hierarchy and
  -- chapter-relative srcs to source-tree files, converting svg as needed.
  -- pgf/standalone sources are LaTeX inputs with their own commands and
  -- src conventions (extensionless); they never go through asset resolution.
  local is_pgf_or_standalone = el.classes:includes('standalone')
    or el.classes:includes('pgf') or el.src:match('%.pgf$')
  local notebook_ctx = os.getenv('PARODY_PROJECT_DIR') ~= nil
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
  -- Notebook sources use unprefixed figure ids (#foo) with prefixed refs
  -- (@fig:foo); the web resolver tolerates that, \cref needs the prefix.
  local label = el.identifier
  if os.getenv('PARODY_PROJECT_DIR') and label ~= ''
      and not label:match('^%a+:') then
    label = 'fig:' .. label
  end
  local fig_tex = graphics_list_reset .. fig_begin .. content
    .. '\n\\figcaption' .. options .. '[]{' .. label .. '}{' .. caption .. '}\n'
    .. fig_end
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
    caption = el.content[#el.content]
  end
  local subfigures = {}
  for i = 1, n_subfigures do
    subfigures[i] = el.content[i].content[1]
  end
  local caps, srcs, labels, classes = {}, {}, {}, {}
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
    labels[i] = img.identifier
    if labels[i] == nil or labels[i] == '' then
      labels[i] = 'fig:sub-' .. i
    end
    classes[i] = img.classes or {}
  end
  local fig_tex = '\\begin{figure}[H]\n\\centering\n'
  local cols = math.ceil(n_subfigures / rows)
  local current_row = 1
  local subcaption_width = 1 / cols - 0.05
  fig_tex = fig_tex .. '% Row 1\n'
  for i = 1, #subfigures do
    if math.fmod(i - 1, cols) == 0 and i ~= 1 then
      current_row = current_row + 1
      fig_tex = fig_tex .. '\\\\\n% Row ' .. current_row .. '\n'
    end
    local graphics_command
    if classes[i]:includes('pgf') or srcs[i]:match('%.pgf$') then
      graphics_command = '\\noindent\\inputpgf{' .. srcs[i]:gsub('%.pgf$', '') .. '}'
    else
      graphics_command = '\\noindent\\includegraphics{' .. srcs[i] .. '}'
    end
    local filler_after = ''
    if math.fmod(i, cols) == 0 then
      filler_after = '\\hspace*{\\fill}%\n'
    end
    fig_tex = fig_tex .. '\\hspace*{\\fill}%\n'
      .. '\\subcaptionbox{' .. caps[i] .. '\\label{' .. labels[i] .. '}}'
      .. '[' .. string.format('%.2f', subcaption_width) .. '\\linewidth]\n'
      .. '{' .. graphics_command .. '}\n' .. filler_after
  end
  local caption_tex = pandoc.write(pandoc.Pandoc(caption), 'latex')
  fig_tex = fig_tex .. '\\figcaption{' .. el.identifier .. '}{' .. caption_tex .. '}\n'
    .. '\\end{figure}\n'
  return pandoc.RawBlock('latex', fig_tex)
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
  if el.t == 'Table' then
    el = pandoc.utils.to_simple_table(el)
  end
  local caption = pandoc.utils.stringify(el.caption)
  local id = string.match(caption, '%{.*%}$')
  if id == nil then id = '' end
  return string.sub(id, 3, -2)
end

local function tabler_latex(el)
  local identifier = get_table_id(el)
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

  local caption_text = pandoc.utils.stringify(simple.caption)
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
    if file_exists(candidate) then resolved = candidate end
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
      local html_read = pandoc.read(el.text, 'html+tex_math_dollars').blocks
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

function Div(el)
  if el.classes:includes('section') then
    return el -- section-divs pass through; versioning filters are Phase 4
  end
  if el.classes:includes('infobox') then
    return infoboxer(el)
  elseif el.classes:includes('listing') then
    return listinger(el)
  elseif el.classes:includes('output') then
    return outputer(el)
  elseif el.classes:includes('exercise') then
    return exerciser(el)
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
  if el.classes:includes('pgf') or el.src:match('%.pgf$') then
    return imager(el)
  end
end

function Span(el)
  if el.classes:includes('key') or el.classes:includes('keys') then
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

return {
  { Div = Div },
  { Header = Header },
  { RawBlock = RawBlock },
  { OrderedList = OrderedList },
  { Code = Code },
  { CodeBlock = CodeBlock },
  { RawInline = RawInline },
  { Cite = Cite },
  { Span = Span },
  { Link = Link },
  { Math = Math },
  { Figure = Figure },
  -- After Figure: Figure consumes its own images via figurer; this pass
  -- catches only bare images that no block handler claimed.
  { Image = Image },
  { Table = Table },
}
