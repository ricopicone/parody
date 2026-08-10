local function read_file(path)
  local file = io.open(path, "r")
  if not file then
    return nil
  end
  local content = file:read("*all")
  file:close()
  return content
end

local function has_cell_tag(tags, target_tag)
  if not tags then
    return false
  end
  for _, tag in ipairs(tags) do
    if tag == target_tag then
      return true
    end
  end
  return false
end

local function read_json_file(path)
  local file = io.open(path, "r")
  if not file then
    return nil
  end
  local content = file:read("*all")
  file:close()
  -- Simple JSON parsing for our metadata (assumes well-formed JSON)
  local json = content:gsub('"([^"]+)":', function(key) return key .. ':' end)
  return json
end

local function find_figure_metadata(base_path, image_name)
  -- Look for metadata files that correspond to this image
  local metadata_dir = base_path .. "/_figure_metadata"
  local handle = io.popen("find " .. metadata_dir .. " -name 'metadata_*.json' 2>/dev/null | head -10")
  if not handle then
    return nil
  end

  local result = handle:read("*a")
  handle:close()

  -- For simplicity, we'll use the most recent metadata file
  -- In a more sophisticated implementation, we'd match by timestamp or other criteria
  local latest_file = nil
  for file in result:gmatch("[^\r\n]+") do
    latest_file = file
  end

  if latest_file then
    local content = read_file(latest_file)
    if content then
      -- Simple JSON parsing - extract caption and id
      local caption = content:match('"caption"%s*:%s*"([^"]*)"')
      local id = content:match('"id"%s*:%s*"([^"]*)"')
      local width = content:match('"width"%s*:%s*"([^"]*)"')
      local height = content:match('"height"%s*:%s*"([^"]*)"')

      return {
        caption = caption,
        id = id,
        width = width,
        height = height
      }
    end
  end

  return nil
end


local function escape_html_attr(value)
  if not value then
    return ""
  end
  local escaped = value:gsub("&", "&amp;")
  escaped = escaped:gsub("\"", "&quot;")
  escaped = escaped:gsub("<", "&lt;")
  escaped = escaped:gsub(">", "&gt;")
  return escaped
end

local function escape_html_text(value)
  if not value then
    return ""
  end
  local escaped = value:gsub("&", "&amp;")
  escaped = escaped:gsub("<", "&lt;")
  escaped = escaped:gsub(">", "&gt;")
  return escaped
end

local function tabset(el)
  local tab_blocks = {}
  local is_first = true

  for _, block in ipairs(el.content) do
    if block.t == "Div" and block.classes:includes("tab") then
      local title = block.attributes.title or block.attributes.label or "Tab"
      local title_attr = escape_html_attr(title)
      local title_text = escape_html_text(title)
      local selected_attr = is_first and ' aria-selected="true"' or ' aria-selected="false"'

      local tab_html = string.format(
        '<div role="tab" class="tab" aria-label="%s"%s>%s</div>',
        title_attr, selected_attr, title_text
      )

      local tab_classes = { "tab-content", "border-base-300", "bg-base-100", "p-4" }
      for _, class in ipairs(block.classes) do
        if class ~= "tab" then
          table.insert(tab_classes, class)
        end
      end
      local tab_attr_parts = { string.format('class="%s"', table.concat(tab_classes, " ")), 'role="tabpanel"' }
      if block.identifier and block.identifier ~= "" then
        table.insert(tab_attr_parts, string.format('id="%s"', escape_html_attr(block.identifier)))
      end

      local content_html = pandoc.write(pandoc.Pandoc(block.content), "html")
      local tab_content_html = string.format('%s\n<div %s>%s</div>', tab_html, table.concat(tab_attr_parts, " "), content_html)
      table.insert(tab_blocks, pandoc.RawBlock("html", tab_content_html))
      is_first = false
    else
      table.insert(tab_blocks, block)
    end
  end

  local wrapper_classes = { "tabs" }
  for _, class in ipairs(el.classes) do
    if class ~= "tabset" and class ~= "tabs" then
      table.insert(wrapper_classes, class)
    end
  end

  local wrapper_attr = {
    class = table.concat(wrapper_classes, " "),
    role = "tablist"
  }
  if el.identifier and el.identifier ~= "" then
    wrapper_attr.id = el.identifier
  end

  return pandoc.Div(tab_blocks, wrapper_attr)
end

-- Apply filters to parsed content
local function apply_filters_to_blocks(blocks, notebook_slug, chapter_slug, base_name)
  local processed_blocks = {}
  for i, block in ipairs(blocks) do
    if block.t == "CodeBlock" then
      local result = CodeBlock(block)
      if result then
        table.insert(processed_blocks, result)
      else
        table.insert(processed_blocks, block)
      end
    elseif block.t == "Div" then
      -- Recursively apply filters to div content
      if block.content then
        block.content = apply_filters_to_blocks(block.content, notebook_slug, chapter_slug, base_name)
      end
      local result = Div(block)
      if result then
        table.insert(processed_blocks, result)
      else
        table.insert(processed_blocks, block)
      end
    elseif block.t == "Table" then
      local result = Table(block)
      if result then
        table.insert(processed_blocks, result)
      else
        table.insert(processed_blocks, block)
      end
    else
      -- For other block types, apply inline filters with context
      block = pandoc.walk_block(block, {
        Link = Link,
        Image = function(img)
          return Image(img, notebook_slug, chapter_slug, base_name)
        end
      })
      table.insert(processed_blocks, block)
    end
  end
  return processed_blocks
end

