# Web: number problems and lab problems (task #499)

## Problem

On the web every `::: {.exercise}` renders as a box headed by a bare word
`Exercise`, with no number. The box carries Tailwind class names
(`rounded border border-green-400 shadow-md bg-white`) that parody-web has no
stylesheet for, so it reads as an unstyled block. Cross-references to problems
resolve off a single per-chapter counter that mixes lab and non-lab problems,
so those numbers are wrong as well.

## What the book actually does

From `rtcbook/common/styles-tex/environments.sty` and `packages.sty`, confirmed
against the built original `real-time-computing-0.pdf`:

| Kind | Counter | Heading | Cross-reference |
|---|---|---|---|
| `exercise` (`.exercise`) | `within = chapter` | `Problem 1.2` | `problem 1.5` |
| `lab` (`.exercise .lab`) | `\newcounter{labexercise}[chapter]`, `the-counter = L\thechapter.\arabic{labexercise}` | `Problem L4.5` | `lab problem L4.4` |

Lab *sections* are titled `Lab 0` … `Lab 8` — the lab number is the chapter
number, not a running count of lab sections. RTC sets `chapter_start: 0`, so
parody-web's sequential `Lab exercise {1,2,3…}` is off by one for every lab.

Print already renders all of this correctly: RTC builds under the mitpress
profile, which loads the book's own `environments.sty`. **Print is out of scope.**

## Split of responsibility

`filter.lua` keeps emitting the exact box HTML it emits today. Those Tailwind
classes are live CSS in homepage-django, which is a second consumer of these
artifacts, and the golden artifacts in `tests/golden/` lock the markup in. The
build-side change is therefore *additive markers only*; all presentation lives
in parody-web.

Verified golden-safe: none of the five golden corpora contain a `.lab`
exercise, so an additive change that only fires on `.lab` leaves them
byte-identical.

## A. parody (build) — additive only

**`parody/filters/filter.lua`, `exercise(el)`** — when the div carries `.lab`,
append `lab` to the wrapper's class list and set `data-lab="1"`. Nothing else
changes.

**`parody/writers/artifact.py`, div-anchor extraction** (the `with_hashes`
branch that builds `div_matches`) — when an exercise div's classes include
`lab`, set `"lab": true` on the anchor. Emitted only when true, so artifacts
without lab problems stay byte-identical.

```
anchor: {"id": "wj", "type": "exercise", "hash": "wj", "lab": true}
div:    <div id="wj" class="exercise lab …" data-h="wj"
             data-env-type="exercise" data-lab="1">
```

## B. parody-web (render)

### `parody_web/numbering.py`

1. **Two per-chapter counters** replace the single mixed `exercise` entry in
   `type_counters`:
   - non-lab → number `{cnum}.{n}`, label `Problem {num}`
   - lab → number `L{cnum}.{k}`, label `Lab problem {num}`

   `_TYPE_LABELS["exercise"]` becomes `"Problem"`; the lab label word is
   selected inline from `a.get("lab")`. Reference-site casing continues to work
   through `_recase_label`, which toggles only the leading letter — giving
   `problem 1.5` and `lab problem L4.4`, matching the original.

2. **Lab section number** becomes `f"Lab exercise {cnum}"` — the chapter
   number. The running `lab_n` counter is deleted.

3. **New `problem_caps`** — `{section_slug: {anchor_id: display_number}}`,
   mirroring `example_caps`, carrying the display number into pass 2.

4. **Pass 2 rewrite** of each exercise div, keyed on its id:
   - normalize the opening tag's class to `exercise` (or `exercise lab`),
     dropping the dead Tailwind classes;
   - inject `<div class="problem-label">Problem L4.5</div>` as the first child;
   - drop the legacy `<section …><h3 …>Exercise</h3></section>` header that
     immediately follows the opening tag.

   Same shape as the existing freadinglist box rebuild. If an exercise carries
   a `title=` attribute (no book currently does), it is appended after the
   number rather than discarded.

### `parody_web/static/parody_web/css/content.css`

Real `.exercise` / `.problem-label` rules in the design system: display font,
`--accent`, and a `scroll-margin-top` that clears the sticky masthead (the
`scroll-mt-20` class the filter emits is dead CSS here).

### Result

```
Problem 0.1
In section 0.5.4, the modulo operator is used in the primality()…

Problem L4.5
Repeat lab problem L4.4 while printing the speed (pressing the switch)…
```

## Tests

**parody**
- `.exercise .lab` renders with the `lab` class and `data-lab="1"`; its anchor
  carries `lab: true`.
- A plain `.exercise` renders byte-identically to today and its anchor has no
  `lab` key.

**parody-web**
- Lab and non-lab problems advance independent per-chapter counters.
- Headings read `Problem 0.1` and `Problem L4.1`.
- Cross-refs read `problem 1.5` / `Problem 1.5` and `lab problem L4.4` /
  `Lab problem L4.4` per reference-site casing.
- A lab section's label is its chapter number (`Lab exercise 0` for chapter 0).
- Pass 2 injects the label and removes the legacy header.

## Ships via

Both packages to PyPI, then the six-step rtcbook.org deploy chain.
