# Twin Pages Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `parody twin --lang de` builds a translated *twin* PDF whose page N holds exactly the content of English print page N (same page number, page size and margins, with the type scaled down to fit), plus a landscape side-by-side PDF. It is proved on Electronics Primer chapter 1 in German and Chinese.

**Architecture:** This is subsystem 2 of 5 in the spec. It reads the translation files subsystem 1 writes.

1. **Page inventory.** The English book is built a second time with *zero-node* sentence marks. `\parodys{V}` sets a LuaTeX attribute, which inserts no node, and writes the values of every counter to a side file. A Lua `pre_shipout_filter` records which mark values appear on how many lines of each page.
2. **Paginate.** Each unit (a chunk's head, or one of its sentences) is assigned to the page with most of its lines. Pages become lists of pieces: whole chunks or sentence ranges of chunks.
3. **Compose.** Each page's pieces are cut from the translation, at the matching sentence boundary or proportionally as a fallback. They are converted with the normal pandoc + `print.lua` path and wrapped in a `twinpage` environment.
4. **Typeset.** The environment restores the English counters, sets the page number and running heads, and typesets the content at 11 pt in a column 1/s wider. It then scales the result by s, lowering s until it fits the text block.
5. **Two passes.** The first pass measures the scale each page needs. The language's base scale is the 10th percentile. The second pass typesets at that base, and denser pages squeeze further, with no lower limit.

**Tech Stack:** Python ≥3.11, LuaLaTeX (TeX Live 2026), luatexbase attributes and callbacks, expl3 (`\fp_*`, `+b` arguments), memoir and the parody profile, babel (de/fr/es), ctex (zh), luatexko (ko), pypdf, pytest.

**Spec:** `docs/superpowers/specs/2026-10-17-translations-design.md`, sections "Twin pages (print), the hardest part", "Side-by-side PDF" and "When translations lag the English", and decisions D2–D4 and D14.

## What the spikes established (2026-10-17, electronics, 113 pages)

- **The marks don't move the English pages.** With `\setattribute` marks at every chunk and sentence, the marked build has the same 113 pages and the same lines on every page. One paragraph (page 106) hyphenated at a different point, and a few lines differ in inter-word spacing. The page-break comparison is therefore a *gate* (Task 3), not an assumption.
- **The inventory is complete.** Chapter 1 occupies abspages 5–33 and yields 342 mark values. 38 sentences straddle a page break, and each has line counts on both pages.
- **The scale-to-fit approach works.** Typesetting at 11 pt in a `\textwidth/s` minipage and scaling it by s works in memoir with `babel` (German) and `ctex`/Songti (Chinese). It handles parody boxes, `[H]` figures, display maths, blanks and minipage footnotes. A whole three-page German section fitted one page at s = 0.49.
- **Three fixes the spikes showed are needed:** restore counters on every measuring attempt; set arabic footnote numbering; and mute `\label` during measurement.
- **Electronics' figures are all `[H]`**, so nothing floats away from its text. Tables and floating figures are out of scope for the proof. See Review Focus 5.

## Global Constraints

- The English print path must produce byte-identical `.tex` and the same PDF when `parody pdf` runs without twin options. Every hook defaults to off.
- Mark values: `V = section_index * 1_000_000 + (chunk_index + 1) * 1000 + sentence`.
  - `section_index` is 1-based, in parody.yaml order.
  - `sentence = 0` is the chunk's head; `sentence = s ≥ 1` begins after the s-th sentence boundary.
  - Raise `ValueError` if a chunk has ≥ 999 sentences or a section has ≥ 999 chunks.
- Chunks are `parody.translate.chunks.split_chunks` of the section body after front matter, exactly as the translate step computes them. Marks are inserted **before** plugin transforms.
- Per-language base scale: the 10th percentile of the pages' required scales, capped at 1.0 and floored to 0.01. Effective type size = 11 pt × scale.
- **Never drop text to fit.** Every piece of every page is typeset, and the report lists every page whose scale is below the base.
- A missing translation sets the **English** text with a "not yet translated" marker. A stale one sets the previous translation with a "may lag the English" marker (spec, "When translations lag").
- Heading title-casing (`\parodytitlecap`) is the identity in twins.
- babel is loaded with `shorthands=off` for every language.

## Review Focus

1. **A unit with no lines on any page** (a figure-only chunk, an empty chunk head) must still land on a page: the first page it appears on, or its predecessor's page. It must never be dropped. *Pinned in Task 4.*
2. **Translation sentence counts that differ from the English**, for example "z. B." or "e.g." splitting a sentence. Use proportional cutting, flag it as approximate, and never cut inside maths, code or an attribute block. *Pinned in Task 5.*
3. **A fenced div (a definition box) split across pages.** It must be closed on the first page and reopened on the next, under the *same* box number, without duplicating its `{#id}`. *Pinned in Tasks 5 and 7.*
4. **An inventory page whose text differs from the published English PDF.** The twin for that page is still built, from the inventory, and the report names the page. *Pinned in Task 3.*
5. **Content the proof doesn't support** (floating tables or figures, longtables). The page is built and the report says "unsupported: float on page N" instead of silently misplacing it. *Pinned in Task 8.*

---

## File Structure

```
parody/twin/
  __init__.py       build_twin
  marks.py          sentence_starts(), mark_section(), decode()
  inventory.py      read_rows(), read_counters(), compare_pages(), build_inventory()
  paginate.py       Piece, TwinPage, paginate()
  slices.py         slice_chunk()
  compose.py        page_markdown(), twin_tex()
  languages.py      TWIN_LANGUAGES (preamble, names, fonts), cjk_font()
  sidebyside.py     side_by_side()
  build.py          build_twin(), TwinReport
parody/profiles/_shared/parody-twinmarks.sty, parody-twinmarks.lua   (marked English build)
parody/profiles/_shared/parody-twin.sty                              (twin document)
parody/profiles/memoir/parody-environments.sty   box/problem names via \parody…name macros
parody/writers/latex.py   strip_frontmatter(hook=…), build_pdf(section_hook=…, extra_support=…, extra_flags=…)
parody/translate/run.py   chapter titles → translations/<lang>/book.yaml
parody/cli.py             cmd_twin
tests/test_twin_*.py
```

---

### Task 1: Sentence boundaries and section marks

**Files:** Create `parody/twin/__init__.py` (empty) and `parody/twin/marks.py`. Test in `tests/test_twin_marks.py`.

**Interfaces:**
- Produces:
  - `sentence_starts(text: str, language: str = "en") -> list[int]`. Returns offsets where a sentence begins, i.e. just after the boundary's whitespace.
  - `mark_section(body: str, section_index: int) -> str`.
  - `decode(value: int) -> tuple[int, int, int]`, returning `(section_index, chunk_index, sentence)` with `chunk_index` 0-based.
  - `MARK_MACRO = "parodys"`.

**What counts as a boundary:**
- *en, de, fr, es:* `[.?!]`, optionally followed by closing quotes or brackets (`"'”’»)`), then whitespace (spaces, or a newline plus indentation). The next character must be an uppercase letter (`str.isupper()`).
- *ko:* the same, but the next character only has to be non-space.
- *zh:* `[。！？]` plus optional closers. Whitespace is optional, and the next character only has to be non-space.

Boundaries are never found inside these protected regions:
- code fences;
- `\begin{env}…\end{env}`;
- `$$…$$` and `$…$`;
- inline code;
- image syntax with its attributes;
- `{…}` attribute blocks;
- link targets `](…)`;
- lines starting with `#`, `|`, `:::` or `+-`.

**How `mark_section` places marks:** for chunk k, `head = \parodys{V0}`. If the chunk starts with a list marker, a quote `>`, a footnote definition `[^x]:` or a definition `:   `, the head goes inline, right after that marker; otherwise it goes on its own line followed by a blank line. Sentence marks go inline at each `sentence_starts` offset. Chunks are rejoined with `"\n\n"`.

- [ ] **Step 1: Write the failing tests**
  - `test_english_boundaries`: `"One. Two! Three? four. $a. B$ Five."` → offsets of "Two", "Three" and "Five" only.
  - `test_newline_boundary`: `"word.\nNext"` → offset of "Next".
  - `test_protected_regions`: no boundary inside `$$x. Y$$`, `` `a. B` ``, `![A. B](x.pdf)`, `{title="A. B"}`, or a `# Heading. Two` line.
  - `test_chinese_boundaries`: `"第一句。第二句！第三句"` → 2 offsets.
  - `test_korean_boundaries`: `"첫 문장이다. 둘째 문장."` → 1 offset.
  - `test_mark_section_paragraph_head_is_own_block`: the result starts `\parodys{2001000}\n\nFirst.`.
  - `test_mark_section_list_head_is_inline`: `"- a item.\n\n- b item."` → `"- \parodys{1001000}a item.\n\n- \parodys{1002000}b item."`. It must not split the list.
  - `test_mark_section_sentences`: the second sentence of chunk 1 in section 3 is `\parodys{3001001}`.
  - `test_decode`: `decode(3002005) == (3, 1, 5)`.
  - `test_limits_raise`: 1000 chunks raises `ValueError`.
- [ ] **Step 2: Run, expect FAIL.** `uv run pytest tests/test_twin_marks.py -q`
- [ ] **Step 3: Implement `marks.py`.**
- [ ] **Step 4: Run, expect PASS.** Then run `mark_section` over every section of the four books (as in the translate-step corpus check). Assert that `split_chunks(mark_section(body)) ` minus the head lines has the same chunk count as `split_chunks(body)`.
- [ ] **Step 5: Commit** `feat(twin): sentence boundaries and section marks`

### Task 2: Marked English build hooks and the marks package

**Files:**
- Modify `parody/writers/latex.py`:
  - `strip_frontmatter(md_path, dest_path, transform=None, hook=None)`. `hook(md_path, body) -> body` runs before `transform`.
  - `build_pdf(..., section_hook=None, extra_support=(), extra_flags=())`. Each `extra_support` path is copied into the build dir, and each `extra_flags` string is appended to `flags`.
- Create `parody/profiles/_shared/parody-twinmarks.sty` and `parody-twinmarks.lua`.
- Test in `tests/test_twin_inventory.py`.

**Interfaces:**
- `\parodys{V}`:
  - It runs `\setattribute\parodytwinattr{V}`.
  - It runs `\immediate\write\parodytwinctr{V\string\t<name>=<value>,…}` over every counter in `\cl@@ckpt`, to `\jobname.twinctr`.
- The Lua callback writes `abspage\tpage\tV\tlines` rows to `\jobname.twin`, one per (page, V) present. `lines` counts hlists of subtype line, equation or equation number (1, 6 and 7) that contain V in a leaf (glyph, rule or whatsit).
- `read_rows(path) -> list[tuple[int, int, int, int]]` and `read_counters(path) -> dict[int, dict[str, int]]`. The latter keeps the first occurrence of each V.

- [ ] **Step 1: Write the failing tests:**
  - `test_strip_frontmatter_hook_runs_before_transform`. Pure Python: the hook output feeds the transform.
  - `test_build_pdf_defaults_unchanged`. Monkeypatch latexmk out: with no twin args, `main.tex` and the section `.tex` are identical to before.
  - `test_read_rows_and_counters`: on a hand-written fixture.
  - `@needs_tex test_marked_build_inventory`. Build a two-section tmp book with `section_hook=mark_section`. Every inserted V appears in `.twin`; a section starting on a new page has its head on that page; `.twinctr` has `chapter` and `equation` for every V.
- [ ] **Step 2: Run, expect FAIL.**
- [ ] **Step 3: Implement.** Copy the spike's `.lua` (`/private/tmp/…/twin/spike-shared/`) and extend it with the counters write.
- [ ] **Step 4: Run, expect PASS. Then run the full suite**; the English path must be untouched.
- [ ] **Step 5: Commit** `feat(twin): zero-node sentence marks and the marked English build`

### Task 3: Inventory and the page-break gate

**Files:** Create `parody/twin/inventory.py`. Test in `tests/test_twin_inventory.py`.

**Interfaces:**
- `@dataclass Inventory(rows: list, counters: dict, section_index: dict[str, int], marked_pdf: Path, mismatched_pages: list[int])`. `section_index` maps `"ch/sec"` to its index.
- `compare_pages(published: Path, marked: Path) -> list[int]`. Returns the 1-based abspages whose text differs after removing all whitespace and `-\n` hyphen breaks. A different page count is reported as every page from the shorter count onwards.
- `build_inventory(project_dir: Path, build_dir: Path, published_pdf: Path) -> Inventory`. It runs `build_pdf(..., section_hook=…, extra_support=[twinmarks .sty/.lua], extra_flags=["\\usepackage{parody-twinmarks}"])`.

- [ ] **Step 1: Write the failing tests:**
  - `test_compare_pages_ignores_whitespace_and_hyphenation`. Use pypdf-built PDFs. Fixture idea: two tiny PDFs made with `pypdf` and reportlab-free text? If no text writer is available, use two LaTeX builds under `@needs_tex`.
  - `test_compare_pages_flags_moved_text`.
  - `@needs_tex test_build_inventory_on_tiny_book`. `mismatched_pages == []` and every section has rows.
- [ ] **Step 2–4:** RED, implement, GREEN.
- [ ] **Step 5: Commit** `feat(twin): page inventory with a page-break gate against the published PDF`

### Task 4: Paginate

**Files:** Create `parody/twin/paginate.py`. Test in `tests/test_twin_paginate.py`.

**Interfaces:**
- `@dataclass(frozen=True) Piece(section: int, chunk: int, start: int, end: int | None)` covers sentences `[start, end)` of a chunk; `end=None` means to the chunk end.
- `@dataclass TwinPage(abspage: int, page: int, pieces: list[Piece], counters: dict[str, int], chapter_start: bool, notes: list[str])`.
- `paginate(rows, counters, sections: set[int], first_section_of_chapter: set[int]) -> list[TwinPage]`. Returns one page per abspage in the span of the selected sections, including blank pages.

**Rules:**
- A unit is (section, chunk, sentence). Its page is the abspage holding the most lines; ties go to the earlier page.
- A unit with rows but zero lines goes to its first page. A unit absent from the rows inherits its predecessor's page and gets a note.
- A unit's page is clamped to be ≥ its predecessor's page, keeping source order; a note is added.
- Consecutive units of the same chunk on the same page merge into one piece.
- `counters` are those of the page's first unit. When the page's first piece starts at `start > 0` inside a fenced-div chunk, also record `reopen=True`; see Task 7.
- `chapter_start` is true when the page holds the head of the first chunk of a section in `first_section_of_chapter`.

- [ ] **Step 1: Write the failing tests** on synthetic rows:
  - `test_whole_chunks_per_page`.
  - `test_straddling_sentence_goes_to_page_with_more_lines`.
  - `test_unit_without_lines_lands_on_first_page`.
  - `test_missing_unit_inherits_predecessor_page`.
  - `test_blank_page_is_kept`.
  - `test_order_is_clamped`.
  - `test_chapter_start`.
- [ ] **Step 2–4:** RED, implement, GREEN.
- [ ] **Step 5: Commit** `feat(twin): paginate the inventory into per-page pieces`

### Task 5: Slicing a translated chunk

**Files:** Create `parody/twin/slices.py`. Test in `tests/test_twin_slices.py`.

**Interfaces:**
- `@dataclass Slice(text: str, approximate: bool, reopened: bool)`.
- `slice_chunk(text: str, language: str, start: int, end: int | None, english_boundaries: int) -> Slice`.

**Rules:**
- Get the translated boundaries `b = sentence_starts(text, language)`.
- If `len(b) == english_boundaries`, cut at `b[start-1]` and `b[end-1]` exactly; boundary 0 is the chunk start.
- Otherwise map English boundary i to `round(i * len(b) / english_boundaries)` and set `approximate=True`.
- If the cut start lies inside open fenced divs, reopen them: repeat their opener lines with any `#id` removed (`reopened=True`). If the cut end lies inside open divs, close them with `:::`.

- [ ] **Step 1: Write the failing tests:**
  - `test_exact_slice`.
  - `test_proportional_slice_when_counts_differ`.
  - `test_slice_never_cuts_inside_maths`.
  - `test_div_closed_and_reopened_without_id`: `::: {#def:x .definition}` reopens as `::: {.definition}`.
  - `test_whole_chunk_when_start_0_end_none`.
- [ ] **Step 2–4:** RED, implement, GREEN.
- [ ] **Step 5: Commit** `feat(twin): slice translated chunks at sentence boundaries`

### Task 6: Chapter titles and localised box names

**Files:**
- Modify `parody/translate/run.py`. Add `translate_chapter_titles(project, language, engine, today=None) -> SectionStatus`, which writes `translations/<lang>/book.yaml` as `{chapters: {slug: {title, hash}}}`. The `hash` is `chunk_hash(English title)`. The function is called at the end of each language in `translate_project`.
- Modify `parody/profiles/memoir/parody-environments.sty`. Add the macros `\parodydefinitionname`, `\parodytheoremname`, `\parodyexamplename`, `\parodyboxname`, `\parodyproblemname` and `\parodylabexercisename`, with English defaults, and use them where the literals are now (lines ~202, 211, 234, 352, 357, 389, 399).
- Tests: `tests/test_translate_run.py`, and `tests/test_print_memoir.py` (the English macros expand to today's words).

- [ ] **Step 1: Write the failing tests:**
  - `test_chapter_titles_translated_once`: a second run makes no call.
  - `test_chapter_title_stale_after_rename`.
  - `test_environment_names_default_english`: the `.sty` contains `\newcommand{\parodydefinitionname}{Definition}`, and a `@needs_tex` build of a definition box still prints "Definition 1.1".
- [ ] **Step 2–4:** RED, implement, GREEN. Then run the full suite; golden and print tests must be unchanged.
- [ ] **Step 5: Commit** `feat(translate,print): chapter title translations; box names are macros`

### Task 7: The twin document package and language preambles

**Files:** Create `parody/profiles/_shared/parody-twin.sty` and `parody/twin/languages.py`. Test in `tests/test_twin_tex.py`.

**Interfaces (LaTeX):**
- `\begin{twinpage}{<page>}{<start scale>}{<counter restore code>}{<chapter mark>}{<section mark>} … \end{twinpage}`, using an xparse `+b` body. It:
  1. calls `\clearpage` and `\setcounter{page}{<page>}`;
  2. sets the marks: after the restore code it calls `\chaptermark{<chapter mark>}`, then `\sectionmark{<section mark>}` when the section mark is non-empty;
  3. loops: restore counters, `\let\label\@gobble`, set `\hbox` of a `\textwidth/s` minipage with arabic `mpfootnote` set from `footnote`. If `(ht + dp) * s` exceeds `\textheight − \pagetotal`, it lowers s by 0.01 and tries again;
  4. finally restores counters and typesets the body once more with labels on, scaled by s;
  5. writes `TWINFIT page=<page> scale=<s>` to the log.
- `\parodytwinchapter{<n>}{<title>}` sets the chapter counter to n−1 and calls `\chapter{<title>}`. It is used only on a `chapter_start` page, before `twinpage`.
- `\parodyuntranslated` and `\parodystale` mark untranslated and stale text with a small italic note in the margin: "English: not yet translated" and "may lag the English", localised.
- `\renewcommand\parodytitlecap[1]{#1}`.

**Interfaces (Python):**
- `TWIN_LANGUAGES: dict[str, dict]` with keys `preamble` (a string), `names` (a dict of `\parody…name` and `\figurename`/`\tablename`/`\chaptername` overrides) and `fonts` (CJK family candidates).
  - de: `\usepackage[ngerman,shorthands=off]{babel}`.
  - fr: `[french,shorthands=off]`.
  - es: `[spanish,es-noshorthands,shorthands=off]`.
  - zh: `\usepackage[fontset=none,heading=false,scheme=plain]{ctex}\setCJKmainfont{<font>}`, with fonts Noto Serif CJK SC, then Source Han Serif SC, then Songti SC.
  - ko: `\usepackage{luatexko}\setmainhangulfont{<font>}`, with fonts Noto Serif KR, then Apple SD Gothic Neo.
- `cjk_font(language) -> str`. It returns the first candidate `fc-list` knows, or raises `RuntimeError` naming the fonts to install.

- [ ] **Step 1: Write the failing tests:**
  - `test_names_cover_every_box_macro`.
  - `test_cjk_font_missing_raises_with_install_hint`, with `fc-list` monkeypatched.
  - `@needs_tex test_twinpage_fits_and_restores_counters`. Two `twinpage`s whose body has a `\refstepcounter{equation}`: the second shows equation 1.5 when restored to 4. Content of 3× `\textheight` reports `scale<0.4` and still ships one page.
  - `@needs_tex test_chinese_twinpage_compiles`, skipped without a CJK font.
- [ ] **Step 2–4:** RED, implement, GREEN.
- [ ] **Step 5: Commit** `feat(twin): twinpage environment, fitting and language preambles`

### Task 8: Compose and build

**Files:** Create `parody/twin/compose.py` and `parody/twin/build.py`, and fill in `parody/twin/__init__.py`. Test in `tests/test_twin_build.py`.

**Interfaces:**
- `page_markdown(page: TwinPage, project, language: str, english: dict, translations: dict) -> tuple[list[tuple[str, str]], list[str]]`.
  - It returns `[(section_key, markdown)]`, grouped by section in page order, plus notes.
  - The notes are `approximate`, `untranslated chunk …`, `stale chunk …` and `unsupported: float`.
  - Footnote definition chunks of that section are appended to each group.
  - A reopened div is preceded by raw LaTeX that sets each counter that changed between the chunk's head mark and its first sentence mark back to its head value.
- `twin_tex(pages, project, language, start_scale, groups_tex) -> str`. It writes the main document: profile preamble, `parody-twin.sty`, the language preamble and names, then each page.
- `@dataclass TwinReport(language, base_scale, squeezed: list[tuple[int, float]], approximate: list[int], untranslated: int, stale: int, mismatched_pages: list[int], unsupported: list[str])`.
- `build_twin(project_dir, language, chapters: list[str] | None, published_pdf: Path | None, out: Path, build_dir: Path | None = None) -> tuple[Path, TwinReport]`. Its steps:
  1. build or accept the published English PDF;
  2. build the inventory;
  3. paginate the selected chapters;
  4. compose. Each (page, section) group goes through `section_to_latex` with the section's directory as cwd, exactly like `build_pdf`; a group holding the section start goes through `synthesize_section_heading` with the translated title;
  5. run pass 1 at start scale 1.0;
  6. parse the `TWINFIT` lines, giving each page's required scale;
  7. compute the base scale;
  8. run pass 2 twice (for cross-references);
  9. return the report.

- [ ] **Step 1: Write the failing tests:**
  - `test_page_markdown_whole_and_split_chunks`, with a synthetic translation.
  - `test_page_markdown_untranslated_uses_english_with_marker`.
  - `test_page_markdown_stale_uses_old_translation`, aligned by hash via `align_chunks`.
  - `test_base_scale_is_10th_percentile`.
  - `@needs_tex test_build_twin_tiny_book`. Use a 2-page tmp book whose "translation" is the English with "alpha"→"Alpha-DE". The twin PDF has the same page count over the chapter span and page numbers equal to the English, and the report is empty of problems.
- [ ] **Step 2–4:** RED, implement, GREEN.
- [ ] **Step 5: Commit** `feat(twin): compose translated pages and build the twin PDF`

### Task 9: Side-by-side PDF

**Files:** Create `parody/twin/sidebyside.py`. Test in `tests/test_twin_sidebyside.py`.

**Interfaces:**
- `side_by_side(english_pdf: Path, twin_pdf: Path, abspages: list[int], out: Path) -> Path`.
  - The sheet is letter landscape, 792 × 612 pt.
  - Scale = min(396 / w, 612 / h) for an English page of w × h pt; for 6×9 that is 0.9167.
  - The English page goes left and the twin right, each centred in its half.
  - It uses `PageObject.create_blank_page` plus `merge_transformed_page`. Read `pdf-composition-gotchas` in project memory first.

- [ ] **Step 1: Write the failing test** `test_side_by_side_geometry`. Make two 432 × 648 pt PDFs with pypdf blank pages. The result has `len(abspages)` landscape pages of 792 × 612, and each page's content stream holds two transforms with the scale.
- [ ] **Step 2–4:** RED, implement, GREEN.
- [ ] **Step 5: Commit** `feat(twin): side-by-side landscape PDF`

### Task 10: CLI, the real proof, and release prep

**Files:** Modify `parody/cli.py` (`cmd_twin`) and `README.md` (a Twin pages section). Bump to version `0.62.0` with `uv.lock`.

**Interface:** `parody twin [project_dir] --lang de [--chapter SLUG …] [-o twin.pdf] [--side-by-side sbs.pdf] [--english english.pdf]`. It prints the report, and exits 1 if the inventory gate or a TeX error failed.

- [ ] **Step 1: Write the failing tests:** `test_cli_twin_requires_lang`, and `test_cli_twin_reports`, with `build_twin` monkeypatched.
- [ ] **Step 2–4:** RED, implement, GREEN. Run the full suite.
- [ ] **Step 5: Real proof.** On the scratch copy of electronics, which has chapter 1 translated into de and zh, run `parody twin --lang de --chapter fundamentals --side-by-side`, and the same for zh. Record the base scale, the squeezed pages and the approximate splits. Read at least four page pairs as images: a chapter-opening page, a page with a split paragraph, a page with a split definition box if there is one, and the densest page. Compare text and page numbers by eye.
- [ ] **Step 6: Commit** `0.62.0: parody twin builds page-for-page translated PDFs`
