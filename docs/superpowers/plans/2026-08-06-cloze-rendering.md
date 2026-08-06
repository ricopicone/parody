# Cloze Rendering Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Render `.cloze` / `.blank` fill-in-the-blank markup in both output paths, in three modes — `blank` (student handout), `key` (instructor), `full` (cloze-free publication build).

**Architecture:** One build axis, `--clozes blank|key|full`, orthogonal to `--solutions`. Print renders clozes **in TeX** (LaTeX can measure the hidden box with `\settowidth`, so widths are exact and the answer never enters the PDF content stream). The web renders them **in `filter.lua`** (HTML cannot measure at build time, and anything the filter emits is fetchable, so in `blank` mode the answer is never written). Figure-variant swapping happens in both filters, where asset resolution already lives.

**Tech Stack:** Python 3, pandoc 3.6.1 via pypandoc (pinned), pandoc Lua filters, LaTeX (memoir + tcolorbox + etoolbox), pytest.

**Spec:** `docs/superpowers/specs/2026-08-06-cloze-rendering-design.md`

## Global Constraints

- Modes are exactly `blank`, `key`, `full`. Default `blank` — the default must never leak an answer.
- `--clozes` is orthogonal to `--solutions`; neither implies the other.
- Named sizes resolve **in Lua**, not in TeX/CSS: `sm`=2em, `md`=5em, `lg`=10em, `xl`=20em. `width=` overrides `size=`. No size and no width ⇒ `md`.
- In `full` mode the web HTML must be byte-identical to a book that never had clozes: unwrap, do not restyle.
- In `blank` mode the answer string must not appear anywhere in the emitted HTML, LaTeX, or artifact JSON.
- Presentation lives downstream: the filter emits `class="cloze-blank"` + a `--cloze-w` custom property; parody-web owns the CSS. Build-side changes stay additive (the exercise/env box HTML is frozen — see project memory `exercise-box-html-is-frozen-for-homepage`).
- Never `git add -A`: this worktree is shared with other sessions. Stage explicit paths only.
- Run tests with `uv run pytest`.

---

## File Structure

| file | responsibility |
|---|---|
| `parody/config.py` | `CLOZE_MODES`, `resolve_cloze_mode(meta, override)` — the single definition of what a valid mode is |
| `parody/cli.py` | `--clozes` on `build` and `pdf` |
| `parody/build.py` | thread mode into `build_project`, export `PARODY_CLOZE_MODE` + `PARODY_CHAPTER_DIR`, record `cloze_mode` |
| `parody/writers/artifact.py` | `convert_solution_to_html(..., cloze_mode=None)` — force `full` for solutions |
| `parody/writers/latex.py` | `\def\clozemode{…}` flag + `PARODY_CLOZE_MODE` for print.lua |
| `parody/filters/filter.lua` | web rendering: Span, Div, Math, figure variant |
| `parody/filters/print.lua` | print emission: Span, Div, `interior_filter` Div entry, figure variant |
| `parody/profiles/*/parody-*.sty` | `\clozemode`, `\cloze`, `\blank`, `\clozelines`, `clozeblock` |
| `parody/profiles/PROFILE-CONTRACT.md` | document the four names + the flag |
| `parody/schemas/artifact-v2.json` | `cloze_mode` |
| `tests/test_cloze.py` | all filter behavior, all three modes, plus the no-leak assertions |
| `tests/print_fixtures/cloze.md` + `cloze-<mode>.golden.tex` | pinned LaTeX emission |

---

## Task 1: Mode resolution and plumbing

No rendering yet — just make every layer able to say which mode it is in.

**Files:**
- Modify: `parody/config.py` (add after `normalize_editions`)
- Modify: `parody/cli.py:259` (build parser), `parody/cli.py:299` (pdf parser), `cmd_build`, `cmd_pdf`
- Modify: `parody/build.py:197` (`_slug_env`), `parody/build.py:317` (`build_project`), `parody/build.py:359` (output dict)
- Modify: `parody/writers/latex.py:191` (`build_pdf` signature), `:293` (flags)
- Modify: `parody/schemas/artifact-v2.json`
- Test: `tests/test_cloze.py` (new)

**Interfaces:**
- Produces: `parody.config.CLOZE_MODES = ("blank", "key", "full")`; `parody.config.resolve_cloze_mode(meta: dict, override: str | None = None) -> str` (raises `ValueError` on an unknown mode); `build_project(..., cloze_mode=None)`; `build_pdf(..., cloze_mode=None)`; env var `PARODY_CLOZE_MODE`; artifact key `cloze_mode` (emitted only when not `"blank"`).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_cloze.py`:

```python
"""Cloze (fill-in-the-blank) rendering: mode plumbing and both filters.

Three modes: blank (student handout), key (instructor), full (publication).
The load-bearing assertions are the negative ones — in `blank` mode the
answer must not appear in the output at all.
"""

import os
from contextlib import contextmanager
from pathlib import Path

import pytest

from parody.config import CLOZE_MODES, resolve_cloze_mode

FILTERS = Path(__file__).parent.parent / "parody" / "filters"


@contextmanager
def cloze_mode(mode):
    """Set PARODY_CLOZE_MODE for a filter run, restoring it afterwards."""
    saved = os.environ.get("PARODY_CLOZE_MODE")
    if mode is None:
        os.environ.pop("PARODY_CLOZE_MODE", None)
    else:
        os.environ["PARODY_CLOZE_MODE"] = mode
    try:
        yield
    finally:
        if saved is None:
            os.environ.pop("PARODY_CLOZE_MODE", None)
        else:
            os.environ["PARODY_CLOZE_MODE"] = saved


# --- mode resolution -------------------------------------------------------

def test_modes_are_exactly_three():
    assert CLOZE_MODES == ("blank", "key", "full")


def test_default_mode_is_blank():
    assert resolve_cloze_mode({}) == "blank"


def test_yaml_default_is_honored():
    assert resolve_cloze_mode({"cloze": {"default": "full"}}) == "full"


def test_override_beats_yaml():
    assert resolve_cloze_mode({"cloze": {"default": "full"}}, "blank") == "blank"


def test_unknown_mode_rejected():
    with pytest.raises(ValueError) as exc:
        resolve_cloze_mode({}, "hidden")
    assert "hidden" in str(exc.value)
    assert "blank" in str(exc.value)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_cloze.py -v`
Expected: FAIL — `ImportError: cannot import name 'CLOZE_MODES' from 'parody.config'`

- [ ] **Step 3: Add mode resolution to `parody/config.py`**

Append after `normalize_editions`:

```python
# Cloze (fill-in-the-blank) rendering mode. `blank` hides answers behind
# rules (student handout), `key` shows them accented (instructor copy),
# `full` renders them as ordinary text (publication build). Orthogonal to
# --solutions: a published student book wants clozes filled and exercise
# solutions hidden. Default `blank` so a build can never leak by omission.
CLOZE_MODES = ("blank", "key", "full")


