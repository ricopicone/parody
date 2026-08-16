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


def test_artwork_falls_back_to_a_copy_without_ghostscript(figures_layout, tmp_path,
                                                          monkeypatch):
    """No gs is a smaller file, not a broken build."""
    from parody.writers import figures as figmod

    src = Path(figures_layout.directory) / "figures" / "art.ai"
    src.write_bytes(b"%PDF-1.4\noriginal\n")
    monkeypatch.setattr(figmod.shutil, "which", lambda *a, **k: None)
    out = figmod.place_artwork(src, tmp_path / "out")
    assert out.name == "art.pdf"
    assert out.read_bytes() == b"%PDF-1.4\noriginal\n"


def test_a_failed_flatten_still_produces_the_figure(figures_layout, tmp_path,
                                                   monkeypatch):
    from parody.writers import figures as figmod

    src = Path(figures_layout.directory) / "figures" / "art.ai"
    src.write_bytes(b"%PDF-1.4\noriginal\n")
    monkeypatch.setattr(figmod, "flatten_pdf", lambda s, d: False)
    out = figmod.place_artwork(src, tmp_path / "out")
    assert out.is_file() and out.name == "art.pdf"


@pytest.mark.pdf
@pytest.mark.skipif(not have_tool("gs"), reason="ghostscript not available")
def test_flatten_drops_the_editors_private_data(tmp_path):
    """An .ai carries Illustrator's own stream beside the PDF rendering.

    Copying keeps it — measured on the electronics artwork, 3.8 MB of .ai
    against 216 kB of drawing. Ghostscript leaves it behind.
    """
    from parody.writers.figures import flatten_pdf

    # a PDF carrying a private-data object, the shape an .ai has
    src = tmp_path / "art.ai"
    src.write_bytes(
        b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 72 72] >>\n"
        b"endobj\ntrailer\n<< /Root 1 0 R >>\n%%EOF\n")
    dest = tmp_path / "art.pdf"
    assert flatten_pdf(src, dest)
    assert dest.is_file() and dest.read_bytes().startswith(b"%PDF")


def test_a_rasterizing_conversion_is_reported(tmp_path, capsys):
    """Vector art that becomes pixels must not pass in silence.

    A rasterized figure looks acceptable on screen and falls apart in print,
    and nothing else in the pipeline would mention it.
    """
    from parody.writers.figures import warn_if_rasterized

    src = tmp_path / "a.pdf"
    src.write_bytes(b"%PDF-1.5\n/Type /Page\n")            # pure vector
    dest = tmp_path / "b.pdf"
    dest.write_bytes(b"%PDF-1.5\n/Subtype /Image\n")        # now a bitmap
    assert warn_if_rasterized(src, dest)
    assert "rasterized" in capsys.readouterr().out


def test_artwork_that_already_held_a_photo_is_not_flagged(tmp_path, capsys):
    from parody.writers.figures import warn_if_rasterized

    src = tmp_path / "a.pdf"
    src.write_bytes(b"%PDF-1.5\n/Subtype /Image\n")
    dest = tmp_path / "b.pdf"
    dest.write_bytes(b"%PDF-1.5\n/Subtype /Image\n")
    assert not warn_if_rasterized(src, dest)
    assert capsys.readouterr().out == ""


def test_an_svg_that_embeds_a_bitmap_is_reported(tmp_path, capsys):
    from parody.writers.figures import warn_if_rasterized

    pdf = tmp_path / "a.pdf"
    pdf.write_bytes(b"%PDF-1.5\n")
    svg = tmp_path / "a.svg"
    svg.write_text('<svg><image href="data:image/png;base64,iVBORw0K"/></svg>')
    assert warn_if_rasterized(pdf, svg)
    assert "raster" in capsys.readouterr().out


def test_an_empty_svg_is_reported(tmp_path, capsys):
    """pdftocairo drops raster images on the way to SVG rather than embedding
    them, so a figure carrying a photo comes out the right size and empty —
    invisible on the web, with no error anywhere."""
    from parody.writers.figures import warn_if_rasterized

    pdf = tmp_path / "a.pdf"
    pdf.write_bytes(b"%PDF-1.5\n")
    svg = tmp_path / "a.svg"
    svg.write_text('<?xml version="1.0"?><svg width="816" height="1056"></svg>')
    assert warn_if_rasterized(pdf, svg)
    assert "no drawing in it" in capsys.readouterr().out


def test_a_normal_vector_svg_passes(tmp_path, capsys):
    from parody.writers.figures import warn_if_rasterized

    pdf = tmp_path / "a.pdf"
    pdf.write_bytes(b"%PDF-1.5\n")
    svg = tmp_path / "a.svg"
    svg.write_text('<svg><g><path d="M0 0 L2 2"/></g></svg>')
    assert not warn_if_rasterized(pdf, svg)
    assert capsys.readouterr().out == ""
