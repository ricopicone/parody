# Web Problem/Lab-Problem Numbering Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** On the book web site, render problems as `Problem 3.2` and lab problems as `Problem L4.1` (today both render as an unnumbered box headed `Exercise`).

**Architecture:** parody's `filter.lua` keeps emitting the exact exercise box HTML it emits today — those Tailwind classes are live CSS in homepage-django, a second consumer of these artifacts, and `tests/golden/` locks the markup in. The build-side change is *additive markers only* (`lab` class + `data-lab="1"` on the div, `"lab": true` on the anchor). All numbering and presentation happens in parody-web's `numbering.py` and `content.css`.

**Tech Stack:** Python 3, pandoc 3.6.1 via pypandoc-binary (pinned), Lua pandoc filters, Django 5, plain CSS.

**Spec:** `docs/superpowers/specs/2026-08-03-web-problem-numbering-design.md`

## Global Constraints

- Two repos: **parody** at `/Users/picone/parody/.claude-worktrees/fleet-zephyr` (this worktree), **parody-web** at `/Users/picone/parody-web` (branch it before committing — see Task 3).
- **Non-lab exercise HTML must stay byte-identical.** `tests/golden/engineering-artificial-intelligence.json` contains 7 exercise divs and no lab exercises. Any change to non-lab output breaks golden parity with homepage-django.
- Numbering authority is the original book, `rtcbook/common/styles-tex/environments.sty`:
  - heading for both kinds uses `exercise-name = Problem` → `Problem 1.2`, `Problem L4.5`
  - non-lab counter is `within = chapter` → number `{chapter}.{n}`
  - lab counter is `\newcounter{labexercise}[chapter]`, `the-counter = L\thechapter.\arabic{labexercise}` → number `L{chapter}.{k}`
  - cross-ref words differ from the heading: `\crefname{problem}{problem}` and `\crefname{labproblem}{lab problem}` → `problem 1.5`, `lab problem L4.4`
  - lab *sections* are `Lab 0` … `Lab 8` — the lab number **is** the chapter number
- Reference-site casing is already handled by `_recase_label`, which toggles only the leading letter. Labels must therefore be stored in sentence case (`Lab problem L4.4`), never `Lab Problem`.
- Print is **out of scope** — RTC builds under the mitpress profile, which loads the book's own `environments.sty` and already renders all of this correctly.
- Test commands:
  - parody: `cd /Users/picone/parody/.claude-worktrees/fleet-zephyr && uv run pytest <args>`
  - parody-web single test: `cd /Users/picone/parody-web && DJANGO_SETTINGS_MODULE=tests.settings .venv/bin/python -m django test <label>`
  - parody-web full suite: `cd /Users/picone/parody-web && .venv/bin/python runtests.py`

## Reference: the HTML the filter emits today

Captured from the real pipeline (`uv run pytest` helper `web()` in `tests/test_filter_cite_and_links.py`). Note pandoc wraps lines, so **newlines appear inside opening tags** — every regex below uses `[^>]*` (which matches `\n`) and `\s*`, never `.` without `re.S`:

```html
<div id="8y"
class="exercise numbered-environment rounded border border-green-400 shadow-md my-4 bg-white scroll-mt-20"
data-h="8y" data-env-type="exercise">
<section
class="text-lg font-semibold text-green-900 px-4 py-2 border-b border-green-400 bg-green-50 rounded-t">
<h3 class="text-lg font-semibold text-green-900">Exercise</h3>
</section>
<div class="px-4 py-3 text-sm text-gray-700">
<p>Body text.</p>
</div>
</div>
```

## File Structure

**parody** (build side, additive only)
- Modify `parody/filters/filter.lua` — `exercise(el)` at lines 495-528: keep `.lab` on the wrapper.
- Modify `parody/writers/artifact.py` — div-anchor extraction at lines 371-430: record `"lab": true`.
- Modify `tests/test_filter_cite_and_links.py` — new exercise-div tests.
- Modify `tests/test_schema_v2.py` — new lab-anchor assertions.

**parody-web** (render side)
- Modify `parody_web/numbering.py` — `_TYPE_LABELS`, the pass-1 anchor loop, the lab-section label, a new `problem_caps` dict, a new `_number_exercises()` helper called in pass 2.
- Modify `parody_web/static/parody_web/css/content.css` — `.exercise`, `.exercise.lab`, `.problem-label`, `.problem-body`.
- Modify `parody_web/tests.py` — numbering and pass-2 tests.

---

### Task 1: parody — `filter.lua` keeps `.lab` on the exercise div

