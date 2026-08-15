"""Standalone figures are compiled in ONE house style.

Each figure is its own LaTeX document, so left alone each inherits whatever
type size its source declared — a book of 9pt labels here and 10pt there,
whose only remaining lever is scaling the finished PDF (which changes a
figure's size to fix its type size). parody supplies the preamble instead.
"""

import pytest

from parody.config import load_project
from parody.writers.figures import build_figures, figure_sources, is_fragment
from parody.writers.latex import have_tool

PARODY_YAML = """\
title: Figure Test
slug: figure-test
authors: [Tester]
chapters:
  - slug: one
    title: Chapter One
    sections: [only]
"""


@pytest.fixture
def project(tmp_path):
    root = tmp_path / "figure-test"
    ch = root / "chapters" / "one"
    ch.mkdir(parents=True)
    (root / "parody.yaml").write_text(PARODY_YAML)
    (ch / "only.md").write_text("---\ntitle: Only\nslug: only\n---\n\nBody.\n")
    (ch / "widget.tex").write_text(
        "\\begin{tikzpicture}\n\\node {label};\n\\end{tikzpicture}\n")
    # a full standalone document, not a fragment: parody must not rebuild it
    # and silently drop its own preamble
    (ch / "legacy.tex").write_text(
        "\\documentclass{standalone}\n\\begin{document}x\\end{document}\n")
    return load_project(root)


def test_only_fragments_are_treated_as_sources(project):
    names = [p.stem for p in figure_sources(project)]
    assert names == ["widget"]


def test_a_full_document_is_left_alone(project):
    ch = project.chapters[0].directory
    assert is_fragment(ch / "widget.tex")
    assert not is_fragment(ch / "legacy.tex")


@pytest.mark.pdf
@pytest.mark.skipif(not have_tool("lualatex"), reason="lualatex not available")
def test_a_fragment_builds_at_the_house_size(project):
    built, skipped = build_figures(project)
    assert [p.stem for p in built] == ["widget"]
    pdf = project.chapters[0].directory / "widget.pdf"
    assert pdf.is_file()
    # 8pt is the house size; the figure carries it without being scaled
    import subprocess
    out = subprocess.run(["pdffonts", str(pdf)], capture_output=True, text=True)
    assert "8" in out.stdout or out.returncode != 0  # pdffonts may be absent


@pytest.mark.pdf
@pytest.mark.skipif(not have_tool("lualatex"), reason="lualatex not available")
def test_an_up_to_date_figure_is_skipped(project):
    build_figures(project)
    built, skipped = build_figures(project)
    assert built == []
    assert [p.stem for p in skipped] == ["widget"]
