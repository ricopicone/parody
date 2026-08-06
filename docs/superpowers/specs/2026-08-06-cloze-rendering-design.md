# Cloze (fill-in-the-blank) rendering

**Date:** 2026-08-06
**Task:** #507
**Status:** approved design

## Problem

`parody/migrate/filters/latex-to-md.lua` already converts LaTeX `\cloze{…}` into
`[text]{.cloze}` spans and `.cloze` paragraphs, but **nothing consumes them**.
Neither `parody/filters/filter.lua` (web) nor `parody/filters/print.lua` (print)
nor any profile `.sty` mentions the class, so migrated fill-in-the-blank content
renders with every answer visible — the opposite of the intent.

Three books need this: the ME 465 Modern Robotics notebook migration, and the
electronics-primer and system-dynamics migrations, whose whole pedagogy is
fill-in-the-blank notes students print and complete by hand.

Alongside the student handout, both output paths must be able to produce a
**cloze-free** rendering — answers in place, no visual trace of the blanks — for
instructors and for official print publication.

## Modes

One new build axis, **orthogonal to `--solutions`**:

| mode | audience | clozes | manual blanks |
|---|---|---|---|
| `blank` | student handout | hidden, rule in their place | rule |
| `key` | instructor copy | shown, accented and ruled | rule |
| `full` | publication / clean copy | shown as ordinary text | dropped entirely |

`--solutions` stays what it is: whether exercise solutions print. A published
student book wants clozes *filled* and exercise solutions *hidden*, which is why
the two axes cannot be collapsed into `\issolution`.

`--clozes key --solutions` is the full instructor build; both flags compose.

## Authoring surface

```markdown
Automatic blank, sized to the answer:
  The damping ratio is [0.707]{.cloze}.

Manual blank (nothing hidden behind it), named sizes:
  Sketch the pole locations: []{.blank size=lg}
  []{.blank width=4cm}

Block forms:
  ::: {.blank lines=6}
  :::

  ::: {.cloze}
  A whole hidden paragraph, blanked to its own height.
  :::

Math (a real TeX macro, not a span):
  $\tau = \cloze{RC}$
  $y(t) = \clozeblank{3em}$

Incomplete artwork:
  ![Root locus](rl.pdf){#fig:rl cloze="rl-blank.pdf"}
  ![Root locus](rl.pdf){#fig:rl}     # picks up rl-cloze.pdf if present

Inside boxes — no special case:
  ::: {.example h="c4"}
  Then $\omega_n = \cloze{\sqrt{k/m}}$, so []{.blank size=md}.
  :::
```

Named sizes `sm`/`md`/`lg`/`xl` = 2/5/10/20 em. `width=` takes a raw length and
wins over `size=`. `lines=` on a block defaults to 4.

Math uses a macro rather than a span because pandoc treats math as opaque text —
a `[…]{.cloze}` cannot exist inside `$…$`. The macro is real LaTeX in print and
is rewritten at build time on the web.

## Mode plumbing

- **`parody.yaml`**

  ```yaml
  cloze:
    default: blank      # blank | key | full
  ```

  Absent ⇒ `blank`. The default can never leak an answer.

- **CLI** — `parody build --clozes MODE` and `parody pdf --clozes MODE`, both
  overriding the YAML default. An unrecognised value is a hard error naming the
  three valid modes. Output paths stay caller-chosen
  (`parody build --clozes full -o artifact/mr-full.json`), exactly as
  `--online-only` works today; no magic filename suffixes.

- **Print** — `writers/latex.py` appends `\def\clozemode{<mode>}` to the existing
  `flags` block that already carries `\issolution` and `\ispartial`.

- **Web** — `build.py` exports `PARODY_CLOZE_MODE` alongside the existing
  `PARODY_*` filter context, and `filter.lua` bakes the decision into the HTML.

- **Artifact** — schema v2 gains a top-level `"cloze_mode"` string so parody-web
  can label an instructor site and gate it.

### Split of labor

Print renders clozes **in TeX**; the web renders them **in the Lua filter**.

LaTeX can measure the hidden content (`\settowidth`, `\savebox`), so print gets
exact widths for free and needs no build-side stripping. HTML cannot measure at
build time, and — more importantly — anything the filter emits is fetchable by
the reader, so on the web the answer must never be written at all.

Figure-variant swapping is the exception: it happens in **both** filters, because
that is where asset resolution and SVG conversion already live.

## Rendering matrix

