# `starred` exercises and `.staff-only` blocks

*2026-08-31. Spans parody and parody-web; homepage-django is the first consumer
of both.*

Two marks the Chapter 2 problem set of the ME 465 robotics notes had to work
around. Neither workaround is broken — both are in production and tested — but
both put the mark somewhere it cannot be read as data.

- A **starred problem** is currently spelled in the words of its title
  (`title="Starred problem (MME 565): …"`). Nothing downstream can render a star
  without matching on prose.
- The **grading notes** at the end of each solution are stripped by a
  homepage-django template that shadows `parody_web/solution.html`. It works
  because `teaching` precedes `parody_web` in `INSTALLED_APPS`, and it breaks
  silently if that order changes or the template is renamed upstream.

The two halves are independent: `starred` touches no access policy, and
`.staff-only` touches no parody Python. They ship as separate releases.

## Part 1 — `starred` on `.exercise`

### Spelling

A class, alongside the environment's own:

```
::: {.exercise .starred #exe:planar-screw title="Planar screw axis"}
```

Not an attribute (`starred="true"`). Three reasons: `.lab` is already a class,
the artifact's attribute scan already collects the raw class list, and classes
compose — `::: {.exercise .lab .starred}` is a starred lab problem, which the
attribute form makes awkward to express and awkward to read.

`starred` is deliberately generic. parody must not know about MME 565. What the
star *means* — that the problem is the graduate students' — stays on the course
side, in `ChecklistItem.audience` and `ChecklistItem.is_starred`, which remain
authoritative for who is actually set the problem and what their checklist score
is out of. The book grows a star to match; it does not become the source of
truth.

### `starred` is a modifier; `lab` is a kind

This distinction drives the whole implementation, and getting it wrong is the
one way to make the feature actively harmful.

`.lab` is a *kind* of exercise: it runs on its own per-chapter counter
(`labexercise`), takes an `L`-prefixed number ("Problem L4.1"), and gets its own
`\DeclareExerciseType` in the print profiles.

`.starred` must get **none** of that. A starred problem keeps its place in the
ordinary sequence — it is still Problem 2.5, and the problem after it is 2.6.
Giving it a counter of its own would silently renumber every problem set that
adopts it.

It follows that:

- No new xsim exercise type, and no new counter anywhere.
- Cross-references stay clean: `[@exe:x]` renders "Problem 2.5", not
  "Problem 2.5★". A star describes the problem; it is not part of its name.
- `starred` and `lab` compose. Every guard must treat them as orthogonal.

### parody

| file | change |
|---|---|
| `parody/filters/filter.lua` (`exercise()`, ~line 563) | when `el.classes:includes('starred')`, append `"starred"` to the box's class list and `{"data-starred","1"}` to its attributes — beside the existing `lab` branch at line 567, not inside it |
| `parody/filters/print.lua` (`exerciser()`, ~line 836) | when the class is present, prefix the exercise body with `\parodystarmark`. The `env`/`sol_env` selection is untouched. |
| `parody/profiles/memoir/parody-environments.sty` | `\providecommand{\parodystarmark}{\textbf{$\star$}\enspace}` |
| `parody/profiles/print/parody-print.sty` | the same `\providecommand`, so a house style can redefine it per profile |
| `parody/writers/artifact.py` (~line 490) | `is_starred = 'starred' in div_classes`, carried through `div_matches` and stamped `anchor['starred'] = True` under the **same exercise-only guard** as `lab` at line 543 |
| `parody/writers/artifact.py` (`extract_exercise_problems`, `extract_exercise_solutions`) | `'starred': _fence_has_class(attrs, 'starred')` on each bucket entry |

#### Why the print mark is injected into the body

The obvious route is a custom xsim property — `\DeclareExerciseProperty{starred}`
beside the existing `hash` (`parody-print.sty:141`), passed as
`\begin{exercise}[ID=…,hash=…,starred=1]` and read by the heading template.