**Files:**
- Modify: `parody/filters/filter.lua:495-528`
- Test: `tests/test_filter_cite_and_links.py`

**Interfaces:**
- Produces: for `::: {.exercise .lab h="ag"}`, a wrapper div whose class list ends with `lab` and which carries `data-lab="1"`. For a plain `::: {.exercise}`, output unchanged byte-for-byte.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_filter_cite_and_links.py`:

```python
# --- web: exercise divs carry lab-ness (task #499) --------------------------

# The non-lab box HTML is frozen: homepage-django styles these Tailwind class
# names for real, and tests/golden/*.json pin the markup. Only lab exercises
# gain markers.
PLAIN_EXERCISE_HTML = (
    '<div id="8y"\n'
    'class="exercise numbered-environment rounded border border-green-400'
    ' shadow-md my-4 bg-white scroll-mt-20"\n'
    'data-h="8y" data-env-type="exercise">\n'
    '<section\n'
    'class="text-lg font-semibold text-green-900 px-4 py-2 border-b'
    ' border-green-400 bg-green-50 rounded-t">\n'
    '<h3 class="text-lg font-semibold text-green-900">Exercise</h3>\n'
    '</section>\n'
    '<div class="px-4 py-3 text-sm text-gray-700">\n'
    '<p>Body text.</p>\n'
    '</div>\n'
    '</div>\n'
)


def test_plain_exercise_html_is_unchanged():
    assert web(':::: {.exercise h="8y"}\nBody text.\n::::\n') == PLAIN_EXERCISE_HTML