| source | `blank` | `key` | `full` |
|---|---|---|---|
| `[0.707]{.cloze}` | rule, `\settowidth` of content + 1 em slack, min 2 em | answer in `parodyaccent`, ruled | `0.707`, no markup |
| `[]{.blank size=lg}` | rule at named width | same rule | dropped |
| `::: {.blank lines=6}` | 6 ruled lines | 6 ruled lines | dropped |
| `::: {.cloze}` | `\savebox`, `(\ht+\dp)/\baselineskip` ruled lines | content accented, ruled | content, plain |
| `$\tau=\cloze{RC}$` | rule sized to `$RC$` | `\class{cloze-key}{RC}` | `RC` |
| `$\clozeblank{3em}$` | 3 em rule | 3 em rule | dropped |
| `![](rl.pdf){cloze=rl-blank.pdf}` | `rl-blank.pdf` | `rl.pdf` | `rl.pdf` |

In `full` mode the web HTML is **byte-identical to a book that never had
clozes** — spans are unwrapped, not restyled. That is what makes it a publication
build rather than a themed one.

A figure with no cloze variant (no `cloze=` attribute and no `<stem>-cloze.<ext>`
sibling) renders complete in every mode. Absence of a variant means the artwork
is not part of the exercise.

## Print implementation

`print.lua` emits four contract names and nothing more:

- `\cloze{<content>}` — inline, `\ifmmode`-aware so one macro serves text and math
- `\clozeblank{<size-or-length>}` — manual inline blank
- `\clozelines{<n>}` — manual block blank
- `clozeblock` environment — hidden block, self-measuring

Handlers to add:

- `Span`: `.cloze` → `\cloze{…}`, `.blank` → `\clozeblank{…}`, wired into the existing
  `Span` dispatch chain (`print.lua:1595`). `Span` is **already** in
  `interior_filter` (`print.lua:53`), so inline clozes inside exercise/example
  bodies and captions work with no extra wiring.
- `Div`: `.cloze` → `clozeblock`, `.blank` → `\clozelines{n}`. `Div` is *not* in
  `interior_filter`; add a narrow entry that handles only these two classes and
  returns `nil` otherwise, so nested block clozes work inside boxes without
  re-entering the exercise/example handlers.
- `Image`/`Figure`: swap `src` to the cloze variant in `blank` mode, before
  `resolve_asset` runs.

Math needs **no** filter work: `Math` already passes `InlineMath` through as raw
TeX, so `\cloze` inside `$…$` reaches LaTeX intact.

The math macro is `\clozeblank`, not `\blank`: **memoir already defines
`\blank`**, and `\newcommand` over an existing macro raises a LaTeX error and
silently leaves the *other* definition in force — it compiles, and renders
wrong. Found during implementation; the compile test now fails on any
`LaTeX Error` in the log, not just undefined control sequences.

The profile defines the four names, branching on `\clozemode`:

```tex
\providecommand{\clozemode}{blank}
```

`blank` mode leaks nothing into the PDF either: `\settowidth` typesets into a box
that is discarded, so the answer never enters the content stream and `pdftotext`
cannot recover it.

`PROFILE-CONTRACT.md` gains `\clozemode` under build flags and the four
names under commands/environments.

## Web implementation

`filter.lua` reads `PARODY_CLOZE_MODE` once (default `blank`) and gains:

- **`Span`** — `.cloze` and `.blank`. In `blank`/`key`, emit
  `<span class="cloze-blank" style="--cloze-w: 5.2em"></span>` or
  `<span class="cloze-key">0.707</span>`. In `full`, return the bare inlines so
  no wrapper survives. In `blank` mode **the answer text is never written**.
- **`Div`** — block forms emit `<div class="cloze-lines" data-lines="6">`;
  parody-web draws the rules. Line count for a hidden block is estimated as
  `max(1, ceil(chars / 90))`.
- **`Math`** — rewrite `\cloze{…}` / `\clozeblank{…}` inside `el.text`.

Width estimate (both spans and math): strip TeX control sequences, count the
remaining characters `n`, then `clamp(2, 0.6n + 0.8, 14)` em. Emitted as a
`--cloze-w` custom property so parody-web owns the actual appearance, consistent
with the frozen-HTML rule (build-side changes additive; presentation lives in
parody-web).

The math rewriter needs a **brace-matching scanner, not a regex** — `\cloze{\sqrt{k/m}}`
nests. Rewrites:

