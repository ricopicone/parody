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
    assert "\\usepackage{parody-print}" in main
    assert "\\input{sections/one/a-section.tex}" in main
    assert "\\addbibresource{book.bib}" in main
    section = (build_dir / "sections" / "one" / "a-section.tex").read_text()
    assert "\\begin{exercise}[ID=exe:warmup,hash=exe:warmup]" in section
    assert "\\begin{definition}{Thing}{def:thing}" in section


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
