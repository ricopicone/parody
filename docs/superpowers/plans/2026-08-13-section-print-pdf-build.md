# Section Print PDF — Build Side (`parody`) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `parody` record, for every section, the absolute page range that section occupies in the full print PDF, and publish print + web together in one command.

**Architecture:** A tiny LaTeX package writes a `zref-abspage` mark at each section's heading; after `latexmk` runs, the marks are read back out of `main.aux` and turned into inclusive `[start, end]` page ranges. The ranges go into a JSON sidecar next to the PDF, and `parody build` folds them into the artifact. Nothing is ever compiled per-section — the ranges describe cuts into the one full-book PDF.

**Tech Stack:** Python 3.12, pytest, LaTeX (`zref` / `zref-abspage`), poppler (`pdfinfo`), pandoc via pypandoc.

**Spec:** `docs/superpowers/specs/2026-08-13-section-print-pdf-design.md`

**Companion plan:** `docs/superpowers/plans/2026-08-13-section-print-pdf-web.md` (the `parody-web` half; execute this plan first — it defines the artifact fields that one consumes).

## Global Constraints

- **Never compile a section separately.** Per-section PDFs are page ranges cut from the full book PDF. `parody pdf --section CH/SEC` exists but is *not* the mechanism here (spec D6).
- **Never edit a print profile to add the page map.** It is injected through the existing `$flags` template slot so book-private profiles (MIT Press, in content repos) are covered without being touched.
- **Ranges are inclusive at both ends**: `end(i) = max(own_end(i), start(i+1) - 1)`. A shared boundary sheet appearing in two PDFs is intended; a page belonging wholly to the *next* section is not. See the amendment below.
- **Absolute pages only** (`\abspage`), never printed page numbers (`\page`). Front matter is roman-numbered, so they differ — verified: `\zref@newlabel{parodypage@one/lead-in}{\default{1}\page{1}\abspage{3}}`.
- This repo's working tree is shared with concurrent agent sessions. **Never `git add -A`.** Add only the exact paths each task names.
- Version bumps must commit `pyproject.toml` **and** `uv.lock` in the same commit.
- Tests that compile LaTeX carry `@pytest.mark.pdf` and skip when TeX is absent, following `tests/test_print_pdf.py`.

## Amendment (during execution, after Task 4)

Tasks 1–4 shipped, but the range rule this plan originally specified —
`end(i) = start(i+1)` — was **wrong at chapter breaks** and was corrected in
commit `df19e4f`. `\chapter` forces a page break, so the next section's opening
page can belong wholly to it; under the original rule the last section of every
chapter ended with the *next* chapter's title page. Dumping per-page text of a
real build caught it; the original "tiling" assertion passed happily.

What changed, versus the code shown in Tasks 1–4 below:

- `build_pdf` emits a **second mark per section**, `\parodypagemark{<key>@end}`,
  immediately after that section's `\input`.
- `build_ranges(order, pages, end_page)` takes one `pages` dict holding both
  marks (not a `starts` dict) and computes
  `end = max(own_end, next_start - 1)`.
- The end-to-end invariant is **coverage with no gaps**, not strict tiling:
  blank verso pages stay covered, but no section swallows a later section's
  opening page.

The code in Tasks 1–4 below is left as originally written for the record. Read
`parody/writers/pagemap.py` for current behaviour. **Tasks 5–7 are unaffected.**

---

### Task 1: `insert_section_mark`

Places the page mark into a generated section `.tex`, immediately after the first sectioning command's argument.

**Files:**
- Create: `parody/writers/pagemap.py`
- Test: `tests/test_pagemap.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `insert_section_mark(tex: str, key: str) -> str`.

Background the implementer needs: `parody/filters/print.lua` (`headerer_latex`, ~line 253) emits headings as `\section{...}`, `\subsection{...}`, `\subsubsection{...}`, or `\lab{...}`, optionally starred, each followed by `\label{...}` lines. Some sections carry **no** heading at all — their title lives in `parody.yaml` (see task #576) — and those must still get a mark.

- [ ] **Step 1: Write the failing test**

```python
"""Section → print-PDF page ranges: placing the page marks."""

from parody.writers.pagemap import insert_section_mark

MARK = "\\parodypagemark{one/alpha}"


def test_mark_goes_after_the_first_sectioning_command():
    tex = "\\section{Alpha}\n\\label{sec:alpha}\n\nBody.\n"
    out = insert_section_mark(tex, "one/alpha")
    assert out.startswith("\\section{Alpha}" + MARK)
    assert "\\label{sec:alpha}" in out


def test_starred_and_deeper_levels_are_recognised():
    for cmd in ("section*", "subsection", "subsubsection", "lab"):
        tex = "\\%s{T}\nBody.\n" % cmd
        out = insert_section_mark(tex, "one/alpha")
        assert out.startswith("\\%s{T}%s" % (cmd, MARK)), cmd


def test_braces_in_the_title_do_not_end_the_argument():
    tex = "\\section{The \\texttt{argv} array}\nBody.\n"
    out = insert_section_mark(tex, "one/alpha")
    assert out.startswith("\\section{The \\texttt{argv} array}" + MARK)


def test_math_and_escaped_braces_in_the_title():
    tex = "\\section{Sets $\\{x\\}$ and \\$5}\nBody.\n"
    out = insert_section_mark(tex, "one/alpha")
    assert out.startswith("\\section{Sets $\\{x\\}$ and \\$5}" + MARK)


def test_optional_argument_is_skipped():
    tex = "\\section[Short]{Long title}\nBody.\n"
    out = insert_section_mark(tex, "one/alpha")
    assert out.startswith("\\section[Short]{Long title}" + MARK)


def test_headless_section_gets_the_mark_at_the_top():
    # #576: a section whose markdown opens with no heading — its title comes
    # from parody.yaml. It still needs a page mark.
    tex = "Body text with no heading at all.\n"
    out = insert_section_mark(tex, "one/alpha")
    assert out.startswith(MARK)
    assert "Body text" in out


def test_unbalanced_braces_fail_safe_to_the_top():
    tex = "\\section{Never closed\nBody.\n"
    out = insert_section_mark(tex, "one/alpha")
    assert out.startswith(MARK)


def test_the_key_is_used_verbatim():
    out = insert_section_mark("\\section{A}\n", "ch-two/sub-sec")
    assert "\\parodypagemark{ch-two/sub-sec}" in out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_pagemap.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'parody.writers.pagemap'`

- [ ] **Step 3: Write minimal implementation**

```python
"""Section → print-PDF page ranges.

The print PDF is built once; each section's PDF is the page range cut out of
it, never a separate compilation (see the spec's D6 — a separately compiled
section starts at page 1, replaces the book's float placement, and resets
every counter, which destroys the "print one section at a time and it becomes
the whole book" property).

This module owns the three steps that turn a LaTeX build into a range table:

    insert_section_mark   place a \\parodypagemark in a generated section .tex
    read_pagemap          read the marks' absolute pages back out of main.aux
    build_ranges          turn start pages into inclusive [start, end] ranges
"""

import re

# print.lua's headerer_latex emits these; \lab is the MIT-class-private lab
# heading. Longer names first so \subsection is not matched as \section.
_SECTIONING = re.compile(
    r"\\(?:subsubsection|subsection|section|chapter|lab)\*?\s*(?=[\[{])")