def test_lab_exercise_carries_lab_markers():
    out = web(':::: {.exercise .lab h="ag"}\nLab body.\n::::\n')
    # the legacy class string is preserved; "lab" is appended to it
    assert 'bg-white scroll-mt-20 lab"' in out
    assert 'data-lab="1"' in out
    assert 'data-env-type="exercise"' in out
    assert 'id="ag"' in out
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd /Users/picone/parody/.claude-worktrees/fleet-zephyr && uv run pytest tests/test_filter_cite_and_links.py -k "exercise" -v`

Expected: `test_plain_exercise_html_is_unchanged` PASSES (it pins today's behaviour), `test_lab_exercise_carries_lab_markers` FAILS on `assert 'bg-white scroll-mt-20 lab"' in out`.

- [ ] **Step 3: Implement**

In `parody/filters/filter.lua`, replace the `if FORMAT:match 'html' then` block inside `exercise(el)` (currently lines 513-524) with:

```lua
  -- Only transform for HTML
  if FORMAT:match 'html' then
    -- Lab problems (::: {.exercise .lab}) are numbered on their own per-chapter
    -- counter and labelled "Problem L4.5" by the web renderer, so the artifact
    -- has to carry the distinction. Purely additive: the legacy class string and
    -- attribute order are untouched, because homepage-django styles those
    -- Tailwind names for real and tests/golden/*.json pins the markup.
    local classes = {"exercise", "numbered-environment", "rounded", "border",
                     "border-green-400", "shadow-md", "my-4", "bg-white",
                     "scroll-mt-20"}
    local kv = {{"data-h", hash}, {"data-env-type", "exercise"}}
    if el.classes:includes('lab') then
      classes[#classes + 1] = "lab"
      kv[#kv + 1] = {"data-lab", "1"}
    end
    return pandoc.Div({
      pandoc.Div({
        pandoc.Header(3, title, { class = "text-lg font-semibold text-green-900" })
      }, { class = "px-4 py-2 border-b border-green-400 bg-green-50 rounded-t" }),
      pandoc.Div(filtered_content, { class = "px-4 py-3 text-sm text-gray-700" })
    }, pandoc.Attr(identifier, classes, kv))
  else
    return el
  end
```

An explicit `pandoc.Attr` replaces the attribute *table* so the emitted
attribute order is deterministic rather than dependent on Lua `pairs()`
ordering — which is what makes the byte-identical guarantee for non-lab
exercises real rather than incidental.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd /Users/picone/parody/.claude-worktrees/fleet-zephyr && uv run pytest tests/test_filter_cite_and_links.py -k "exercise" -v`

Expected: both PASS. `test_plain_exercise_html_is_unchanged` passing after the rewrite is the golden-parity guarantee.

- [ ] **Step 5: Run the wider filter suite for regressions**

Run: `cd /Users/picone/parody/.claude-worktrees/fleet-zephyr && uv run pytest tests/test_filter_cite_and_links.py tests/test_golden_artifacts.py -v`

Expected: all PASS or SKIP (the golden tests skip unless `~/homepage-django/teaching/notebooks-source` exists — it does not on this machine, so `skipped` is the expected result there).

- [ ] **Step 6: Commit**

```bash
cd /Users/picone/parody/.claude-worktrees/fleet-zephyr && git add parody/filters/filter.lua tests/test_filter_cite_and_links.py && git commit -m "filter: keep .lab on exercise divs (task #499)"
```

---

### Task 2: parody — artifact anchors record `lab: true`

**Files:**
- Modify: `parody/writers/artifact.py:371-430`
- Test: `tests/test_schema_v2.py`

**Interfaces:**
- Consumes: nothing from Task 1 (independent code path — Task 1 rewrites HTML, this rewrites the anchor list).
- Produces: `extract_anchor_ids(md, with_hashes=True)` returns `{"id": "ag", "type": "exercise", "level": None, "title": None, "hash": "ag", "lab": True}` for a `.exercise .lab` div. The key is **absent**, not `False`, on every other anchor.

- [ ] **Step 1: Write the failing test**

In `tests/test_schema_v2.py`, append to the `SECTION_MD` string (just before the closing `"""`, after the figure line):

```python
::: {.exercise .lab h="ag"}
Lab problem — numbered L<chapter>.<n> by the web renderer.
:::
```

Then append this test:

```python
def test_v2_extraction_flags_lab_exercises():
    # ::: {.exercise .lab} is a lab problem ("Problem L4.1"); plain .exercise is
    # a chapter problem ("Problem 4.1"). They run on separate counters, so the
    # artifact has to carry the distinction (task #499).
    anchors = {a["id"]: a for a in extract_anchor_ids(SECTION_MD, with_hashes=True)}
    assert anchors["ag"] == {
        "id": "ag", "type": "exercise", "level": None, "title": None,
        "hash": "ag", "lab": True,
    }
    # the flag is omitted (not False) elsewhere, so non-lab artifacts are
    # byte-identical to before
    assert "lab" not in anchors["ho"]
    assert "lab" not in anchors["ex:demo"]
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd /Users/picone/parody/.claude-worktrees/fleet-zephyr && uv run pytest tests/test_schema_v2.py -k lab -v`

Expected: FAIL — `anchors["ag"]` has no `"lab"` key.

- [ ] **Step 3: Implement**

In `parody/writers/artifact.py`, the `with_hashes` branch builds `div_matches` as 4-tuples. Widen them to 5-tuples carrying lab-ness.

Replace the loop body that appends to `div_matches` (currently lines 379-399) with:

```python
        div_matches = []
        for m in re.finditer(r'^:{3,}\s*\{([^}]*)\}', markdown_content,
                             flags=re.MULTILINE):
            attr_text = m.group(1)
            idm = re.search(r'#([A-Za-z0-9_:-]+)', attr_text)
            div_classes = re.findall(r'\.([A-Za-z0-9_-]+)', attr_text)
            env_class = next((c for c in div_classes if c in class_type_map), None)
            # ::: {.exercise .lab} is a lab problem: its own per-chapter counter
            # and an "L"-prefixed number ("Problem L4.1") in the renderer.
            is_lab = 'lab' in div_classes
            # infoboxes are cross-referenced by their title, not a number, so
            # carry it through to the anchor (see numbering.py).
            tm = re.search(r'title="([^"]*)"', attr_text)
            title = tm.group(1) if tm else None
            if idm and env_class:
                div_matches.append((env_class, idm.group(1),
                                    _attr_hash(attr_text), title, is_lab))
            elif env_class:
                # hash-only env (::: {.exercise h="8y"}): no explicit #id, so key
                # the anchor on its short hash. The filter renders the box with
                # id=hash, so cross-refs ([8y]{.hashref}) resolve and scroll to it.
                h = _attr_hash(attr_text)
                if h:
                    div_matches.append((env_class, h, h, title, is_lab))
    else:
        div_matches = [(m.group(1), m.group(2), None, None, False)
                       for m in re.finditer(div_pattern, markdown_content)]

    for env_class, full_id, div_hash, div_title, div_lab in div_matches:
```

Then, inside that loop, in the block that builds the anchor dict (currently lines 419-428), add the flag after the hash:

```python
        if anchor_id not in found_ids:
            anchor = {
                'id': anchor_id,
                'type': anchor_type,
                'level': None,
                'title': div_title
            }
            if div_hash:
                anchor['hash'] = div_hash
            if div_lab:
                anchor['lab'] = True
            anchors.append(anchor)
            found_ids.add(anchor_id)
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd /Users/picone/parody/.claude-worktrees/fleet-zephyr && uv run pytest tests/test_schema_v2.py -v`

Expected: all PASS — including `test_v2_extraction_captures_hashes`, whose exact-dict assertions prove no stray `lab` key leaked onto non-lab anchors.

- [ ] **Step 5: Run the full parody suite**

Run: `cd /Users/picone/parody/.claude-worktrees/fleet-zephyr && uv run pytest -q`

Expected: no failures (skips are fine).

- [ ] **Step 6: Commit**

```bash
cd /Users/picone/parody/.claude-worktrees/fleet-zephyr && git add parody/writers/artifact.py tests/test_schema_v2.py && git commit -m "artifact: flag lab exercises on their anchors (task #499)"
```

---

### Task 3: parody-web — branch, then split the problem counters

**Files:**
- Modify: `parody_web/numbering.py:349-354` (`_TYPE_LABELS`), `:577` (caps dicts), `:690-705` (the anchor loop)
- Test: `parody_web/tests.py`

**Interfaces:**
- Consumes: `anchor["lab"] is True` from Task 2.
- Produces:
  - `targets[id]["label"]` == `"Problem 1.2"` (non-lab) or `"Lab problem L1.2"` (lab)
  - `problem_caps: {section_slug: {anchor_id: (heading_label, is_lab)}}` where `heading_label` is `"Problem 1.2"` / `"Problem L1.2"` and `is_lab` is a bool — both consumed by Task 5.

- [ ] **Step 1: Create the branch**

```bash
cd /Users/picone/parody-web && git checkout -b problem-numbering
```

- [ ] **Step 2: Write the failing test**

Append to `parody_web/tests.py` inside `class CrossRefResolutionTests` (line 88), after `test_example_gets_numbered_label_injected` (line 249):

```python
    def test_problems_and_lab_problems_use_separate_counters(self):
        # ::: {.exercise} → "Problem C.n"; ::: {.exercise .lab} → "Problem LC.k"
        # on its own counter. Headings say "Problem" for both (the book's
        # exercise-name); cross-refs say "problem" / "lab problem" (its
        # crefnames). Task #499.
        data = {"chapters": [{"title": "C", "slug": "c", "hash": "c1",
            "sections": [{"title": "S", "slug": "s", "anchors": [
                {"id": "p1", "type": "exercise", "hash": "p1"},
                {"id": "l1", "type": "exercise", "hash": "l1", "lab": True},
                {"id": "p2", "type": "exercise", "hash": "p2"},
                {"id": "l2", "type": "exercise", "hash": "l2", "lab": True},
            ], "html": ""}]}]}
        targets = number_artifact(data)
        self.assertEqual(targets["p1"]["label"], "Problem 1.1")
        self.assertEqual(targets["p2"]["label"], "Problem 1.2")
        self.assertEqual(targets["l1"]["label"], "Lab problem L1.1")
        self.assertEqual(targets["l2"]["label"], "Lab problem L1.2")

    def test_problem_crossrefs_follow_reference_site_case(self):
        data = {"chapters": [{"title": "C", "slug": "c", "hash": "c1",
            "sections": [{"title": "S", "slug": "s", "anchors": [
                {"id": "p1", "type": "exercise", "hash": "p1"},
                {"id": "l1", "type": "exercise", "hash": "l1", "lab": True},
            ], "html": '<p><span class="hashref">p1</span> '
                       '<span class="Hashref">l1</span></p>'}]}]}
        number_artifact(data)
        html = data["chapters"][0]["sections"][0]["html"]
        self.assertIn('>problem 1.1</a>', html)
        self.assertIn('>Lab problem L1.1</a>', html)
```

- [ ] **Step 3: Run the tests to verify they fail**

Run:
```bash
cd /Users/picone/parody-web && DJANGO_SETTINGS_MODULE=tests.settings .venv/bin/python -m django test parody_web.tests -k problem
```

Expected: FAIL — labels come back as `"Exercise 1.1"`, `"Exercise 1.2"`, `"Exercise 1.3"`, `"Exercise 1.4"` (one mixed counter).

- [ ] **Step 4: Implement**

**4a.** In `parody_web/numbering.py`, update the `_TYPE_LABELS` comment and value (line 349-354). The `exercise` key must stay present — the anchor loop uses `t not in _TYPE_LABELS` as its skip guard — but exercises take a dedicated branch below, so annotate it:

```python
# anchor type -> cross-reference label word (per-chapter numbered: "Table 3.1")
# "exercise" is listed so the loop's membership guard admits it, but its label
# is built in the dedicated branch below (lab and non-lab problems differ).
_TYPE_LABELS = {
    "figure": "Figure", "table": "Table", "equation": "Equation",
    "exercise": "Problem", "example": "Example", "theorem": "Theorem",
    "definition": "Definition", "listing": "Listing", "algorithm": "Algorithm",
}
```

**4b.** Next to `example_caps` (line 577) add:

```python
    problem_caps = {}     # per-section: exercise div-id -> (heading label, is_lab)
```

**4c.** In the non-heading anchor loop, immediately after the `if t == "heading" or t not in _TYPE_LABELS: continue` guard (line 690-691) and before the sub-panel `continue` (line 692), insert the exercise branch:

```python
                if t == "exercise":
                    # Problems and lab problems run on separate per-chapter
                    # counters, exactly as the book does: `exercise` is
                    # `within = chapter` ("Problem 3.2") and `lab` counts
                    # L\thechapter.\arabic{labexercise} ("Problem L4.1").
                    # Headings read "Problem" for both (exercise-name = Problem);
                    # cross-refs read "problem" / "lab problem" (the crefnames).
                    is_lab = bool(a.get("lab"))
                    key = "labexercise" if is_lab else "exercise"
                    type_counters[key] = type_counters.get(key, 0) + 1
                    num = (f"L{cnum}.{type_counters[key]}" if is_lab
                           else f"{cnum}.{type_counters[key]}")
                    word = "Lab problem" if is_lab else "Problem"
                    entry = {"label": f"{word} {num}",
                             "url": f"{url}#{a.get('id', '')}"}
                    if a.get("id"):
                        targets[a["id"]] = entry
                    if a.get("hash"):
                        targets[a["hash"]] = entry
                    if a.get("id"):
                        # pass 2 injects this as the box's run-in heading and
                        # needs is_lab to set the wrapper's class
                        problem_caps.setdefault(sec["slug"], {})[a["id"]] = \
                            (f"Problem {num}", is_lab)
                    continue
```

- [ ] **Step 5: Run the tests to verify they pass**

Run:
```bash
cd /Users/picone/parody-web && DJANGO_SETTINGS_MODULE=tests.settings .venv/bin/python -m django test parody_web.tests -k problem
```

Expected: both PASS.

- [ ] **Step 6: Commit**

```bash
cd /Users/picone/parody-web && git add parody_web/numbering.py parody_web/tests.py && git commit -m "numbering: problems and lab problems on separate counters (task #499)"
```

---

### Task 4: parody-web — a lab section's number is its chapter number

**Files:**
- Modify: `parody_web/numbering.py:584` (`lab_n = 0`), `:605-611` (the `elif kind == "lab"` branch)
- Test: `parody_web/tests.py`

**Interfaces:**
- Consumes: `cnum` from `_chapter_label`, already in scope.
- Produces: `sec["number"] == f"Lab exercise {cnum}"` for lab sections; the running `lab_n` variable is gone.

- [ ] **Step 1: Write the failing test**

Append to `class CrossRefResolutionTests` in `parody_web/tests.py`:

```python
    def test_lab_section_number_is_its_chapter_number(self):
        # The book titles lab sections "Lab 0" … "Lab 8" — the lab number IS the
        # chapter number, so its problems can read "Problem L4.1". parody-web
        # used a running 1-based count, which is off by one for any book with
        # chapter_start: 0 (RTC). Task #499.
        def lab_section():
            return {"title": "Lab", "slug": "lab", "hash": "lb", "anchors": [],
                    "html": '<h1 data-h="lb" class="lab">Lab</h1>'}
        data = {"chapter_start": 0, "chapters": [
            {"title": "Zero", "slug": "zero", "hash": "c0",
             "sections": [lab_section()]},
            {"title": "One", "slug": "one", "hash": "c1",
             "sections": [lab_section()]},
        ]}
        number_artifact(data)
        self.assertEqual(data["chapters"][0]["sections"][0]["number"],
                         "Lab exercise 0")
        self.assertEqual(data["chapters"][1]["sections"][0]["number"],
                         "Lab exercise 1")
```

- [ ] **Step 2: Run the test to verify it fails**

Run:
```bash
cd /Users/picone/parody-web && DJANGO_SETTINGS_MODULE=tests.settings .venv/bin/python -m django test parody_web.tests.CrossRefResolutionTests.test_lab_section_number_is_its_chapter_number
```

Expected: FAIL — `"Lab exercise 1" != "Lab exercise 0"`.

- [ ] **Step 3: Implement**

Delete the `lab_n = 0` line (line 584). Replace the `elif kind == "lab":` branch (lines 605-611) with:

```python
            elif kind == "lab":
                secnum = None
                # The lab number is the CHAPTER number: the book titles these
                # sections "Lab 0" … "Lab 8", and their problems are numbered
                # L<chapter>.<n>. Sentence case ("Lab exercise N") so a cross-ref
                # recases only the first letter — "Lab exercise 6" /
                # "lab exercise 6", never the mid-phrase "lab Exercise 6".
                # (_recase_label toggles label[:1].)
                sec["number"] = f"Lab exercise {cnum}"
```

- [ ] **Step 4: Run the test to verify it passes**

Run:
```bash
cd /Users/picone/parody-web && DJANGO_SETTINGS_MODULE=tests.settings .venv/bin/python -m django test parody_web.tests -k lab
```

Expected: PASS. (No pre-existing test asserts a lab section number — `grep -rn "Lab exercise" parody_web/` finds only `numbering.py` — so nothing else needs updating.)

- [ ] **Step 5: Commit**

```bash
cd /Users/picone/parody-web && git add parody_web/numbering.py parody_web/tests.py && git commit -m "numbering: a lab section's number is its chapter number (task #499)"
```

---

### Task 5: parody-web — pass 2 injects the label and strips the legacy chrome

**Files:**
- Modify: `parody_web/numbering.py` (new module-level helper near `_number_subeq_div`; call site next to the `example_caps` injection at line 876-881)
- Test: `parody_web/tests.py`

**Interfaces:**
- Consumes: `problem_caps` from Task 3; `data-lab="1"` on the div from Task 1.
- Produces: rendered `<div id="8y" class="exercise" data-h="8y" data-env-type="exercise"><div class="problem-label">Problem 1.1</div><div class="problem-body">…`.

- [ ] **Step 1: Write the failing test**

Append to `class CrossRefResolutionTests` in `parody_web/tests.py`. The `html` here is verbatim filter output (pandoc wraps lines, so the newlines inside the tags are real):

```python
    EXERCISE_HTML = (
        '<div id="{id}"\n'
        'class="exercise numbered-environment rounded border border-green-400'
        ' shadow-md my-4 bg-white scroll-mt-20{lab}"\n'
        'data-h="{id}" data-env-type="exercise"{labattr}>\n'
        '<section\n'
        'class="text-lg font-semibold text-green-900 px-4 py-2 border-b'
        ' border-green-400 bg-green-50 rounded-t">\n'
        '<h3 class="text-lg font-semibold text-green-900">Exercise</h3>\n'
        '</section>\n'
        '<div class="px-4 py-3 text-sm text-gray-700">\n'
        '<p>Body of {id}.</p>\n'
        '</div>\n'
        '</div>\n'
    )

    def test_problem_label_replaces_legacy_exercise_chrome(self):
        # The filter's box is Tailwind markup for homepage-django; the book site
        # renders a run-in "Problem N.n" heading instead, like print. Task #499.
        html = (self.EXERCISE_HTML.format(id="p1", lab="", labattr="")
                + self.EXERCISE_HTML.format(id="l1", lab=" lab",
                                            labattr=' data-lab="1"'))
        data = {"chapters": [{"title": "C", "slug": "c", "hash": "c1",
            "sections": [{"title": "S", "slug": "s", "anchors": [
                {"id": "p1", "type": "exercise", "hash": "p1"},
                {"id": "l1", "type": "exercise", "hash": "l1", "lab": True},
            ], "html": html}]}]}
        number_artifact(data)
        out = data["chapters"][0]["sections"][0]["html"]
        # dead Tailwind chrome gone, semantic classes in
        self.assertNotIn("border-green-400", out)
        self.assertNotIn("text-gray-700", out)
        self.assertNotIn("<h3", out)
        self.assertIn('<div id="p1" class="exercise" data-h="p1" '
                      'data-env-type="exercise">'
                      '<div class="problem-label">Problem 1.1</div>', out)
        self.assertIn('class="exercise lab"', out)
        self.assertIn('<div class="problem-label">Problem L1.1</div>', out)
        self.assertEqual(out.count('class="problem-body"'), 2)
        # the bodies survive
        self.assertIn("<p>Body of p1.</p>", out)
        self.assertIn("<p>Body of l1.</p>", out)
```

- [ ] **Step 2: Run the test to verify it fails**

Run:
```bash
cd /Users/picone/parody-web && DJANGO_SETTINGS_MODULE=tests.settings .venv/bin/python -m django test parody_web.tests -k problem_label
```

Expected: FAIL on `assertNotIn("border-green-400", out)` — nothing rewrites the box yet.

- [ ] **Step 3: Implement the helper**

Add near the other module-level helpers in `parody_web/numbering.py` (put it just above `def number_artifact`):

```python
# The exercise box comes from parody's filter.lua as Tailwind markup, because
# homepage-django renders those class names for real. The book site wants what
# print gives: a run-in "Problem N.n" heading over the statement. So rewrite the
# box here — normalize the wrapper's classes, swap the <h3>Exercise</h3> header
# block for a .problem-label, and rename the Tailwind body wrapper. pandoc wraps
# long tags across lines, so every part below matches newlines too.
def _rewrite_exercise_box(html, eid, label, is_lab):
    """Rewrite one exercise div (matched by `eid`) into its web presentation."""
    pat = re.compile(
        r'(<div\b(?=[^>]*\bdata-env-type="exercise")[^>]*\bid="'
        + re.escape(eid) + r'"[^>]*>)'
        r'(?:\s*<section\b[^>]*>\s*<h3\b[^>]*>[^<]*</h3>\s*</section>)?'
        r'(\s*<div\b[^>]*\bclass="px-4 py-3 text-sm text-gray-700"[^>]*>)?')

    def rep(mo):
        cls = "exercise lab" if is_lab else "exercise"
        open_tag = re.sub(r'\bclass="[^"]*"', f'class="{cls}"', mo.group(1),
                          count=1)
        # collapse the newlines pandoc wrapped into the opening tag
        open_tag = re.sub(r'\s+', " ", open_tag)
        body = '<div class="problem-body">' if mo.group(2) else ""
        return (open_tag + f'<div class="problem-label">{label}</div>' + body)

    return pat.sub(rep, html, count=1)
```

- [ ] **Step 4: Wire it into pass 2**

In `number_artifact`'s pass 2, right after the `example_caps` injection loop (line 876-881), add:

```python
            for eid, (label, is_lab) in problem_caps.get(sec["slug"], {}).items():
                html = _rewrite_exercise_box(html, eid, label, is_lab)
```

`is_lab` comes from the per-anchor flag recorded in pass 1 — do **not** try to
sniff it out of the section's html, because a section holding both kinds would
then mark them all the same.

- [ ] **Step 5: Run the test to verify it passes**

Run:
```bash
cd /Users/picone/parody-web && DJANGO_SETTINGS_MODULE=tests.settings .venv/bin/python -m django test parody_web.tests -k problem
```

Expected: all PASS (Tasks 3 and 5 tests both).

- [ ] **Step 6: Run the full parody-web suite**

Run: `cd /Users/picone/parody-web && .venv/bin/python runtests.py`

Expected: OK, no failures.

- [ ] **Step 7: Commit**

```bash
cd /Users/picone/parody-web && git add parody_web/numbering.py parody_web/tests.py && git commit -m "numbering: render problems as run-in 'Problem N.n' headings (task #499)"
```

---

### Task 6: parody-web — style the problem block

**Files:**
- Modify: `parody_web/static/parody_web/css/content.css` (add after the `.example` / `.example-label` rules, which end around line 155)

**Interfaces:**
- Consumes: `.exercise`, `.exercise.lab`, `.problem-label`, `.problem-body` from Task 5.

- [ ] **Step 1: Add the rules**

Append after the `.example > .example-solution` rule:

```css
/* problems (::: {.exercise}) and lab problems (::: {.exercise .lab}). The book
   sets these as a run-in subsubsection — a bold "Problem 3.2" / "Problem L4.1"
   heading over the statement, no frame — and pages that are nothing but
   problems read far better that way than as a stack of boxes. numbering.py
   injects the label and strips the filter's Tailwind chrome (task #499).
   `.col [id]` already gives the wrapper its sticky-masthead scroll offset. */
