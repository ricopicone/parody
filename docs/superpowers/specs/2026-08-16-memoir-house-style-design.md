# The bundled memoir profile becomes a real house style

Task #594. Electronics Primer's print PDF looks unfinished next to the RTC book.
This spec closes that gap in the *bundled* profile, so every parody book that has
no book-private profile inherits the result.

## Why the two books differ

RTC does not use anything parody bundles. It builds with
`--profile profile-mitpress`, a book-private directory carrying MIT Press's
`NewMath_MIT.cls`, licensed Palatino, and ~2400 lines of style. Electronics
passes no `--profile` at all, so it gets `DEFAULT_PROFILE = "memoir"`
(`parody/writers/latex.py:217`) — ~480 lines that were written as a portable
fallback and never grew into a house style.

Every complaint on the task traces to something `profile-mitpress` does that the
bundled profile does not.

## Scope

Six changes, all inside `parody/profiles/memoir/`. No filter change, no writer
change: the print contract (`parody/profiles/PROFILE-CONTRACT.md`) already names
every environment involved, and this work only redefines how they render.

### 1. Problems, not exercises

`\xsimsetup{exercise/within=chapter, exercise/name=Problem}`, so the first
problem of chapter 1 is **Problem 1.1**. Lab problems keep the L-prefix used on
the web: `labexercise/the-counter = L\thechapter.\arabic{labexercise}`.

The heading sets **run-in** — bold `Problem 1.1` followed by the problem's first
paragraph on the same line — via a `parodyrunin` exercise template, rather than
xsim's `default` template's display heading.

`\crefname{exercise}` changes from `exercise` to `problem` (and `\Crefname` to
`Problem`). Print currently says "exercise 1.4" where the web already says
"problem 1.4" (task #499); after this they agree.

Problem sets stay **single column**. RTC's two-column set needs float-rescue
machinery for figures inside problems, and Electronics' problems carry
full-width circuit diagrams. Density is not worth that risk in a default.

### 2. Numbering within the chapter

`thmctr`, `infoboxctr`, `examplectr`, `listingctr` all become
`\counterwithin{...}{chapter}`, plus `\numberwithin{equation}{chapter}` and
`\counterwithin*{footnote}{chapter}`. Definitions and theorems continue to
*share* `thmctr`, as they do in RTC.

`Definition 10` / `Box 1` / `Example 5` become `Definition 1.6` / `Box 1.1` /
`Example 1.3`.

### 3. Boxes: corner brackets, no fill

The tinted `tcolorbox` with a solid colored title bar is replaced by the
open-frame bracket design from the author's own
`rtcbook common/styles-tex/environments.sty` — accent-colored bold title, no
background, no full frame, bracket strokes at the corners drawn as a tcolorbox
overlay. Examples keep a dashed segmentation rule between statement and
solution.

This is the same vocabulary parody-web already uses for web examples (task
#318), so the two media converge rather than diverging further.

### 4. A stylized chapter opener

The current opener is a large accent numeral over a large bold title. The new
one is deliberately more graphic:

```
CHAPTER                                                          1
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Fundamentals
```

- `CHAPTER` in letterspaced small caps, accent colour, ranged left.
- The numeral very large (72pt+), accent colour, ranged right and **outdented
  into the outer margin** so it breaks the measure.
- A 2pt accent rule spanning the full measure, sitting under both.
- The title `\HUGE\bfseries`, ragged right, below the rule.

Constraints: it must survive `\appendix` (numeral becomes `A`), `chapter_start:
0` (numeral `0`, used by RTC), and unnumbered `\chapter*` front/back matter,
where the numeral and rule are simply omitted.

### 5. Page furniture

- **Contents — a real bug.** `parody-memoir.cls` sets
  `\cftsectionleader{\hspace*{1.5em}}`. That removes the only stretchable glue
  from the line, so TeX stretches the interword space of the *title* instead,
  producing `Voltage,   current,   resistance,   and   all   that   1`. Restore a
  stretchable leader while keeping the no-dots look.
- **Title page.** `\thispagestyle{empty}` (the folio currently prints on it), and
  a centred, restrained title block rather than the bottom-ragged one.

### 6. Typography

Add `microtype`. It is what makes the measure sit quietly — the current PDF's
justification is visibly loose — and it supplies `\textls` for the chapter
opener's letterspaced small caps.

## Blast radius

Every book on the default profile is restyled: math, systems,
engineering-computing, modern-robotics, Electronics, and RTC's non-MIT builds.
That is the intent. RTC's published build is untouched — its Makefile pins
`PROFILE ?= profile-mitpress`.

## Verification

No claim of completion without all four:

1. Unit tests in `tests/test_print_memoir.py` for the generated `main.tex` and
   the staged profile files; a print-snippet fixture for the run-in problem.
2. `parody pdf` of Electronics compiled locally against TeX Live 2026
   (`/Library/TeX/texbin`), then the resulting pages *read* — title, contents, a
   box spread, a problems spread, a chapter opener. Print builds fail quietly
   (see project memory `print-builds-fail-quietly`); a clean exit is not
   evidence.
3. The other four memoir books compile without new errors.
4. `uv run pytest` green.

## Shipping

parody 0.44.0 to PyPI, then the Electronics content chain (project memory
`electronics-ricopic-one-release-chain` §B and §D — §D applies because print
output changes; §C does not, no figures change).
