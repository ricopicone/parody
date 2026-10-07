"""Cross-references to and inside boxed environments must resolve in print.

print.lua runs BEFORE pandoc-crossref and turns every definition, theorem,
example and exercise into raw LaTeX, so pandoc-crossref never sees inside one.
Two failures followed, both printed into the PDF with no error:

- [@def:screw-axis] (also thm:, exa:, exe:, …) went to \\autocite. biblatex had
  no such key and printed the raw id: "[def:screw-axis]". The robotics notes
  carried 81 of them.
- `$$…$$ {#eq:foo}` inside a box kept its attribute as literal text,
  "{#eq:foo}". The equation had no number, and every reference to it read "??".
"""

import re
import subprocess
from pathlib import Path

import pypandoc
import pytest

from parody.writers.latex import build_pdf, have_tool

FILTER = Path(__file__).parent.parent / "parody" / "filters" / "print.lua"
PROFILES = Path(__file__).parent.parent / "parody" / "profiles"
PANDOC_FROM = "markdown-markdown_in_html_blocks+raw_tex+tex_math_dollars"


def render(md):
    return pypandoc.convert_text(
        md, "latex", format=PANDOC_FROM,
        extra_args=[f"--lua-filter={FILTER}", "--wrap=none"])


@pytest.mark.parametrize("ref, want", [
    ("[@def:screw-axis]", r"\cref{def:screw-axis}"),
    ("[@thm:chasles]", r"\cref{thm:chasles}"),
    ("[@exa:door]", r"\cref{exa:door}"),
    ("[@exe:warmup]", r"\cref{exe:warmup}"),
    ("[@lem:a]", r"\cref{lem:a}"),
    ("[@Def:screw-axis]", r"\Cref{def:screw-axis}"),
    ("[@def:a; @thm:b]", r"\cref{def:a,thm:b}"),
])
def test_box_refs_become_cref(ref, want):
    out = render(f"See {ref}.\n")
    assert want in out, out
    assert "autocite" not in out


@pytest.mark.parametrize("key", ["doe2020", "book:pinker", "wiki:screw"])
def test_citation_keys_stay_citations(key):
    # bibliography keys carry colons too: "has a prefix" is not "is a ref"
    out = render(f"See [@{key}].\n")
    assert f"autocite[]{{{key}}}" in out, out


def test_box_refs_inside_a_box_become_cref():
    out = render('::: {.infobox title="Note"}\nSee [@def:x] and [@exa:y].\n:::\n')
    assert r"\cref{def:x}" in out and r"\cref{exa:y}" in out, out


@pytest.mark.parametrize("env", ["definition", "theorem", "example", "infobox"])
def test_an_equation_label_inside_a_box_is_a_label(env):
    md = (f'::: {{.{env} #{env[:3]}:a title="T"}}\nText.\n\n'
          "$$ x = 1 $$ {#eq:inside}\n:::\n")
    out = render(md)
    assert r"\label{eq:inside}" in out, out
    assert "#eq:inside" not in out
    assert r"\begin{equation}" in out


def test_a_clozed_equation_in_a_box_is_labelled_once():
    md = ('::: {.theorem #thm:a title="T"}\n::: cloze\n'
          "$$ x = 1 $$ {#eq:clozed}\n:::\n:::\n")
    out = render(md)
    assert out.count("eq:clozed") == 1, out
    assert r"\begin{clozeequation}{eq:clozed}" in out


def test_a_top_level_equation_is_left_to_pandoc_crossref():
    out = render("$$ x = 1 $$ {#eq:top}\n")
    assert r"\begin{equation}" not in out


@pytest.mark.parametrize("sty", [
    "memoir/parody-environments.sty", "print/parody-print.sty"])
def test_boxes_label_with_their_own_cleveref_type(sty):
    # one shared counter, so without a typed label every box is a "result"
    text = (PROFILES / sty).read_text()
    for env in ("definition", "theorem", "lemma", "corollary", "proposition"):
        assert f"\\label[{env}]{{#2}}" in text
        assert f"\\crefname{{{env}}}{{{env}}}" in text


PARODY_YAML = """\
title: Xref Test
slug: xref-test
authors: [Tester]
chapters:
  - slug: one
    title: Chapter One
    sections: [a-section]
"""

SECTION_MD = """\
---
title: A Section
slug: a-section
---

# A section {#sec-a}

::: {.definition #def:screw-axis title="Screw axis"}
A screw axis is a line.

$$ S = (\\omega, v) $$ {#eq:screw-axis}
:::

::: {.theorem #thm:chasles title="Chasles"}
Every motion is a screw motion.
:::

::: {.example #exa:door}
A door is a revolute screw.
:::

::: {.exercise #exe:warmup title="Warmup"}
Compute $1+1$.
:::

See [@def:screw-axis], [@thm:chasles], [@exa:door], [@exe:warmup] and
[@eq:screw-axis].
"""


@pytest.mark.pdf
@pytest.mark.skipif(not (have_tool("latexmk") and have_tool("lualatex")),
                    reason="TeX (latexmk + lualatex) not available")
def test_no_raw_ids_reach_the_pdf(tmp_path):
    project = tmp_path / "xref-test"
    (project / "chapters" / "one").mkdir(parents=True)
    (project / "parody.yaml").write_text(PARODY_YAML)
    (project / "chapters" / "one" / "a-section.md").write_text(SECTION_MD)
    pdf = build_pdf(project)
    text = subprocess.run(["pdftotext", str(pdf), "-"], capture_output=True,
                          text=True, check=True).stdout
    text = " ".join(text.split())
    assert not re.search(r"\[(def|thm|exa|exe|lem|cor|prp):", text), text
    assert "{#eq:" not in text and "??" not in text, text
    assert ("See definition 1.1, theorem 1.2, example 1.1, problem 1.1 and "
            "equation (1.1)") in text, text


def test_a_captionless_fig_id_image_is_a_labelled_float(tmp_path, monkeypatch):
    # ![](src){#fig:x} with no class used to print a bare \includegraphics,
    # so every ref to it read "??" (the robotics intro's block diagram)
    out = render("![](diagram.png){#fig:block}\n")
    assert r"\figcaption[]{fig:block}" in out, out


def test_web_keeps_the_id_on_a_captionless_fig_id_image():
    out = pypandoc.convert_text(
        "![](notebooks/b/diagram.png){#fig:block}\n", "html", format=PANDOC_FROM,
        extra_args=[f"--lua-filter={FILTER.parent / 'filter.lua'}"])
    assert 'id="fig:block"' in out, out


@pytest.mark.parametrize("md", [
    # an image with alt text inline in a footnote, and a row of panels
    "Text.[^n]\n\n[^n]: A car. ![A car](car.png){#fig:car}\n",
    "![left](a.png){#fig:a} ![right](b.png){#fig:b}\n",
])
def test_an_image_with_alt_text_is_not_promoted(md):
    out = render(md)
    assert r"\figcaption" not in out, out