| mode | `\cloze{X}` | `\clozeblank{L}` |
|---|---|---|
| `blank` | `\underline{\hspace{<w>em}}` | `\underline{\hspace{L}}` |
| `key` | `\class{cloze-key}{X}` | `\underline{\hspace{L}}` |
| `full` | `X` | removed |

`\class` requires MathJax's `html` package. **Verified in a browser against
MathJax v3 (`tex-mml-chtml`)** during implementation:

- `\underline{\hspace{<w>}}` draws a clean rule with correct spacing. A bare
  `\rule[-0.3em]{<w>}{0.4pt}` also renders, but butts directly against the
  preceding operator with no gap — so `\underline{\hspace{…}}` it is.
- `\class` needs **two** lines of MathJax config, not just the package list:
  `loader: {load: ['[tex]/html']}` **and** `tex: {packages: {'[+]': ['html']}}`.
  With only the second it renders as a red undefined-macro error.

## Boxes and solutions

Clozes inside `.example` / `.exercise` / `.definition` need no special case:
within one pandoc filter table inlines run before blocks, so spans are already
rewritten by the time a Div handler sees the box.

**A cloze inside a solution always renders `full`.** Blanking the answer in an
answer key is nonsense.

- Web: `convert_solution_to_html` (`artifact.py:598`) is a separate pandoc call;
  force `PARODY_CLOZE_MODE=full` around it. The same applies to
  `extract_exercise_problems` output, which routes through the same helper —
  problems keep the ambient mode, so that call site must **not** be forced.
  (Give the helper an explicit `cloze_mode` argument rather than relying on a
  wrapping context, so the two call sites differ visibly.)
- Print: the `solution` and `labsolution` environments locally
  `\renewcommand{\clozemode}{full}`.

## Testing

- **`tests/print_fixtures/`** — a new `cloze.md` fixture covering every construct
  (inline, manual, block, math, in-box, figure variant), with a golden `.tex` per
  mode, following the `--regen-golden` idiom of `test_print_snippets.py`.
- **`tests/test_cloze.py`** — per-construct assertions on filter output for all
  three modes, plus the load-bearing negative: in `blank` mode the rendered HTML
  and LaTeX **do not contain the answer string**. This is the leak test; it must
  cover span, block, math, and figure cases.
- **Golden artifacts** — no existing book uses `.cloze`, so
  `tests/golden/*.json` are unaffected. Confirm they still pass unchanged.
- **`tests/test_print_pdf.py`** — extend the compile smoke test with a section
  containing clozes, compiled in all three modes, so the profile macros are
  exercised by a real LaTeX run.
- **CLI** — `--clozes` accepted by `build` and `pdf`; bad value errors.

## Non-goals

- **No click-to-reveal on the web.** In `blank` mode the answer is not in the DOM
  to reveal.
- **No gated cloze bucket in a single artifact.** Instructor and student are
  separate builds, the way editions already are. Hosting two artifacts is
  parody-web's concern; `cloze_mode` in the artifact is what lets it decide.
- **No per-cloze numbering or labels.**
- **The stubbed `.example` HTML box** (`filter.lua:530`) stays a sibling task. It
  is box chrome, it touches the frozen exercise HTML, and folding it in would put
  two unrelated risks in one change.

## Files touched

| file | change |
|---|---|
| `parody/cli.py` | `--clozes` on `build` and `pdf`; validation |
| `parody/config.py` | read `cloze.default` from `parody.yaml` |
| `parody/build.py` | export `PARODY_CLOZE_MODE`; record `cloze_mode` |
| `parody/writers/artifact.py` | `cloze_mode` in output; force `full` for solutions |
| `parody/writers/latex.py` | `\def\clozemode{…}` flag |
| `parody/filters/print.lua` | Span/Div/Image handlers; `interior_filter` Div entry |
| `parody/filters/filter.lua` | Span/Div/Math handlers; width estimator |
| `parody/profiles/memoir/parody-environments.sty` | the four macros |
| `parody/profiles/print/parody-print.sty` | the four macros |
| `parody/profiles/PROFILE-CONTRACT.md` | document `\clozemode` + names |
| `parody/schemas/artifact-v2.json` | `cloze_mode` |
| `tests/` | as above |

parody-web follow-on (separate repo, separate release): CSS for `.cloze-blank`,
`.cloze-key`, `.cloze-lines`; MathJax `html` package (both the `loader.load`
and `tex.packages` entries above); optional instructor-copy labelling from
`cloze_mode`.