local function include_code_file(el)
  -- Handle simple include directive for code files
  -- Format: ```{.include-code path="relative/path/to/file.py"}
  local path = el.attr.attributes['path']
  if not path then
    return el
  end

  -- Get the current directory from PANDOC_STATE if available
  local current_dir = ""
  if PANDOC_STATE and PANDOC_STATE.input_files and #PANDOC_STATE.input_files > 0 then
    local input_file = PANDOC_STATE.input_files[1]
    current_dir = input_file:match("^(.*/)")
    if current_dir then
      current_dir = current_dir
    else
      current_dir = ""
    end
  end

  -- Try the path relative to current directory first
  local full_path = current_dir .. path
  local content = read_file(full_path)

  -- If not found, try the original path
  if not content then
    content = read_file(path)
  end

  if not content then
    return pandoc.Div({
      pandoc.Para({pandoc.Strong({pandoc.Str("Error: Could not find file " .. path)})})
    }, {class = "include-error"})
  end

  -- Detect language from file extension
  local language = path:match("%.([^.]+)$") or "text"
  -- Map extensions to language identifiers
  local lang_map = {
    py = "python",
    js = "javascript",
    ts = "typescript",
    java = "java",
    cpp = "cpp",
    c = "c",
    rb = "ruby",
    go = "go",
    rs = "rust",
    sh = "bash",
    bash = "bash",
    sql = "sql",
    html = "html",
    css = "css",
    md = "markdown",
    json = "json",
    yaml = "yaml",
    yml = "yaml",
    xml = "xml",
    lua = "lua"
  }
  language = lang_map[language] or language

  -- Return code block with filename header
  return pandoc.Div({
    pandoc.Para({pandoc.Emph({pandoc.Str("Source code for file " .. path)})}),
    pandoc.CodeBlock(content, {class = language})
  }, {class = "include-code"})
end

local function link_code_file(el)
  -- Handle download link directive for code files
  -- Format: ```{.link-code path="relative/path/to/file.py"}
  -- Also accepts .download-code as alias
  local path = el.attr.attributes['path']
  if not path then
    return el
  end

  -- Get the current directory to determine notebook/chapter context
  local current_dir = ""
  if PANDOC_STATE and PANDOC_STATE.input_files and #PANDOC_STATE.input_files > 0 then
    local input_file = PANDOC_STATE.input_files[1]
    current_dir = input_file:match("^(.*/)")
    if current_dir then
      current_dir = current_dir
    else
      current_dir = ""
    end
  end

  -- Extract notebook and chapter slugs from path
  local notebook_slug = ""
  local chapter_slug = ""
  if current_dir then
    notebook_slug = current_dir:match("notebooks%-source/([^/]+)/") or ""
    chapter_slug = current_dir:match("(chapter_[^/]+)/") or ""
  end

  -- Fallback for standalone content repos (no notebooks-source/ ancestor):
  -- the build provides the slugs via env vars.
  if notebook_slug == "" then
    notebook_slug = os.getenv("PARODY_NOTEBOOK_SLUG") or ""
  end
  if chapter_slug == "" then
    chapter_slug = os.getenv("PARODY_CHAPTER_SLUG") or ""
  end

  -- Build media path for download link. Paths already inside the media
  -- hierarchy (notebooks/... or media/...) pass through unchanged so a
  -- directive can point at shared assets outside its own chapter.
  local media_path = path
  if path:match("^notebooks/") or path:match("^media/") then
    media_path = path:gsub("^media/", "")
  elseif notebook_slug ~= "" and chapter_slug ~= "" then
    media_path = string.format("notebooks/%s/%s/%s",
      notebook_slug, chapter_slug, path)
  end

  -- Extract filename for display
  local filename = path:match("([^/]+)$") or path

  -- Optional custom label
  local label = el.attr.attributes['label'] or ("Download " .. filename)

  -- Generate download link using Django auth_button tag
  local link_html = string.format(
    '{%% auth_button href="%s" label="%s" %%}',
    media_path, label
  )

  return pandoc.RawBlock("html", link_html)
end

