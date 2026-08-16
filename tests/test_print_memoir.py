"""The bundled memoir print profile: name resolution + end-to-end compile.

Shares the tiny content repo from test_print_pdf.py.
"""

import pytest

from parody.writers.latex import (BUNDLED_PROFILES, build_pdf, have_tool,
                                   resolve_profile)
from tests.test_print_pdf import tiny_project  # noqa: F401  (pytest fixture)

needs_tex = pytest.mark.skipif(
    not (have_tool("latexmk") and have_tool("lualatex")),
    reason="TeX (latexmk + lualatex) not available",
)


def test_resolve_profile_default():
    assert resolve_profile(None) == BUNDLED_PROFILES / "memoir"


def test_resolve_profile_bare_name():
    assert resolve_profile("memoir") == BUNDLED_PROFILES / "memoir"
    assert resolve_profile("print") == BUNDLED_PROFILES / "print"


def test_resolve_profile_unknown_name_is_path(tmp_path):
    # A bare name with no matching bundled dir is treated as a path verbatim.
    assert resolve_profile("nope").name == "nope"
    assert resolve_profile(str(tmp_path)) == tmp_path


def test_memoir_profile_is_well_formed():
    prof = BUNDLED_PROFILES / "memoir"
    for f in ("parody-memoir.cls", "parody-theme-default.sty",
              "parody-environments.sty", "main.tex.template", "latexmkrc"):
        assert (prof / f).is_file(), f
    template = (prof / "main.tex.template").read_text()
    assert "\\documentclass[11pt]{parody-memoir}" in template
    assert "\\usepackage{parody-theme-default}" in template
    assert "\\usepackage{parody-environments}" in template


def test_memoir_sources_generated_without_tex(tiny_project, monkeypatch):  # noqa: F811
    monkeypatch.setattr("parody.writers.latex.shutil.which", lambda *a, **k: None)
    build_pdf(tiny_project, profile_dir="memoir")
    main = (tiny_project / "build" / "print" / "main.tex").read_text()
    assert "\\documentclass[11pt]{parody-memoir}" in main
    assert "\\usepackage{parody-environments}" in main
    # the memoir class/theme/env files were staged into the build dir
    build_dir = tiny_project / "build" / "print"
    assert (build_dir / "parody-memoir.cls").is_file()
    assert (build_dir / "parody-theme-default.sty").is_file()


@pytest.mark.pdf
@needs_tex
def test_memoir_pdf_compiles(tiny_project):  # noqa: F811
    pdf = build_pdf(tiny_project, profile_dir="memoir")
    assert pdf is not None and pdf.exists() and pdf.stat().st_size > 10_000


def test_exercise_setup_names_problems():
    env = (BUNDLED_PROFILES / "memoir" / "parody-environments.sty").read_text()
    assert "exercise/within=chapter" in env
    assert "exercise/name=Problem" in env
    assert "\\crefname{exercise}{problem}{problems}" in env
    assert "\\Crefname{exercise}{Problem}{Problems}" in env


def pdf_text(pdf):
    """All text in a compiled PDF, pages joined by newlines."""
    from pypdf import PdfReader
    return "\n".join(p.extract_text() or "" for p in PdfReader(str(pdf)).pages)


def squashed(pdf):
    """PDF text with all whitespace removed.

    Letterspacing and justification make extracted text unstable at word
    level; squashing lets an assertion pin the glyphs without pinning the
    spacing.
    """
    return "".join(pdf_text(pdf).split())


@pytest.mark.pdf
@needs_tex
def test_problems_are_named_and_numbered_by_chapter(tiny_project):  # noqa: F811
    pdf = build_pdf(tiny_project, profile_dir="memoir")
    text = squashed(pdf)
    assert "Problem1.1" in text
    assert "Exercise" not in text


@pytest.mark.pdf
@needs_tex
def test_boxes_number_within_the_chapter(tiny_project):  # noqa: F811
    pdf = build_pdf(tiny_project, profile_dir="memoir")
    text = squashed(pdf)
    assert "Definition1.1" in text
    assert "Box1.1" in text
    assert "Example1.1" in text
    assert "Listing1.1" in text