def _skip_group(tex, i, open_ch, close_ch):
    """Index just past the balanced group starting at ``i``, or None.

    Honours TeX escaping: ``\\{`` is a literal brace, not a nesting level.
    """
    if i >= len(tex) or tex[i] != open_ch:
        return None
    depth = 0
    while i < len(tex):
        c = tex[i]
        if c == "\\":
            i += 2  # an escaped character, whatever it is
            continue
        if c == open_ch:
            depth += 1
        elif c == close_ch:
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return None


def insert_section_mark(tex, key):
    """Return ``tex`` with ``\\parodypagemark{key}`` after its first heading.

    The mark must land *after* the sectioning command, not before it: a mark in
    vertical mode ahead of a heading can be carried to the previous page by the
    page builder, which would start the range one page late and silently drop
    the section's first page. After the heading it always reports the page the
    heading itself landed on.

    Sections with no heading of their own (#576) take the mark at the top,
    which is the correct start for them.
    """
    mark = "\\parodypagemark{%s}" % key
    m = _SECTIONING.search(tex)
    if m is None:
        return mark + "%\n" + tex
    i = m.end()
    if i < len(tex) and tex[i] == "[":
        i = _skip_group(tex, i, "[", "]")
        if i is None:
            return mark + "%\n" + tex
    i = _skip_group(tex, i, "{", "}")
    if i is None:
        return mark + "%\n" + tex
    return tex[:i] + mark + tex[i:]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_pagemap.py -v`
Expected: PASS (8 tests)

- [ ] **Step 5: Commit**

```bash
git add parody/writers/pagemap.py tests/test_pagemap.py
git commit -m "pagemap: place print page marks in generated section LaTeX (task #583)"
```

---

### Task 2: `read_pagemap` and `build_ranges`

Read the marks back out of `main.aux` and turn start pages into inclusive ranges.

**Files:**
- Modify: `parody/writers/pagemap.py`
- Test: `tests/test_pagemap.py`

**Interfaces:**
- Consumes: `insert_section_mark` (same module).
- Produces:
  - `read_pagemap(aux_path) -> dict[str, int]` — `{key: abspage}`, `@end` included as a key.
  - `build_ranges(order: list[str], starts: dict[str, int], end_page: int) -> dict[str, list[int]]` — `{key: [start, end]}`.

The `.aux` format was verified against TeX Live 2026 with a live compile:

```
\zref@newlabel{parodypage@one/lead-in}{\default{1}\page{1}\abspage{3}}
\zref@newlabel{parodypage@one/alpha}{\default{1.1}\page{2}\abspage{4}}
\zref@newlabel{parodypage@@end}{\default{1.2}\page{3}\abspage{5}}
```

Note `\page{1}` and `\abspage{3}` on the same record: the printed page number and the physical one, differing because of roman front matter. **Read `\abspage`.**

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_pagemap.py

from parody.writers.pagemap import build_ranges, read_pagemap

AUX = """\
\\relax
\\@writefile{toc}{\\contentsline {chapter}{One}{1}{}}
\\zref@newlabel{parodypage@one/lead-in}{\\default{1}\\page{1}\\abspage{3}}
\\zref@newlabel{parodypage@one/alpha}{\\default{1.1}\\page{2}\\abspage{4}}
\\zref@newlabel{parodypage@one/beta}{\\default{1.2}\\page{3}\\abspage{9}}
\\zref@newlabel{parodypage@@end}{\\default{1.2}\\page{3}\\abspage{11}}
\\newlabel{sec:alpha}{{1.1}{4}{Alpha}{section.1.1}{}}
\\gdef\\zref@default{}
"""


def test_read_pagemap_reads_abspage_not_printed_page(tmp_path):
    aux = tmp_path / "main.aux"
    aux.write_text(AUX)
    got = read_pagemap(aux)
    # \page{1} vs \abspage{3}: roman front matter makes them differ.
    assert got["one/lead-in"] == 3
    assert got["one/alpha"] == 4
    assert got["@end"] == 11


def test_read_pagemap_ignores_other_labels(tmp_path):
    aux = tmp_path / "main.aux"
    aux.write_text(AUX)
    assert "sec:alpha" not in read_pagemap(aux)


def test_read_pagemap_missing_file_is_empty(tmp_path):
    assert read_pagemap(tmp_path / "nope.aux") == {}


def test_ranges_are_inclusive_and_tile_the_book():
    order = ["one/lead-in", "one/alpha", "one/beta"]
    starts = {"one/lead-in": 3, "one/alpha": 4, "one/beta": 9}
    got = build_ranges(order, starts, end_page=11)
    assert got == {
        "one/lead-in": [3, 4],   # shares page 4 with alpha — tolerated
        "one/alpha": [4, 9],     # shares page 9 with beta
        "one/beta": [9, 11],
    }
    # the tiling invariant: each range ends where the next begins
    keys = list(got)
    for a, b in zip(keys, keys[1:]):
        assert got[a][1] == got[b][0]


def test_ranges_skip_sections_that_produced_no_mark():
    order = ["one/lead-in", "one/missing", "one/beta"]
    starts = {"one/lead-in": 3, "one/beta": 9}
    got = build_ranges(order, starts, end_page=11)
    assert "one/missing" not in got
    assert got["one/lead-in"] == [3, 9]


def test_a_backwards_end_never_produces_an_inverted_range():
    order = ["one/a", "one/b"]
    starts = {"one/a": 7, "one/b": 5}
    got = build_ranges(order, starts, end_page=9)
    assert got["one/a"] == [7, 7]


def test_empty_inputs_are_empty():
    assert build_ranges([], {}, end_page=1) == {}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_pagemap.py -v`
Expected: FAIL — `ImportError: cannot import name 'build_ranges'`

- [ ] **Step 3: Write minimal implementation**

Append to `parody/writers/pagemap.py` (and add `from pathlib import Path` to the imports at the top):

```python
# zref-abspage writes one record per mark. \page is the PRINTED page number
# (roman in front matter, restarted at \mainmatter); \abspage is the physical
# one. Extraction needs the physical one.
_ZREF_RECORD = re.compile(
    r"\\zref@newlabel\{parodypage@(?P<key>[^}]*)\}\{(?P<body>[^\n]*)\}")
_ABSPAGE = re.compile(r"\\abspage\{(\d+)\}")


def read_pagemap(aux_path):
    """``{key: absolute page}`` for every page mark recorded in ``main.aux``.

    Returns ``{}`` when the aux file is absent — a build that skipped LaTeX
    (no latexmk installed) must degrade to "no page map", never to a crash.
    """
    path = Path(aux_path)
    if not path.is_file():
        return {}
    text = path.read_text(encoding="utf-8", errors="replace")
    pages = {}
    for m in _ZREF_RECORD.finditer(text):
        abspage = _ABSPAGE.search(m.group("body"))
        if abspage:
            pages[m.group("key")] = int(abspage.group(1))
    return pages


def build_ranges(order, starts, end_page):
    """Inclusive ``[start, end]`` page ranges, keyed ``"<chapter>/<section>"``.

    ``end(i)`` is ``start(i+1)`` — deliberately inclusive. When one section
    ends and the next begins on the same sheet, that sheet appears in both
    PDFs; the task accepts this, and it makes the ranges tile the book with no
    gaps, which is the end-to-end invariant worth asserting.

    Sections whose mark never reached the aux (a build error, a section that
    emitted nothing) are omitted rather than guessed at.
    """
    known = [k for k in order if k in starts]
    ranges = {}
    for i, key in enumerate(known):
        start = starts[key]
        end = starts[known[i + 1]] if i + 1 < len(known) else end_page
        # max(): a backwards end would mean a stale aux; clamp rather than
        # emit an inverted range the slicer would reject.
        ranges[key] = [start, max(start, end)]
    return ranges
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_pagemap.py -v`
Expected: PASS (15 tests)