.exercise { margin: 1.6rem 0; }
.problem-label { font-family: var(--font-display); font-weight: 700;
    color: var(--accent); margin-bottom: .35rem; }
.problem-body > :first-child { margin-top: 0; }
.problem-body > :last-child { margin-bottom: 0; }
```

- [ ] **Step 2: Confirm the stylesheet is shipped by the wheel**

parody-web ships static assets only if the directory is listed in
`[tool.setuptools.package-data]`; a stylesheet in an unlisted subdir is
silently dropped from the wheel and the deploy ships a site with no CSS.
`content.css` is an existing file in an existing directory, so no change is
needed — verify and move on:

Run: `cd /Users/picone/parody-web && grep -A5 'package-data' pyproject.toml`

Expected: a pattern that already covers `parody_web/static/parody_web/css/*.css`.

- [ ] **Step 3: Run the full suite**

Run: `cd /Users/picone/parody-web && .venv/bin/python runtests.py`

Expected: OK.

- [ ] **Step 4: Commit**

```bash
cd /Users/picone/parody-web && git add parody_web/static/parody_web/css/content.css && git commit -m "css: style problems as run-in headings (task #499)"
```

---

### Task 7: End-to-end check against the real book

**Files:** none modified — this is a verification task.

- [ ] **Step 1: Build the RTC artifact with the local parody**

```bash
cd /Users/picone/real-time-computing-parody && uv run --project /Users/picone/parody/.claude-worktrees/fleet-zephyr parody build --online-only
```

Expected: build completes. If the CLI flags differ, run `uv run --project /Users/picone/parody/.claude-worktrees/fleet-zephyr parody build --help` and use the artifact-target invocation.

- [ ] **Step 2: Confirm lab-ness reached the artifact**

```bash
python3 -c "import json,glob,sys; d=json.load(open(sorted(glob.glob('/Users/picone/real-time-computing-parody/build/**/*.json', recursive=True))[0])); a=[x for c in d['chapters'] for s in c['sections'] for x in s.get('anchors',[]) if x.get('type')=='exercise']; print('exercises', len(a), 'lab', sum(1 for x in a if x.get('lab')))"
```

Expected: roughly 101 exercises, 42 of them flagged `lab` (the eight lab sections hold 4+5+3+9+8+3+6+4 lab problems).

- [ ] **Step 3: Number it with the local parody-web and spot-check**

```bash
cd /Users/picone/parody-web && .venv/bin/python -c "
import json, glob, sys
sys.path.insert(0, '.')
import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'tests.settings')
django.setup()
from parody_web.numbering import number_artifact
d = json.load(open(sorted(glob.glob('/Users/picone/real-time-computing-parody/build/**/*.json', recursive=True))[0]))
t = number_artifact(d)
labs = sorted({v['label'] for v in t.values() if v['label'].startswith('Lab problem')})
probs = sorted({v['label'] for v in t.values() if v['label'].startswith('Problem')})
print(labs[:4], labs[-2:])
print(probs[:4], probs[-2:])
"
```

Expected: lab labels of the form `Lab problem L1.1` … `Lab problem L8.3` — **no `L0.x`**, because chapter 0 has a lab section but no lab problems. Problem labels start at `Problem 0.1`. Compare against the original: `pdftotext ~/rtcbook/real-time-computing/real-time-computing-0.pdf - | grep -o "Problem L\?[0-9]*\.[0-9]*" | sort -uV`.

- [ ] **Step 4: Report the comparison**

Write up any label that differs from the original PDF's, with the chapter and problem it belongs to. Differences caused by version-conditional content (the PDF is a specific T/D variant build) are expected in the *counts*; the *scheme* must match.

---

### Task 8: Version bumps and release prep

**Files:**
- Modify: `pyproject.toml` (both repos)

- [ ] **Step 1: Bump parody**

`version = "0.28.1"` → `"0.28.2"` in `/Users/picone/parody/.claude-worktrees/fleet-zephyr/pyproject.toml`.

- [ ] **Step 2: Bump parody-web**

`version = "0.31.0"` → `"0.32.0"` in `/Users/picone/parody-web/pyproject.toml` (minor: new rendering behaviour).

- [ ] **Step 3: Run both suites one final time**

```bash
cd /Users/picone/parody/.claude-worktrees/fleet-zephyr && uv run pytest -q
```
```bash
cd /Users/picone/parody-web && .venv/bin/python runtests.py
```

Expected: both green.

- [ ] **Step 4: Commit both**

```bash
cd /Users/picone/parody/.claude-worktrees/fleet-zephyr && git add pyproject.toml && git commit -m "0.28.2: flag lab exercises through to the artifact (task #499)"
```
```bash
cd /Users/picone/parody-web && git add pyproject.toml && git commit -m "0.32.0: number problems and lab problems (task #499)"
```

- [ ] **Step 5: Stop and hand back**

Publishing to PyPI and running the six-step rtcbook.org deploy chain is
outward-facing and needs explicit go-ahead. Report that both repos are green
and version-bumped, and ask before publishing or deploying.
