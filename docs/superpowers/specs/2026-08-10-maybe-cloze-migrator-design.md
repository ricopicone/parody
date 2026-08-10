# Routing `\maybe*` and the cloze package through cloze in the migrator

**Date:** 2026-08-10
**Task:** #542
**Status:** approved design
**Depends on:** `2026-08-06-cloze-rendering-design.md` (#507), which defines the
cloze authoring surface this migration targets.

## Problem

`parody/migrate/filters/latex-to-md.lua` dispatches only `\cloze` to `clozer`
(RawInline line 883, RawBlock line 961), which emits the `[…]{.cloze}` span that
`filter.lua:771` and `print.lua` render. The `\maybe*` family — which predates
parody's cloze support — routes to legacy handlers that emit classes no renderer
knows:

| macro | migrator emits | renderer knows it? |
|---|---|---|
| `\cloze` | `[…]{.cloze}` | yes |
| `\mayb` | `class='maybe'` | **no** |
| `\maybeeq` | `class='maybe maybeeq'` | **no** |
| `\maybeeqn` (inline) | `class='maybe maybeeq'` | **no** |
| `\maybeeqn` (block) | nothing — handler commented out, `return el` | **no** (raw LaTeX passthrough) |

`maybe` appears nowhere in `filter.lua`, `print.lua`, or `artifact.py`. Those
spans pass through unstyled, so **the cloze silently reveals its answer instead
of blanking it** — the failure mode looks like success.

The `\cloze` path is not healthy either. `clozer` extracts its argument with
`element.text:match("{(.-)}")`, which is non-greedy and stops at the first `}`:
`\cloze{\keyword{stationary point}}` captures `\keyword{stationary point`. The
argument is also stuffed into a `Span` as a raw string, so nested markup never
converts.

## Exposure

`\maybe*` is not confined to the electronics primer. Counts are of real call
sites, excluding `\newcommand` definitions and the orphaned
`common/versioned/93/` duplicate section:

| book | `\mayb` | `\maybeeq` | `\maybeeqn` | `\examplemaybe` |
|---|---|---|---|---|
| system-dynamics | 27 | 78 | 6 | 38 |
| math | 4 | 30 | 2 | 12 |
| electronics-primer | 2 | 21 | 5 | 6 |
| differential-equations-primer | 0 | 16 | 0 | 4 |
| rtc (`~/rtcbook`) | 12 | 1 | 0 | 10 |
| **total** | **45** | **146** | **13** | **70** |

The electronics row matches the 28 instances task #542 records. `~/rtcbook` and
`~/real-time-computing` are duplicate working copies of one book; per the
`rtc-meta-source-location` memory, `~/rtcbook` is the live source and only it is
counted. `common/versioned/93/` exists only in the electronics primer.

`\maybe` and `\mayben` have **zero** call sites anywhere — only their
`\newcommand` definitions. They are handled for completeness, not for content.

Traditional `cloze` package usage is real but narrow: `\cloze{…}` in
system-dynamics (61) and math (35), plus `\clozeset{hide|show}` in preambles. No
`\clozeline`, `\clozefil`, `\clozebox`, `\clozepage`, `\clozenol`, `\clozefix`,
or `\clozeextend` appears anywhere in the corpus. `engineering-computing`,
`modern-robotics-notebook`, `mechatronics_lab_manual`, and `control-systems` use
neither family.

## Source semantics

Per the electronics primer's `electronics/common/styles-tex/environments.sty`
(lines 818–890), every `\maybe*` is an `\ifthenelse{\boolean{show}}` reveal:

- `\mayb{X}` → `X` or `\phantom{X}` — a blank sized to the answer.
- `\maybe{X}` → an unframed, untitled `tcolorbox`, visible or `upperbox=invisible`.
- `\mayben{title}{label}{X}` → `infobox` vs `infoboxi`: box and title stay, contents hide.
- `\maybeeq{X}` → `eqboxtwo` vs `eqboxtwoi`: a colour-framed, untitled, unnumbered box.
- `\maybeeqn{title}{label}{X}` → `eqbox` vs `eqboxi`: `\stepcounter{equation}`,
  title `Equation \theequation\quad #1`, `\label{#2}`. Numbered, titled, and a
  live cross-reference target while blanked.

`upperbox=invisible` hides the contents while preserving their space — which is
precisely what `::: {.cloze}` means in the #507 contract.

`\maybeeqn` bodies are **not always pure math**. `electronics/ch03_00.tex:494`
and `:505` open with a sentence of prose before an `align*`. Any mapping that
assumes "this is an equation" is wrong.

## Mapping

Everything lands on the authoring surface #507 already defines. Nothing is added
to `filter.lua`, `print.lua`, the profile `.sty` files, or the artifact schema.

| LaTeX | markdown | note |
|---|---|---|
| `\mayb{X}` inline | `[X]{.cloze}` | exact `\phantom{X}` equivalent |
| `\mayb{X}` block | `::: {.cloze}` | |
| `\maybe{X}` | `::: {.cloze}` | no call sites; completeness |
| `\mayben{t}{l}{X}` | `::: {.infobox #l title="t"}` wrapping `::: {.cloze}` | no call sites; completeness |
| `\maybeeq{X}` | `::: {.cloze}` containing the converted body | frame dropped — see below |
| `\maybeeqn{t}{l}{X}` | `::: {.infobox #l title="t"}` wrapping `::: {.cloze}` | empty `{}` label ⇒ no identifier |
| `\cloze{X}` in prose | `[X]{.cloze}` | |
| `\cloze{X}` inside math | **untouched** | |
| `\clozeset{…}` | dropped | preamble concern; the migrator emits no preamble |
| any other `\cloze*` | left raw + stderr warning | |

Worked example, from `electronics/ch03_00.tex:494`:

```markdown
::: {.infobox #eq:voltage_divider_general_impedance title="general impedance voltage divider"}
::: {.cloze}
For the output voltage across impedance $Z_k$ in series with $n$ impedance
elements with input $v_\text{in}$ is

$$\begin{aligned}
  v_k &= \frac{Z_k}{Z_1+Z_2+\cdots+Z_k+\cdots+Z_n} v_\text{in}.
\end{aligned}$$
:::
:::
```

`.infobox` is the target for the titled forms because it already carries a
title attribute and an identifier on both paths (`filter.lua:408`,
`print.lua:624`) and already has cross-ref anchoring from #306. Cross-references
will read "Infobox N" rather than "Equation N"; adding a first-class titled
equation box was considered and rejected as scope beyond the migrator.

### `\cloze` inside math is deliberately left alone

Pandoc keeps `\cloze` inside the `Math` node rather than emitting a `RawInline`
— verified against the pinned pandoc 3.6.1 for both `$…$` and a display
`align`. `filter.lua:848` and `print.lua` already rewrite the macro there, per
the #507 contract ("Math uses a macro rather than a span because pandoc treats
math as opaque text"). Converting it in the migrator would break the one case
that already works.

### Accepted fidelity losses

- **`\maybeeq` loses its coloured frame.** `eqboxtwo` draws a border even in
  *show* mode, so the frame is chrome rather than purely the hiding mechanism.
  An `.infobox` with no title renders an empty `<h3>`, which is worse. Plain
  `::: {.cloze}` it is. This is the highest-volume construct (146 call sites).
- **`\maybeeqn` cross-refs read "Infobox N", not "Equation N".** The label keys
  stay `eq:*`, so nothing dangles; only the printed prefix changes.
- **`\maybeeqn`'s equation-counter step is not reproduced.** The infobox has its
  own counter.

## Implementation

### One brace-matched argument reader

The root cause of every broken handler is argument extraction. Two patterns are
in use, both wrong for real content:

- `{(.-)}` — non-greedy, stops at the first `}` (`clozer` line 143,
  `clozer_block` line 148).
- `{.-}{(.-)}{.-}` — mis-splits whenever any argument nests
  (`replace_maybeeqn_inline` line 544, `replace_examplemaybe` line 592).

Add one helper, `read_args(text, n)`, that walks `%b{}` *n* times from the end of
the macro name and returns the *n* arguments with outer braces stripped. Every
handler uses it. This replaces the ad-hoc `%b{}` / `sub(2,-2)` / leading-`%`
scrubbing repeated across `replace_maybeeq`, `replace_maybeeq_inline`,
`replace_mayb`, and `replace_mayb_inline`; that scrubbing moves into the helper.

### Recursive argument conversion

Arguments are converted, not passed through as raw strings: `pandoc.read(arg,
'latex+raw_tex')` walked with `inline_filter` / `block_filter`. This is the
idiom `replace_examplemaybe` already uses (lines 602–615) and that `keyworder`
and the title handlers at lines 367 and 392 use via `pandoc.walk_inline`.

Inline arguments take `.blocks[1].content` and walk with `inline_filter`; block
arguments take `.blocks` and walk with `block_filter`.

Today `clozer` builds `pandoc.Span(raw_string, …)`, so `\cloze{\keyword{stationary
point}}` never produces a nested `.keyword` span. 31 of the 96 `\cloze` call
sites — roughly a third — wrap a macro or math and are affected.

`clozer_block` is separately broken: `pandoc.Para(text, {class='cloze'})` passes
an attr to a constructor that takes none, and a string where inlines belong. It
becomes a `Div` with class `cloze`.

### Dispatch ordering

The RawInline and RawBlock chains dispatch on `starts_with`, so longer names
must be tested first. The existing order is `\maybeeqn` → `\maybeeq` → `\mayb{`;
inserting `\maybe{` and `\mayben{` requires
`\maybeeqn` → `\maybeeq` → `\mayben{` → `\maybe{` → `\mayb{`. Getting this wrong
routes `\maybeeqn` into the `\maybe` handler and silently drops the title and
label — the same class of quiet failure this task exists to remove. The
trailing brace in `\mayb{` is what already keeps it from swallowing the others,
and it must stay.

### Display-math bodies

`\maybeeq` and `\maybeeqn` bodies wrapped in `\begin{align*}…\end{align*}`
continue to convert to `$$\begin{aligned}…\end{aligned}$$`, matching what the
existing handlers do and what `parody-web` 0.28.1 expects (it promotes inner
`aligned` → `align` so `\tag` is legal).

### `\examplemaybe`

Its semantic mapping is unchanged — it is the `--solutions` axis, not the cloze
axis, and `.example` + solution sub-div is already correct. It is touched only
to swap in the shared `read_args` reader, since it carries the same
mis-splitting bug across ~70 call sites.

### Warnings

`latex-to-md.lua` has no warning facility. Add a `warn()` writing the macro name
and a short content excerpt to stderr, used for:

- unhandled `\cloze*` variants (`\clozeline`, `\clozefil`, `\clozebox`,
  `\clozepage`, `\clozenol`, `\clozefix`, `\clozeextend`), which are left raw;
- any `\mayb*` found inside a `Math` node, which no renderer understands and
  which would otherwise pass through silently.

Confirm during implementation that `parody/migrate/latex_to_md.py` surfaces
pandoc's stderr rather than swallowing it; if it does not, route the warnings so
they reach the operator.

## Testing

`tests/test_latex_to_md.py` extends with per-construct assertions through
`convert_latex_file`, following the existing substring idiom:

- each `\maybe*` form, inline and block, against its row in the mapping table;
- nested-brace arguments (`\cloze{\keyword{x}}`, `\maybeeqn` with an `align*`
  body) — these fail against the current extractor;
- recursive conversion — the inner `\keyword` becomes a `.keyword` span;
- `\cloze` in prose, in `$…$`, and in a display `align` — the latter two emerge
  unchanged inside the math;
- `\maybeeqn` with an empty `{}` label ⇒ infobox with no identifier;
- an unhandled `\cloze*` variant ⇒ left raw, warning emitted.

The load-bearing test is end to end: migrate a fixture containing every
construct, build it with `--clozes blank`, and assert the answer strings are
**absent** from the output. That is what distinguishes this from the current
failure mode, in which the cloze silently reveals its answer. It reuses the
`tests/test_cloze.py` machinery from #507.

Golden artifacts are unaffected — no migrated book in `tests/golden/` uses these
macros. Confirm they still pass unchanged.

## Non-goals

- **No new build-side environment.** No titled equation box; `.infobox` carries
  the titled forms.
- **No cloze-package commands beyond `\cloze`.** The rest have no call sites in
  the corpus; they warn rather than guess. Adding them later is additive.
- **No `\clozeset` / preamble handling.** Mode selection is `--clozes`, per #507.
- **No `\examplemaybe` semantic change.**
- **No re-migration of already-converted books.** This changes the migrator;
  when each book is re-migrated is a separate call.

## Files touched

| file | change |
|---|---|
| `parody/migrate/filters/latex-to-md.lua` | `read_args` helper; `warn()`; rewrite `clozer`, `clozer_block`, `replace_mayb{,_inline}`, `replace_maybeeq{,_inline}`, `replace_maybeeqn{,_inline}`; new `\maybe` / `\mayben` handlers; wire `\maybe`/`\mayben` into the RawInline and RawBlock dispatch chains; `read_args` in `replace_examplemaybe` |
| `parody/migrate/latex_to_md.py` | only if stderr is swallowed |
| `tests/test_latex_to_md.py` | per-construct assertions |
| `tests/test_cloze.py` | end-to-end migrate → `--clozes blank` leak test |