def resolve_cloze_mode(meta, override=None):
    """CLI override > parody.yaml `cloze.default` > "blank"."""
    value = override or (meta.get("cloze") or {}).get("default") or "blank"
    if value not in CLOZE_MODES:
        raise ValueError(
            f"unknown cloze mode {value!r} (expected one of: "
            + ", ".join(CLOZE_MODES) + ")")
    return value
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_cloze.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Add the CLI flags**

In `parody/cli.py`, add to the `build` parser (next to `--online-only`):

```python
    p_build.add_argument("--clozes", metavar="MODE",
                         help="cloze rendering: blank (student handout, the "
                              "default), key (instructor copy), or full "
                              "(cloze-free publication build)")
```

Add the identical argument to the `pdf` parser (next to `--solutions`):

```python
    p_pdf.add_argument("--clozes", metavar="MODE",
                       help="cloze rendering: blank (student handout, the "
                            "default), key (instructor copy), or full "
                            "(cloze-free publication build)")
```

In `cmd_build`, add to the `kwargs` dict:

```python
        cloze_mode=getattr(args, "clozes", None),
```

In `cmd_pdf`, pass it through to `build_pdf`:

```python
        cloze_mode=args.clozes,
```

- [ ] **Step 6: Thread the mode through `parody/build.py`**

Extend `_slug_env` (line 197) with two more context vars — `PARODY_CHAPTER_DIR` is needed by Task 7's sibling-file lookup, and adding it here keeps the web filter's context equal to print's:

```python
@contextlib.contextmanager
def _slug_env(notebook_slug=None, chapter_slug=None, media_root=None,
              chapter_dir=None, cloze_mode=None):
    """Set PARODY_* context env vars, restoring previous values on exit."""
    updates = {
        "PARODY_NOTEBOOK_SLUG": notebook_slug,
        "PARODY_CHAPTER_SLUG": chapter_slug,
        "PARODY_MEDIA_ROOT": str(media_root) if media_root else None,
        "PARODY_CHAPTER_DIR": str(chapter_dir) if chapter_dir else None,
        "PARODY_CLOZE_MODE": cloze_mode,
    }
```

(The body below is unchanged — it already loops over `updates`.)

Add the parameter to `build_project` (line 317):

```python
def build_project(project_dir, output_path, convert_jupytext=True,
                  media_root=None, online_only=False, edition=None,
                  cloze_mode=None):
```

and to its docstring:

```
    cloze_mode: "blank" | "key" | "full" (see config.resolve_cloze_mode).
    None takes parody.yaml's `cloze.default`, itself defaulting to "blank".
```

Immediately after `project = load_project(project_dir)`, resolve it:

```python
    from .config import resolve_cloze_mode
    cloze_mode = resolve_cloze_mode(project.meta, cloze_mode)
```

In the `output` dict assembly (line 359), after the `chapter_start` block, add:

```python
    # Cloze rendering mode. Emitted only when it isn't the default, so
    # artifacts of books without fill-in-the-blank content stay byte-identical
    # (same convention as chapter_start). Absence means "blank".
    if cloze_mode != "blank":
        output["cloze_mode"] = cloze_mode
```

Update the `_slug_env` call at line 398:

```python
        with _slug_env(project.slug, chapter.slug, media_root,
                       chapter_dir=chapter.directory, cloze_mode=cloze_mode):
```

`build_editions` passes `**kwargs` straight through, so it needs no change.

- [ ] **Step 7: Add the print flag in `parody/writers/latex.py`**

Signature (line 191):

```python
def build_pdf(project_dir, output_pdf=None, solutions=False, section=None,
              profile_dir=None, keep_build=False, build_dir=None,
              cloze_mode=None):
```

After `project = load_project(project_dir)`:

```python
    from ..config import resolve_cloze_mode
    cloze_mode = resolve_cloze_mode(project.meta, cloze_mode)
```

Add `"PARODY_CLOZE_MODE"` to the `_ctx_keys` tuple and set it alongside the other context vars:

```python
    os.environ["PARODY_CLOZE_MODE"] = cloze_mode
```

In the flags block (line 293):

```python
    flags = []
    if solutions:
        flags.append("\\def\\issolution{1}")
    # Cloze mode is a separate axis from --solutions: a published student book
    # wants clozes filled and exercise solutions hidden.
    flags.append("\\def\\clozemode{%s}" % cloze_mode)
```

- [ ] **Step 8: Add `cloze_mode` to the schema**

In `parody/schemas/artifact-v2.json`, alongside `chapter_start` in the top-level `properties`:

```json
    "cloze_mode": {
      "description": "Cloze (fill-in-the-blank) rendering this artifact was built with: \"key\" (instructor copy, answers shown accented) or \"full\" (cloze-free publication build). Absent means \"blank\" — the student handout, where answers are replaced by rules at build time and never reach the browser.",
      "type": "string",
      "enum": ["key", "full"]
    },
```

- [ ] **Step 9: Add plumbing tests**

Append to `tests/test_cloze.py`:

```python
# --- plumbing --------------------------------------------------------------

def test_build_records_non_default_mode(tmp_path):
    from parody.build import build_project

    src = Path(__file__).parent / "smoke-book"
    out = build_project(src, tmp_path / "a.json", convert_jupytext=False,
                        media_root=tmp_path, cloze_mode="full")
    assert out["cloze_mode"] == "full"


def test_build_omits_default_mode(tmp_path):
    from parody.build import build_project

    src = Path(__file__).parent / "smoke-book"
    out = build_project(src, tmp_path / "a.json", convert_jupytext=False,
                        media_root=tmp_path)
    assert "cloze_mode" not in out


def test_pdf_flag_emitted(tmp_path, monkeypatch):
    """build_pdf writes \\def\\clozemode into main.tex, next to \\issolution."""
    import shutil

    from parody.writers import latex as latex_writer

    # build_pdf writes main.tex, then bails with a warning when latexmk is
    # missing (latex.py:348) — so faking its absence gives a fast, TeX-free
    # assertion on the generated source.
    monkeypatch.setattr(latex_writer.shutil, "which",
                        lambda *a, **k: None)
    src = Path(__file__).parent / "smoke-book"
    build_dir = tmp_path / "build"
    latex_writer.build_pdf(src, build_dir=build_dir, cloze_mode="key",
                           output_pdf=tmp_path / "out.pdf")
    main_tex = (build_dir / "main.tex").read_text(encoding="utf-8")
    assert "\\def\\clozemode{key}" in main_tex


def test_pdf_flag_is_independent_of_solutions(tmp_path, monkeypatch):
    from parody.writers import latex as latex_writer

    monkeypatch.setattr(latex_writer.shutil, "which", lambda *a, **k: None)
    src = Path(__file__).parent / "smoke-book"
    build_dir = tmp_path / "build"
    latex_writer.build_pdf(src, build_dir=build_dir, cloze_mode="key",
                           solutions=True, output_pdf=tmp_path / "out.pdf")
    main_tex = (build_dir / "main.tex").read_text(encoding="utf-8")
    assert "\\def\\clozemode{key}" in main_tex
    assert "\\def\\issolution{1}" in main_tex
```