local function include_jupytext_code(el)
  -- Handle include directive for jupytext code
  -- Format: ```{.include-py path="relative/path/to/file.py"}
  local path = el.attr.attributes['path']
  if not path then
    return el
  end

  -- Get the current directory from PANDOC_STATE if available
  local current_dir = ""
  if PANDOC_STATE and PANDOC_STATE.input_files and #PANDOC_STATE.input_files > 0 then
    local input_file = PANDOC_STATE.input_files[1]
    current_dir = input_file:match("^(.*/)")
    if current_dir then
      current_dir = current_dir
    else
      current_dir = ""
    end
  end

  -- Extract context for building media paths
  local notebook_slug = ""
  local chapter_slug = ""
  if current_dir then
    -- Extract notebook and chapter from path like "/Users/.../notebooks-source/sample-notebook/chapter_python-examples/"
    notebook_slug = current_dir:match("notebooks%-source/([^/]+)/") or ""
    chapter_slug = current_dir:match("(chapter_[^/]+)/") or ""
  end

  -- Fallback for parody content-repo layout (chapters/<ch>/<sec>.md): the
  -- build sets these env vars since the legacy path patterns can't match.
  if notebook_slug == "" then
    notebook_slug = os.getenv("PARODY_NOTEBOOK_SLUG") or ""
  end
  if chapter_slug == "" then
    chapter_slug = os.getenv("PARODY_CHAPTER_SLUG") or ""
  end

  -- Get the base name without extension for media path construction
  local base_name = path:gsub("%.py$", "")

  -- Convert .py extension to .md for the converted file
  local md_path = path:gsub("%.py$", ".md")

  -- Try the path relative to current directory first
  local full_md_path = current_dir .. md_path
  local content = read_file(full_md_path)

  -- If not found, try the original path
  if not content then
    content = read_file(md_path)
  end

  if not content then
    -- Fallback: try to read the original Python file and display as code
    local full_py_path = current_dir .. path
    local py_content = read_file(full_py_path)
    if not py_content then
      py_content = read_file(path)
    end

    if py_content then
      return pandoc.Div({
        pandoc.Para({pandoc.Emph({pandoc.Str("Source code for file " .. path)})}),
        pandoc.CodeBlock(py_content, {class="python"})
      }, {class = "jupytext-fallback"})
    else
      return pandoc.Div({
        pandoc.Para({pandoc.Strong({pandoc.Str("Error: Could not find file " .. path)})})
      }, {class = "jupytext-error"})
    end
  end

  -- Parse the markdown content and return as Pandoc AST
  local parsed = pandoc.read(content, "markdown")

  -- Apply filters to the parsed content with context
  local processed_blocks = apply_filters_to_blocks(parsed.blocks, notebook_slug, chapter_slug, base_name)

  return pandoc.Div(processed_blocks, {class = "jupytext-included"})
end

local function infoboxer(el)
  -- Apply interior filter to the content
  local title = el.attr.attributes['title'] or ""
  local identifier = el.identifier or ""

  -- Only transform for HTML
  if FORMAT:match 'html' then
    return pandoc.Div({
      pandoc.Div({
        pandoc.Header(3, title, { class = "text-lg font-semibold text-gray-800" })
      }, { class = "px-4 py-2 border-b border-gray-300 bg-gray-100 rounded-t" }),
      pandoc.Div(el.content, { class = "px-4 py-3 text-sm text-gray-700" })
    }, {
      class = "infobox rounded border border-gray-300 shadow-md my-4 bg-white",
      id = identifier
    })
  else
    return el
  end
end

local function definition(el)
  -- Apply interior filter to the content
  local title = el.attr.attributes['title'] or "Definition"
  local identifier = el.identifier or ""

  -- Only transform for HTML
  if FORMAT:match 'html' then
    return pandoc.Div({
      pandoc.Div({
        pandoc.Header(3, title, { class = "text-lg font-semibold text-cyan-900" })
      }, { class = "px-4 py-2 border-b border-cyan-400 bg-cyan-50 rounded-t" }),
      pandoc.Div(el.content, { class = "px-4 py-3 text-sm text-gray-700" })
    }, {
      class = "definition numbered-environment rounded border border-cyan-400 shadow-md my-4 bg-white scroll-mt-20",
      id = identifier,
      ["data-env-type"] = "definition"
    })
  else
    return el
  end
end

local function comment(el)
  -- Apply interior filter to the content
  local title = el.attr.attributes['title'] or "Comment"
  local identifier = el.identifier or ""

  -- Only transform for HTML
  if FORMAT:match 'html' then
    return pandoc.Div({
      pandoc.Div({
        pandoc.Header(3, title, { class = "text-lg font-semibold text-amber-900" })
      }, { class = "px-4 py-2 border-b border-amber-400 bg-amber-50 rounded-t" }),
      pandoc.Div(el.content, { class = "px-4 py-3 text-sm text-gray-700" })
    }, {
      class = "comment numbered-environment rounded border border-amber-400 shadow-md my-4 bg-white scroll-mt-20",
      id = identifier,
      ["data-env-type"] = "comment"
    })
  else
    return el
  end
end

local function theorem(el)
  -- Apply interior filter to the content
  local title = el.attr.attributes['title'] or "Theorem"
  local identifier = el.identifier or ""

  -- Only transform for HTML
  if FORMAT:match 'html' then
    return pandoc.Div({
      pandoc.Div({
        pandoc.Header(3, title, { class = "text-lg font-semibold text-purple-900" })
      }, { class = "px-4 py-2 border-b border-purple-400 bg-purple-50 rounded-t" }),
      pandoc.Div(el.content, { class = "px-4 py-3 text-sm text-gray-700" })
    }, {
      class = "theorem numbered-environment rounded border border-purple-400 shadow-md my-4 bg-white scroll-mt-20",
      id = identifier,
      ["data-env-type"] = "theorem"
    })
  else
    return el
  end
end

local function exercise(el)
  -- Apply interior filter to the content, but remove exercise-solution divs
  local title = el.attr.attributes['title'] or "Exercise"
  -- The cross-ref handle is the short hash (::: {.exercise h="8y"}); fall back to
  -- it as the DOM id when there's no explicit identifier, so [8y]{.hashref} links
  -- land on the box. Without this the hash was dropped and refs dangled.
  local hash = el.attr.attributes['h'] or ""
  local identifier = (el.identifier ~= "" and el.identifier) or hash

  -- Filter out exercise-solution divs from content
  local filtered_content = {}
  for _, block in ipairs(el.content) do
    if not (block.t == "Div" and block.classes:includes("exercise-solution")) then
      table.insert(filtered_content, block)
    end
  end

  -- Only transform for HTML
  if FORMAT:match 'html' then
    -- Lab problems (::: {.exercise .lab}) are numbered on their own per-chapter
    -- counter and labelled "Problem L4.5" by the web renderer. The "lab" class
    -- and data-lab="1" attribute below are artifact semantics for consumers in
    -- general (e.g. homepage-django's Tailwind styling); parody-web itself does
    -- not read them here — it derives lab-ness from the anchor's own "lab" flag
    -- (artifact.py) and rebuilds the exercise box's class attribute from
    -- scratch. Purely additive: the legacy class string and attribute order are
    -- untouched, because homepage-django styles those Tailwind names for real
    -- and tests/golden/*.json pins the markup.
    local classes = {"exercise", "numbered-environment", "rounded", "border",
                     "border-green-400", "shadow-md", "my-4", "bg-white",
                     "scroll-mt-20"}
    local kv = {{"data-h", hash}, {"data-env-type", "exercise"}}
    if el.classes:includes('lab') then
      classes[#classes + 1] = "lab"
      kv[#kv + 1] = {"data-lab", "1"}
    end
    return pandoc.Div({
      pandoc.Div({
        pandoc.Header(3, title, { class = "text-lg font-semibold text-green-900" })
      }, { class = "px-4 py-2 border-b border-green-400 bg-green-50 rounded-t" }),
      pandoc.Div(filtered_content, { class = "px-4 py-3 text-sm text-gray-700" })
    }, pandoc.Attr(identifier, classes, kv))
  else
    return el
  end
end

local function example(el)
  -- Examples carry their cross-ref handle in the short hash (::: {.example
  -- h="c4"}); pandoc emits data-h but no DOM id, so [c4]{.hashref} had nowhere
  -- to land. Give the div an id from the hash, then build the same header/body
  -- box definition() and exercise() build. Print has always boxed examples
  -- (print.lua's exampler -> \begin{myexample}); this is the web catching up.
  -- Amber keeps them distinct from definitions (cyan) and exercises (green).
  local title = el.attr.attributes['title'] or "Example"
  local hash = el.attr.attributes['h'] or ""
  local identifier = (el.identifier ~= "" and el.identifier) or hash

  if FORMAT:match 'html' then
    return pandoc.Div({
      pandoc.Div({
        pandoc.Header(3, title, { class = "text-lg font-semibold text-amber-900" })
      }, { class = "px-4 py-2 border-b border-amber-400 bg-amber-50 rounded-t" }),
      pandoc.Div(el.content, { class = "px-4 py-3 text-sm text-gray-700" })
    }, {
      class = "example numbered-environment rounded border border-amber-400 shadow-md my-4 bg-white scroll-mt-20",
      id = identifier,
      ["data-env-type"] = "example"
    })
  else
    return el
  end
end

local function caption_from_list(ol)
  -- A subfigure main caption like "(a) … and (b) …" starts with "(a)", which
  -- pandoc parses as a LowerAlpha ordered list. Rebuild it as one inline
  -- paragraph (marker text + item content) so it renders as caption prose.
  local la = ol.listAttributes or {}
  local start = la.start or 1
  local inlines = {}
  for i, item in ipairs(ol.content) do
    local n = start + i - 1
    local m
    if la.style == "LowerAlpha" then m = string.char(96 + n)
    elseif la.style == "UpperAlpha" then m = string.char(64 + n)
    else m = tostring(n) end
    if la.delimiter == "TwoParens" then m = "(" .. m .. ")"
    elseif la.delimiter == "OneParen" then m = m .. ")"
    else m = m .. "." end
    if i > 1 then table.insert(inlines, pandoc.Space()) end
    table.insert(inlines, pandoc.Str(m))
    table.insert(inlines, pandoc.Space())
    for _, blk in ipairs(item) do
      if blk.content then
        for _, inl in ipairs(blk.content) do table.insert(inlines, inl) end
      end
    end
  end
  return pandoc.Para(inlines)
end

local function subfigures(el)
  -- ::: {#fig:main .figure .subfigures rows=N} with ![subcap](img){#fig:sub
  -- .subfigure ...} panels and a trailing main-caption paragraph. Print is
  -- handled by print.lua's figurediver; here we emit one outer <figure> holding
  -- the panel <figure class="subfigure">s (already rendered by Figure() in this
  -- bottom-up walk) plus the main caption as a <figcaption>. parody-web's
  -- number_artifact assigns the shared figure number + per-panel letters.
  if not FORMAT:match 'html' then return el end
  -- inlines run before blocks, so each panel is a Figure(Plain(<img> RawInline))
  -- with its sub-caption on Figure.caption; the trailing Para is the main caption.
  local function blocks_html(blocks)
    if not blocks or #blocks == 0 then return "" end
    return (pandoc.write(pandoc.Pandoc(blocks), "html")
      :gsub("^%s*<p>(.-)</p>%s*$", "%1"):gsub("%s+$", ""))
  end
  local panels, caption_blocks, panel_n = {}, {}, 0
  for _, block in ipairs(el.content) do
    if block.t == "Figure" then
      -- captioned panel: ![subcap](img){#fig:sub} → lettered subfigure
      panel_n = panel_n + 1
      local img = blocks_html(block.content)
      local subcap = block.caption and blocks_html(block.caption.long) or ""
      local cap_el = subcap ~= ""
        and '<figcaption>' .. subcap .. '</figcaption>' or ""
      panels[#panels + 1] = string.format(
        '<figure id="%s" class="subfigure">%s%s</figure>',
        block.identifier or "", img, cap_el)
    elseif block.t == "Para" and blocks_html({block}):match("^%s*<img[^>]*>%s*$") then
      -- caption-less panel (empty-subcaption \subcaptionbox or a tabular grid):
      -- pandoc leaves it a Para>Image, not a Figure. Recover the panel id from
      -- data-subid (else generate one matching the converter's #fig:main-N) so
      -- number_artifact skips it in the figure count. A \subcaptionbox panel
      -- still gets an (empty) <figcaption> so it receives an (a)/(b) letter;
      -- tabular grids (.nosublabels) suppress it.
      panel_n = panel_n + 1
      local img = blocks_html({block})
      local pid = img:match('data%-subid="([^"]*)"')
        or string.format("%s-%d", el.identifier or "fig", panel_n)
      local cap_el = el.classes:includes("nosublabels") and ""
        or "<figcaption></figcaption>"
      panels[#panels + 1] = string.format(
        '<figure id="%s" class="subfigure">%s%s</figure>', pid, img, cap_el)
    elseif not (block.t == "Para" and #block.content == 0) then
      if block.t == "OrderedList" then
        block = caption_from_list(block)
      end
      caption_blocks[#caption_blocks + 1] = block
    end
  end
  local cap_html = ""
  if #caption_blocks > 0 then
    cap_html = '<figcaption class="subfigures-caption">'
      .. blocks_html(caption_blocks) .. '</figcaption>'
  end
  local rows = tonumber(el.attr.attributes['rows'] or "1") or 1
  local cols = math.max(1, math.ceil(#panels / rows))
  local perm = el.attr.attributes['permission'] or ""
  local perm_attr = perm ~= "" and string.format(' data-permission="%s"', perm) or ""
  local out = string.format(
    '<figure id="%s" class="figure subfigures" data-rows="%d" '
      .. 'style="--sf-cols:%d"%s>\n%s\n%s</figure>',
    el.identifier or "", rows, cols, perm_attr,
    table.concat(panels, "\n"), cap_html)
  return pandoc.RawBlock("html", out)
end

local function subtables(el)
  -- ::: {#tbl:main .subtables rows=N} with markdown tables (each ': subcap
  -- {#tbl:sub}') laid out side by side + a trailing main caption — the table
  -- analogue of .subfigures. number_artifact shares the "Table C.n" number and
  -- letters the panels (a)/(b). (Print: print.lua handles .subtables for LaTeX.)
  if not FORMAT:match 'html' then return el end
  local function blocks_html(blocks)
    if not blocks or #blocks == 0 then return "" end
    return (pandoc.write(pandoc.Pandoc(blocks), "html")
      :gsub("^%s*<p>(.-)</p>%s*$", "%1"):gsub("%s+$", ""))
  end
  local panels, caption_blocks = {}, {}
  for _, block in ipairs(el.content) do
    if block.t == "Table" then
      panels[#panels + 1] = '<div class="subtable">' .. blocks_html({block}) .. '</div>'
    elseif not (block.t == "Para" and #block.content == 0) then
      caption_blocks[#caption_blocks + 1] = block
    end
  end
  local cap_html = ""
  if #caption_blocks > 0 then
    cap_html = '<figcaption class="subtables-caption">'
      .. blocks_html(caption_blocks) .. '</figcaption>'
  end
  local rows = tonumber(el.attr.attributes['rows'] or "1") or 1
  local cols = math.max(1, math.ceil(#panels / rows))
  -- table captions sit ABOVE the tables (table convention), so the main caption
  -- comes first in the float; each panel table's own <caption> is top-side too.
  local out = string.format(
    '<figure id="%s" class="subtables" style="--st-cols:%d">\n%s\n%s</figure>',
    el.identifier or "", cols, cap_html, table.concat(panels, "\n"))
  return pandoc.RawBlock("html", out)
end

function CodeBlock(el)
  if el.classes:includes("mermaid") then
    -- Emit raw HTML so mermaid.js can parse the diagram text directly.
    -- Inside $$...$$ math blocks, remove braces around single-char arguments
    -- (e.g. \mathbf{w} → \mathbf w) because mermaid's parser treats { }
    -- as special syntax and strips them before KaTeX sees the TeX.
    local text = el.text:gsub('%$%$(.-)%$%$', function(tex)
      return '$$' .. tex:gsub('\\(%a+){(%a)}', '\\%1 %2') .. '$$'
    end)
    return pandoc.RawBlock("html", '<pre class="mermaid">\n' .. text .. '\n</pre>')
  elseif el.classes:includes("include-code") then
    return include_code_file(el)
  elseif el.classes:includes("link-code") or el.classes:includes("download-code") then
    return link_code_file(el)
  elseif el.classes:includes("include-py") then
    return include_jupytext_code(el)
  end

  -- Enhanced styling for syntax highlighting
  if #el.classes > 0 then
    local language = el.classes[1]
    -- Add language as data attribute for CSS styling
    el.attr.attributes['data-lang'] = language

    -- Ensure sourceCode class is present for styling
    if not el.classes:includes("sourceCode") then
      el.classes:insert("sourceCode")
    end

    -- Add language-specific class
    local lang_class = "language-" .. language
    if not el.classes:includes(lang_class) then
      el.classes:insert(lang_class)
    end
  end

  return el
end

-- ---- cloze (fill-in-the-blank) -------------------------------------------
-- PARODY_CLOZE_MODE: blank (default) | key | full.
--
-- In `blank` the hidden text is NEVER written into the HTML: anything this
-- filter emits is fetchable by the reader, so the answer is replaced here at
-- build time, not hidden with CSS. Widths are estimates (HTML can't measure
-- at build time); print measures the real box instead — see print.lua.
local CLOZE_MODE = os.getenv('PARODY_CLOZE_MODE') or 'blank'

local CLOZE_SIZES = { sm = '2em', md = '5em', lg = '10em', xl = '20em' }

-- Width of a manual blank: explicit width= wins, then a named size=, then md.
local function cloze_manual_width(el)
  local w = el.attributes and el.attributes.width
  if w and w ~= '' then return w end
  local size = (el.attributes and el.attributes.size) or 'md'
  return CLOZE_SIZES[size] or CLOZE_SIZES.md
end

-- Width of an automatic blank, estimated from the hidden content. TeX control
-- sequences are stripped first so \sqrt{k/m} counts its glyphs, not its source.
local function cloze_estimate_width(text)
  local plain = text:gsub('\\%a+%s*', ''):gsub('[{}$]', '')
  local n = pandoc.text.len(plain)
  local w = 0.6 * n + 0.8
  if w < 2 then w = 2 elseif w > 14 then w = 14 end
  return string.format('%.1fem', w)
end

local function cloze_blank_html(width)
  return string.format(
    '<span class="cloze-blank" style="--cloze-w: %s"></span>', width)
end

-- [answer]{.cloze} — hide the answer behind a rule sized to it.
local function clozer(el)
  if CLOZE_MODE == 'full' then
    return el.content  -- no wrapper at all: identical to a book without clozes
  elseif CLOZE_MODE == 'key' then
    return pandoc.Span(el.content, { class = 'cloze-key' })
  end
  return pandoc.RawInline('html', cloze_blank_html(
    cloze_estimate_width(pandoc.utils.stringify(el.content))))
end

-- []{.blank size=lg} — a manual blank with nothing behind it. `key` keeps the
-- rule (there is no answer to reveal); `full` drops it (a published book has
-- no room to write in).
local function blanker(el)
  if CLOZE_MODE == 'full' then return {} end
  return pandoc.RawInline('html', cloze_blank_html(cloze_manual_width(el)))
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

-- Rewrite every `\<name>{...}` in a TeX string, honoring nested braces.
-- A regex can't do this: \cloze{\sqrt{k/m}} would stop at the first brace.
-- Escaped braces (\{ \}) inside an argument are not supported; clozes are
-- authored as prose or short expressions, and the scanner leaves the string
-- untouched if it ever finds the braces unbalanced.
local function cloze_rewrite_macro(text, name, replace)
  local out, i = {}, 1
  local head = '\\' .. name
  while true do
    local s = text:find(head .. '%s*{', i)
    if not s then break end
    local open = text:find('{', s + #head)
    local depth, j = 1, open + 1
    while j <= #text and depth > 0 do
      local c = text:sub(j, j)
      if c == '{' then depth = depth + 1
      elseif c == '}' then depth = depth - 1 end
      j = j + 1
    end
    if depth ~= 0 then return text end  -- unbalanced: leave it alone
    out[#out + 1] = text:sub(i, s - 1)
    out[#out + 1] = replace(text:sub(open + 1, j - 2))
    i = j
  end
  out[#out + 1] = text:sub(i)
  return table.concat(out)
end

-- Math is opaque to pandoc, so clozes inside it are a TeX macro rather than a
-- span. Rewrite them here so the answer never reaches the browser in `blank`
-- mode.
--
-- Both replacements were checked against MathJax v3 (tex-mml-chtml) in a
-- browser: \underline{\hspace{w}} draws a clean rule with correct spacing
-- (a bare \rule butts against the preceding operator), and \class needs BOTH
-- lines of MathJax config, not just the package list:
--     loader: {load: ['[tex]/html']},
--     tex: {packages: {'[+]': ['html']}}
-- With only the second, \class renders as a red undefined-macro error.
function Math(el)
  if not el.text:find('\\cloze') then  -- also catches \clozeblank
    return el
  end
  local t = cloze_rewrite_macro(el.text, 'cloze', function(arg)
    if CLOZE_MODE == 'full' then return arg end
    if CLOZE_MODE == 'key' then
      return '\\class{cloze-key}{' .. arg .. '}'
    end
    return '\\underline{\\hspace{' .. cloze_estimate_width(arg) .. '}}'
  end)
  t = cloze_rewrite_macro(t, 'clozeblank', function(arg)
    if CLOZE_MODE == 'full' then return '' end
    return '\\underline{\\hspace{' .. arg .. '}}'
  end)
  el.text = t
  return el
end

-- Block forms. `::: {.blank lines=6}` is empty work space; `::: {.cloze}`
-- hides a whole passage, blanked to roughly its own height (~90 chars/line).
-- data-lines carries the count semantically; --cloze-lines repeats it as a
-- custom property because CSS cannot read an attribute into a length (attr()
-- outside `content` is not portable), and parody-web needs the count to size
-- the ruled area: height = var(--cloze-lines) * line-height.
local function cloze_lines_html(n)
  return string.format(
    '<div class="cloze-lines" data-lines="%d" style="--cloze-lines: %d"></div>',
    n, n)
end

local function blank_div(el)
  if CLOZE_MODE == 'full' then return {} end
  local n = tonumber(el.attributes and el.attributes.lines) or 4
  return pandoc.RawBlock('html', cloze_lines_html(math.max(1, math.floor(n))))
end

local function cloze_div(el)
  if CLOZE_MODE == 'full' then
    return el.content
  elseif CLOZE_MODE == 'key' then
    return pandoc.Div(el.content, { class = 'cloze-key-block' })
  end
  local chars = pandoc.text.len(pandoc.utils.stringify(el.content))
  return pandoc.RawBlock('html', cloze_lines_html(
    math.max(1, math.ceil(chars / 90))))
end

-- ---- solutions-only ------------------------------------------------------
-- PARODY_SOLUTIONS: set when this run is rendering answer-key content (the
-- owner-gated `solutions` bucket), unset for section html and problem bodies.
--
-- A `.solutions-only` div belongs to the solutions manual. Print gates it with
-- \ifdefined\issolution (print.lua); the web has no solutions manual, so the
-- block is DROPPED here at build time rather than hidden — anything this
-- filter emits into section html is fetchable by any reader.
local SOLUTIONS = (os.getenv('PARODY_SOLUTIONS') or '') ~= ''

function Div(el)
  if el.classes:includes("solutions-only") and not SOLUTIONS then
    return {}
  -- A solution div nested in an .exercise is stripped by exercise() below;
  -- one that is NOT nested reached no handler at all and rendered as ordinary
  -- content. Drop it here so the gate does not depend on where it was written.
  -- (Solutions destined for the owner-gated bucket are converted from content
  -- the extractor has already unwrapped, so this never sees their fence.)
  elseif el.classes:includes("exercise-solution") and not SOLUTIONS then
    return {}
  elseif el.classes:includes("cloze") then
    return cloze_div(el)
  elseif el.classes:includes("blank") then
    return blank_div(el)
  elseif el.classes:includes("subfigures") then
    return subfigures(el)
  elseif el.classes:includes("subtables") then
    return subtables(el)
  elseif el.classes:includes("infobox") then
    return infoboxer(el)
  elseif el.classes:includes("definition") then
    return definition(el)
  elseif el.classes:includes("comment") then
    return comment(el)
  elseif el.classes:includes("theorem") then
    return theorem(el)
  elseif el.classes:includes("exercise") then
    return exercise(el)
  elseif el.classes:includes("example") then
    return example(el)
  elseif el.classes:includes("tabset") then
    return tabset(el)
  elseif el.classes:includes("editable-table") then
    -- Process tables with the "editable-table" class
    local inner = el.content[1]
    if inner and inner.t == "Table" then
      inner.classes:insert("editable-table")
      inner.identifier = el.identifier
      -- Pass caption attribute from div to table
      if el.attributes.caption and pandoc.Caption then
        inner.caption = pandoc.Caption(pandoc.Plain({pandoc.Str(el.attributes.caption)}))
      end
      return Table(inner)
    else
      return el
    end
  end
end

function Link(el)
  local path = el.target
  local text = pandoc.utils.stringify(el.content)

  if el.classes:includes("static") then
    local html = string.format('<a href="{%% static \'%s\' %%}">%s</a>', path, text)
    return pandoc.RawInline("html", html)
  elseif el.classes:includes("media") then
    local html = string.format('<a href="{%% media \'%s\' %%}">%s</a>', path, text)
    return pandoc.RawInline("html", html)
  end
end

function Image(el, notebook_slug, chapter_slug, base_name)
  local variant = cloze_variant_src(el)
  if variant then el.src = variant end
  local path = el.src
  local alt = ""
  if el.content then
    alt = pandoc.utils.stringify(el.content)
  end

  if el.classes:includes("static") then
    local html = string.format('<img src="{%% static \'%s\' %%}" alt="%s">', path, alt)
    return pandoc.RawInline("html", html)
  else
    local media_path = path
    local caption = alt
    local fig_id = ""
    local width_attr = ""
    local height_attr = ""

    -- Check for width parameter in attributes
    local width = el.attributes.width
    if width and width ~= "" then
      width_attr = string.format(' style="width: %s;"', width)
    end

    -- Check for height parameter in attributes
    local height = el.attributes.height
    if height and height ~= "" then
      if width_attr ~= "" then
        width_attr = string.format(' style="width: %s; height: %s;"', width or "auto", height)
      else
        width_attr = string.format(' style="height: %s;"', height)
      end
    end

    -- Normalize leading slash and media/ prefix for {% media %} usage
    if path:match("^/media/") then
      path = path:gsub("^/media/", "")
    end
    if path:match("^media/") then
      path = path:gsub("^media/", "")
    end
    if path:match("^/notebooks/") then
      path = path:gsub("^/", "")
    end

    -- If path already includes media hierarchy, keep it
    local has_full_path = path:match("^notebooks/") or path:match("^media/")

    -- If we have context from included content, build hierarchical path
    if not has_full_path and notebook_slug and notebook_slug ~= "" and chapter_slug and chapter_slug ~= "" and base_name then
      media_path = string.format("notebooks/%s/%s/%s_files/%s",
        notebook_slug, chapter_slug, base_name, path)
    end

    -- Extract caption and label from engcom-style alt text
    -- engcom typically generates alt text like "caption|label" or similar patterns
    if alt and alt ~= "" then
      -- Try to extract structured information from alt text
      local extracted_caption, extracted_label = alt:match("^(.-)%|(.+)$")
      if extracted_caption and extracted_label then
        caption = extracted_caption
        fig_id = extracted_label
      elseif alt ~= "png" and alt ~= "svg" and alt ~= "" then
        -- Use alt as caption if it's meaningful
        caption = alt
        -- Generate a simple ID from the image filename
        fig_id = path:match("([^/]+)%.[^%.]+$") or path:gsub("[^%w]", "-"):lower()
      end
    end

    -- Default caption if still empty or generic
    if caption == "" or caption == "png" or caption == "svg" then
      caption = "Figure"
    end

    -- Ensure we have an ID for figures
    if fig_id == "" then
      fig_id = path:match("([^/]+)%.[^%.]+$") or "fig"
      fig_id = fig_id:gsub("[^%w]", "-"):lower()
    end

    -- carry permission (licensed-art flag) onto the img so the renderer can
    -- swap it for a print-only placeholder on public pages (permission=permission)
    local perm = el.attributes and el.attributes['permission'] or ""
    local perm_attr = perm ~= "" and string.format(' data-permission="%s"', perm) or ""
    -- a caption-less subfigure panel ![](img){#fig:sub .subfigure} is a Para>Image
    -- (no Figure wrapper), so its id is lost once converted here — stash it on the
    -- img as data-subid for subfigures() to put back on the panel <figure>.
    local subid = ""
    if el.classes and el.classes:includes("subfigure") and el.identifier ~= "" then
      subid = string.format(' data-subid="%s"', el.identifier)
    elseif el.classes and el.identifier ~= ""
        and (el.classes:includes("figure") or el.classes:includes("standalone")) then
      -- a caption-less standalone figure ![](img){#fig:x .figure} is also a
      -- Para>Image — keep its id on the img so cross-refs land and number_artifact
      -- can promote it to a numbered <figure>.
      subid = string.format(' id="%s"', el.identifier)
    end
    -- Create figure element with proper structure for numbering
    local figure_html = string.format([[<img src="{%% media '%s' %%}" alt="%s"%s%s%s class="figure-img">]], media_path, alt, width_attr, perm_attr, subid)
    return pandoc.RawInline("html", figure_html)
  end
end

function Figure(el)
  -- Handle Pandoc Figure elements (newer Pandoc versions)
  -- Figure elements contain an Image and a caption

  if #el.content > 0 and el.content[1].content and #el.content[1].content > 0 and el.content[1].content[1].t == "Image" then
    local image = el.content[1].content[1]  -- Figure -> Plain -> Image
    local variant = cloze_variant_src(image)
    if variant then image.src = variant end
    local path = image.src
    local alt = pandoc.utils.stringify(image.content)

    -- Use the figure's caption if available, otherwise use image alt
    local caption = ""
    if el.caption and #el.caption > 0 then
      caption = pandoc.utils.stringify(el.caption)
    elseif alt and alt ~= "" then
      caption = alt
    end

    -- Get figure ID from attributes
    local fig_id = el.identifier or ""

    -- Check for width/height parameters in figure or image attributes
    local width_style = ""
    local width = nil
    local height = nil

    -- Extract width/height from image attributes
    if image.attr and image.attr.attributes then
      for k, v in pairs(image.attr.attributes) do
        if k == "width" then width = v end
        if k == "height" then height = v end
      end
    end

    -- Also check figure attributes
    if el.attr and el.attr.attributes then
      for k, v in pairs(el.attr.attributes) do
        if k == "width" and not width then width = v end
        if k == "height" and not height then height = v end
      end
    end

    if width and width ~= "" then
      width_style = string.format(' style="width: %s;"', width)
      if height and height ~= "" then
        width_style = string.format(' style="width: %s; height: %s;"', width, height)
      end
    elseif height and height ~= "" then
      width_style = string.format(' style="height: %s;"', height)
    end

    -- If this looks like an engcom-generated figure, extract info from the image
    if image.classes:includes("figure") or image.classes:includes("svg") then
      -- Build media path using context
      local media_path = path
      if notebook_slug and notebook_slug ~= "" and chapter_slug and chapter_slug ~= "" and base_name then
        media_path = string.format("notebooks/%s/%s/%s_files/%s",
          notebook_slug, chapter_slug, base_name, path)
      end

      -- Ensure we have a proper figure ID
      if fig_id == "" then
        fig_id = path:match("([^/]+)%.[^%.]+$") or "fig"
        fig_id = fig_id:gsub("[^%w]", "-"):lower()
      end

      -- Use the figure's original caption and ID structure
      -- This prevents duplication since we're replacing the entire Figure element
      local figcaption = caption ~= "" and caption or ""
      local figcaption_html = figcaption ~= "" and string.format('<figcaption class="figure-caption">%s</figcaption>', figcaption) or ""
      -- carry permission (licensed-art flag) so the renderer can show a
      -- print-only placeholder on public pages (permission=permission)
      local perm = (image.attr and image.attr.attributes['permission']) or ""
      local perm_attr = perm ~= "" and string.format(' data-permission="%s"', perm) or ""
      local figure_html = string.format([[
<figure id="%s" class="figure"%s>
  <img src="{%% media '%s' %%}" alt="%s" class="figure-img"%s>
  %s
</figure>]], fig_id, perm_attr, media_path, caption, width_style, figcaption_html)

      return pandoc.RawBlock("html", figure_html)
    end
  end

  -- For non-engcom figures, let Pandoc handle them normally
  return el
end

function Table(el)
  -- Add a class to identify this as a notes-table for custom styling
  if not el.classes:includes("notes-table") then
    el.classes:insert("notes-table")
  end
  -- If this table has the "editable-table" class, we will transform it into an interactive table
  if el.classes:includes("editable-table") then
    local rows = {}
    local table_id = el.identifier or "unknown"
    local caption_text = ""

    -- Extract caption text if available
    if el.caption and el.caption.long and #el.caption.long > 0 then
      caption_text = pandoc.utils.stringify(el.caption.long)
    end

    -- Helper function to convert cell contents while preserving MathJax
    local function cell_to_html(cell_contents)
      -- Use latex writer which preserves raw math, then convert basic formatting to HTML
      local temp_doc = pandoc.Pandoc(cell_contents)
      local latex_content = pandoc.write(temp_doc, "latex")

      -- Convert basic LaTeX commands to HTML while preserving math delimiters
      local html_content = latex_content
      -- Convert \textbf{} to <strong>
      html_content = html_content:gsub("\\textbf{([^}]*)}", "<strong>%1</strong>")
      -- Convert \textit{} to <em>
      html_content = html_content:gsub("\\textit{([^}]*)}", "<em>%1</em>")
      -- Convert \emph{} to <em>
      html_content = html_content:gsub("\\emph{([^}]*)}", "<em>%1</em>")
      -- Remove any paragraph breaks
      html_content = html_content:gsub("\n\n", " ")
      html_content = html_content:gsub("\n", " ")
      -- Trim whitespace
      html_content = html_content:match("^%s*(.-)%s*$")

      return html_content
    end

    -- Extract column headers for JSON export
    local column_headers = {}
    for col_index, cell in ipairs(el.head.rows[1].cells) do
      local val = cell_to_html(cell.contents)
      column_headers[col_index] = val
    end
    
    -- Extract row headers from first column of table body
    local row_headers = {}
    for row_index, row in ipairs(el.bodies[1].body) do
      if #row.cells > 0 then
        local first_cell = cell_to_html(row.cells[1].contents)
        -- Only use as row header if it's not empty and not an input field
        if first_cell ~= "" then
          row_headers[row_index] = first_cell
        end
      end
    end
    
    -- Build HTML for the table header
    local header_html = "<thead><tr>"
    for col_index, cell in ipairs(el.head.rows[1].cells) do
      -- Convert cell contents to HTML while preserving MathJax
      local val = cell_to_html(cell.contents)
      header_html = header_html .. "<th>" .. val .. "</th>"
    end
    header_html = header_html .. "</tr></thead>"

    -- Build HTML for the table body
    local body_html = "<tbody>"
    for row_index, row in ipairs(el.bodies[1].body) do
      body_html = body_html .. "<tr>"
      for col_index, cell in ipairs(row.cells) do
        local val = cell_to_html(cell.contents)
        if val ~= "" then
          body_html = body_html .. string.format('<td>%s</td>', val)
        else
          body_html = body_html .. string.format(
            '<td><input name="cell-%d-%d" type="text" class="input input-bordered text-sm" style="min-width: 120px; width: 120px;" value="{%% get_cell \"%s\" %d %d %%}" /></td>',
            row_index, col_index, table_id, row_index, col_index
          )
        end
      end
      body_html = body_html .. "</tr>"
    end
    body_html = body_html .. "</tbody>"

    local hidden_input = string.format('<input type="hidden" name="table_id" value="%s">', table_id)

    local anchor_input = string.format('<input type="hidden" name="anchor" value="%s">', table_id)

    -- Generate caption HTML if available
    local caption_html = ""
    if caption_text ~= "" then
      caption_html = string.format('<div class="table-caption">%s</div>', caption_text)
    end

    -- Build JSON strings for headers (escape quotes for HTML attributes)
    local column_headers_json = "{"
    local first_col = true
    for i, header in pairs(column_headers) do
      if not first_col then column_headers_json = column_headers_json .. "," end
      column_headers_json = column_headers_json .. string.format('"%d":"%s"', i, header:gsub('"', '&quot;'))
      first_col = false
    end
    column_headers_json = column_headers_json .. "}"
    
    local row_headers_json = "{"
    local first_row = true
    for i, header in pairs(row_headers) do
      if not first_row then row_headers_json = row_headers_json .. "," end
      row_headers_json = row_headers_json .. string.format('"%d":"%s"', i, header:gsub('"', '&quot;'))
      first_row = false
    end
    row_headers_json = row_headers_json .. "}"

    local full_table = string.format([[
<div id="%s" class="editable-table-anchor scroll-mt-20" data-column-headers='%s' data-row-headers='%s'>
%s
<form method="POST" class="editable-table-wrapper">
  {%% csrf_token %%}
  %s
  %s
  <div class="overflow-x-auto">
    <table class="table table-zebra w-full">
      %s
      %s
    </table>
  </div>
  <div class="flex gap-2 mt-2">
    <button class="btn btn-primary" type="submit">Save</button>
    <a href="{%% url 'teaching:export_table_data' notebook.slug chapter.slug section.slug '%s' %%}"
       class="btn btn-outline"
       download="%s-data.json">Download JSON</a>
  </div>
</form>
</div>
    ]], table_id, column_headers_json, row_headers_json, caption_html, hidden_input, anchor_input, header_html, body_html, table_id, table_id)

    return pandoc.RawBlock("html", full_table)
  end
  
  return el
end

function Span(el)
    -- `.solutions-only` means the same mid-sentence as it does on a block, and
    -- a sentence is where an answer is most likely to be written inline. Drop
    -- the run and keep the prose around it. See the Div handler for the gate.
    if el.classes:includes("solutions-only") and not SOLUTIONS then
        return {}
    end
    if el.classes:includes("cloze") then
        return clozer(el)
    elseif el.classes:includes("blank") then
        return blanker(el)
    end
    if el.classes:includes("cite") then
        -- Collect all text content from the span
        local cite_text = pandoc.utils.stringify(el.content)

        -- Trim whitespace from the entire citation text
        if cite_text then
            cite_text = cite_text:match("^%s*(.-)%s*$")
        end

        if cite_text and cite_text ~= "" then
            -- Check for no-parentheses classes
            local no_parens = el.classes:includes("plain") or el.classes:includes("no-parentheses")

            -- Extract post note if present (format: "key|post note" or "key1,key2|post note")
            local post_note = nil
            local pipe_pos = cite_text:find("|")
            if pipe_pos then
                post_note = cite_text:sub(pipe_pos + 1):match("^%s*(.-)%s*$") -- trim whitespace
                cite_text = cite_text:sub(1, pipe_pos - 1):match("^%s*(.-)%s*$") -- trim whitespace
            end

            -- Build additional arguments
            local args = {}
            if no_parens then
                table.insert(args, '"no-parentheses"')
            end
            if post_note and post_note ~= "" then
                table.insert(args, string.format('note="%s"', post_note))
            end
            local args_str = ""
            if #args > 0 then
                args_str = " " .. table.concat(args, " ")
            end

            -- If there are commas, use cite_many tag; otherwise, use cite
            local django_tag
            if cite_text:find(",") then
                -- Split by commas, trim whitespace
                local keys = {}
                for key in cite_text:gmatch("([^,]+)") do
                    -- Trim whitespace from each key
                    key = key:match("^%s*(.-)%s*$")
                    if key ~= "" then
                        table.insert(keys, key)
                    end
                end
                -- Only generate cite_many if we have keys
                if #keys > 0 then
                    local keys_str = '"' .. table.concat(keys, '" "') .. '"'
                    if no_parens then
                        keys_str = keys_str .. ' "no-parentheses"'
                    end
                    django_tag = string.format('{%% cite_many %s %%}', keys_str)
                    return pandoc.RawInline("html", django_tag)
                end
            else
                django_tag = string.format('{%% cite "%s"%s %%}', cite_text, args_str)
                return pandoc.RawInline("html", django_tag)
            end
        end
    end

    return el
end

function Str(el)
    -- Convert em-dashes: --- becomes —
    -- Also handle -- to en-dash (–) for better typography
    -- But be careful not to convert markdown-style horizontal rules
    
    if el.text then
        -- Replace em-dash (three hyphens)
        -- Only replace if not at boundaries (to avoid affecting code/math)
        el.text = el.text:gsub("%-%-%-", "—")
        
        -- Replace en-dash (two hyphens) with spaces or letters on either side
        -- This is more conservative to avoid breaking markdown constructs
        el.text = el.text:gsub("([%w%s%)])%-%-([%w%s%(])", "%1–%2")
    end
    
    return el
end

-- Remove explicit return table to allow Pandoc to find all global functions