- [ ] **Step 5: Commit**

```bash
git add parody/writers/pagemap.py tests/test_pagemap.py
git commit -m "pagemap: read absolute pages from the aux and build inclusive ranges (task #583)"
```

---

### Task 3: The LaTeX package and `build_pdf` wiring

Emit the marks during a print build, without editing any profile.

**Files:**
- Create: `parody/profiles/_shared/parody-pagemap.sty`
- Modify: `parody/writers/latex.py` (`resolve_profile` ~line 173; `build_pdf` ~lines 191–389)
- Test: `tests/test_pagemap_build.py`

**Interfaces:**
- Consumes: `insert_section_mark` from Task 1.
- Produces: `build_pdf(..., pagemap=True)` writes marks into `main.tex` and each section `.tex`; `build_pdf` gains a module-level constant `SHARED_PROFILE_DIR`.

Key placement rules from the spec:
- A chapter's **first** section is marked in `main.tex` right after `\chapter{...}\label{...}`, so its range opens on the chapter title page (this is what makes "chapter title + lead-in is one section" work). That section's own `.tex` is therefore *not* marked.
- Every other section is marked inside its own `.tex`.
- `\parodypagemark{@end}` is appended after the last chapter, before `\backmatter`, so the last section stops at the bibliography.

- [ ] **Step 1: Write the failing test**

```python
"""Page marks reach main.tex and the section .tex tree during a print build.

These run without TeX: build_pdf writes the whole LaTeX tree before it ever
calls latexmk, so the wiring is checkable by reading the generated sources.
"""

import pytest

from parody.writers.latex import build_pdf

PARODY_YAML = """\
title: Page Map Test
slug: pagemap-test
authors: [Tester]
chapters:
  - slug: one
    title: Chapter One
    sections: [lead-in, alpha]
  - slug: two
    title: Chapter Two
    sections: [beta]
"""


@pytest.fixture
def project(tmp_path, monkeypatch):
    # No TeX: build_pdf writes the sources and returns None.
    monkeypatch.setattr("parody.writers.latex.shutil.which", lambda *a, **k: None)
    root = tmp_path / "pagemap-test"
    (root / "chapters" / "one").mkdir(parents=True)
    (root / "chapters" / "two").mkdir(parents=True)
    (root / "parody.yaml").write_text(PARODY_YAML)
    (root / "chapters" / "one" / "lead-in.md").write_text("Chapter intro prose.\n")
    (root / "chapters" / "one" / "alpha.md").write_text("# Alpha\n\nAlpha body.\n")
    (root / "chapters" / "two" / "beta.md").write_text("# Beta\n\nBeta body.\n")
    return root


def test_the_pagemap_package_is_injected_without_editing_the_profile(project):
    build_pdf(project)
    build = project / "build" / "print"
    assert "\\usepackage{parody-pagemap}" in (build / "main.tex").read_text()
    # copied in beside the profile's own files
    assert (build / "parody-pagemap.sty").is_file()


def test_first_section_of_a_chapter_is_marked_at_the_chapter_opening(project):
    build_pdf(project)
    build = project / "build" / "print"
    main = (build / "main.tex").read_text()
    # the mark sits after \chapter, so the range opens on the chapter page
    assert "\\chapter{Chapter One}" in main
    assert "\\parodypagemark{one/lead-in}" in main
    assert main.index("\\chapter{Chapter One}") < main.index(
        "\\parodypagemark{one/lead-in}")
    assert main.index("\\parodypagemark{one/lead-in}") < main.index(
        "\\input{sections/one/lead-in.tex}")
    # ...and NOT a second time inside the section itself
    leadin = (build / "sections" / "one" / "lead-in.tex").read_text()
    assert "\\parodypagemark" not in leadin


def test_later_sections_are_marked_inside_their_own_tex(project):
    build_pdf(project)
    build = project / "build" / "print"
    alpha = (build / "sections" / "one" / "alpha.tex").read_text()
    assert "\\parodypagemark{one/alpha}" in alpha
    assert alpha.index("\\section{Alpha}") < alpha.index("\\parodypagemark")
    assert "\\parodypagemark{one/alpha}" not in (build / "main.tex").read_text()


def test_every_chapter_gets_its_own_first_section_mark(project):
    build_pdf(project)
    main = (project / "build" / "print" / "main.tex").read_text()
    # chapter two's only section is its first, so it is marked at the opening
    assert "\\parodypagemark{two/beta}" in main
    assert "\\parodypagemark" not in (
        project / "build" / "print" / "sections" / "two" / "beta.tex").read_text()


def test_end_sentinel_closes_the_last_section(project):
    build_pdf(project)
    main = (project / "build" / "print" / "main.tex").read_text()
    assert "\\parodypagemark{@end}" in main
    assert main.index("\\input{sections/two/beta.tex}") < main.index(
        "\\parodypagemark{@end}")
    assert main.index("\\parodypagemark{@end}") < main.index("\\backmatter")


def test_pagemap_can_be_turned_off(project):
    build_pdf(project, pagemap=False)
    main = (project / "build" / "print" / "main.tex").read_text()
    assert "\\parodypagemark" not in main
    assert "\\usepackage{parody-pagemap}" not in main


def test_shared_is_not_selectable_as_a_profile():
    from parody.writers.latex import resolve_profile
    # "_shared" holds support files, not a profile; a bare "_shared" must be
    # treated as a filesystem path (and so not resolve to the bundled dir).
    assert resolve_profile("_shared").name == "_shared"
    assert "profiles" not in str(resolve_profile("_shared").parent)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_pagemap_build.py -v`
Expected: FAIL — `TypeError: build_pdf() got an unexpected keyword argument 'pagemap'`

- [ ] **Step 3a: Create the LaTeX package**

Create `parody/profiles/_shared/parody-pagemap.sty`:

```latex
%% parody-pagemap — absolute page marks for per-section PDF extraction.
%%
%% Injected by parody's print writer through main.tex.template's $flags slot,
%% so no print profile (including book-private ones) needs to know about it.
%%
%% \abspage is the PHYSICAL page index. The printed page number is not usable
%% here: front matter is roman-numbered and \mainmatter restarts the arabic
%% count, so page "1" is not the first sheet.
\NeedsTeXFormat{LaTeX2e}
\ProvidesPackage{parody-pagemap}[2026/08/13 parody per-section page marks]
\RequirePackage[user]{zref}
\RequirePackage{zref-abspage}
%% Distinctive name: a clash with a class/package macro would be masked by
%% nonstopmode and silently render the OTHER definition.
\newcommand{\parodypagemark}[1]{\zlabel{parodypage@#1}}
```