`build_pdf` calls `section_to_latex`, which needs pandoc — already a hard test
dependency (pypandoc-binary is pinned), so no skip guard is needed.

- [ ] **Step 10: Run the whole suite**

Run: `uv run pytest tests/test_cloze.py tests/test_schema_v2.py tests/test_golden_artifacts.py tests/test_cli.py -v`
Expected: PASS. The golden artifacts must be untouched — no existing book uses `.cloze`.

- [ ] **Step 11: Commit**

```bash
git add parody/config.py parody/cli.py parody/build.py parody/writers/latex.py parody/schemas/artifact-v2.json tests/test_cloze.py
git commit -m "cloze: add the blank/key/full build axis and plumbing"
```

---

## Task 2: Web inline spans

**Files:**
- Modify: `parody/filters/filter.lua` (helpers before `function Span`, at :1095; new cases inside `Span`)
- Test: `tests/test_cloze.py`

**Interfaces:**
- Consumes: env var `PARODY_CLOZE_MODE` (Task 1).
- Produces: Lua locals `CLOZE_MODE`, `cloze_estimate_width(text) -> string`, `cloze_manual_width(el) -> string`, `cloze_blank_html(width) -> string`, used by Tasks 3, 4, 7.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_cloze.py`:

```python
import pypandoc

WEB_FROM = ("markdown-smart-markdown_in_html_blocks+raw_tex"
            "+tex_math_dollars+grid_tables")
PRINT_FROM = "markdown-markdown_in_html_blocks+raw_tex+tex_math_dollars"


def web(md, mode="blank", cwd=None):
    with cloze_mode(mode):
        return pypandoc.convert_text(
            md, "html", format=WEB_FROM,
            extra_args=[f"--lua-filter={FILTERS / 'filter.lua'}", "--mathjax"],
            cworkdir=str(cwd) if cwd else None,
        )


# --- web: inline spans -----------------------------------------------------

SPAN_MD = "The damping ratio is [0.707]{.cloze}."


def test_web_blank_hides_the_answer():
    out = web(SPAN_MD, "blank")
    assert "0.707" not in out
    assert 'class="cloze-blank"' in out
    assert "--cloze-w:" in out


def test_web_key_shows_the_answer_marked():
    out = web(SPAN_MD, "key")
    assert "0.707" in out
    assert "cloze-key" in out


def test_web_full_leaves_no_trace():
    out = web(SPAN_MD, "full")
    assert "0.707" in out
    assert "cloze" not in out


def test_web_default_mode_is_blank():
    with cloze_mode(None):
        out = pypandoc.convert_text(
            SPAN_MD, "html", format=WEB_FROM,
            extra_args=[f"--lua-filter={FILTERS / 'filter.lua'}"])
    assert "0.707" not in out


def test_web_manual_blank_named_size():
    out = web("Sketch it: []{.blank size=lg}", "blank")
    assert "--cloze-w: 10em" in out


def test_web_manual_blank_explicit_width_wins():
    out = web("[]{.blank size=lg width=4cm}", "blank")
    assert "--cloze-w: 4cm" in out


def test_web_manual_blank_defaults_to_md():
    out = web("[]{.blank}", "blank")
    assert "--cloze-w: 5em" in out


def test_web_manual_blank_dropped_in_full():
    out = web("Sketch it: []{.blank size=lg}", "full")
    assert "cloze-blank" not in out


def test_web_manual_blank_survives_in_key():
    """Nothing is hidden behind a manual blank, so key still needs the rule."""
    assert "cloze-blank" in web("[]{.blank size=lg}", "key")


def test_web_blank_width_scales_with_the_answer():
    short = web("[a]{.cloze}", "blank")
    long = web("[a much longer hidden answer]{.cloze}", "blank")
    def width(html):
        return float(html.split("--cloze-w: ")[1].split("em")[0])
    assert width(short) < width(long)


def test_web_blank_width_is_clamped():
    def width(html):
        return float(html.split("--cloze-w: ")[1].split("em")[0])
    assert width(web("[x]{.cloze}", "blank")) >= 2.0
    assert width(web("[" + "x" * 400 + "]{.cloze}", "blank")) <= 14.0


def test_web_cloze_inside_a_box():
    """Clozes inside .example/.exercise bodies are rewritten too."""
    md = "::: {.example h=\"c4\"}\nThe ratio is [0.707]{.cloze}.\n:::"
    out = web(md, "blank")
    assert "0.707" not in out
    assert "cloze-blank" in out
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_cloze.py -k web -v`
Expected: FAIL — the answer text is still present (`.cloze` passes through as an ordinary span).

- [ ] **Step 3: Implement the helpers and Span cases**

In `parody/filters/filter.lua`, insert immediately before `function Span(el)` (line 1095):

```lua
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
```

Then add the two cases at the top of `Span(el)`, before the `.cite` branch:

```lua
function Span(el)
    if el.classes:includes("cloze") then
        return clozer(el)
    elseif el.classes:includes("blank") then
        return blanker(el)
    end
    if el.classes:includes("cite") then
```

- [ ] **Step 4: Run to verify they pass**

Run: `uv run pytest tests/test_cloze.py -k web -v`
Expected: PASS

- [ ] **Step 5: Check nothing else regressed**

Run: `uv run pytest tests/test_golden_artifacts.py tests/test_filter_cite_and_links.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add parody/filters/filter.lua tests/test_cloze.py
git commit -m "cloze: render .cloze and .blank spans on the web"
```

---

## Task 3: Web block forms

**Files:**
- Modify: `parody/filters/filter.lua` (helpers next to Task 2's; new cases in `Div`, :712)
- Test: `tests/test_cloze.py`

**Interfaces:**
- Consumes: `CLOZE_MODE`, `cloze_estimate_width` (Task 2).
- Produces: `<div class="cloze-lines" data-lines="N"></div>` — parody-web draws N rules.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_cloze.py`:

