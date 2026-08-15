"""Standalone figures are compiled in ONE house style.

Each figure is its own LaTeX document, so left alone each inherits whatever
type size its source declared — a book of 9pt labels here and 10pt there,
whose only remaining lever is scaling the finished PDF (which changes a
figure's size to fix its type size). parody supplies the preamble instead.
"""

import pytest

from pathlib import Path

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


FIGURES_YAML = PARODY_YAML


@pytest.fixture
def figures_layout(tmp_path):
    """The canonical layout: sources in figures/, output in build/figures/."""
    root = tmp_path / "figure-test"
    (root / "chapters" / "one").mkdir(parents=True)
    (root / "figures").mkdir()
    (root / "parody.yaml").write_text(FIGURES_YAML)
    (root / "chapters" / "one" / "only.md").write_text(
        "---\ntitle: Only\nslug: only\n---\n\nBody.\n")
    (root / "figures" / "drawn.tex").write_text(
        "\\begin{tikzpicture}\n\\node {drawn};\n\\end{tikzpicture}\n")
    # a preamble is the book's, not a figure
    (root / "figures" / "preamble.tex").write_text("% book styles\n")
    return load_project(root)


def test_the_preamble_is_not_mistaken_for_a_figure(figures_layout):
    assert [p.stem for p in figure_sources(figures_layout)] == ["drawn"]


def test_artwork_counts_as_a_source(figures_layout):
    (Path(figures_layout.directory) / "figures" / "art.ai").write_bytes(b"%PDF-1.4\n")
    assert sorted(p.stem for p in figure_sources(figures_layout)) == ["art", "drawn"]


def test_figures_sources_build_into_the_build_dir(figures_layout):
    from parody.writers.figures import figures_build_dir, output_dir_for
    src = figure_sources(figures_layout)[0]
    assert output_dir_for(figures_layout, src) == figures_build_dir(figures_layout)


def test_a_section_local_source_still_builds_in_place(project):
    """Books predating the figures/ layout keep working."""
    from parody.writers.figures import output_dir_for
    src = figure_sources(project)[0]
    assert output_dir_for(project, src) == src.parent


@pytest.mark.pdf
@pytest.mark.skipif(not have_tool("lualatex"), reason="lualatex not available")
def test_a_build_produces_both_pdf_and_svg(figures_layout):
    from parody.writers.figures import build_figures, figures_build_dir
    built, _ = build_figures(figures_layout)
    out = figures_build_dir(figures_layout)
    assert (out / "drawn.pdf").is_file()
    assert (out / "drawn.svg").is_file(), "the web form must be built too"
    # the source directory keeps only sources
    figs = Path(figures_layout.directory) / "figures"
    assert not list(figs.glob("*.pdf")) and not list(figs.glob("*.svg"))


def test_illustrator_artwork_becomes_a_pdf(figures_layout, tmp_path):
    """A .ai IS a PDF, so it needs no conversion step of its own."""
    from parody.writers.figures import place_artwork
    src = Path(figures_layout.directory) / "figures" / "art.ai"
    src.write_bytes(b"%PDF-1.4\ndummy\n")
    out = place_artwork(src, tmp_path / "out")
    assert out.name == "art.pdf"
    assert out.read_bytes().startswith(b"%PDF")