- [ ] **Step 3b: Wire it into `build_pdf`**

In `parody/writers/latex.py`, add near `BUNDLED_PROFILES` (~line 130):

```python
# Support files copied into every build dir regardless of profile (the page-map
# package). Leading underscore: not a selectable profile.
SHARED_PROFILE_DIR = BUNDLED_PROFILES / "_shared"
```

In `resolve_profile`, guard the underscore namespace — change the bundled-name
branch so support dirs cannot be selected:

```python
    if os.sep not in name and (os.altsep or os.sep) not in name:
        candidate = BUNDLED_PROFILES / name
        # names starting with "_" are support dirs (e.g. _shared), not profiles
        if candidate.is_dir() and not name.startswith("_"):
            return candidate
```

In `build_pdf`, change the signature to add `pagemap=True`:

```python
def build_pdf(project_dir, output_pdf=None, solutions=False, section=None,
              profile_dir=None, keep_build=False, build_dir=None,
              cloze_mode=None, pagemap=True):
```

After the profile files are copied (~line 222), add:

```python
    # Page-map support package, copied in beside the profile's own files. A
    # single-section build has no book to index into, so it never gets one.
    template_text = (profile_dir / "main.tex.template").read_text(encoding="utf-8")
    if pagemap and section:
        pagemap = False
    if pagemap and "$flags" not in template_text:
        print(f"⚠️  profile {profile_dir.name} has no $flags slot — "
              "per-section page map disabled for this build")
        pagemap = False
    if pagemap:
        shutil.copy2(SHARED_PROFILE_DIR / "parody-pagemap.sty",
                     build_dir / "parody-pagemap.sty")
```

Add `from .pagemap import build_ranges, insert_section_mark, read_pagemap` to
the module imports.

Inside the chapter loop, track order and mark the chapter's first section.
Replace the section loop body (~lines 273–281) with:

```python
            os.environ["PARODY_CHAPTER_DIR"] = str(Path(chapter.directory).resolve())
            first_in_chapter = bool(sections) and not section
            for sec_slug in sections:
                key = f"{chapter.slug}/{sec_slug}"
                pagemap_order.append(key)
                src = chapter.directory / f"{sec_slug}.md"
                stripped = build_dir / "sections" / chapter.slug / f"{sec_slug}.md"
                stripped.parent.mkdir(parents=True, exist_ok=True)
                strip_frontmatter(src, stripped, transform=transform)
                tex_path = build_dir / "sections" / chapter.slug / f"{sec_slug}.tex"
                print(f"  pandoc: {chapter.slug}/{sec_slug}.md → .tex")
                section_to_latex(stripped, tex_path, resource_dir=chapter.directory)
                if pagemap:
                    if first_in_chapter:
                        # Marked at the chapter opening instead (see below), so
                        # the range covers the chapter title page + lead-in.
                        chapters_tex.append(f"\\parodypagemark{{{key}}}")
                    else:
                        tex_path.write_text(
                            insert_section_mark(
                                tex_path.read_text(encoding="utf-8"), key),
                            encoding="utf-8")
                first_in_chapter = False
                chapters_tex.append(f"\\input{{sections/{chapter.slug}/{sec_slug}.tex}}")
```

Declare `pagemap_order = []` next to `chapters_tex = []` (~line 238).

After the loop, before the `if not chapters_tex:` guard, add:

```python
    if pagemap and chapters_tex:
        # Closes the last section's range at the end of the body, so it stops
        # at the bibliography rather than running through the back matter.
        chapters_tex.append("\\parodypagemark{@end}")
```

And in the flags block (~line 300), add:

```python
    if pagemap:
        flags.append("\\usepackage{parody-pagemap}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_pagemap_build.py tests/test_print_pdf.py -v`
Expected: PASS — the new file plus no regression in the existing print tests.

- [ ] **Step 5: Commit**

```bash
git add parody/profiles/_shared/parody-pagemap.sty parody/writers/latex.py tests/test_pagemap_build.py
git commit -m "print: emit absolute page marks per section, injected via \$flags (task #583)"
```

---

### Task 4: Emit the sidecar, and prove the ranges against a real PDF

**Files:**
- Modify: `parody/writers/pagemap.py`, `parody/writers/latex.py`
- Test: `tests/test_pagemap_build.py`

**Interfaces:**
- Consumes: `read_pagemap`, `build_ranges` (Task 2); the marks (Task 3).
- Produces:
  - `pdf_page_count(pdf_path) -> int | None` in `pagemap.py`
  - `sha256_file(path) -> str`
  - `sidecar_path(pdf_path) -> Path` — `book.pdf` → `book.pages.json`
  - `write_sidecar(pdf_path, ranges, cloze_mode="blank", solutions=False) -> Path`
  - `build_pdf` writes that sidecar beside the PDF it produced.

Sidecar shape (spec):

```json
{"schema": 1, "pdf": "book.pdf", "pages": 512, "sha256": "…",
 "cloze_mode": "blank", "solutions": false,
 "sections": {"one/lead-in": [3, 4]}}
```

Page count comes from poppler's `pdfinfo`, already a build dependency (content-repo CI installs poppler-utils for figure conversion). Absent → `None`, and the sidecar still ships with its ranges.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_pagemap_build.py

import json

from parody.writers.latex import build_pdf, have_tool

needs_tex = pytest.mark.skipif(
    not (have_tool("latexmk") and have_tool("lualatex")),
    reason="TeX (latexmk + lualatex) not available",
)


def test_no_sidecar_when_latex_never_ran(project):
    # No TeX → no PDF → nothing to describe. Must not crash or write a lie.
    assert build_pdf(project) is None
    assert not list(project.glob("*.pages.json"))


@pytest.mark.pdf
@needs_tex
def test_sidecar_ranges_tile_the_real_pdf(tmp_path):
    root = tmp_path / "pagemap-test"
    (root / "chapters" / "one").mkdir(parents=True)
    (root / "chapters" / "two").mkdir(parents=True)
    (root / "parody.yaml").write_text(PARODY_YAML)
    (root / "chapters" / "one" / "lead-in.md").write_text(
        "Chapter intro prose.\n\n\\clearpage\n\nMore intro.\n")
    (root / "chapters" / "one" / "alpha.md").write_text(
        "# Alpha\n\nAlpha body.\n\n\\clearpage\n\nMore alpha.\n")
    (root / "chapters" / "two" / "beta.md").write_text("# Beta\n\nBeta body.\n")

    pdf = build_pdf(root)
    assert pdf is not None and pdf.is_file()

    from parody.writers.pagemap import pdf_page_count
    sidecar = json.loads(pdf.with_suffix(".pages.json").read_text())

    assert sidecar["schema"] == 1
    assert sidecar["pdf"] == pdf.name
    assert sidecar["solutions"] is False
    assert len(sidecar["sha256"]) == 64

    ranges = sidecar["sections"]
    assert set(ranges) == {"one/lead-in", "one/alpha", "two/beta"}

    # every range is well formed and inside the document
    total = pdf_page_count(pdf)
    assert total is not None and sidecar["pages"] == total
    for key, (start, end) in ranges.items():
        assert 1 <= start <= end <= total, key

    # the tiling invariant: consecutive sections share their boundary page
    ordered = ["one/lead-in", "one/alpha", "two/beta"]
    for a, b in zip(ordered, ordered[1:]):
        assert ranges[a][1] == ranges[b][0], (a, b)

    # a chapter's first section opens ON the chapter page, so chapter two's
    # first section starts strictly after chapter one's content
    assert ranges["two/beta"][0] > ranges["one/alpha"][0]


