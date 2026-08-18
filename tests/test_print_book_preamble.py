r"""A book can hand the print build its own preamble.

parody owns the house style; a book still has its own MATH vocabulary — \diff,
\abs, \Transpose, the operators it declares. The web has always had one (the
MathJax config parody-web ships), but print had no seam at all: every such
macro reached lualatex undefined, and because latexmk runs in nonstopmode the
build "succeeded" while 48 spots in System Dynamics printed the argument with
the operator silently dropped. Nothing in the log matches "LaTeX Error", which
is exactly why this is tested by compiling and reading main.log.

    print:
      preamble: profile/bookmathmacros.sty

A `.sty` is loaded with \usepackage (it is a package, and LaTeX makes
\makeatletter implicit inside one); anything else is \input verbatim.
"""

import pytest

from parody.writers.latex import build_pdf, have_tool

PARODY_YAML = """\
title: Preamble Test
slug: preamble-test
authors: [Tester]
chapters:
  - slug: one
    title: Chapter One
    sections: [a-section]
"""

SECTION_MD = """\
# A section {#sec-a}

The macro comes from the book, not from parody: $f = m \\diff x$.
"""

STY = r"""\ProvidesPackage{bookmacros}
\RequirePackage{amsmath}
\newcommand*{\diff}{\mathop{}\!d}
"""


@pytest.fixture
def no_tex(monkeypatch):
    """build_pdf writes the whole LaTeX tree before it calls latexmk, so the
    wiring is checkable by reading the generated sources with no TeX at all."""
    monkeypatch.setattr("parody.writers.latex.shutil.which", lambda *a, **k: None)


@pytest.fixture
def project(tmp_path):
    root = tmp_path / "preamble-test"
    (root / "chapters" / "one").mkdir(parents=True)
    (root / "profile").mkdir()
    (root / "parody.yaml").write_text(PARODY_YAML)
    (root / "chapters" / "one" / "a-section.md").write_text(SECTION_MD)
    (root / "profile" / "bookmacros.sty").write_text(STY)
    return root


def _declare(root, value):
    meta = root / "parody.yaml"
    meta.write_text(meta.read_text() + f"print:\n  preamble: {value}\n")


def test_a_sty_preamble_is_copied_in_and_used_as_a_package(project, no_tex):
    _declare(project, "profile/bookmacros.sty")
    build_pdf(project)
    build = project / "build" / "print"
    assert (build / "bookmacros.sty").read_text() == STY
    main = (build / "main.tex").read_text()
    assert "\\usepackage{bookmacros}" in main
    # Before the profile's own packages, so a book macro is available to
    # anything they expand, and after \documentclass, which is where $flags is.
    assert main.index("\\documentclass") < main.index("\\usepackage{bookmacros}")


def test_a_tex_preamble_is_inputted_verbatim(project, no_tex):
    (project / "profile" / "macros.tex").write_text("\\newcommand{\\q}{q}\n")
    _declare(project, "profile/macros.tex")
    build_pdf(project)
    build = project / "build" / "print"
    assert (build / "macros.tex").exists()
    assert "\\input{macros.tex}" in (build / "main.tex").read_text()


def test_a_missing_preamble_warns_and_still_builds(project, no_tex, capsys):
    _declare(project, "profile/nope.sty")
    build_pdf(project)
    assert "print.preamble not found" in capsys.readouterr().out
    assert "nope" not in (project / "build" / "print" / "main.tex").read_text()


def test_no_preamble_declared_changes_nothing(project, no_tex):
    build_pdf(project)
    main = (project / "build" / "print" / "main.tex").read_text()
    assert "\\usepackage{bookmacros}" not in main


@pytest.mark.skipif(
    not (have_tool("latexmk") and have_tool("lualatex")),
    reason="TeX (latexmk + lualatex) not available",
)
def test_the_book_macro_actually_compiles(project):
    """The proof: without the seam this same source logs "Undefined control
    sequence" and prints `x` where `\\diff x` was written — with no error the
    build gates on."""
    _declare(project, "profile/bookmacros.sty")
    pdf = build_pdf(project)
    assert pdf is not None and pdf.exists()
    log = (project / "build" / "print" / "main.log").read_text(errors="replace")
    assert "Undefined control sequence" not in log