```python
# --- web: block forms ------------------------------------------------------

def test_web_manual_block_blank():
    out = web("::: {.blank lines=6}\n:::", "blank")
    assert 'class="cloze-lines"' in out
    assert 'data-lines="6"' in out


def test_web_manual_block_defaults_to_four_lines():
    assert 'data-lines="4"' in web("::: {.blank}\n:::", "blank")


def test_web_manual_block_dropped_in_full():
    assert "cloze-lines" not in web("::: {.blank lines=6}\n:::", "full")


def test_web_hidden_block_hides_its_text():
    md = "::: {.cloze}\nA whole hidden paragraph of derivation.\n:::"
    out = web(md, "blank")
    assert "derivation" not in out
    assert 'class="cloze-lines"' in out


def test_web_hidden_block_shows_text_in_key_and_full():
    md = "::: {.cloze}\nA whole hidden paragraph of derivation.\n:::"
    assert "derivation" in web(md, "key")
    assert "cloze-key-block" in web(md, "key")
    full = web(md, "full")
    assert "derivation" in full
    assert "cloze" not in full


def test_web_hidden_block_line_count_grows_with_content():
    def lines(html):
        return int(html.split('data-lines="')[1].split('"')[0])
    short = web("::: {.cloze}\nshort\n:::", "blank")
    long = web("::: {.cloze}\n" + "word " * 200 + "\n:::", "blank")
    assert lines(short) == 1
    assert lines(long) > 1
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_cloze.py -k "block or hidden" -v`
Expected: FAIL — the paragraph text is still in the HTML.

- [ ] **Step 3: Implement**

Add next to Task 2's helpers in `filter.lua`:

```lua
-- Block forms. `::: {.blank lines=6}` is empty work space; `::: {.cloze}`
-- hides a whole passage, blanked to roughly its own height (~90 chars/line).
local function cloze_lines_html(n)
  return string.format('<div class="cloze-lines" data-lines="%d"></div>', n)
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
```

Add the cases at the top of `Div(el)` (line 712), before the `subfigures` branch:

```lua
function Div(el)
  if el.classes:includes("cloze") then
    return cloze_div(el)
  elseif el.classes:includes("blank") then
    return blank_div(el)
  elseif el.classes:includes("subfigures") then
```

- [ ] **Step 4: Run to verify they pass**

Run: `uv run pytest tests/test_cloze.py -k "block or hidden" -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add parody/filters/filter.lua tests/test_cloze.py
git commit -m "cloze: render block .cloze and .blank on the web"
```

---

## Task 4: Web math

**Files:**
- Modify: `parody/filters/filter.lua` (add `function Math(el)` next to `function Str(el)`, :1161)
- Test: `tests/test_cloze.py`

**Interfaces:**
- Consumes: `CLOZE_MODE`, `cloze_estimate_width` (Task 2).
- Produces: `cloze_rewrite_macro(text, name, replace) -> string` — a balanced-brace TeX macro rewriter.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_cloze.py`:

```python
# --- web: math -------------------------------------------------------------

def test_web_math_cloze_hidden():
    out = web(r"The constant is $\tau = \cloze{RC}$.", "blank")
    assert "RC" not in out
    assert "underline" in out


def test_web_math_cloze_nested_braces():
    """A brace-matching scanner, not a regex: \\cloze{\\sqrt{k/m}} nests."""
    out = web(r"$\omega_n = \cloze{\sqrt{k/m}}$", "blank")
    assert "sqrt" not in out
    assert "k/m" not in out


def test_web_math_cloze_key():
    out = web(r"$\tau = \cloze{RC}$", "key")
    assert "RC" in out
    assert r"\class{cloze-key}" in out


def test_web_math_cloze_full():
    out = web(r"$\tau = \cloze{RC}$", "full")
    assert "RC" in out
    assert "cloze" not in out


def test_web_math_manual_blank():
    out = web(r"$y(t) = \blank{3em}$", "blank")
    assert "3em" in out
    assert "underline" in out


def test_web_math_manual_blank_dropped_in_full():
    out = web(r"$y(t) = \blank{3em}$", "full")
    assert "blank" not in out
    assert "3em" not in out


def test_web_display_math_cloze():
    out = web(r"$$x = \cloze{\frac{a}{b}}$$", "blank")
    assert "frac" not in out


def test_web_math_without_cloze_untouched():
    out = web(r"$E = mc^2$", "blank")
    assert "mc^2" in out
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_cloze.py -k math -v`
Expected: FAIL — `RC` still present (math passes through untouched).

- [ ] **Step 3: Implement**

Add to `filter.lua` next to the other cloze helpers:

```lua
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
```

And the handler, next to `function Str(el)`:

```lua
-- Math is opaque to pandoc, so clozes inside it are a TeX macro rather than a
-- span. Rewrite them here so the answer never reaches the browser in `blank`
-- mode. \class needs MathJax's html package (configured in parody-web).
function Math(el)
    if not (el.text:find('\\cloze') or el.text:find('\\blank')) then
        return el
    end
    local t = cloze_rewrite_macro(el.text, 'cloze', function(arg)
        if CLOZE_MODE == 'full' then return arg end
        if CLOZE_MODE == 'key' then
            return '\\class{cloze-key}{' .. arg .. '}'
        end
        return '\\underline{\\hspace{' .. cloze_estimate_width(arg) .. '}}'
    end)
    t = cloze_rewrite_macro(t, 'blank', function(arg)
        if CLOZE_MODE == 'full' then return '' end
        return '\\underline{\\hspace{' .. arg .. '}}'
    end)
    el.text = t
    return el
end
```

- [ ] **Step 4: Run to verify they pass**

Run: `uv run pytest tests/test_cloze.py -k math -v`
Expected: PASS

- [ ] **Step 5: Verify the MathJax rendering claim**

`\underline{\hspace{…}}` must actually draw a visible rule in MathJax v3. Build the preview and look:

```bash
uv run parody preview tests/smoke-book -o /tmp/cloze-preview
```

If the rule does not appear, change the `blank` replacement to
`'\\rule[-0.3em]{' .. cloze_estimate_width(arg) .. '}{0.4pt}'` and re-run the tests, updating the `"underline" in out` assertions to match. Record whichever wins in a comment on the handler.

- [ ] **Step 6: Commit**

```bash
git add parody/filters/filter.lua tests/test_cloze.py
git commit -m "cloze: rewrite \\cloze and \\blank inside math on the web"
```

---

## Task 5: Print spans and blocks

**Files:**
- Modify: `parody/filters/print.lua` (helpers near `keyworder`; cases in `Span` :1595; `Div` entry in `interior_filter` :53; cases in the top-level `Div`)
- Test: `tests/test_cloze.py`

**Interfaces:**
- Produces the four profile-contract names consumed by Task 6: `\cloze{…}`, `\blank{<length>}`, `\clozelines{<n>}`, `\begin{clozeblock}…\end{clozeblock}`.

Note the split: print emits the macro **in every mode** and lets TeX decide, because only LaTeX can measure the hidden box. Sizes are still resolved in Lua, so the profile always receives a real length.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_cloze.py`:

```python
# --- print -----------------------------------------------------------------

def latex(md, mode="blank"):
    with cloze_mode(mode):
        return pypandoc.convert_text(
            md, "latex", format=PRINT_FROM,
            extra_args=[f"--lua-filter={FILTERS / 'print.lua'}", "--biblatex",
                        "--wrap=none"])


def test_print_cloze_span():
    assert "\\cloze{0.707}" in latex("The ratio is [0.707]{.cloze}.")


def test_print_manual_blank_named_size():
    assert "\\blank{10em}" in latex("Sketch: []{.blank size=lg}")


def test_print_manual_blank_explicit_width():
    assert "\\blank{4cm}" in latex("[]{.blank width=4cm}")


def test_print_manual_blank_defaults_to_md():
    assert "\\blank{5em}" in latex("[]{.blank}")


def test_print_block_blank():
    assert "\\clozelines{6}" in latex("::: {.blank lines=6}\n:::")


def test_print_hidden_block():
    out = latex("::: {.cloze}\nHidden derivation.\n:::")
    assert "\\begin{clozeblock}" in out
    assert "\\end{clozeblock}" in out
    assert "Hidden derivation." in out  # TeX decides; the mode is a \def


def test_print_math_cloze_passes_through():
    """Math needs no filter work in print: TeX defines \\cloze itself."""
    assert "\\cloze{RC}" in latex(r"$\tau = \cloze{RC}$")


def test_print_cloze_inside_a_box():
    """interior_filter must reach spans and divs nested in environments."""
    md = ("::: {.exercise h=\"8y\"}\n"
          "The ratio is [0.707]{.cloze}.\n\n"
          "::: {.blank lines=3}\n:::\n"
          ":::")
    out = latex(md)
    assert "\\cloze{0.707}" in out
    assert "\\clozelines{3}" in out
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_cloze.py -k print -v`
Expected: FAIL — spans pass through as plain text.

- [ ] **Step 3: Implement**

In `print.lua`, add near `keyworder` (before the `Span` dispatch):

```lua
-- ---- cloze (fill-in-the-blank) -------------------------------------------
-- Print emits the profile-contract macros in every mode and lets TeX branch on
-- \clozemode: only LaTeX can measure the hidden box (\settowidth), so widths
-- are exact, and the discarded measuring box never enters the PDF content
-- stream — a `blank` PDF cannot be mined for answers. Named sizes are resolved
-- here so the profile always receives a real length. See filter.lua for the
-- web side, which must strip instead.
local CLOZE_SIZES = { sm = '2em', md = '5em', lg = '10em', xl = '20em' }

local function cloze_manual_width(el)
  local w = el.attributes and el.attributes.width
  if w and w ~= '' then return w end
  local size = (el.attributes and el.attributes.size) or 'md'
  return CLOZE_SIZES[size] or CLOZE_SIZES.md
end

local function clozer_latex(el)
  return pandoc.RawInline('tex', '\\cloze{' .. inlines_to_latex(el.content) .. '}')
end

local function blanker_latex(el)
  return pandoc.RawInline('tex', '\\blank{' .. cloze_manual_width(el) .. '}')
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
```

`inlines_to_latex` is the file's existing inline-to-LaTeX helper
(`print.lua:106`, used by the caption paths at `:862` and `:1065`). Use it, not
`pandoc.utils.stringify` — stringify flattens math and markup to plain text and
would destroy `[$x$]{.cloze}`.

Add the cases at the top of `Span(el)`:

```lua
  if el.classes:includes('cloze') then
    return clozer_latex(el)
  elseif el.classes:includes('blank') then
    return blanker_latex(el)
  elseif el.classes:includes('label') then
```

Add the same two cases at the top of the top-level `Div(el)` dispatch.

Add a narrow `Div` entry to `interior_filter` (line 53) so block clozes nested inside exercise/example bodies are reached — returning `nil` for every other class leaves the existing bespoke nested-Div handling alone:

```lua
  -- Only cloze blocks: returning nil for anything else leaves the bespoke
  -- nested-Div handling in the environment handlers untouched.
  Div = function(el)
    if el.classes:includes('cloze') then return cloze_div_latex(el) end
    if el.classes:includes('blank') then return blank_div_latex(el) end
    return nil
  end,
```

- [ ] **Step 4: Run to verify they pass**

Run: `uv run pytest tests/test_cloze.py -k print -v`
Expected: PASS

- [ ] **Step 5: Check the pinned LaTeX emission is unchanged**

Run: `uv run pytest tests/test_print_snippets.py tests/test_print_memoir.py tests/test_print_includes.py -v`
Expected: PASS — no existing fixture uses `.cloze`, so `environments.golden.tex` must not move. If it does, something in the shared dispatch changed; fix rather than regenerate.

- [ ] **Step 6: Commit**

```bash
git add parody/filters/print.lua tests/test_cloze.py
git commit -m "cloze: emit \\cloze/\\blank/\\clozelines/clozeblock from print.lua"
```

---

## Task 6: Profile macros

**Files:**
- Modify: `parody/profiles/memoir/parody-environments.sty`
- Modify: `parody/profiles/print/parody-print.sty`
- Modify: `parody/profiles/PROFILE-CONTRACT.md`
- Test: `tests/test_cloze.py` (a real LaTeX compile)

**Interfaces:**
- Consumes: `\def\clozemode{…}` (Task 1), the four names emitted by Task 5.
- Both `.sty` files get the **same** block; they are separate profiles, not a shared include.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_cloze.py`:

```python
# --- print: real LaTeX compile ---------------------------------------------

CLOZE_TEX_SNIPPET = r"""
Text cloze: \cloze{0.707} and manual \blank{10em}.

Math cloze: $\tau = \cloze{RC}$ and $y = \blank{3em}$.

\clozelines{3}

\begin{clozeblock}
A whole hidden paragraph that should blank to its own height.
\end{clozeblock}
"""


@pytest.mark.parametrize("mode", ["blank", "key", "full"])
def test_profile_macros_compile(tmp_path, mode):
    """The four contract names must compile in every mode, in both profiles."""
    pytest.importorskip("pypandoc")
    import shutil
    import subprocess

    if shutil.which("pdflatex") is None:
        pytest.skip("no LaTeX toolchain")

    profile = (Path(__file__).parent.parent / "parody" / "profiles" / "memoir")
    for f in profile.iterdir():
        if f.is_file() and f.name != "main.tex.template":
            shutil.copy2(f, tmp_path / f.name)
    (tmp_path / "main.tex").write_text(
        "\\documentclass[11pt]{parody-memoir}\n"
        f"\\def\\clozemode{{{mode}}}\n"
        "\\usepackage{parody-theme-default}\n"
        "\\usepackage{parody-environments}\n"
        "\\begin{document}\n" + CLOZE_TEX_SNIPPET + "\n\\end{document}\n",
        encoding="utf-8")
    r = subprocess.run(["pdflatex", "-interaction=nonstopmode", "main.tex"],
                       cwd=tmp_path, capture_output=True, text=True)
    assert (tmp_path / "main.pdf").exists(), r.stdout[-3000:]
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_cloze.py -k profile_macros -v`
Expected: FAIL — `Undefined control sequence \cloze` (or SKIP if there is no LaTeX toolchain; in that case verify via Task 9's PDF build instead).

- [ ] **Step 3: Implement the macros**

Add to **both** `.sty` files, after the build-flags comment block (memoir line 40, print line 42). `etoolbox` and `xcolor` are already required by both; `@` is a letter inside a package.

```tex
% ---- cloze (fill-in-the-blank) --------------------------------------------
% \clozemode is set by the writer via \def: blank | key | full. `blank` hides
% the answer behind a rule measured from the real box, so the answer is never
% typeset and cannot be recovered from the PDF. Orthogonal to \issolution.
\providecommand{\clozemode}{blank}
\newlength{\parodyclozewd}

