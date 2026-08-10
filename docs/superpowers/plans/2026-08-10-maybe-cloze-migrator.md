# `\maybe*` and cloze-package migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `parody/migrate/filters/latex-to-md.lua` convert the `\maybe*`
macro family and the traditional `cloze` package's `\cloze` into the `.cloze` /
`.infobox` authoring surface that `filter.lua` and `print.lua` already render,
so migrated fill-in-the-blank content blanks instead of silently revealing its
answer.

**Architecture:** One shared brace-matched argument reader (`read_args`) plus two
recursive conversion helpers (`convert_inlines`, `convert_blocks`) replace the
brace-naive Lua patterns every handler currently uses. Each `\maybe*` handler is
then a thin mapping onto `.cloze` or `.infobox`. `\cloze` inside math is
deliberately untouched — the renderers already handle the macro there.

**Tech Stack:** Lua 5.4 (pandoc's embedded interpreter), pandoc 3.6.1 pinned via
`pypandoc-binary==1.15`, pytest.

## Global Constraints

- Target only the authoring surface defined by
  `docs/superpowers/specs/2026-08-06-cloze-rendering-design.md` (#507):
  `[X]{.cloze}`, `::: {.cloze}`, `::: {#id .infobox title="…"}`. Add nothing to
  `filter.lua`, `print.lua`, the profile `.sty` files, or the artifact schema.
- The canonical infobox form is `::: {#id .infobox title="…"}` — verified against
  migrated content in `~/real-time-computing-parody`. Do **not** copy
  `replace_infobox`'s legacy `infobox_name` sub-div shape; that is a separate
  wart.
- `\cloze` inside a `Math` node must emerge byte-identical. `filter.lua:848` and
  `print.lua` rewrite it; converting it in the migrator breaks the working case.
- `\examplemaybe`'s semantic mapping does not change. It is the `--solutions`
  axis. It is touched only to adopt `read_args`.
- Dispatch is `starts_with`, so longer macro names must be tested first:
  `\maybeeqn` → `\maybeeq` → `\mayben{` → `\maybe{` → `\mayb{`. The trailing
  brace on `\mayb{` is load-bearing and must stay.
- Never `git add -A` — this worktree shares a repo with concurrent sessions
  (`never-git-add-dash-a-in-shared-worktrees`). Stage named paths only.
- A version bump must commit `uv.lock` alongside `pyproject.toml`
  (`version-bumps-must-commit-uv-lock`).

---

## File Structure

| file | responsibility |
|---|---|
| `parody/migrate/filters/latex-to-md.lua` | all conversion logic (single-file filter, existing pattern — do not split) |
| `tests/test_latex_to_md.py` | per-construct migrator assertions |
| `tests/test_cloze.py` | end-to-end migrate → render leak test |
| `pyproject.toml`, `uv.lock` | version bump |

Helpers go immediately after `starts_with` (line 134–136) so every handler below
can see them. Handlers stay where they are.

---

### Task 1: Shared argument reader, recursive conversion, and `\cloze`

**Files:**
- Modify: `parody/migrate/filters/latex-to-md.lua:134-151` (add helpers after
  `starts_with`; rewrite `clozer` and `clozer_block`)
- Modify: `parody/migrate/filters/latex-to-md.lua:882` and `:960` (dispatch)
- Test: `tests/test_latex_to_md.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `read_args(text, n)` → table of `n` argument strings (outer braces stripped,
    leading `%`-comment debris trimmed), or `nil` if fewer than `n` are present.
  - `convert_inlines(tex)` → list of Inline, LaTeX parsed and walked with `inline_filter`.
  - `convert_blocks(tex)` → list of Block, LaTeX parsed and walked with `block_filter`.
  - `warn(fmt, ...)` → writes `latex-to-md: …` to stderr.
  - `excerpt(text)` → first 60 chars of `text`, newlines collapsed, for warnings.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_latex_to_md.py`:

```python
CLOZE_TEX = textwrap.dedent(r"""
    \section[S]{cloze-sample}{bk}{Cloze sample}

    The damping ratio is \cloze{0.707} here.

    A nested one: \cloze{\keyword{stationary point}} ok.

    Inline math: $\tau = \cloze{RC}$ done.

    \begin{align}
      y &= \cloze{g(x)} \label{eq:o}
    \end{align}
    """)


def convert_src(tmp_path, tex, name="sample.tex"):
    src = tmp_path / "src"
    src.mkdir(exist_ok=True)
    path = src / name
    path.write_text(tex)
    return convert_latex_file(path, src)


def test_cloze_becomes_a_cloze_span(tmp_path):
    out = convert_src(tmp_path, CLOZE_TEX)
    assert "[0.707]{.cloze}" in out


def test_cloze_argument_survives_nested_braces(tmp_path):
    out = convert_src(tmp_path, CLOZE_TEX)
    # brace-naive extraction captured "\keyword{stationary point" and dropped
    # the closing brace; the whole phrase must survive
    assert "stationary point" in out
    assert "{.cloze}" in out


def test_cloze_argument_is_recursively_converted(tmp_path):
    out = convert_src(tmp_path, CLOZE_TEX)
    # the inner \keyword must become a .keyword span, not a raw string
    assert ".keyword" in out


def test_cloze_inside_math_is_left_alone(tmp_path):
    out = convert_src(tmp_path, CLOZE_TEX)
    assert r"\cloze{RC}" in out
    assert r"\cloze{g(x)}" in out
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_latex_to_md.py -k cloze -v`

Expected: `test_cloze_argument_survives_nested_braces` and
`test_cloze_argument_is_recursively_converted` FAIL. The nested case currently
yields `[\keyword{stationary point]{.cloze}`-style debris because
`match("{(.-)}")` stops at the first `}`.

- [ ] **Step 3: Add the helpers**

Insert after `starts_with` (currently ends line 136):

```lua
-- Read the first `n` brace-delimited arguments of a macro, honouring nesting.
-- The old `{(.-)}` / `{.-}{(.-)}{.-}` patterns stop at the first `}` and
-- mis-split every nested argument; this is the only extractor handlers use.
local function read_args(text, n)
  local args, pos = {}, 1
  for _ = 1, n do
    local s, e = text:find('%b{}', pos)
    if not s then return nil end
    -- strip outer braces, then LaTeX line-continuation debris (a `%` comment
    -- and its newline) that authors put after the opening brace
    args[#args + 1] = text:sub(s + 1, e - 1):gsub('^%s*%%?%s*', '')
    pos = e + 1
  end
  return args
end

-- Convert a LaTeX argument, running the migrator's own handlers over it, so
-- nested macros (\keyword, \myindex, ...) convert instead of passing through
-- as a raw string.
local function convert_blocks(tex)
  local blocks = pandoc.read(tex, 'latex+raw_tex').blocks
  for i = 1, #blocks do
    blocks[i] = pandoc.walk_block(blocks[i], block_filter)
  end
  return blocks
end

local function convert_inlines(tex)
  local inlines = pandoc.utils.blocks_to_inlines(convert_blocks(tex))
  return pandoc.walk_inline(pandoc.Span(inlines), inline_filter).content
end

local function excerpt(text)
  return (text:gsub('%s+', ' '):sub(1, 60))
end

local function warn(fmt, ...)
  io.stderr:write('latex-to-md: ' .. string.format(fmt, ...) .. '\n')
end
```

- [ ] **Step 4: Rewrite `clozer` and `clozer_block`**

Replace the bodies at lines 143–151:

```lua
local function clozer(element)
  local args = read_args(element.text, 1)
  if not args then return element end
  return pandoc.Span(convert_inlines(args[1]), {class = 'cloze'})
end

local function clozer_block(element)
  local args = read_args(element.text, 1)
  if not args then return element end
  return pandoc.Div(convert_blocks(args[1]), {class = 'cloze'})
end
```

`clozer_block` previously built `pandoc.Para(string, {class=…})` — `Para` takes
no attr and no string, so it was doubly wrong; it becomes a `Div`.

- [ ] **Step 5: Tighten the dispatch**

`RawInline` line 882 and `RawBlock` line 960 currently match bare `\\cloze`,
which also swallows `\clozeline`, `\clozefil`, etc. In **both** functions,
replace the single branch with:

```lua
  elseif starts_with('\\cloze{', el.text) then
    return clozer(el)          -- clozer_block(el) in RawBlock
  elseif starts_with('\\clozeset', el.text) then
    return {}
```

Leave the unhandled-variant warning to Task 5.

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run pytest tests/test_latex_to_md.py -v`

Expected: PASS, including the pre-existing tests. If the markdown writer emits a
differently-spelled but equivalent span, pin the assertion to what it actually
writes rather than reshaping the filter.

- [ ] **Step 7: Commit**

```bash
git add parody/migrate/filters/latex-to-md.lua tests/test_latex_to_md.py
git commit -m "migrate: brace-matched arg reader and recursive cloze conversion (task #542)"
```

---

### Task 2: `\mayb` → `.cloze`

**Files:**
- Modify: `parody/migrate/filters/latex-to-md.lua:559-587` (`replace_mayb`, `replace_mayb_inline`)
- Test: `tests/test_latex_to_md.py`

**Interfaces:**
- Consumes: `read_args`, `convert_inlines`, `convert_blocks` from Task 1.
- Produces: nothing new.

- [ ] **Step 1: Write the failing test**

```python
MAYB_TEX = textwrap.dedent(r"""
    \section[S]{mayb-sample}{bk}{Mayb sample}

    The answer is \mayb{42} and that is all.
    """)


def test_mayb_becomes_a_cloze_span(tmp_path):
    out = convert_src(tmp_path, MAYB_TEX)
    assert "[42]{.cloze}" in out
    assert "maybe" not in out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_latex_to_md.py -k mayb -v`
Expected: FAIL — output contains `class="maybe"` / `{.maybe}`, which no renderer
knows.

- [ ] **Step 3: Replace both handlers**

```lua
local function replace_mayb(el)
  local args = read_args(el.text, 1)
  if not args then return el end
  return pandoc.Div(convert_blocks(args[1]), {class = 'cloze'})
end

local function replace_mayb_inline(el)
  local args = read_args(el.text, 1)
  if not args then return el end
  return pandoc.Span(convert_inlines(args[1]), {class = 'cloze'})
end
```

The `align`-to-`aligned` string rewriting in the old bodies is dropped
deliberately: pandoc's LaTeX reader turns `\begin{align*}…\end{align*}` into a
`DisplayMath` node natively, which `convert_blocks` now gets for free. The old
rewrite also had a truncated pattern (`\\end{align%*?` with no closing brace,
lines 568 and 581).

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_latex_to_md.py -k mayb -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add parody/migrate/filters/latex-to-md.lua tests/test_latex_to_md.py
git commit -m "migrate: route \\mayb through .cloze (task #542)"
```

---

### Task 3: `\maybeeq` → block `.cloze`

**Files:**
- Modify: `parody/migrate/filters/latex-to-md.lua:488-503` (`replace_maybeeq`),
  `:524-539` (`replace_maybeeq_inline`)
- Test: `tests/test_latex_to_md.py`

**Interfaces:**
- Consumes: `read_args`, `convert_blocks` from Task 1.
- Produces: nothing new.

- [ ] **Step 1: Write the failing test**

```python
MAYBEEQ_TEX = textwrap.dedent(r"""
    \section[S]{maybeeq-sample}{bk}{Maybeeq sample}

    \maybeeq{%
    \begin{align*}
      v_k = \frac{Z_k}{Z_1 + Z_2} v_\text{in}.
    \end{align*}
    }
    """)


def test_maybeeq_becomes_a_cloze_div(tmp_path):
    out = convert_src(tmp_path, MAYBEEQ_TEX)
    assert "{.cloze}" in out
    assert "v_k" in out
    assert "maybeeq" not in out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_latex_to_md.py -k maybeeq -v`
Expected: FAIL — output carries `maybe maybeeq` classes.

- [ ] **Step 3: Replace both handlers**

```lua
local function replace_maybeeq(el)
  local args = read_args(el.text, 1)
  if not args then return el end
  return pandoc.Div(convert_blocks(args[1]), {class = 'cloze'})
end

local function replace_maybeeq_inline(el)
  local args = read_args(el.text, 1)
  if not args then return el end
  return pandoc.Div(convert_blocks(args[1]), {class = 'cloze'})
end
```

Both return a `Div`: `\maybeeq` is always a display box in the source
(`eqboxtwo`), even where pandoc happened to hand it to us as a `RawInline`. The
`RawInline` handler returning a Block is fine — pandoc's markdown writer accepts
it because the surrounding `Para` is rewritten wholesale by the walk.

If pandoc rejects a Block from an inline position at Step 4, wrap instead:
return `pandoc.Span(pandoc.utils.blocks_to_inlines(convert_blocks(args[1])), {class = 'cloze'})`
from `replace_maybeeq_inline` only.

The coloured `eqboxtwo` frame is dropped — an `.infobox` with no title renders an
empty heading, which is worse. Recorded as an accepted fidelity loss in the spec.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_latex_to_md.py -k maybeeq -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add parody/migrate/filters/latex-to-md.lua tests/test_latex_to_md.py
git commit -m "migrate: route \\maybeeq through .cloze (task #542)"
```

---

### Task 4: `\maybeeqn`, `\mayben`, `\maybe` → `.infobox` wrapping `.cloze`

**Files:**
- Modify: `parody/migrate/filters/latex-to-md.lua:505-522` (`replace_maybeeqn`,
  currently a commented-out stub returning `el`), `:541-557`
  (`replace_maybeeqn_inline`)
- Modify: `parody/migrate/filters/latex-to-md.lua:918-923` and `:1010-1015` (dispatch order)
- Test: `tests/test_latex_to_md.py`

**Interfaces:**
- Consumes: `read_args`, `convert_blocks`, `convert_inlines` from Task 1.
- Produces:
  - `maybe_infobox(el)` → `Div` with class `infobox`, identifier from arg 2 (empty
    ⇒ no identifier), `title` attribute from arg 1, containing one `Div` of class
    `cloze` built from arg 3.
  - `maybe_block(el)` → `Div` of class `cloze` from arg 1, for `\maybe`.

- [ ] **Step 1: Write the failing test**

```python
MAYBEEQN_TEX = textwrap.dedent(r"""
    \section[S]{maybeeqn-sample}{bk}{Maybeeqn sample}

    \maybeeqn{general impedance voltage divider}{eq:vdiv}{%
    For the output voltage across impedance $Z_k$ we have
    \begin{align*}
      v_k = \frac{Z_k}{Z_1 + Z_2} v_\text{in}.
    \end{align*}
    }

    \maybeeqn{piecewise linear diode model}{}{%
    \begin{align*}
      i_D = 0.
    \end{align*}
    }
    """)


def test_maybeeqn_becomes_a_titled_infobox(tmp_path):
    out = convert_src(tmp_path, MAYBEEQN_TEX)
    assert '.infobox' in out
    assert 'title="general impedance voltage divider"' in out
    assert '#eq:vdiv' in out


def test_maybeeqn_hides_only_its_contents(tmp_path):
    out = convert_src(tmp_path, MAYBEEQN_TEX)
    # the box survives; a .cloze div nests inside it
    assert '{.cloze}' in out
    assert 'v_k' in out


def test_maybeeqn_empty_label_yields_no_identifier(tmp_path):
    out = convert_src(tmp_path, MAYBEEQN_TEX)
    assert 'title="piecewise linear diode model"' in out
    assert '#labelme' not in out
    assert '{# ' not in out


def test_maybeeqn_body_prose_survives(tmp_path):
    out = convert_src(tmp_path, MAYBEEQN_TEX)
    assert "For the output voltage" in out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_latex_to_md.py -k maybeeqn -v`
Expected: FAIL — the block handler returns `el` unchanged, so the raw
`\maybeeqn{…}` LaTeX is still in the output.

- [ ] **Step 3: Write the handlers**

Replace `replace_maybeeqn` and `replace_maybeeqn_inline` with a shared builder:

```lua
-- \maybeeqn{title}{label}{body} and \mayben{title}{label}{body}: the box, its
-- title and its cross-ref target stay visible; only the contents hide.
local function maybe_infobox(el)
  local args = read_args(el.text, 3)
  if not args then return el end
  local title = pandoc.utils.stringify(convert_inlines(args[1]))
  local label = args[2]:gsub('%%', ''):gsub('^%s*(.-)%s*$', '%1')
  local inner = pandoc.Div(convert_blocks(args[3]), {class = 'cloze'})
  return pandoc.Div({inner}, pandoc.Attr(label, {'infobox'}, {title = title}))
end

-- \maybe{body}: an unframed, untitled box whose contents hide.
local function maybe_block(el)
  local args = read_args(el.text, 1)
  if not args then return el end
  return pandoc.Div(convert_blocks(args[1]), {class = 'cloze'})
end
```

Then point both old names at it, so the dispatch sites need no renaming:

```lua
local function replace_maybeeqn(el) return maybe_infobox(el) end
local function replace_maybeeqn_inline(el) return maybe_infobox(el) end
```

- [ ] **Step 4: Fix the dispatch order and add the new macros**

In `RawInline`, replace lines 918–923 with:

```lua
  elseif starts_with('\\maybeeqn', el.text) then
    return maybe_infobox(el)
  elseif starts_with('\\maybeeq', el.text) then
    return replace_maybeeq_inline(el)
  elseif starts_with('\\mayben{', el.text) then
    return maybe_infobox(el)
  elseif starts_with('\\maybe{', el.text) then
    return maybe_block(el)
  elseif starts_with('\\mayb{', el.text) then
    return replace_mayb_inline(el)
```

In `RawBlock`, replace lines 1010–1015 with the same chain, using
`replace_maybeeq` and `replace_mayb` for the two block forms, and keeping the
`\examplemaybe` branch that follows.

Order matters: `\maybeeqn` before `\maybeeq` before `\mayben{` before `\maybe{`
before `\mayb{`. Test `\maybeeqn` first or it routes into `\maybe` and silently
loses its title and label.

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_latex_to_md.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add parody/migrate/filters/latex-to-md.lua tests/test_latex_to_md.py
git commit -m "migrate: route \\maybeeqn/\\mayben/\\maybe through .infobox + .cloze (task #542)"
```

---

### Task 5: Warnings for unhandled macros

**Files:**
- Modify: `parody/migrate/filters/latex-to-md.lua` (`RawInline`, `RawBlock`
  cloze branches; new global `Math` handler)
- Test: `tests/test_latex_to_md.py`

**Interfaces:**
- Consumes: `warn`, `excerpt` from Task 1.
- Produces: global `Math(el)` returning `el` unchanged.

- [ ] **Step 1: Write the failing test**

`convert_latex_file` returns markdown, not stderr, so assert on both the
passthrough and the warning via captured stderr:

```python
UNHANDLED_TEX = textwrap.dedent(r"""
    \section[S]{unhandled}{bk}{Unhandled}

    A fixed blank: \clozeline[3cm] here.
    """)


def test_unhandled_cloze_macro_passes_through_with_a_warning(tmp_path, capfd):
    out = convert_src(tmp_path, UNHANDLED_TEX)
    assert "clozeline" in out          # left raw, not silently swallowed
    err = capfd.readouterr().err
    assert "latex-to-md" in err
    assert "clozeline" in err
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_latex_to_md.py -k unhandled -v`
Expected: FAIL — no warning is emitted (the file has no warning facility, and
after Task 1 the branch no longer matches bare `\cloze`).

- [ ] **Step 3: Add the warning branches**

In both `RawInline` and `RawBlock`, after the `\clozeset` branch:

```lua
  elseif starts_with('\\cloze', el.text) then
    warn('unhandled cloze-package macro, left raw: %s', excerpt(el.text))
    return el
```

Add a global `Math` handler near `Figure` (line 929):

```lua
-- \cloze inside math is intentional and handled by filter.lua/print.lua.
-- \maybe* inside math is not known to any renderer — say so rather than let it
-- pass through silently.
function Math(el)
  if el.text:find('\\mayb') then
    warn('\\maybe* macro inside math (no renderer support): %s', excerpt(el.text))
  end
  return el
end
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_latex_to_md.py -v`
Expected: PASS. If `capfd` shows nothing, `parody/migrate/latex_to_md.py` is
swallowing pandoc's stderr — check how it invokes pandoc and let stderr through
rather than weakening the test.

- [ ] **Step 5: Commit**

```bash
git add parody/migrate/filters/latex-to-md.lua tests/test_latex_to_md.py
git commit -m "migrate: warn on unhandled cloze macros and \\maybe* in math (task #542)"
```

---

### Task 6: `\examplemaybe` adopts `read_args` — **DROPPED**

**Outcome: not done, deliberately.** Step 2 showed the test passing against the
unmodified handler. The premise was wrong: `{.-}{(.-)}{.-}{.-}` is followed by
more groups, so Lua backtracks to a parse consistent with all four — the correct
split for balanced input. Verified with `\frac{a}{b}` and `\textbf{…}` nesting.
Only `clozer`'s trailing-context-free `{(.-)}` genuinely breaks.

The handler is left untouched (70 call sites, no demonstrated defect). The test
is kept as a characterisation guard. Original task text follows for the record.



**Files:**
- Modify: `parody/migrate/filters/latex-to-md.lua:589-600`
- Test: `tests/test_latex_to_md.py`

**Interfaces:**
- Consumes: `read_args` from Task 1.
- Produces: nothing new. Output shape is unchanged.

- [ ] **Step 1: Write the failing test**

```python
EXAMPLEMAYBE_TEX = textwrap.dedent(r"""
    \section[S]{example-sample}{bk}{Example sample}

    \examplemaybe{A title}{Find $\frac{a}{b}$ when $a=1$.}{Because
    $\frac{a}{b}$ is one half, the answer is $0.5$.}{ex:halves}
    """)


def test_examplemaybe_splits_nested_arguments(tmp_path):
    out = convert_src(tmp_path, EXAMPLEMAYBE_TEX)
    assert ".example" in out
    assert "the answer is" in out       # solution not truncated at \frac{a}{b}
    assert "ex:halves" in out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_latex_to_md.py -k examplemaybe -v`
Expected: FAIL — `{.-}{(.-)}{.-}{.-}` mis-splits on the `\frac{a}{b}` braces, so
the problem/solution boundary lands in the wrong place.

- [ ] **Step 3: Swap in the shared reader**

Replace lines 592–600 (the three `match` calls and the label scrubbing) with:

```lua
  local args = read_args(el.text, 4)
  if not args then return el end
  local problem, solution, label = args[2], args[3], args[4]
  label = label:gsub('%%', ''):gsub('^%s*(.-)%s*$', '%1')
```

Everything from `local problem_blocks = …` onward is unchanged.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_latex_to_md.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add parody/migrate/filters/latex-to-md.lua tests/test_latex_to_md.py
git commit -m "migrate: brace-matched argument split for \\examplemaybe (task #542)"
```

---

### Task 7: End-to-end leak test

**Files:**
- Modify: `tests/test_cloze.py` (append a section)
- Test: same file

**Interfaces:**
- Consumes: `web(md, mode)` from `tests/test_cloze.py:116`,
  `convert_latex_file` from `parody.migrate.latex_to_md`.
- Produces: nothing.

This is the load-bearing test. Everything above asserts the migrator writes the
right markdown; this asserts the whole chain actually blanks the answer, which
is the failure the task exists to fix.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_cloze.py`:

```python
# --- end to end: migrated LaTeX must actually blank ------------------------

import textwrap  # noqa: E402

from parody.migrate.latex_to_md import convert_latex_file  # noqa: E402

MIGRATION_TEX = textwrap.dedent(r"""
    \section[S]{leak}{bk}{Leak check}

    The damping ratio is \mayb{ZETASECRET} here.

    \maybeeqn{a titled result}{eq:leak}{%
    \begin{align*}
      v = VSECRET.
    \end{align*}
    }
    """)


def test_migrated_clozes_do_not_leak_in_blank_mode(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    tex = src / "leak.tex"
    tex.write_text(MIGRATION_TEX)
    md = convert_latex_file(tex, src)

    # the migrator keeps the answers -- they live in the markdown source
    assert "ZETASECRET" in md and "VSECRET" in md

    out = web(md, "blank")
    assert "ZETASECRET" not in out, "inline cloze leaked its answer"
    assert "VSECRET" not in out, "block cloze leaked its answer"
    # the box and its title survive the blanking
    assert "a titled result" in out


def test_migrated_clozes_show_in_full_mode(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    tex = src / "leak.tex"
    tex.write_text(MIGRATION_TEX)
    md = convert_latex_file(tex, src)

    out = web(md, "full")
    assert "ZETASECRET" in out
    assert "VSECRET" in out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_cloze.py -k migrated -v`

Expected on a clean checkout of `main`: FAIL, with the answers present in
`blank` mode — the exact defect. After Tasks 1–6 it should pass; run it against
the current branch and confirm it passes for the right reason (temporarily
revert Task 2's handler if you want to see it fail).

- [ ] **Step 3: Run the whole suite**

Run: `uv run pytest -q`

Expected: PASS. Golden artifacts are unaffected — no book in `tests/golden/`
uses these macros — so `tests/test_golden_artifacts.py` must pass unchanged. If
it does not, something in `convert_blocks` is reaching content it should not.

- [ ] **Step 4: Commit**

```bash
git add tests/test_cloze.py
git commit -m "test: end-to-end migrate to blank-mode leak check (task #542)"
```

---

### Task 8: Real-corpus smoke check

**Files:**
- None modified. This is a verification task.

**Interfaces:**
- Consumes: the finished filter.
- Produces: a go/no-go on the release.

The fixtures are synthetic. The corpus has 274 `\maybe*` and 96 `\cloze` call
sites; run the converter over real chapters before releasing.

- [ ] **Step 1: Convert real chapters and look for debris**

```bash
uv run python -c "
from pathlib import Path
from parody.migrate.latex_to_md import convert_latex_file
src = Path.home() / 'electronics-primer' / 'electronics'
for name in ['ch03_00.tex', 'ch04_00.tex']:
    out = convert_latex_file(src / name, src)
    print(name, 'maybe-debris:', out.count('maybeeq') + out.count('{.maybe'), 'clozes:', out.count('{.cloze}'))
"
```

Expected: `maybe-debris: 0` and a non-zero cloze count for both files.

- [ ] **Step 2: Repeat for the highest-volume book**

```bash
uv run python -c "
from pathlib import Path
from parody.migrate.latex_to_md import convert_latex_file
src = Path.home() / 'system-dynamics-book' / 'systems'
out = convert_latex_file(src / 'ch_lap.tex', src)
print('maybe-debris:', out.count('maybeeq') + out.count('{.maybe'), 'clozes:', out.count('{.cloze}'))
"
```

Expected: `maybe-debris: 0`, clozes > 0.

- [ ] **Step 3: Record the numbers**

No commit. Report the counts; if any file still shows debris, stop and diagnose
before releasing.

---

### Task 9: Release

**Files:**
- Modify: `pyproject.toml:3`, `uv.lock`

**Interfaces:**
- Consumes: a green suite from Task 7 and a clean smoke check from Task 8.
- Produces: `parody` on PyPI.

- [ ] **Step 1: Re-derive the version against `main`**

```bash
git fetch origin main && git show origin/main:pyproject.toml | grep '^version'
```

`main` moves via parallel sessions; an identical version on both sides merges
with no conflict and silently ships a duplicate release
(`recheck-version-against-main-before-merging`). Branch base is `0.29.3`; the
target is the next **minor** (`0.30.0`) because migrator output changes shape.
If `main` has already moved past `0.30.0`, take the next free minor.

- [ ] **Step 2: Bump and refresh the lock**

```bash
uv version 0.30.0 && uv lock
```

`uv.lock` pins the project's own version; a bump that touches only
`pyproject.toml` leaves the lock stale (`version-bumps-must-commit-uv-lock`).

- [ ] **Step 3: Commit both files together**

```bash
git add pyproject.toml uv.lock
git commit -m "0.30.0: route \\maybe* and cloze-package macros through cloze in the migrator"
```

- [ ] **Step 4: Merge to main and push**

```bash
git checkout main && git pull && git merge --no-ff clever-beacon && uv run pytest -q && git push origin main
```

Run the suite **after** the merge, before the push — the merge may pull in
another session's work.

- [ ] **Step 5: Publish to PyPI**

This step is outward-facing and irreversible — a version cannot be unpublished.
Confirm with the user before running it.

```bash
rm -rf dist && uv build && uvx twine upload dist/*
```

Credentials are in `~/.pypirc`; `twine` is not installed, hence `uvx`. CI does
not auto-publish.

- [ ] **Step 6: Verify the upload**

```bash
uv run --with parody==0.30.0 --no-project python -c "import parody; print(parody.__file__)"
```

Expected: resolves and prints a path.

**Deliberately not done:** the rest of the `rtcbook-deploy-release-chain`
(content pin, content tag, rtcbook-web deploy). This change alters only what
`parody migrate` *produces*; rtc's markdown is already migrated and the migrator
does not run at build time, so a content rebuild and site deploy would be a
no-op re-release. Bumping the content repo's `build.yml` parody pin is optional
hygiene, not a requirement of this change.

---

## Self-Review

**Spec coverage:**

| spec requirement | task |
|---|---|
| `\mayb` → `[X]{.cloze}` / `::: {.cloze}` | 2 |
| `\maybe` → `::: {.cloze}` | 4 |
| `\mayben` → `.infobox` + `.cloze` | 4 |
| `\maybeeq` → `::: {.cloze}` | 3 |
| `\maybeeqn` → `.infobox` + `.cloze`, empty label ⇒ no id | 4 |
| `\cloze` in prose → `[X]{.cloze}` | 1 |
| `\cloze` in math untouched | 1 |
| `\clozeset` dropped | 1 |
| other `\cloze*` raw + warning | 5 |
| shared `%b{}` `read_args` | 1 |
| recursive argument conversion | 1 |
| dispatch ordering | 4 |
| `warn()` facility; `\mayb*`-in-math warning | 5 |
| `\examplemaybe` reader swap, semantics unchanged | 6 |
| end-to-end blank-mode leak test | 7 |
| golden artifacts unchanged | 7, step 3 |

No gaps.

**Placeholder scan:** every code step carries real code; no TBD, no "similar to
Task N", no "add error handling". Task 8 is verification with concrete commands
and concrete expected numbers.

**Type consistency:** `read_args` returns a table in every call site (Tasks 1–6
all index `args[n]`); `convert_blocks`/`convert_inlines` names are used
identically throughout; `maybe_infobox`/`maybe_block` are defined in Task 4 and
referenced only there and in Task 4's dispatch.