It does not survive contact with both profiles. The memoir profile defines its
own run-in template (`parodyrunin`, `parody-environments.sty:224`) and could read
the property happily. The print profile sets `exercise-template=default`
(`parody-print.sty:152`) and hands the heading to the MIT class, so reading a
property there means overriding template internals we do not own.

`\parodystarmark` as the first token of the body is correct in both without
touching xsim at all: under a run-in template it lands immediately after
"Problem 2.5", and under a display heading it opens the first line. Each profile
decides how to draw it.

The mark goes on the exercise only. Its solution follows it in the manual and
needs no mark of its own.

#### Schema

`SCHEMA_VERSION` stays 1. `starred` is an optional key, exactly as `lab` is, and
it is produced only by the v2 (`with_hashes`) attribute scan — the v1
`div_pattern` path does not parse classes and never has. A consumer that does
not know the key ignores it.

### parody-web

`numbering.py` reads `a.get("starred")` beside `a.get("lab")` at line 1343 and
threads it to the box rewrite. `problem_caps` currently stores a
`(label, is_lab)` tuple (line 1359, consumed at line 1603); it becomes
`(label, is_lab, is_starred)`.

`_rewrite_exercise_box` (line 733) emits `class="exercise starred"` — composing
with `lab`, so a starred lab problem is `class="exercise lab starred"` — and
puts the mark inside the run-in label:

```html
<div class="problem-label">Problem 2.5 <span class="problem-star"
     role="img" aria-label="starred problem">★</span> …</div>
```

`content.css` (near `.problem-label`, line 175) styles it.

`solution_detail` passes `entry.get("starred")` into the template context and
`solution.html` shows the same mark beside its `<h1>`.

The counter code at lines 1343–1348 is not touched: `key`, `num` and `word` are
chosen by `is_lab` alone.

## Part 2 — `.staff-only`

### Why a convention rather than an HTML hook

The narrower ask was `policy.solution_html(request, section, exercise_id, html)`
— an identity-by-default hook letting the host do arbitrary surgery on solution
HTML. It would work, and it would leave the host owning an HTML stripper for a
concept the book itself is expressing.

A first-class `.staff-only` div is better on three counts: parody-web deletes
the host's stripper rather than relocating it; the gate is a boolean
(`can_view_staff_notes`) rather than a string transform, which is far easier to
reason about and to test; and it covers **section prose**, not just solutions,
which is where the leaks in the current arrangement actually are (below).

### Inverted from `.solutions-only`

`.staff-only` looks like a sibling of the existing `.solutions-only` and behaves
oppositely in the one way that matters.

`.solutions-only` is a **build-time** gate: `filter.lua:973` deletes the div from
the HTML unless `PARODY_SOLUTIONS` is set, so the content never enters the
artifact a student's site loads.

`.staff-only` must **survive into the artifact intact**. One artifact serves both
audiences, and who is staff is a question only the serving site can answer — it
depends on the reader, not on the build.

- **parody / `filter.lua`** — pass `.staff-only` through untouched in HTML. An
  unknown div class already survives with its class intact, so the change is a
  documented guarantee plus a test that pins it, so a later refactor cannot
  quietly start eating it.
- **parody / `print.lua`** — wrap in `\ifdefined\issolution`, reusing the
  `.solutions-only` machinery at line 1829. The solutions manual is the only
  staff print artifact there is, so that mapping is exact.

### parody-web

New module `parody_web/staffonly.py`:

- `strip_staff_only(html)` — pure. A depth-balanced forward scan from each
  opening tag, so a block that later grows a nested `<div>` is removed whole
  rather than leaving its tail behind, and an unbalanced block drops the
  remainder rather than shipping half a grading note. This is the scanner
  already written and tested as `teaching/notes/solutions.py::strip_grading_notes`
  in homepage-django, moved up and renamed.
- `for_reader(request, html)` — consults the policy once and calls the stripper
  when the answer is no.

One new hook on `DefaultPolicy`:

```python
def can_view_staff_notes(self, request):
    """May this reader see `.staff-only` blocks — marking guidance, rubrics,
    answer notes — that ship inside otherwise-readable content?"""
    return self.is_owner(request)
```