\newcommand{\parody@clozeswitch}[3]{% #1 blank, #2 key, #3 full
  \ifdefstring{\clozemode}{full}{#3}{%
    \ifdefstring{\clozemode}{key}{#2}{#1}}}

\newcommand{\parody@blankrule}{%
  \ifdim\parodyclozewd<2em\relax\setlength{\parodyclozewd}{2em}\fi
  \leavevmode\rule[-0.55ex]{\dimexpr\parodyclozewd+1em\relax}{0.4pt}}

% \settowidth typesets in LR mode, so the outer math/text mode must be
% captured before measuring — \ifmmode inside the box would always be false.
\newcommand{\parody@cloze@text}[1]{%
  \parody@clozeswitch
    {\settowidth{\parodyclozewd}{#1}\parody@blankrule}
    {\underline{\textcolor{parodyaccent}{#1}}}
    {#1}}
\newcommand{\parody@cloze@math}[1]{%
  \parody@clozeswitch
    {\settowidth{\parodyclozewd}{$#1$}\mbox{\parody@blankrule}}
    {\underline{{\color{parodyaccent}#1}}}
    {#1}}
\newcommand{\cloze}[1]{%
  \relax\ifmmode\parody@cloze@math{#1}\else\parody@cloze@text{#1}\fi}

% Manual blank: nothing is hidden, so `key` keeps the rule and `full` drops it.
\newcommand{\blank}[1]{%
  \parody@clozeswitch
    {\leavevmode\rule[-0.55ex]{#1}{0.4pt}}
    {\leavevmode\rule[-0.55ex]{#1}{0.4pt}}
    {}}

\newcounter{parodyclozeline}
\newcommand{\parody@rulelines}[1]{%
  \par\nobreak\medskip
  \setcounter{parodyclozeline}{0}%
  \@whilenum\value{parodyclozeline}<#1\do{%
    \noindent\rule{\linewidth}{0.4pt}\par\vspace{0.5\baselineskip}%
    \stepcounter{parodyclozeline}}%
  \medskip}
\newcommand{\clozelines}[1]{%
  \parody@clozeswitch{\parody@rulelines{#1}}{\parody@rulelines{#1}}{}}

% Hidden block: capture the content, then blank it to its own height.
\newsavebox{\parodyclozebox}
\newenvironment{clozeblock}
  {\begin{lrbox}{\parodyclozebox}\begin{minipage}{\linewidth}}
  {\end{minipage}\end{lrbox}%
   \parody@clozeswitch
     {\@tempcnta=\dimexpr\ht\parodyclozebox+\dp\parodyclozebox\relax
      \@tempcntb=\baselineskip
      \divide\@tempcnta by \@tempcntb
      \advance\@tempcnta by 1
      \parody@rulelines{\@tempcnta}}
     {\par\medskip\noindent\textcolor{parodyaccent}{\usebox{\parodyclozebox}}\par\medskip}
     {\par\noindent\usebox{\parodyclozebox}\par}}
```

If `\parodyaccent` is not defined in the generic `print` profile's theme, use that profile's existing accent colour name — read the file rather than inventing one.

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_cloze.py -k profile_macros -v`
Expected: PASS for all three modes

- [ ] **Step 5: Document the contract**

In `parody/profiles/PROFILE-CONTRACT.md`, add to the environments list:

```markdown
- `clozeblock` — fill-in-the-blank passage; blanks to its own measured height
  in `blank` mode, prints its content in `full`.
```

to the commands list:

```markdown
- `\cloze{content}` (text- and math-mode), `\blank{length}`, `\clozelines{n}`
  — fill-in-the-blank rendering; all three branch on `\clozemode`.
```

and to the build-flags line:

```markdown
`\issolution` (solutions manual), `\ispartial` (sample build), `\nocropmarks`,
`\clozemode` (`blank` | `key` | `full`, default `blank`).
```

- [ ] **Step 6: Commit**

```bash
git add parody/profiles/memoir/parody-environments.sty parody/profiles/print/parody-print.sty parody/profiles/PROFILE-CONTRACT.md tests/test_cloze.py
git commit -m "cloze: define \\cloze/\\blank/\\clozelines/clozeblock in both print profiles"
```

---

## Task 7: Incomplete figure variants

**Files:**
- Modify: `parody/filters/print.lua` (`Image`, near `resolve_asset` usage at :791)
- Modify: `parody/filters/filter.lua` (`Image` :761, and the image extraction in `Figure` :864)
- Test: `tests/test_cloze.py`

**Interfaces:**
- Consumes: `PARODY_CLOZE_MODE`, `PARODY_CHAPTER_DIR` (Task 1 exports it on the web path too).
- Produces: `cloze_variant_src(el) -> string | nil` in each filter — returns the incomplete artwork's src in `blank` mode only.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_cloze.py`:

```python
# --- figures ---------------------------------------------------------------

@pytest.fixture
def figdir(tmp_path):
    (tmp_path / "rl.pdf").write_bytes(b"%PDF-1.4\n")
    (tmp_path / "rl-blank.pdf").write_bytes(b"%PDF-1.4\n")
    (tmp_path / "bode.pdf").write_bytes(b"%PDF-1.4\n")
    (tmp_path / "bode-cloze.pdf").write_bytes(b"%PDF-1.4\n")
    (tmp_path / "plain.pdf").write_bytes(b"%PDF-1.4\n")
    return tmp_path


def with_chapter_dir(d):
    return {"PARODY_CHAPTER_DIR": str(d)}


def web_fig(md, mode, figdir):
    saved = os.environ.get("PARODY_CHAPTER_DIR")
    os.environ["PARODY_CHAPTER_DIR"] = str(figdir)
    try:
        return web(md, mode, cwd=figdir)
    finally:
        if saved is None:
            os.environ.pop("PARODY_CHAPTER_DIR", None)
        else:
            os.environ["PARODY_CHAPTER_DIR"] = saved


def test_web_explicit_cloze_variant(figdir):
    md = '![Root locus](rl.pdf){#fig:rl cloze="rl-blank.pdf"}'
    out = web_fig(md, "blank", figdir)
    assert "rl-blank.pdf" in out
    assert "rl.pdf" not in out.replace("rl-blank.pdf", "")


def test_web_complete_artwork_in_key_and_full(figdir):
    md = '![Root locus](rl.pdf){#fig:rl cloze="rl-blank.pdf"}'
    for mode in ("key", "full"):
        out = web_fig(md, mode, figdir)
        assert "rl-blank.pdf" not in out


def test_web_sibling_variant_autodetected(figdir):
    out = web_fig("![Bode](bode.pdf){#fig:b}", "blank", figdir)
    assert "bode-cloze.pdf" in out


def test_web_no_variant_renders_complete(figdir):
    """No variant authored means the artwork isn't part of the exercise."""
    out = web_fig("![Plain](plain.pdf){#fig:p}", "blank", figdir)
    assert "plain.pdf" in out


def test_print_explicit_cloze_variant(figdir):
    saved = os.environ.get("PARODY_CHAPTER_DIR")
    os.environ["PARODY_CHAPTER_DIR"] = str(figdir)
    try:
        out = latex('![Root locus](rl.pdf){#fig:rl cloze="rl-blank.pdf"}')
    finally:
        if saved is None:
            os.environ.pop("PARODY_CHAPTER_DIR", None)
        else:
            os.environ["PARODY_CHAPTER_DIR"] = saved
    assert "rl-blank" in out
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_cloze.py -k "variant or artwork" -v`
Expected: FAIL — the complete artwork is emitted in `blank` mode.

- [ ] **Step 3: Implement in both filters**

Add this helper to **each** filter (`filter.lua` next to the other cloze helpers; `print.lua` next to `cloze_manual_width`):

```lua
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
```

`print.lua` needs `local CLOZE_MODE = os.getenv('PARODY_CLOZE_MODE') or 'blank'` added next to its Task 5 helpers.

In each filter's `Image` handler, as the first statement:

```lua
  local variant = cloze_variant_src(el)
  if variant then el.src = variant end
```

In `filter.lua`'s `Figure` handler (:864) and `print.lua`'s `figurer`, apply the same swap to the extracted image before its src is used. Read each function and place the swap before any path resolution or `{% media %}` rewriting.

- [ ] **Step 4: Run to verify they pass**

Run: `uv run pytest tests/test_cloze.py -k "variant or artwork" -v`
Expected: PASS

- [ ] **Step 5: Check figure handling didn't regress**

Run: `uv run pytest tests/test_figure_mover.py tests/test_rights_figures.py tests/test_golden_artifacts.py tests/test_print_snippets.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add parody/filters/filter.lua parody/filters/print.lua tests/test_cloze.py
git commit -m "cloze: swap in incomplete figure variants in blank mode"
```

---

## Task 8: Solutions always render full

Blanking the answer inside an answer key is nonsense: a cloze inside a solution renders `full` regardless of the build's mode.

**Files:**
- Modify: `parody/writers/artifact.py:598` (`convert_solution_to_html`) and its two call sites (:657 solutions, :670 problems)
- Modify: `parody/profiles/memoir/parody-environments.sty`, `parody/profiles/print/parody-print.sty`
- Test: `tests/test_cloze.py`

**Interfaces:**
- Produces: `convert_solution_to_html(solution_markdown, chapter_dir, cloze_mode=None)` — `cloze_mode` overrides `PARODY_CLOZE_MODE` for that one pandoc run; `None` keeps the ambient mode.

The **solutions** call site passes `cloze_mode="full"`. The **problems** call site passes nothing — a problem statement is student-facing and keeps the ambient mode.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_cloze.py`:

```python
# --- solutions -------------------------------------------------------------

def test_solution_clozes_always_render_full(tmp_path):
    """An answer key must not blank its own answers."""
    from parody.writers.artifact import convert_solution_to_html

    with cloze_mode("blank"):
        html = convert_solution_to_html(
            "The ratio is [0.707]{.cloze}.", str(tmp_path), cloze_mode="full")
    assert "0.707" in html
    assert "cloze-blank" not in html


def test_problem_bodies_keep_the_ambient_mode(tmp_path):
    from parody.writers.artifact import convert_solution_to_html

    with cloze_mode("blank"):
        html = convert_solution_to_html(
            "The ratio is [0.707]{.cloze}.", str(tmp_path))
    assert "0.707" not in html
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_cloze.py -k "solution or problem" -v`
Expected: FAIL — `TypeError: convert_solution_to_html() got an unexpected keyword argument 'cloze_mode'`

- [ ] **Step 3: Implement the web side**

In `parody/writers/artifact.py`:

```python
def convert_solution_to_html(solution_markdown, chapter_dir, cloze_mode=None):
    """Convert solution markdown content to HTML using pypandoc.

    cloze_mode overrides PARODY_CLOZE_MODE for this one run. Solutions pass
    "full": blanking the answer inside an answer key is nonsense. Problem
    bodies pass nothing and keep the build's ambient mode.
    """
    import tempfile
```

Wrap the `pypandoc.convert_file` call so the override is set and restored:

```python
        saved = os.environ.get("PARODY_CLOZE_MODE")
        if cloze_mode is not None:
            os.environ["PARODY_CLOZE_MODE"] = cloze_mode
        try:
            html = pypandoc.convert_file(...)   # unchanged
        finally:
            if cloze_mode is not None:
                if saved is None:
                    os.environ.pop("PARODY_CLOZE_MODE", None)
                else:
                    os.environ["PARODY_CLOZE_MODE"] = saved
            # the existing temp-file cleanup stays here too
```

`os` is imported inside the existing `finally` in this function; hoist `import os` to the top of the function so both blocks can use it.

At the solutions call site (line ~657):

```python
        solution_content_html = convert_solution_to_html(
            solution_data['content'], chapter_dir, cloze_mode="full")
```

Leave the problems call site (line ~670) unchanged.

- [ ] **Step 4: Implement the print side**

In both `.sty` files, make the xsim solution environments render clozes full. After the `\DeclareExerciseType{labexercise}{…}` block, add:

```tex
% A cloze inside a solution always renders full — an answer key must not blank
% its own answers. Scoped to the environment, so the ambient \clozemode returns
% at \end.
\AtBeginEnvironment{solution}{\renewcommand{\clozemode}{full}}
\AtBeginEnvironment{labsolution}{\renewcommand{\clozemode}{full}}
```

`\AtBeginEnvironment` is etoolbox, already required. `\clozemode` is defined by `\providecommand`, so `\renewcommand` is safe; if the compile reports it undefined, the `\providecommand` in the cloze block has not run yet — move these two lines after it.

- [ ] **Step 5: Run to verify they pass**

Run: `uv run pytest tests/test_cloze.py -v`
Expected: PASS (whole file)

- [ ] **Step 6: Commit**

```bash
git add parody/writers/artifact.py parody/profiles/memoir/parody-environments.sty parody/profiles/print/parody-print.sty tests/test_cloze.py
git commit -m "cloze: solutions always render full, in both paths"
```

---

## Task 9: Golden fixture, end-to-end build, and docs

**Files:**
- Create: `tests/print_fixtures/cloze.md`, `tests/print_fixtures/cloze-blank.golden.tex`, `cloze-key.golden.tex`, `cloze-full.golden.tex`
- Modify: `tests/test_print_snippets.py`
- Modify: `README.md`
- Test: `tests/test_cloze.py`

**Interfaces:**
- Consumes: everything above.

- [ ] **Step 1: Write the fixture**

Create `tests/print_fixtures/cloze.md`:

```markdown
# Cloze constructs

The damping ratio is [0.707]{.cloze}, and the time constant is
$\tau = \cloze{RC}$.

Sketch the pole locations: []{.blank size=lg}

An exact-width blank: []{.blank width=4cm}

::: {.blank lines=6}
:::

::: {.cloze}
A whole hidden paragraph of derivation that should blank to its own height
rather than to a single inline rule.
:::

::: {.example h="c4"}
Inside a box: $\omega_n = \cloze{\sqrt{k/m}}$, so []{.blank size=md}.

::: {.blank lines=3}
:::
:::

::: {.exercise h="8y"}
Find the gain [K]{.cloze}.

::: {.exercise-solution}
The gain is [42]{.cloze}, which must print in full.
:::
:::
```

- [ ] **Step 2: Add the golden test**

Append to `tests/test_print_snippets.py`:

```python
@pytest.mark.parametrize("mode", ["blank", "key", "full"])
def test_cloze_snippet_matches_golden(request, mode, monkeypatch):
    """print.lua's cloze emission is identical in all three modes — TeX
    branches on \\clozemode — except for figure variants, which the filter
    resolves. Pinning all three catches an accidental mode leak into the
    filter."""
    monkeypatch.setenv("PARODY_CLOZE_MODE", mode)
    md = FIXTURES / "cloze.md"
    golden = FIXTURES / f"cloze-{mode}.golden.tex"
    out = render(md)
    if request.config.getoption("--regen-golden"):
        golden.write_text(out, encoding="utf-8")
        pytest.skip("golden regenerated")
    assert golden.exists(), "golden missing — run with --regen-golden once"
    assert out == golden.read_text(encoding="utf-8")
```

- [ ] **Step 3: Generate the goldens and read them**

Run: `uv run pytest tests/test_print_snippets.py -k cloze --regen-golden`

Then **read all three golden files** and confirm by eye: `\cloze{0.707}`, `\blank{10em}`, `\blank{4cm}`, `\clozelines{6}`, `clozeblock`, the in-box `\cloze{\sqrt{k/m}}` and `\clozelines{3}`, and the solution's `\cloze{42}`. Fix the filter and regenerate if anything is missing — do not commit a golden that pins a bug.

- [ ] **Step 4: Run to verify the goldens hold**

Run: `uv run pytest tests/test_print_snippets.py -v`
Expected: PASS

- [ ] **Step 5: End-to-end build test**

Append to `tests/test_cloze.py`:

```python
# --- end to end ------------------------------------------------------------

def test_full_artifact_has_no_cloze_markup(tmp_path):
    """A `full` build must be indistinguishable from a book without clozes."""
    import json

    src = Path(__file__).parent / "smoke-book"
    from parody.build import build_project

    out = build_project(src, tmp_path / "full.json", convert_jupytext=False,
                        media_root=tmp_path, cloze_mode="full")
    blob = json.dumps(out)
    assert "cloze-blank" not in blob
    assert "cloze-key" not in blob
```

Add cloze content to `tests/smoke-book/chapters/intro/hello.md` — one paragraph,
appended, nothing existing removed:

```markdown
The damping ratio is [0.707]{.cloze}, and $\tau = \cloze{RC}$. Sketch the
response: []{.blank size=lg}
```

The smoke book is what `Dockerfile.print` compiles in CI, so this also puts the
profile macros under a real `lualatex` run on every print-image build.

- [ ] **Step 6: Build a real PDF in each mode**

```bash
uv run parody pdf tests/smoke-book --clozes blank --no-execute -o /tmp/cloze-blank.pdf
uv run parody pdf tests/smoke-book --clozes key --no-execute -o /tmp/cloze-key.pdf
uv run parody pdf tests/smoke-book --clozes full --no-execute -o /tmp/cloze-full.pdf
```

Open all three. Confirm: rules appear in `blank`, accented answers in `key`, clean prose in `full`. Then confirm the no-leak property directly:

```bash
pdftotext /tmp/cloze-blank.pdf - | grep -c 0.707
```

Expected: `0`. If it prints anything else, `\settowidth` is not the only place the content is typeset — fix before proceeding.

- [ ] **Step 7: Document the feature**

Add a section to `README.md` next to the existing build/pdf documentation:

````markdown
### Fill-in-the-blank (cloze) content

`[answer]{.cloze}` hides text behind a blank sized to it; `[]{.blank size=lg}`
is an empty blank with nothing behind it (`sm`/`md`/`lg`/`xl`, or `width=4cm`).
Block forms: `::: {.blank lines=6}` for work space, `::: {.cloze}` for a hidden
passage. Inside math, use the macros: `$\tau = \cloze{RC}$`, `$y = \blank{3em}$`.
A figure can carry incomplete artwork with `cloze="fig-blank.pdf"`, or by
putting a `<stem>-cloze.<ext>` sibling next to it.

Three build modes, set by `--clozes` (or `cloze: {default: …}` in
`parody.yaml`), independent of `--solutions`:

| mode | who it is for |
|---|---|
| `blank` (default) | student handout — answers replaced by rules at build time |
| `key` | instructor copy — answers shown, accented |
| `full` | publication — answers as ordinary text, blanks dropped entirely |

```
parody pdf   . --clozes blank
parody build . artifact/book-full.json --clozes full
```

In `blank` mode the answer never reaches the browser or the PDF content
stream — it is removed at build time, not hidden with CSS.
````

- [ ] **Step 8: Run the whole suite**

Run: `uv run pytest -x -q`
Expected: PASS

- [ ] **Step 9: Commit**

```bash
git add tests/print_fixtures/cloze.md tests/print_fixtures/cloze-blank.golden.tex tests/print_fixtures/cloze-key.golden.tex tests/print_fixtures/cloze-full.golden.tex tests/test_print_snippets.py tests/test_cloze.py README.md
git commit -m "cloze: golden fixtures, end-to-end coverage, and docs"
```

---

## Follow-on (out of scope for this plan)

parody-web, separate repo and separate release: CSS for `.cloze-blank` (an
inline-block whose width comes from `--cloze-w`, with a bottom rule),
`.cloze-key`, `.cloze-key-block`, and `.cloze-lines` (N rules from
`data-lines`, drawn with a repeating gradient); MathJax `html` package so
`\class` resolves; optional "instructor copy" labelling driven by the
artifact's `cloze_mode`.
