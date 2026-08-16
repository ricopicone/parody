"""Phase 3 end-to-end: tiny content repo → lualatex PDF.

Requires a TeX installation (latexmk + lualatex + biber); skips otherwise.
"""


import pytest

from parody.writers.latex import build_pdf, have_tool

SECTION_MD = """\
---
title: A Section
slug: a-section
---

# A Section {#sec-a shortid="sec:a"}

Body text with a [keyword]{.keyword}, math $x^2$, and a citation
[@doe2020]. See [sec:a]{.hashref}.

::: {.definition #def:thing title="Thing"}
A thing is a thing.
:::

::: {.infobox #box:note title="A Note"}
Worth noticing.
:::

::: {.example #ex:one}
An example of a thing.
:::

::: {.exercise #exe:warmup title="Warmup"}
Compute $1+1$.

::: {.exercise-solution}
It is $2$.
:::

:::

::: {.listing #lst:py caption="A snippet"}
```python
print("ok")
```
:::

| a | b |
|---|---|
| 1 | 2 |

: Tiny table {#tbl:tiny}
"""

BIB = """\
@book{doe2020, author={Doe, Jane}, title={A Book}, year={2020},
publisher={Pub}}
"""

PARODY_YAML = """\
title: PDF Smoke Test
slug: pdf-smoke
authors: [Tester]
chapters:
  - slug: one
    title: Chapter One
    sections: [a-section]
"""


@pytest.fixture
def tiny_project(tmp_path):
    project = tmp_path / "pdf-smoke"
    (project / "chapters" / "one").mkdir(parents=True)
    (project / "parody.yaml").write_text(PARODY_YAML)
    (project / "chapters" / "one" / "a-section.md").write_text(SECTION_MD)
    (project / "book.bib").write_text(BIB)
    return project


needs_tex = pytest.mark.skipif(
    not (have_tool("latexmk") and have_tool("lualatex")),
    reason="TeX (latexmk + lualatex) not available",
)


def test_latex_sources_generated_without_tex(tiny_project, monkeypatch):
    # Even without TeX, the writer must produce the .tex tree.
    monkeypatch.setattr("parody.writers.latex.shutil.which", lambda *a, **k: None)
    result = build_pdf(tiny_project)
    assert result is None
    build_dir = tiny_project / "build" / "print"
    main = (build_dir / "main.tex").read_text()
    # default profile is now memoir
    assert "\\documentclass[11pt]{parody-memoir}" in main
    assert "\\usepackage{parody-environments}" in main
    assert "\\input{sections/one/a-section.tex}" in main
    assert "\\addbibresource{book.bib}" in main
    section = (build_dir / "sections" / "one" / "a-section.tex").read_text()
    assert "\\begin{exercise}[ID=exe:warmup,hash=exe:warmup]" in section
    assert "\\begin{definition}{Thing}{def:thing}" in section
    # default chapter numbering (start 1): no counter seed emitted
    assert "\\setcounter{chapter}" not in main


def test_generic_print_profile_still_selectable(tiny_project, monkeypatch):
    # The portable stock-book profile remains available via --profile print.
    monkeypatch.setattr("parody.writers.latex.shutil.which", lambda *a, **k: None)
    build_pdf(tiny_project, profile_dir="print")
    main = (tiny_project / "build" / "print" / "main.tex").read_text()
    assert "\\documentclass[11pt]{book}" in main
    assert "\\usepackage{parody-print}" in main


def test_chapter_start_seeds_chapter_counter(tiny_project, monkeypatch):
    # chapter_start: 0 → seed the LaTeX chapter counter to -1 so the first
    # \chapter prints "0". The seed precedes the first section input.
    monkeypatch.setattr("parody.writers.latex.shutil.which", lambda *a, **k: None)
    meta = tiny_project / "parody.yaml"
    meta.write_text(meta.read_text() + "chapter_start: 0\n")
    build_pdf(tiny_project)
    main = (tiny_project / "build" / "print" / "main.tex").read_text()
    assert "\\setcounter{chapter}{-1}" in main
    assert main.index("\\setcounter{chapter}{-1}") < main.index(
        "\\input{sections/one/a-section.tex}")


CODE_IN_EXERCISE_MD = """\
---
title: Code Exercise
slug: code-exercise
---

# Code Exercise {#sec-ce}

::: {.exercise #exe:code title="Code"}
Run this:

``` python
import numpy as np
x = 1
```

::: {.exercise-solution}
``` python
y = 2
```
:::

:::
"""


def test_verbatim_inside_exercise_is_externalized(tiny_project, monkeypatch):
    # xsim re-tokenizes exercise bodies, which kills minted's verbatim
    # scanning; the writer must move such blocks to \input'd side files
    # (the ancestor meta-book's own pattern).
    monkeypatch.setattr("parody.writers.latex.shutil.which", lambda *a, **k: None)
    (tiny_project / "chapters" / "one" / "code-exercise.md").write_text(
        CODE_IN_EXERCISE_MD)
    import yaml
    cfg_path = tiny_project / "parody.yaml"
    cfg = yaml.safe_load(cfg_path.read_text())
    cfg["chapters"][0]["sections"].append("code-exercise")
    cfg_path.write_text(yaml.dump(cfg))
    build_pdf(tiny_project)
    sec_dir = tiny_project / "build" / "print" / "sections" / "one"
    tex = (sec_dir / "code-exercise.tex").read_text()
    assert "\\begin{minted}" not in tex
    assert "\\input{sections/one/code-exercise-verb1.tex}" in tex
    assert "\\input{sections/one/code-exercise-verb2.tex}" in tex
    side = (sec_dir / "code-exercise-verb1.tex").read_text()
    assert "\\begin{minted}" in side and "import numpy as np" in side
    # code outside exercises is untouched (the fixture's listing div)
    a_section = (sec_dir / "a-section.tex").read_text()
    assert "\\begin{listingsboxfloat}" in a_section
    assert "\\input{sections/one/a-section-verb" not in a_section


def test_relative_project_dir(tiny_project, monkeypatch):
    # `parody pdf .` — pandoc runs with cwd at each section dir, so the
    # writer must resolve the project path up front.
    monkeypatch.setattr("parody.writers.latex.shutil.which", lambda *a, **k: None)
    monkeypatch.chdir(tiny_project)
    result = build_pdf(".")
    assert result is None
    section = (tiny_project / "build" / "print" / "sections" / "one"
               / "a-section.tex").read_text()
    assert "\\begin{exercise}" in section


@pytest.mark.pdf
@needs_tex
def test_full_pdf_compiles(tiny_project):
    pdf = build_pdf(tiny_project)
    assert pdf is not None and pdf.exists() and pdf.stat().st_size > 10_000


@pytest.mark.pdf
@needs_tex
def test_solutions_manual_compiles(tiny_project):
    pdf = build_pdf(tiny_project, solutions=True)
    assert pdf is not None and pdf.exists()
    assert pdf.name.endswith("-solutions.pdf")