@pytest.mark.pdf
@needs_tex
def test_pagemap_package_does_not_clash_with_the_class(tmp_path, capfd):
    # A \newcommand collision is masked by nonstopmode and silently renders the
    # OTHER definition, so gate on "LaTeX Error" rather than only on
    # "Undefined control sequence".
    root = tmp_path / "pagemap-test"
    (root / "chapters" / "one").mkdir(parents=True)
    (root / "chapters" / "two").mkdir(parents=True)
    (root / "parody.yaml").write_text(PARODY_YAML)
    (root / "chapters" / "one" / "lead-in.md").write_text("Intro.\n")
    (root / "chapters" / "one" / "alpha.md").write_text("# Alpha\n\nBody.\n")
    (root / "chapters" / "two" / "beta.md").write_text("# Beta\n\nBody.\n")
    build_pdf(root)
    log = (root / "build" / "print" / "main.log").read_text(
        encoding="utf-8", errors="replace")
    assert "LaTeX Error" not in log
    assert "already defined" not in log
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_pagemap_build.py -v`
Expected: FAIL — `ImportError: cannot import name 'pdf_page_count'`

- [ ] **Step 3a: Add the sidecar helpers**

Append to `parody/writers/pagemap.py` (add `import hashlib`, `import json`,
`import shutil`, `import subprocess` at the top):

```python
SIDECAR_SCHEMA = 1