### Four call sites, three of them leaks the workaround never covered

The shadowed template covers the solution page. It is not the only surface that
serves `.staff-only` content, and the others are worse because they are silent:

| site | leak |
|---|---|
| `views.py:765` `solution_detail` | the solution body — the known one |
| `views.py:~476` `section_detail` | `.staff-only` prose in a section body |
| `views.py:487` `_excerpt(section.html)` | becomes `<meta name="description">` — staff notes served to search engines |
| `import_artifact.py:184` `_plain_text(sec["html"])` | fills `Section.plain`, which `search()` (`views.py:340`) matches with `icontains` and returns as highlighted snippets |

The first three take `for_reader(request, …)` at render time.

**Search is stripped at import instead.** Snippets come from a stored column with
no per-reader variant, so the safe answer is that `plain` never contains staff
content at all. The cost is real and worth naming in the docs: staff cannot
full-text-search their own grading notes. They can still read them on the page.
The alternative — a second `plain_staff` column and a policy-aware query — buys
little and doubles the thing that has to stay in sync.

### homepage-django

`teaching/notes/solutions.py` and `teaching/templates/parody_web/solution.html`
are deleted. `CoursePolicy` (`teaching/parody_policy.py`) gains:

```python
def can_view_staff_notes(self, request):
    return user_teaches_any_course(self._user(request))
```

`teaching/views.py` (the legacy exercise-solution page, ~line 2462) calls
`parody_web.staffonly.for_reader` in place of the deleted `solution_html_for`.

### The `.grading-notes` migration

The robotics notes currently write `::: {.grading-notes}`. They become

```
::: {.staff-only .grading-notes}
```

Both classes, because they say different things: `grading-notes` is
presentational and keeps whatever styling it has; `staff-only` is the access
mark parody-web gates on. A find/replace over the chapter sources, plus a
rewrite — not a deletion — of the note in `docs/AUTHORING-STYLE.md`.

Rejected: a `PARODY_WEB_STAFF_ONLY_CLASS` setting, which would spare the edit at
the price of making "what counts as secret" configurable. A setting that can be
misconfigured into serving grading notes is a worse failure mode than a
find/replace.

## Testing

**parody**

- Artifact: a `.exercise .starred` div stamps `starred` on its anchor and on both
  bucket entries; a `.example .starred` and an `.infobox .starred` stamp nothing
  (the exercise-only guard); `.exercise .lab .starred` stamps both.
- filter.lua: the emitted box carries `starred` and `data-starred="1"`, and
  still carries `lab`/`data-lab` when both classes are present.
- print.lua: a starred exercise's body opens with `\parodystarmark`; an unstarred
  one does not; the environment is still `exercise` (or `labexercise`), proving
  no new type was introduced.
- filter.lua: a `.staff-only` div survives HTML conversion with its class intact;
  print.lua wraps it in `\ifdefined\issolution`.

**parody-web**

- Numbering: beside the existing `lab` fixtures (`tests.py:348`), a starred
  problem numbers in the ordinary sequence — the assertion that would have
  caught a stray counter — and its box carries `class="exercise starred"`.
- `strip_staff_only`: nested divs, attributes in any order, multiple blocks,
  unbalanced input, absent-class passthrough, `None`/empty.
- Policy: all four surfaces in both roles. The `meta_description` and search
  ones matter most — they are the two that would otherwise regress in silence.

**homepage-django**

`tests_grading_notes_on_the_book_site.py` moves down into parody-web as a policy
test and stops being a canary for `INSTALLED_APPS` ordering.
`tests_solution_grading_notes.py` moves with the scanner it covers.

## Releases

Independent, and shipped separately so the homepage can take the `.staff-only`
fix without waiting on the print star.

1. `starred` — parody 0.56.0, parody-web 0.97.0
2. `.staff-only` — parody 0.57.0, parody-web 0.98.0
3. homepage-django: pin both, delete the workaround, add the hook override.
