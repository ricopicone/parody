# Memoir House Style Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn parody's bundled `memoir` print profile from a portable fallback into a finished house style, so Electronics Primer (and every other book without a book-private profile) prints as well as RTC does.

**Architecture:** All changes live in `parody/profiles/memoir/` — three files, one responsibility each: `parody-memoir.cls` owns page furniture (chapter opener, TOC, title page), `parody-environments.sty` owns environments/counters/problems, `parody-theme-default.sty` owns fonts and palette. No filter or writer change: the print contract already names every environment involved, and this work only redefines how they render.

**Tech Stack:** LaTeX (memoir, tcolorbox+TikZ overlays, xsim, microtype), lualatex via latexmk, TeX Live 2026 at `/Library/TeX/texbin`. Tests: pytest + pypdf text extraction on real compiled PDFs.

**Spec:** `docs/superpowers/specs/2026-08-16-memoir-house-style-design.md`

## Global Constraints

- **PATH for every TeX invocation:** `export PATH="/Library/TeX/texbin:$PATH"` — latexmk/lualatex are NOT on the default PATH in this shell. Without it every PDF test silently skips (`needs_tex`).
- **Print builds fail quietly** (project memory `print-builds-fail-quietly`): latexmk exits 0 with a mangled document. A green test run is not evidence — the PDF must be *read*.
- **@ is already a letter** inside `.sty`/`.cls` files; `\parody@…` names need no `\makeatletter`.
- **Do not touch** `parody/filters/print.lua`, `parody/writers/latex.py`, or `parody/profiles/print/` (the stock fallback profile). RTC is pinned to its own `profile-mitpress` and must stay unaffected.
- **Never `git add -A`** (project memory `never-git-add-dash-a-in-shared-worktrees`) — this worktree shares a repo with concurrent sessions. Stage named paths only.
- **Version bump touches both** `pyproject.toml` and `uv.lock` in the same commit (project memory `version-bumps-must-commit-uv-lock`).
- Accent colours already defined by the theme: `parodyaccent` (#1F4E79), `parodyinfoframe` (#2F5C86), `parodyexframe` (#3F7D5E).

---

### Task 1: Test scaffolding — read text out of a compiled PDF

Everything after this task asserts on what actually printed. Build the helper first.

**Files:**
- Modify: `tests/test_print_pdf.py:9-45` (extend `SECTION_MD` fixture)
- Modify: `tests/test_print_memoir.py` (add helper + first PDF-text test)

**Interfaces:**
- Produces: `pdf_text(pdf_path) -> str` and `squashed(pdf_path) -> str` in `tests/test_print_memoir.py`, used by Tasks 2–5.

- [ ] **Step 1: Extend the shared fixture with an infobox and an example**

In `tests/test_print_pdf.py`, inside `SECTION_MD`, immediately after the `.definition` div and before the `.exercise` div, insert:

```markdown
::: {.infobox #box:note title="A Note"}
Worth noticing.
:::

::: {.example #ex:one}
An example of a thing.
:::
```

Existing assertions use `in` checks, so adding content is safe.

- [ ] **Step 2: Add the PDF-text helpers and a failing numbering test**

Append to `tests/test_print_memoir.py`:

```python
def pdf_text(pdf):
    """All text in a compiled PDF, pages joined by newlines."""
    from pypdf import PdfReader
    return "\n".join(p.extract_text() or "" for p in PdfReader(str(pdf)).pages)


def squashed(pdf):
    """PDF text with all whitespace removed.

    Letterspacing and justification make extracted text unstable at word
    level; squashing lets an assertion pin the glyphs without pinning the
    spacing.
    """
    return "".join(pdf_text(pdf).split())


@pytest.mark.pdf
@needs_tex
def test_problems_are_named_and_numbered_by_chapter(tiny_project):  # noqa: F811
    pdf = build_pdf(tiny_project, profile_dir="memoir")
    text = squashed(pdf)
    assert "Problem1.1" in text
    assert "Exercise" not in text
```

- [ ] **Step 3: Run it and confirm it fails for the right reason**

```bash
export PATH="/Library/TeX/texbin:$PATH" && uv run pytest tests/test_print_memoir.py -k problems_are_named -v
```

Expected: FAIL — `assert "Problem1.1" in text`. If it SKIPS, the PATH export was lost; fix that before continuing. If it fails on `pypdf` import, add nothing — `pypdf>=4.0` is already a dev dependency (`pyproject.toml:39`).

- [ ] **Step 4: Commit the scaffolding**

```bash
git add tests/test_print_memoir.py tests/test_print_pdf.py && git commit -m "test: read compiled-PDF text in memoir profile tests (task #594)"
```

---

### Task 2: Problems, not exercises

**Files:**
- Modify: `parody/profiles/memoir/parody-environments.sty:124-141` (xsim block), `:327-328` (crefnames)
- Test: `tests/test_print_memoir.py`

**Interfaces:**
- Consumes: `squashed()` from Task 1.
- Produces: exercise template named `parodyrunin`, referenced by nothing else.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_print_memoir.py`:

```python
def test_exercise_setup_names_problems():
    env = (BUNDLED_PROFILES / "memoir" / "parody-environments.sty").read_text()
    assert "exercise/within=chapter" in env
    assert "exercise/name=Problem" in env
    assert "\\crefname{exercise}{problem}{problems}" in env
    assert "\\Crefname{exercise}{Problem}{Problems}" in env
```

- [ ] **Step 2: Run both tests to verify they fail**

```bash
export PATH="/Library/TeX/texbin:$PATH" && uv run pytest tests/test_print_memoir.py -k "exercise_setup or problems_are_named" -v
```

Expected: both FAIL.

- [ ] **Step 3: Set the naming and per-chapter numbering**

In `parody/profiles/memoir/parody-environments.sty`, in the `% ---- exercises (xsim) ----` block, immediately after `\DeclareExerciseProperty{hash}`, insert:

```latex
% End-of-chapter problem sets: named "Problem" (the web says the same, task
% #499) and numbered within the chapter, so print and web agree on "1.1".
\xsimsetup{exercise/within=chapter, exercise/name=Problem}
```

- [ ] **Step 4: Add the run-in template**

In the same block, immediately after the `\DeclareExerciseType{labexercise}{...}` group, insert:

```latex
% Run-in heading: "Problem 1.1" set bold on the same line as the problem's
% first paragraph. xsim's `default` template sets a display heading instead.
% (RTC's profile gets this from the MIT class's run-in \subsubsection*;
% memoir's \subsubsection is a display head, so the run-in is spelled out.)
\DeclareExerciseEnvironmentTemplate{parodyrunin}{%
  \par\addvspace{\medskipamount}%
  \noindent
  {\bfseries\XSIMmixedcase{\GetExerciseName}\nobreakspace
   \GetExerciseProperty{counter}}%
  \hspace{0.75em}\ignorespaces
}{\par\addvspace{\medskipamount}}
\xsimsetup{exercise/template=parodyrunin, solution/template=parodyrunin}
% Lab problems: same run-in style, numbered L<chapter>.n as on the web.
\xsimsetup{
  labexercise/name = Problem,
  labexercise/within = chapter,
  labexercise/the-counter = L\thechapter.\arabic{labexercise},
  labexercise/template = parodyrunin,
  labsolution/template = parodyrunin,
}
```

- [ ] **Step 5: Fix the cross-reference names**

Replace lines 327-328 of the same file:

```latex
\crefname{exercise}{exercise}{exercises}
\crefname{labexercise}{lab exercise}{lab exercises}
```

with:

```latex
\crefname{exercise}{problem}{problems}
\Crefname{exercise}{Problem}{Problems}
\crefname{labexercise}{problem}{problems}
\Crefname{labexercise}{Problem}{Problems}
```

- [ ] **Step 6: Run the tests**

```bash
export PATH="/Library/TeX/texbin:$PATH" && uv run pytest tests/test_print_memoir.py -k "exercise_setup or problems_are_named" -v
```

Expected: both PASS.

- [ ] **Step 7: Commit**

```bash
git add parody/profiles/memoir/parody-environments.sty tests/test_print_memoir.py && git commit -m "print: memoir profile calls them problems, numbered by chapter, run-in (task #594)"
```

---

### Task 3: Number everything within the chapter

**Files:**
- Modify: `parody/profiles/memoir/parody-environments.sty` (new block near the end, before `\endinput`)
- Test: `tests/test_print_memoir.py`

**Interfaces:**
- Consumes: counters `thmctr`, `infoboxctr`, `examplectr`, `listingctr` defined earlier in the same file.

- [ ] **Step 1: Write the failing test**

```python
@pytest.mark.pdf
@needs_tex
def test_boxes_number_within_the_chapter(tiny_project):  # noqa: F811
    pdf = build_pdf(tiny_project, profile_dir="memoir")
    text = squashed(pdf)
    assert "Definition1.1" in text
    assert "Box1.1" in text
    assert "Example1.1" in text
    assert "Listing1.1" in text
```

- [ ] **Step 2: Run it to verify it fails**

```bash
export PATH="/Library/TeX/texbin:$PATH" && uv run pytest tests/test_print_memoir.py -k boxes_number -v
```

Expected: FAIL — the PDF says `Definition 1`, not `Definition 1.1`.

- [ ] **Step 3: Add the counter block**

In `parody/profiles/memoir/parody-environments.sty`, immediately before the `% hashref targets` comment near the end, insert:

```latex
% ---- chapter-relative numbering ----------------------------------------
% Figures, tables and sections already number within chapter (memoir default).
% Everything parody counts follows: a reader looking at "Definition 1.6" knows
% which chapter to turn to, and a book-wide counter reaching "Definition 47"
% tells them nothing. Definitions and theorems deliberately SHARE thmctr.
\numberwithin{equation}{chapter}
\counterwithin{thmctr}{chapter}     % Definition/Theorem/Lemma/... N.M
\counterwithin{infoboxctr}{chapter} % Box N.M
\counterwithin{examplectr}{chapter} % Example N.M
\counterwithin{listingctr}{chapter} % Listing N.M
\counterwithin*{footnote}{chapter}  % restart each chapter (* = keep arabic)
```

- [ ] **Step 4: Run the test**

```bash
export PATH="/Library/TeX/texbin:$PATH" && uv run pytest tests/test_print_memoir.py -k boxes_number -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add parody/profiles/memoir/parody-environments.sty tests/test_print_memoir.py && git commit -m "print: number boxes, examples, listings and equations within the chapter (task #594)"
```

---

### Task 4: Boxes become corner brackets

**Files:**
- Modify: `parody/profiles/memoir/parody-environments.sty:151-204` (`parodythmbox`, `infobox`, `myexample`)
- Test: `tests/test_print_memoir.py`

**Interfaces:**
- Produces: tcolorbox styles `parodyboxbase` and `parodybox=<colour>` (a `.style n args={1}` taking the hue), plus `\parody@brk@{un,first,mid,last}{<colour>}`. Nothing outside this file consumes them.

- [ ] **Step 1: Write the failing test**

```python
def test_boxes_are_bracket_framed_not_filled():
    env = (BUNDLED_PROFILES / "memoir" / "parody-environments.sty").read_text()
    # the bracket shell exists and each box type picks its own hue
    assert "parodyboxbase/.style" in env
    assert "parodybox/.style n args" in env
    assert "parodybox=parodyaccent" in env    # definition/theorem family
    assert "parodybox=parodyinfoframe" in env  # infobox
    assert "parodybox=parodyexbox" not in env  # (typo guard)
    assert "parodybox=parodyexframe" in env    # examples
    # no tinted backgrounds left on the reader-facing boxes
    assert "colback=parodythmback" not in env
    assert "colback=parodyinfoback" not in env
    assert "colback=parodyexback" not in env
```

- [ ] **Step 2: Run it to verify it fails**

```bash
uv run pytest tests/test_print_memoir.py -k bracket_framed -v
```

Expected: FAIL on `parodyboxbase/.style`.

- [ ] **Step 3: Add the bracket shell**

In `parody/profiles/memoir/parody-environments.sty`, immediately before the `% ---- theorem-like environments` comment, insert:

```latex
% ---- the house box: open frame, corner brackets, no fill ----------------
% An accent-coloured bold title over an open frame with bracket strokes at the
% corners — the same vocabulary parody-web uses for examples (task #318),
% rather than a tinted panel with a solid title bar. Each box type carries its
% own hue so a reader can tell a definition from a worked example at a glance,
% matching the web's per-type hue tokens (task #565).
\newlength{\parodybracketlen}\setlength{\parodybracketlen}{16pt}
\def\parody@brkoff{0.5pt}
\tikzset{parodybracketline/.style={line width=0.9pt, line cap=round}}
% #1 = hue. Four cases because a breakable box draws its own overlay per
% fragment: only the first fragment has a title, only the last has a foot.
\newcommand{\parody@brk@un}[1]{%
  \draw[#1,parodybracketline]
    ([xshift=\parodybracketlen]title.south west) --
    ([xshift=\parody@brkoff]title.south west) --
    ([xshift=\parody@brkoff]frame.south west) --
    ([xshift=\parodybracketlen]frame.south west);
  \draw[#1,parodybracketline]
    ([xshift=-\parodybracketlen]frame.north east) --
    ([xshift=-\parody@brkoff]frame.north east) --
    ([xshift=-\parody@brkoff]frame.south east) --
    ([xshift=-\parodybracketlen]frame.south east);}
\newcommand{\parody@brk@first}[1]{%
  \draw[#1,parodybracketline]
    ([xshift=\parodybracketlen]title.south west) --
    ([xshift=\parody@brkoff]title.south west) --
    ([xshift=\parody@brkoff]frame.south west);
  \draw[#1,parodybracketline]
    ([xshift=-\parodybracketlen]frame.north east) --
    ([xshift=-\parody@brkoff]frame.north east) --
    ([xshift=-\parody@brkoff]frame.south east);}
\newcommand{\parody@brk@mid}[1]{%
  \draw[#1,parodybracketline]
    ([xshift=\parody@brkoff]frame.north west) --
    ([xshift=\parody@brkoff]frame.south west);
  \draw[#1,parodybracketline]
    ([xshift=-\parody@brkoff]frame.north east) --
    ([xshift=-\parody@brkoff]frame.south east);}
\newcommand{\parody@brk@last}[1]{%
  \draw[#1,parodybracketline]
    ([xshift=\parody@brkoff]frame.north west) --
    ([xshift=\parody@brkoff]frame.south west) --
    ([xshift=\parodybracketlen]frame.south west);
  \draw[#1,parodybracketline]
    ([xshift=-\parody@brkoff]frame.north east) --
    ([xshift=-\parody@brkoff]frame.south east) --
    ([xshift=-\parodybracketlen]frame.south east);}
\tcbset{
  parodyboxbase/.style={
    enhanced, breakable, empty,
    attach boxed title to top left,
    minipage boxed title,
    boxed title style={empty, size=minimal, toprule=0pt, top=3pt,
      left=0pt, bottom=2pt, overlay={}},
    fonttitle=\bfseries,
    parbox=false,
    before upper={\setlength{\parindent}{0pt}\noindent},
    boxsep=0pt, left=5pt, right=5pt, top=5pt, bottom=3pt,
    pad at break=0mm,
    before skip=8pt, after skip=8pt,
  },
  parodybox/.style n args={1}{
    parodyboxbase,
    coltitle=#1,
    overlay unbroken={\parody@brk@un{#1}},
    overlay first={\parody@brk@first{#1}},
    overlay middle={\parody@brk@mid{#1}},
    overlay last={\parody@brk@last{#1}},
  },
}
```

- [ ] **Step 4: Point the three box families at it**

Replace the `parodythmbox` definition (currently `\newtcolorbox{parodythmbox}[2]{enhanced, breakable, colback=parodythmback, …}`) with:

```latex
\newtcolorbox{parodythmbox}[2]{parodybox=parodyaccent,
  title={#1\if\relax\detokenize{#2}\relax\else\ \textnormal{\itshape #2}\fi}}
```

Replace the `infobox` environment's `\begin{tcolorbox}[…]` options with:

```latex
   \begin{tcolorbox}[parodybox=parodyinfoframe,
     title={Box~\theinfoboxctr%
       \if\relax\detokenize{#2}\relax\else\ \textnormal{\itshape #2}\fi}, #1]}
```

Replace the `myexample` environment's `\begin{tcolorbox}[…]` options with:

```latex
   \begin{tcolorbox}[parodybox=parodyexframe,
     title={Example~\theexamplectr}]%
```

Leave `formattedoutput` alone — it is a code-output panel, not a reader-facing box, and its `parodyout*` colours stay in use.

- [ ] **Step 5: Run the source test and a real compile**

```bash
export PATH="/Library/TeX/texbin:$PATH" && uv run pytest tests/test_print_memoir.py -k "bracket_framed or boxes_number or memoir_pdf_compiles" -v
```

Expected: PASS. A TikZ node error (`no shape named title`) here means a `title.south west` reference reached a fragment with no title — check the four overlay cases.

- [ ] **Step 6: Look at the box**

```bash
export PATH="/Library/TeX/texbin:$PATH" && uv run python -c "from parody.writers.latex import build_pdf; print(build_pdf('tests/smoke-book', profile_dir='memoir', keep_build=True))"
```

Read the resulting PDF pages with the Read tool. The definition box must have no background tint, an accent title, and visible brackets at the corners. Do not proceed on a clean exit alone.

- [ ] **Step 7: Commit**

```bash
git add parody/profiles/memoir/parody-environments.sty tests/test_print_memoir.py && git commit -m "print: boxes as open corner-bracket frames, one hue per type (task #594)"
```

---

### Task 5: The stylized chapter opener, TOC fix, and title page

**Files:**
- Modify: `parody/profiles/memoir/parody-memoir.cls:56-105` (chapter style, TOC, title page)
- Modify: `parody/profiles/memoir/parody-theme-default.sty` (add microtype)
- Test: `tests/test_print_memoir.py`

**Interfaces:**
- Consumes: `parodyaccent` (already `\providecolor`d in the class).
- Produces: chapter style `parodygraphic`, `\parody@chapopener{<numeral>}`, `\parody@chaprule`, length `\parody@chapbleed`.

- [ ] **Step 1: Write the failing tests**

```python
def test_chapter_opener_is_the_graphic_style():
    cls = (BUNDLED_PROFILES / "memoir" / "parody-memoir.cls").read_text()
    assert "\\makechapterstyle{parodygraphic}" in cls
    assert "\\chapterstyle{parodygraphic}" in cls
    assert "\\parody@chapbleed" in cls        # numeral + rule hang into the margin


def test_toc_leaders_keep_stretchable_glue():
    # \hspace*{1.5em} left the line with no stretch, so TeX stretched the
    # interword space of the title instead ("Voltage,   current,   ...").
    cls = (BUNDLED_PROFILES / "memoir" / "parody-memoir.cls").read_text()
    assert "\\hspace*{1.5em}" not in cls
    assert "\\renewcommand{\\cftsectionleader}{\\hfill}" in cls


def test_title_page_carries_no_folio():
    cls = (BUNDLED_PROFILES / "memoir" / "parody-memoir.cls").read_text()
    assert "\\aliaspagestyle{title}{empty}" in cls


def test_theme_loads_microtype():
    thm = (BUNDLED_PROFILES / "memoir" / "parody-theme-default.sty").read_text()
    assert "\\RequirePackage{microtype}" in thm
```

- [ ] **Step 2: Run them to verify they fail**

```bash
uv run pytest tests/test_print_memoir.py -k "chapter_opener or toc_leaders or title_page or microtype" -v
```

Expected: four FAILs.

- [ ] **Step 3: Load microtype in the theme**

At the end of `parody-theme-default.sty`, before `\endinput`, add:

```latex
% microtype last, after the text fonts it tunes: protrusion and expansion are
% what let a 6x9 measure sit quietly, and \textls supplies the chapter
% opener's letterspaced small caps.
\RequirePackage{microtype}
```

- [ ] **Step 4: Replace the chapter style in the class**

In `parody-memoir.cls`, delete the whole `% ---- chapter opener` block (the `\makechapterstyle{parody}{…}` group and the `\chapterstyle{parody}` line) and put in its place:

```latex
% ---- chapter opener ----------------------------------------------------
%   CHAPTER                                                              1
%   ═══════════════════════════════════════════════════════════════════════
%   Fundamentals
%
% The numeral and the rule both overhang the measure into the outer margin,
% which is what gives the opening its snap. Chapters open recto (memoir's
% `openright`), so the outer margin is the right-hand one. The overhang is
% built by setting a box WIDER than \textwidth inside a \makebox that is
% exactly \textwidth, so TeX's idea of the line width is unchanged.
\newlength{\parody@chapbleed}
\setlength{\parody@chapbleed}{0.32in}
% \textls comes from microtype (loaded by the theme). Keep the class usable
% on its own: fall back to no letterspacing if the theme is absent.
\AtBeginDocument{\providecommand{\textls}[2][]{#2}}

\newcommand{\parody@chapopener}[1]{%
  \noindent\makebox[\textwidth][l]{%
    \makebox[\dimexpr\textwidth+\parody@chapbleed\relax][s]{%
      {\chapnamefont\color{parodyaccent}\textls[200]{\@chapapp}}%
      \hfill
      \smash{\raisebox{-0.2\height}{{\chapnumfont\color{parodyaccent}#1}}}%
    }%
  }\par\nobreak}

\newcommand{\parody@chaprule}{%
  \par\nobreak\vskip 6pt
  \noindent\makebox[\textwidth][l]{%
    {\color{parodyaccent}%
     \rule{\dimexpr\textwidth+\parody@chapbleed\relax}{2pt}}}%
  \par\nobreak\vskip 0.8\onelineskip}

\makechapterstyle{parodygraphic}{%
  \setlength{\beforechapskip}{6pt}%
  \setlength{\midchapskip}{0pt}%
  \setlength{\afterchapskip}{2.4\onelineskip}%
  \renewcommand*{\chapnamefont}{\normalfont\footnotesize\scshape}%
  \renewcommand*{\chapnumfont}{\normalfont\fontsize{80}{80}\selectfont\bfseries}%
  \renewcommand*{\chaptitlefont}{\normalfont\HUGE\bfseries\raggedright}%
  \renewcommand*{\printchaptername}{}%
  \renewcommand*{\chapternamenum}{}%
  \renewcommand*{\printchapternum}{\parody@chapopener{\thechapter}}%
  \renewcommand*{\afterchapternum}{}%
  % The rule lives with the title, not the number, so an unnumbered chapter
  % (Contents, Bibliography) still opens under it.
  \renewcommand*{\printchaptertitle}[1]{\parody@chaprule\chaptitlefont ##1}%
}
\chapterstyle{parodygraphic}
```

`\@chapapp` is memoir's "Chapter"/"Appendix" word, so appendices open with APPENDIX and the numeral becomes `A` with no extra work. `chapter_start: 0` (RTC) prints `0` unchanged.

- [ ] **Step 5: Fix the TOC leaders**

In the `% ---- table of contents` block, replace:

```latex
\renewcommand{\cftsectionleader}{\hspace*{1.5em}}
\renewcommand{\cftsubsectionleader}{\hspace*{1.5em}}
```

with:

```latex
% \hfill, not a fixed \hspace: a fixed skip leaves the line with no
% stretchable glue, so TeX stretches the interword space of the entry title
% instead ("Voltage,   current,   resistance,   and   all   that   1").
\renewcommand{\cftsectionleader}{\hfill}
\renewcommand{\cftsubsectionleader}{\hfill}
```

- [ ] **Step 6: Restyle the title page**

Replace the `% ---- title page` block with:

```latex
% ---- title page: centred, folio-free, under the house rule -------------
\aliaspagestyle{title}{empty}
\pretitle{\vspace*{0.22\textheight}\begin{center}\Huge\bfseries}
\posttitle{\par\end{center}\vskip 0.9em
  \begin{center}{\color{parodyaccent}\rule{0.38\textwidth}{2pt}}\end{center}
  \vskip 1.6em}
\preauthor{\begin{center}\Large}
\postauthor{\par\end{center}\vspace*{\fill}}
\predate{\begin{center}\large}
\postdate{\par\end{center}}
```

- [ ] **Step 7: Run the tests, then compile and LOOK**

```bash
export PATH="/Library/TeX/texbin:$PATH" && uv run pytest tests/test_print_memoir.py -v
```

Expected: all PASS. Then compile the smoke book and read its first pages with the Read tool:

```bash
export PATH="/Library/TeX/texbin:$PATH" && uv run python -c "from parody.writers.latex import build_pdf; print(build_pdf('tests/smoke-book', profile_dir='memoir'))"
```

Check by eye: no folio on the title page; the chapter numeral overhangs the right margin without colliding with the rule; the rule is flush left and bleeds right; TOC section lines have normal word spacing. Expect to tune `\parody@chapbleed`, the `80pt` numeral size, and the `-0.2\height` raise — do it here, while the smoke book is fast to rebuild.

- [ ] **Step 8: Commit**

```bash
git add parody/profiles/memoir/parody-memoir.cls parody/profiles/memoir/parody-theme-default.sty tests/test_print_memoir.py && git commit -m "print: graphic chapter opener, working TOC leaders, folio-free title page (task #594)"
```

---

### Task 6: Verify against the real books, then bump the version

The smoke book proves the profile compiles. Electronics proves it *reads*.

**Files:**
- Modify: `pyproject.toml:3`, `uv.lock`

- [ ] **Step 1: Build Electronics Primer against the working tree**

```bash
export PATH="/Library/TeX/texbin:$PATH" && uv run parody pdf ~/electronics-primer/electronics-parody -o /tmp/ep-594.pdf
```

- [ ] **Step 2: Read the output — five checks, by eye**

Use the Read tool on `/tmp/ep-594.pdf`:
- **pages 1–3** — title page (no folio, rule under the title) and Contents (no stretched word spacing)
- **the chapter 1 opener** — CHAPTER / numeral / rule / title
- **a box spread** (around book page 5–7) — Definition 1.5, Box 1.1, Example 1.1 as bracket frames, no tint
- **the problems spread** (around book page 22) — run-in **Problem 1.1**, and chapter 2's set restarting at **Problem 2.1**
- **the last chapter's problems** — nothing overset into the margin

- [ ] **Step 3: Compile the other four memoir books**

```bash
export PATH="/Library/TeX/texbin:$PATH"; for b in ~/math/math-parody ~/system-dynamics-book/systems-parody ~/engineering-computing-parody ~/modern-robotics-notebook; do echo "== $b"; uv run parody pdf "$b" -o "/tmp/$(basename $b)-594.pdf" 2>&1 | tail -3; done
```

Expected: each produces a PDF. Any book that already failed to build before this change is not a regression — confirm by `git stash`ing and rebuilding that one book before spending time on it.

- [ ] **Step 4: Run the whole suite**

```bash
export PATH="/Library/TeX/texbin:$PATH" && uv run pytest
```

Expected: green. `test_print_snippets.py` goldens pin the *filter's* output and must not move — this work never touched `print.lua`.

- [ ] **Step 5: Bump the version**

Re-derive the number against `origin/main` at this moment (project memory `recheck-version-against-main-before-merging`) — mains move fast. If main is still 0.43.0, the new version is **0.44.0**. Edit `pyproject.toml:3`, then:

```bash
uv lock && git add pyproject.toml uv.lock && git commit -m "0.44.0: the bundled memoir profile becomes a real house style"
```

- [ ] **Step 6: Commit the spec and plan**

```bash
git add docs/superpowers/specs/2026-08-16-memoir-house-style-design.md docs/superpowers/plans/2026-08-16-memoir-house-style.md && git commit -m "docs: spec + plan for the memoir house style (task #594)"
```

---

### Task 7: Ship

Follows project memory `electronics-ricopic-one-release-chain` §B and §D. §C (figure media) does **not** apply — no figures change.

- [ ] **Step 1: Merge to main and publish parody to PyPI**

```bash
git fetch origin && git rebase origin/main && git push origin HEAD:main
```

Then build and upload:

```bash
rm -rf dist && uv build && uvx twine upload dist/*
```

- [ ] **Step 2: Wait for PyPI propagation — 10 minutes, measured from the upload**

Your own PyPI edge is not a proxy for the GitHub runner. parody 0.43.0's tag build failed on exactly this. Budget the wait rather than re-dispatching twice.

- [ ] **Step 3: Repin and tag Electronics**

In `~/electronics-primer/electronics-parody`, bump the parody pin in `.github/workflows/build.yml` to `0.44.0` and the `parody:` key in `parody.yaml`, regenerate the tracked artifact, commit, push, then tag:

```bash
cd ~/electronics-primer/electronics-parody && git tag v0.3.7 && git push origin v0.3.7
```

Use the next patch after the current latest tag (`git tag --list | tail -1`), not `v0.3.7` blindly. Watch the run; on a propagation failure use `gh run rerun <run-id> --failed` — a tag cannot be re-pushed.

- [ ] **Step 4: §D — carry the new book PDF across**

`fetch_notebook_artifacts.py` does not handle `print.zip`, so a print-side fix reaches the release and stops there unless this is done by hand:

```bash
cd /tmp && gh release download vX.Y.Z -R electronics-primer/electronics-parody -p print.zip && unzip -o print.zip && cp electronics.pdf ~/homepage-django/teaching/notebooks_data/
```

- [ ] **Step 5: Repin the manifest and deploy**

```bash
cd ~/homepage-django && python scripts/fetch_notebook_artifacts.py -n electronics --tag vX.Y.Z --update
```

Commit the manifest, the artifact, and `teaching/notebooks_data/electronics.pdf` together, push `main`, and watch `deploy-ec2.yml`.

- [ ] **Step 6: Verify the live site**

Load a section's print PDF on electronics.ricopic.one and confirm it is cut from the new book — a run-in "Problem 1.1", not "Exercise 1".

---

## Self-Review

**Spec coverage:** §1 problems → Task 2. §2 numbering → Task 3. §3 bracket boxes → Task 4. §4 chapter opener → Task 5. §5 TOC + title page → Task 5. §6 microtype → Task 5. Verification (4 items) → Tasks 1, 5 step 7, 6. Shipping → Task 7. No gaps.

**Placeholders:** none — every code step carries the literal LaTeX or Python to insert. The one deliberately unresolved value is the Electronics tag in Task 7, which depends on the repo's current latest tag; the step says how to derive it.

**Type consistency:** `pdf_text`/`squashed` defined in Task 1, used in Tasks 2–3. `parodyboxbase` / `parodybox=<hue>` / `\parody@brk@{un,first,mid,last}` defined and consumed within Task 4. `\parody@chapopener` / `\parody@chaprule` / `\parody@chapbleed` defined and consumed within Task 5. Colour names match the theme's existing definitions.