def pdf_page_count(pdf_path):
    """Page count via poppler's ``pdfinfo``, or None when it is unavailable.

    poppler is already a build dependency (content-repo CI installs
    poppler-utils for figure conversion). A missing pdfinfo degrades the
    sidecar's ``pages`` field to null; the ranges are unaffected.
    """
    exe = shutil.which("pdfinfo")
    if not exe:
        return None
    try:
        out = subprocess.run([exe, str(pdf_path)], capture_output=True,
                             text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None
    for line in out.stdout.splitlines():
        if line.startswith("Pages:"):
            try:
                return int(line.split(":", 1)[1].strip())
            except ValueError:
                return None
    return None


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sidecar_path(pdf_path):
    """Where the page map for ``pdf_path`` lives: book.pdf → book.pages.json."""
    return Path(pdf_path).with_suffix(".pages.json")


def write_sidecar(pdf_path, ranges, cloze_mode="blank", solutions=False):
    """Write the page-map sidecar beside the PDF. Returns its path."""
    pdf_path = Path(pdf_path)
    path = sidecar_path(pdf_path)
    payload = {
        "schema": SIDECAR_SCHEMA,
        "pdf": pdf_path.name,
        "pages": pdf_page_count(pdf_path),
        "sha256": sha256_file(pdf_path),
        "cloze_mode": cloze_mode,
        "solutions": bool(solutions),
        "sections": ranges,
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path
```

- [ ] **Step 3b: Emit it from `build_pdf`**

In `parody/writers/latex.py`, after the PDF is copied to `output_pdf`
(~line 385, right before the `if not keep_build:` line), add:

```python
    if pagemap:
        starts = read_pagemap(build_dir / "main.aux")
        end_page = starts.get("@end")
        if end_page is None:
            print("⚠️  no page marks in main.aux — per-section page map "
                  "omitted (rerun the build if this persists)")
        else:
            ranges = build_ranges(pagemap_order, starts, end_page)
            missing = [k for k in pagemap_order if k not in ranges]
            if missing:
                print(f"⚠️  page map: no mark for {len(missing)} section(s): "
                      f"{', '.join(missing[:5])}"
                      f"{'…' if len(missing) > 5 else ''}")
            side = write_sidecar(output_pdf, ranges, cloze_mode=cloze_mode,
                                 solutions=solutions)
            print(f"  pagemap: {len(ranges)} section ranges → {side.name}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_pagemap_build.py -v` (add `-m pdf` on a machine with TeX to include the compile tests)
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add parody/writers/pagemap.py parody/writers/latex.py tests/test_pagemap_build.py
git commit -m "print: write a page-map sidecar beside the PDF (task #583)"
```

---

### Task 5: Editions in `build_pdf`

`build_pdf` has no edition support; rtcbook has ed1/ed2, so its per-section PDFs would otherwise be wrong. Reuse `build_project`'s existing helpers rather than reimplementing the overlay rules.

**Files:**
- Modify: `parody/writers/latex.py` (`build_pdf`), `parody/cli.py` (`cmd_pdf`, `p_pdf`)
- Test: `tests/test_pagemap_build.py`

**Interfaces:**
- Consumes: `parody.build._meta_for_edition(meta, edition)`, `parody.build._resolve_section_file(chapter_dir, section_slug, edition_id)` (both already exist, `parody/build.py` ~lines 270–300).
- Produces: `build_pdf(..., edition=None)` where `edition` is a normalized edition dict from `config.normalize_editions`; `parody pdf --edition <id>`.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_pagemap_build.py

EDITION_YAML = """\
title: Edition Test
slug: edition-test
authors: [Tester]
editions:
  - id: ed1
    title: First
  - id: ed2
    title: Second
    default: true
chapters:
  - slug: one
    title: Chapter One
    sections: [lead-in, alpha, only-two]
"""


@pytest.fixture
def edition_project(tmp_path, monkeypatch):
    monkeypatch.setattr("parody.writers.latex.shutil.which", lambda *a, **k: None)
    root = tmp_path / "edition-test"
    ch = root / "chapters" / "one"
    ch.mkdir(parents=True)
    (root / "parody.yaml").write_text(EDITION_YAML)
    (ch / "lead-in.md").write_text("Shared intro.\n")
    (ch / "alpha.md").write_text("# Alpha\n\nShared alpha.\n")
    # a per-edition fork: ed2 reads its own copy
    (ch / "alpha.ed2.md").write_text("# Alpha\n\nRevised alpha for ed2.\n")
    # a section only ed2 carries
    (ch / "only-two.md").write_text(
        "---\neditions: [ed2]\n---\n\n# Only Two\n\nSecond edition only.\n")
    return root


def _edition(project_dir, ed_id):
    from parody.config import load_project
    project = load_project(project_dir)
    return next(e for e in project.editions if e["id"] == ed_id)


def test_edition_build_uses_the_per_edition_fork(edition_project):
    build_pdf(edition_project, edition=_edition(edition_project, "ed2"),
              build_dir=edition_project / "build" / "ed2")
    alpha = (edition_project / "build" / "ed2" / "sections" / "one"
             / "alpha.tex").read_text()
    assert "Revised alpha for ed2" in alpha


def test_edition_build_omits_sections_not_in_that_edition(edition_project):
    build_pdf(edition_project, edition=_edition(edition_project, "ed1"),
              build_dir=edition_project / "build" / "ed1")
    main = (edition_project / "build" / "ed1" / "main.tex").read_text()
    assert "\\input{sections/one/alpha.tex}" in main
    assert "only-two" not in main
    assert "\\parodypagemark{one/only-two}" not in main


def test_edition_build_marks_only_the_sections_it_carries(edition_project):
    build_pdf(edition_project, edition=_edition(edition_project, "ed2"),
              build_dir=edition_project / "build" / "ed2")
    main = (edition_project / "build" / "ed2" / "main.tex").read_text()
    assert "\\parodypagemark{one/lead-in}" in main
    assert "\\input{sections/one/only-two.tex}" in main


def test_no_edition_builds_every_section_as_before(edition_project):
    build_pdf(edition_project)
    main = (edition_project / "build" / "print" / "main.tex").read_text()
    for slug in ("lead-in", "alpha", "only-two"):
        assert f"\\input{{sections/one/{slug}.tex}}" in main
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_pagemap_build.py -k edition -v`
Expected: FAIL — `TypeError: build_pdf() got an unexpected keyword argument 'edition'`

- [ ] **Step 3: Write minimal implementation**

In `parody/writers/latex.py`, add `edition=None` to the `build_pdf` signature.
Just after `project = load_project(project_dir)`, add:

```python
    # Editions: reuse build_project's overlay helpers rather than restating the
    # rules, so print and web can never disagree about what an edition contains.
    from ..build import _meta_for_edition, _resolve_section_file
    active_meta = _meta_for_edition(project.meta, edition) if edition \
        else project.meta
```

Change the two `project.meta` reads that follow to `active_meta`:
`resolve_cloze_mode(active_meta, cloze_mode)` and
`content_transforms(active_meta, project.directory, target="print")`.
Also change `chapter_start`, `book`, and `front_matter` lookups later in the
function from `project.meta` to `active_meta`, and the template substitution's
`project.meta.get("title", …)` / `project.meta.get("author", [])`.

In the chapter loop, resolve each section's source file through the overlay.
Replace `src = chapter.directory / f"{sec_slug}.md"` with:

```python
                if edition:
                    filename = _resolve_section_file(
                        chapter.directory, sec_slug, edition["id"])
                    if filename is None:
                        continue  # section absent from this edition
                    src = chapter.directory / filename
                else:
                    src = chapter.directory / f"{sec_slug}.md"
```

Move `pagemap_order.append(key)` to *after* this block so a skipped section is
never ordered, and guard the chapter heading so an edition-empty chapter emits
no `\chapter`: compute the edition's surviving section list before emitting the
chapter heading —

```python
            if edition:
                sections = [
                    s for s in sections
                    if _resolve_section_file(chapter.directory, s,
                                             edition["id"]) is not None]
```

placed immediately after the existing `sections = chapter.section_slugs` /
`--section` filtering, before `if sections and not section:`.

In `parody/cli.py`, `cmd_pdf`: resolve `--edition` the same way `cmd_build`
does and pass it through:

```python
def cmd_pdf(args):
    from .config import load_project
    from .writers.latex import build_pdf

    project = load_project(args.project_dir)
    ed = None
    if getattr(args, "edition", None):
        ed = next((e for e in project.editions if e["id"] == args.edition), None)
        if ed is None:
            known = ", ".join(e["id"] for e in project.editions) or "none"
            print(f"error: unknown edition {args.edition!r} (known: {known})",
                  file=sys.stderr)
            return 1

    if not args.no_execute:
        from .build import build_project
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            build_project(args.project_dir, Path(td) / "artifact.json",
                          convert_jupytext=True, edition=ed)
    build_pdf(
        args.project_dir,
        output_pdf=args.output,
        solutions=args.solutions,
        section=args.section,
        profile_dir=args.profile,
        cloze_mode=args.clozes,
        edition=ed,
    )
    return 0
```

and register the flag beside the other `p_pdf` arguments:

```python
    p_pdf.add_argument("--edition",
                       help="build only this edition (by id); default builds "
                            "the unfiltered book")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_pagemap_build.py tests/test_print_pdf.py tests/test_editions.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add parody/writers/latex.py parody/cli.py tests/test_pagemap_build.py
git commit -m "print: build a single edition, reusing build_project's overlay helpers (task #583)"
```

---

### Task 6: Fold the page map into the artifact

**Files:**
- Modify: `parody/build.py` (`build_project`, `build_editions`), `parody/cli.py` (`cmd_build`, `p_build`), `parody/schemas/artifact-v2.json`
- Test: `tests/test_pagemap_artifact.py`

**Interfaces:**
- Consumes: the sidecar from Task 4.
- Produces:
  - `build_project(..., print_pages=None)` where `print_pages` is a path to a sidecar JSON.
  - Artifact gains top-level `print` = `{"pdf", "pages", "sha256"}` and per-section `print` = `{"pages": [start, end]}`.

- [ ] **Step 1: Write the failing test**

```python
"""The page-map sidecar reaches the artifact, keyed <chapter>/<section>."""

import json

import pytest

from parody.build import build_project

PARODY_YAML = """\
title: Artifact Page Map
slug: artifact-pagemap
authors: [Tester]
chapters:
  - slug: one
    title: Chapter One
    sections: [lead-in, alpha]
"""

SIDECAR = {
    "schema": 1,
    "pdf": "artifact-pagemap.pdf",
    "pages": 42,
    "sha256": "a" * 64,
    "cloze_mode": "blank",
    "solutions": False,
    "sections": {"one/lead-in": [3, 4], "one/alpha": [4, 9]},
}


@pytest.fixture
def project(tmp_path):
    root = tmp_path / "artifact-pagemap"
    (root / "chapters" / "one").mkdir(parents=True)
    (root / "parody.yaml").write_text(PARODY_YAML)
    (root / "chapters" / "one" / "lead-in.md").write_text("Intro.\n")
    (root / "chapters" / "one" / "alpha.md").write_text("# Alpha\n\nBody.\n")
    return root


@pytest.fixture
def sidecar(tmp_path):
    p = tmp_path / "artifact-pagemap.pages.json"
    p.write_text(json.dumps(SIDECAR))
    return p


def _sections(artifact):
    return {s["slug"]: s for s in artifact["chapters"][0]["sections"]}


def test_sections_carry_their_page_range(project, sidecar, tmp_path):
    art = build_project(project, tmp_path / "out.json",
                        convert_jupytext=False, print_pages=sidecar)
    secs = _sections(art)
    assert secs["lead-in"]["print"] == {"pages": [3, 4]}
    assert secs["alpha"]["print"] == {"pages": [4, 9]}


def test_book_level_print_metadata_is_carried(project, sidecar, tmp_path):
    art = build_project(project, tmp_path / "out.json",
                        convert_jupytext=False, print_pages=sidecar)
    assert art["print"] == {
        "pdf": "artifact-pagemap.pdf", "pages": 42, "sha256": "a" * 64}


def test_without_a_sidecar_no_print_keys_appear(project, tmp_path):
    art = build_project(project, tmp_path / "out.json", convert_jupytext=False)
    assert "print" not in art
    assert all("print" not in s for s in _sections(art).values())


def test_a_section_absent_from_the_sidecar_gets_no_print_key(
        project, tmp_path):
    partial = tmp_path / "partial.pages.json"
    partial.write_text(json.dumps(
        dict(SIDECAR, sections={"one/lead-in": [3, 4]})))
    art = build_project(project, tmp_path / "out.json",
                        convert_jupytext=False, print_pages=partial)
    secs = _sections(art)
    assert secs["lead-in"]["print"] == {"pages": [3, 4]}
    assert "print" not in secs["alpha"]


def test_a_missing_sidecar_file_is_an_error(project, tmp_path):
    with pytest.raises(FileNotFoundError):
        build_project(project, tmp_path / "out.json", convert_jupytext=False,
                      print_pages=tmp_path / "nope.json")


def test_the_artifact_still_validates(project, sidecar, tmp_path):
    import jsonschema
    from pathlib import Path

    out = tmp_path / "out.json"
    build_project(project, out, convert_jupytext=False, print_pages=sidecar)
    schema = json.loads(
        (Path("parody/schemas/artifact-v2.json")).read_text())
    jsonschema.Draft202012Validator(schema).validate(json.loads(out.read_text()))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_pagemap_artifact.py -v`
Expected: FAIL — `TypeError: build_project() got an unexpected keyword argument 'print_pages'`

- [ ] **Step 3a: Thread it through `build_project`**

In `parody/build.py`, add `print_pages=None` to the `build_project` signature
and document it in the docstring. Near the top of the function, after
`project = load_project(project_dir)`:

```python
    # Per-section print page ranges from `parody pdf`'s sidecar (see
    # writers/pagemap.py). Absent → the artifact simply carries no print keys
    # and the web side renders no PDF affordance.
    print_map, print_meta = {}, None
    if print_pages:
        import json as _json

        data = _json.loads(Path(print_pages).read_text(encoding="utf-8"))
        print_map = data.get("sections") or {}
        print_meta = {"pdf": data.get("pdf", ""), "pages": data.get("pages"),
                      "sha256": data.get("sha256", "")}
```

Where the top-level output dict is assembled (~line 383, beside `"pdf_file"`),
add after the dict literal:

```python
    if print_meta:
        output["print"] = print_meta
```

In the per-section loop, where `section_data` is built for each section, add:

```python
                pages = print_map.get(f"{chapter.slug}/{section_slug}")
                if pages:
                    section_data["print"] = {"pages": pages}
```

(placed immediately before the section dict is appended to
`chapter_data["sections"]`).

Add `print_pages` passthrough to `build_editions` — it already forwards
`**kwargs`, so only the per-edition sidecar naming needs care; that is Task 7's
job, and `build_editions` needs no change here.

- [ ] **Step 3b: Declare the fields in the schema**

In `parody/schemas/artifact-v2.json`, add to the top-level `properties`:

```json
    "print": {
      "type": "object",
      "description": "The print PDF this artifact's page ranges index into.",
      "properties": {
        "pdf": { "type": "string" },
        "pages": { "type": ["integer", "null"] },
        "sha256": { "type": "string" }
      }
    },
```

and to the section item `properties`:

```json
        "print": {
          "type": "object",
          "description": "Inclusive [start, end] absolute page range of this section in the print PDF. The end page is shared with the next section when both fall on one sheet.",
          "required": ["pages"],
          "properties": {
            "pages": {
              "type": "array",
              "items": { "type": "integer", "minimum": 1 },
              "minItems": 2, "maxItems": 2
            }
          }
        },
```

- [ ] **Step 3c: Expose the CLI flag**

In `parody/cli.py`, add to `cmd_build`'s `kwargs`:

```python
        print_pages=getattr(args, "print_pages", None),
```

and register:

```python
    p_build.add_argument("--print-pages", metavar="SIDECAR.pages.json",
                         help="page-map sidecar from `parody pdf`; folds each "
                              "section's print page range into the artifact")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_pagemap_artifact.py tests/test_schema_v2.py tests/test_golden_artifacts.py -v`
Expected: PASS — golden artifacts unchanged, because no sidecar means no new keys.

- [ ] **Step 5: Commit**

```bash
git add parody/build.py parody/cli.py parody/schemas/artifact-v2.json tests/test_pagemap_artifact.py
git commit -m "artifact: carry per-section print page ranges (task #583)"
```

---

### Task 7: `parody publish`

One command that publishes the latest to print and to web.

**Files:**
- Create: `parody/publish.py`
- Modify: `parody/cli.py`
- Modify: `parody/templates/content_repo/.github/workflows/build.yml`
- Test: `tests/test_publish.py`

**Interfaces:**
- Consumes: `build_pdf` (Tasks 3–5), `build_project` (Task 6), `sidecar_path` (Task 4).
- Produces: `publish(project_dir, output_dir, **kwargs) -> list[Path]` and `parody publish`.

Ordering matters and is not negotiable: the PDF must build **first**, because the artifact consumes its sidecar.

- [ ] **Step 1: Write the failing test**

```python
"""`parody publish`: print then web, in that order, wired by the sidecar."""

import json

import pytest

from parody.publish import publish

PARODY_YAML = """\
title: Publish Test
slug: publish-test
authors: [Tester]
chapters:
  - slug: one
    title: Chapter One
    sections: [lead-in, alpha]
"""

EDITION_YAML = PARODY_YAML + """\
editions:
  - id: ed1
    title: First
  - id: ed2
    title: Second
    default: true
"""


@pytest.fixture
def project(tmp_path):
    root = tmp_path / "publish-test"
    (root / "chapters" / "one").mkdir(parents=True)
    (root / "parody.yaml").write_text(PARODY_YAML)
    (root / "chapters" / "one" / "lead-in.md").write_text("Intro.\n")
    (root / "chapters" / "one" / "alpha.md").write_text("# Alpha\n\nBody.\n")
    return root


def _fake_pdf(monkeypatch, ranges):
    """Stand in for a LaTeX build: drop a PDF + its sidecar and return it."""
    calls = []

    def fake_build_pdf(project_dir, output_pdf=None, **kw):
        from parody.writers.pagemap import sidecar_path
        calls.append({"project_dir": project_dir, "output_pdf": output_pdf, **kw})
        out = __import__("pathlib").Path(output_pdf)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"%PDF-1.7\n")
        sidecar_path(out).write_text(json.dumps({
            "schema": 1, "pdf": out.name, "pages": 9, "sha256": "b" * 64,
            "cloze_mode": "blank", "solutions": False, "sections": ranges}))
        return out

    monkeypatch.setattr("parody.publish.build_pdf", fake_build_pdf)
    return calls


def test_publish_builds_the_pdf_before_the_artifact(project, tmp_path, monkeypatch):
    _fake_pdf(monkeypatch, {"one/lead-in": [1, 2], "one/alpha": [2, 9]})
    out = tmp_path / "out"
    written = publish(project, out, convert_jupytext=False)
    artifact = json.loads((out / "publish-test.json").read_text())
    secs = {s["slug"]: s for s in artifact["chapters"][0]["sections"]}
    assert secs["alpha"]["print"] == {"pages": [2, 9]}
    assert artifact["print"]["pages"] == 9
    assert (out / "publish-test.pdf") in written


def test_skip_pdf_reuses_an_existing_sidecar(project, tmp_path, monkeypatch):
    calls = _fake_pdf(monkeypatch, {"one/alpha": [2, 9]})
    out = tmp_path / "out"
    publish(project, out, convert_jupytext=False)
    calls.clear()
    publish(project, out, convert_jupytext=False, skip_pdf=True)
    assert calls == []
    artifact = json.loads((out / "publish-test.json").read_text())
    assert artifact["print"]["pages"] == 9


def test_pdf_only_writes_no_artifact(project, tmp_path, monkeypatch):
    _fake_pdf(monkeypatch, {"one/alpha": [2, 9]})
    out = tmp_path / "out"
    publish(project, out, convert_jupytext=False, pdf_only=True)
    assert (out / "publish-test.pdf").is_file()
    assert not (out / "publish-test.json").exists()


def test_each_edition_gets_its_own_pdf_and_artifact(tmp_path, monkeypatch):
    root = tmp_path / "publish-test"
    (root / "chapters" / "one").mkdir(parents=True)
    (root / "parody.yaml").write_text(EDITION_YAML)
    (root / "chapters" / "one" / "lead-in.md").write_text("Intro.\n")
    (root / "chapters" / "one" / "alpha.md").write_text("# Alpha\n\nBody.\n")
    calls = _fake_pdf(monkeypatch, {"one/alpha": [2, 9]})
    out = tmp_path / "out"
    publish(root, out, convert_jupytext=False)
    assert {c["edition"]["id"] for c in calls} == {"ed1", "ed2"}
    assert (out / "publish-test.ed1.pdf").is_file()
    assert (out / "publish-test.ed2.pdf").is_file()
    assert (out / "publish-test.ed1.json").is_file()
    assert (out / "publish-test.ed2.json").is_file()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_publish.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'parody.publish'`

- [ ] **Step 3a: Write the module**

Create `parody/publish.py`:

```python
"""`parody publish`: build the print PDF and the web artifact together.

Order is not negotiable — the PDF builds first, because the artifact consumes
the page-map sidecar the PDF build emits. Doing it the other way round yields
an artifact with no print page ranges and therefore a book site with no PDF
downloads, silently.
"""

from pathlib import Path

from .build import build_project
from .config import load_project
from .writers.latex import build_pdf
from .writers.pagemap import sidecar_path


def publish(project_dir, output_dir, convert_jupytext=True, media_root=None,
            online_only=False, cloze_mode=None, profile_dir=None,
            skip_pdf=False, pdf_only=False):
    """Build print + web for every edition (or once, for a single-edition book).

    Returns every path written, PDFs and artifacts alike.
    """
    project_dir = Path(project_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    project = load_project(project_dir)

    editions = project.editions or [None]
    written = []
    for edition in editions:
        suffix = f".{edition['id']}" if edition else ""
        pdf_out = output_dir / f"{project.slug}{suffix}.pdf"
        sidecar = sidecar_path(pdf_out)

        if not skip_pdf:
            produced = build_pdf(
                project_dir,
                output_pdf=pdf_out,
                profile_dir=profile_dir,
                cloze_mode=cloze_mode,
                edition=edition,
                build_dir=project_dir / "build" / f"print{suffix}",
            )
            if produced is None:
                print(f"⚠️  no PDF produced for {project.slug}{suffix} "
                      "(is latexmk installed?)")
            else:
                written.append(Path(produced))
        elif pdf_out.is_file():
            written.append(pdf_out)

        if pdf_only:
            continue

        artifact_out = output_dir / f"{project.slug}{suffix}.json"
        build_project(
            project_dir, artifact_out,
            convert_jupytext=convert_jupytext,
            media_root=media_root,
            online_only=online_only,
            cloze_mode=cloze_mode,
            edition=edition,
            print_pages=sidecar if sidecar.is_file() else None,
        )
        written.append(artifact_out)

    return written
```

- [ ] **Step 3b: Register the command**

In `parody/cli.py`, add the handler:

```python
def cmd_publish(args):
    from .publish import publish

    written = publish(
        args.project_dir, args.output,
        convert_jupytext=not args.no_execute,
        media_root=args.media_root,
        online_only=args.online_only,
        cloze_mode=args.clozes,
        profile_dir=args.profile,
        skip_pdf=args.skip_pdf,
        pdf_only=args.pdf_only,
    )
    print(f"Published {len(written)} file(s): "
          f"{', '.join(p.name for p in written)}")
    return 0
```

and the parser, beside the others:

```python
    p_pub = sub.add_parser(
        "publish",
        help="build the print PDF and the web artifact together (print first, "
             "so the artifact carries each section's page range)")
    p_pub.add_argument("project_dir", help="project directory")
    p_pub.add_argument("-o", "--output", default="artifact",
                       help="output directory for PDFs + artifacts")
    p_pub.add_argument("--no-execute", action="store_true",
                       help="skip jupytext conversion/execution")
    p_pub.add_argument("--media-root", help="directory to receive the media/ tree")
    p_pub.add_argument("--online-only", action="store_true",
                       help="emit only the public web subset (see `build`)")
    p_pub.add_argument("--clozes", metavar="MODE",
                       help="cloze rendering: blank | key | full")
    p_pub.add_argument("--profile", help="LaTeX profile directory or bundled name")
    p_pub.add_argument("--skip-pdf", action="store_true",
                       help="reuse the existing PDF + sidecar; build only the artifact")
    p_pub.add_argument("--pdf-only", action="store_true",
                       help="build only the PDF + sidecar; write no artifact")
    p_pub.set_defaults(func=cmd_publish)
```

- [ ] **Step 3c: Scaffold the opt-in CI job**

Append to `parody/templates/content_repo/.github/workflows/build.yml`, at the
end of the file, commented out:

```yaml
#  # Opt-in print job: builds the PDF + page-map sidecar in the pinned TeX Live
#  # image and attaches them to the release, so the book site can serve
#  # per-section PDFs. Uncomment to enable — it adds ~10-20 min to a tagged
#  # build, and the image is large. Locally, `parody publish` does the same
#  # thing without Docker.
#  print:
#    if: startsWith(github.ref, 'refs/tags/v')
#    runs-on: ubuntu-latest
#    container:
#      image: texlive/texlive:latest-full
#    steps:
#      - uses: actions/checkout@v5
#      - run: apt-get update && apt-get install -y python3-pip poppler-utils
#      - run: pip install --break-system-packages "parody==0.34.0"
#      - name: Build print PDFs + page maps (one per edition)
#        run: parody publish . -o artifact --pdf-only --no-execute
#      - uses: actions/upload-artifact@v4
#        with:
#          name: print
#          path: |
#            artifact/*.pdf
#            artifact/*.pages.json
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_publish.py tests/test_cli.py -v`
Expected: PASS

- [ ] **Step 5: Bump the version and commit**

Bump the minor version in `pyproject.toml` (this adds a command and artifact
fields), then refresh the lock so it does not go stale:

```bash
uv lock
git add parody/publish.py parody/cli.py parody/templates/content_repo/.github/workflows/build.yml tests/test_publish.py pyproject.toml uv.lock
git commit -m "publish: build print + web together, wired by the page map (task #583)"
```

---

## Verification

Before handing off to the `parody-web` plan:

- [ ] `uv run pytest` — full suite green.
- [ ] `uv run pytest -m pdf` on a machine with TeX — the compile tests pass, including the tiling invariant and the no-`LaTeX Error` check.
- [ ] Against a real book: `uv run parody publish ~/electronics-primer/electronics-parody -o /tmp/pub --no-execute`, then confirm the sidecar's ranges tile the PDF and that a spot-checked section's start page really shows that section's heading.
