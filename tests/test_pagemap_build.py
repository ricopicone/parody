"""Page marks reach main.tex and the section .tex tree during a print build.

These run without TeX: build_pdf writes the whole LaTeX tree before it ever
calls latexmk, so the wiring is checkable by reading the generated sources.
"""

import json

import pytest

from parody.writers.latex import build_pdf, have_tool

PARODY_YAML = """\
title: Page Map Test
slug: pagemap-test
authors: [Tester]
chapters:
  - slug: one
    title: Chapter One
    sections: [lead-in, alpha]
  - slug: two
    title: Chapter Two
    sections: [beta]
"""


@pytest.fixture
def project(tmp_path, monkeypatch):
    # No TeX: build_pdf writes the sources and returns None.
    monkeypatch.setattr("parody.writers.latex.shutil.which", lambda *a, **k: None)
    root = tmp_path / "pagemap-test"
    (root / "chapters" / "one").mkdir(parents=True)
    (root / "chapters" / "two").mkdir(parents=True)
    (root / "parody.yaml").write_text(PARODY_YAML)
    (root / "chapters" / "one" / "lead-in.md").write_text("Chapter intro prose.\n")
    (root / "chapters" / "one" / "alpha.md").write_text("# Alpha\n\nAlpha body.\n")
    (root / "chapters" / "two" / "beta.md").write_text("# Beta\n\nBeta body.\n")
    return root


def test_the_pagemap_package_is_injected_without_editing_the_profile(project):
    build_pdf(project)
    build = project / "build" / "print"
    assert "\\usepackage{parody-pagemap}" in (build / "main.tex").read_text()
    # copied in beside the profile's own files
    assert (build / "parody-pagemap.sty").is_file()


def test_first_section_of_a_chapter_is_marked_at_the_chapter_opening(project):
    build_pdf(project)
    build = project / "build" / "print"
    main = (build / "main.tex").read_text()
    # the mark sits after \chapter, so the range opens on the chapter page
    assert "\\chapter{Chapter One}" in main
    assert "\\parodypagemark{one/lead-in}" in main
    assert main.index("\\chapter{Chapter One}") < main.index(
        "\\parodypagemark{one/lead-in}")
    assert main.index("\\parodypagemark{one/lead-in}") < main.index(
        "\\input{sections/one/lead-in.tex}")
    # ...and NOT a second time inside the section itself
    leadin = (build / "sections" / "one" / "lead-in.tex").read_text()
    assert "\\parodypagemark" not in leadin


def test_later_sections_are_marked_inside_their_own_tex(project):
    build_pdf(project)
    build = project / "build" / "print"
    alpha = (build / "sections" / "one" / "alpha.tex").read_text()
    assert "\\parodypagemark{one/alpha}" in alpha
    assert alpha.index("\\section{Alpha}") < alpha.index("\\parodypagemark")
    assert "\\parodypagemark{one/alpha}" not in (build / "main.tex").read_text()


def test_every_chapter_gets_its_own_first_section_mark(project):
    build_pdf(project)
    main = (project / "build" / "print" / "main.tex").read_text()
    # chapter two's only section is its first, so it is marked at the opening
    assert "\\parodypagemark{two/beta}" in main
    assert "\\parodypagemark" not in (
        project / "build" / "print" / "sections" / "two" / "beta.tex").read_text()


def test_each_section_gets_an_end_mark_after_its_input(project):
    build_pdf(project)
    main = (project / "build" / "print" / "main.tex").read_text()
    for key in ("one/lead-in", "one/alpha", "two/beta"):
        ch, sec = key.split("/")
        assert f"\\parodypagemark{{{key}@end}}" in main
        assert main.index(f"\\input{{sections/{ch}/{sec}.tex}}") < main.index(
            f"\\parodypagemark{{{key}@end}}")


def test_end_sentinel_closes_the_last_section(project):
    build_pdf(project)
    main = (project / "build" / "print" / "main.tex").read_text()
    assert "\\parodypagemark{@end}" in main
    assert main.index("\\input{sections/two/beta.tex}") < main.index(
        "\\parodypagemark{@end}")
    assert main.index("\\parodypagemark{@end}") < main.index("\\backmatter")


def test_pagemap_can_be_turned_off(project):
    build_pdf(project, pagemap=False)
    main = (project / "build" / "print" / "main.tex").read_text()
    assert "\\parodypagemark" not in main
    assert "\\usepackage{parody-pagemap}" not in main


needs_tex = pytest.mark.skipif(
    not (have_tool("latexmk") and have_tool("lualatex")),
    reason="TeX (latexmk + lualatex) not available",
)


def test_no_sidecar_when_latex_never_ran(project):
    # No TeX → no PDF → nothing to describe. Must not crash or write a lie.
    assert build_pdf(project) is None
    assert not list(project.glob("*.pages.json"))


@pytest.mark.pdf
@needs_tex
def test_sidecar_ranges_tile_the_real_pdf(tmp_path):
    root = tmp_path / "pagemap-test"
    (root / "chapters" / "one").mkdir(parents=True)
    (root / "chapters" / "two").mkdir(parents=True)
    (root / "parody.yaml").write_text(PARODY_YAML)
    (root / "chapters" / "one" / "lead-in.md").write_text(
        "Chapter intro prose.\n\n\\clearpage\n\nMore intro.\n")
    (root / "chapters" / "one" / "alpha.md").write_text(
        "# Alpha\n\nAlpha body.\n\n\\clearpage\n\nMore alpha.\n")
    (root / "chapters" / "two" / "beta.md").write_text("# Beta\n\nBeta body.\n")

    pdf = build_pdf(root)
    assert pdf is not None and pdf.is_file()

    from parody.writers.pagemap import pdf_page_count
    sidecar = json.loads(pdf.with_suffix(".pages.json").read_text())

    assert sidecar["schema"] == 1
    assert sidecar["pdf"] == pdf.name
    assert sidecar["solutions"] is False
    assert len(sidecar["sha256"]) == 64

    ranges = sidecar["sections"]
    assert set(ranges) == {"one/lead-in", "one/alpha", "two/beta"}

    # every range is well formed and inside the document
    total = pdf_page_count(pdf)
    assert total is not None and sidecar["pages"] == total
    for key, (start, end) in ranges.items():
        assert 1 <= start <= end <= total, key

    # Coverage invariant: printing every section reassembles the body with no
    # page missing (blank versos included).
    covered = set()
    for start, end in ranges.values():
        covered.update(range(start, end + 1))
    body = set(range(ranges["one/lead-in"][0], ranges["two/beta"][1] + 1))
    assert covered == body

    # ...and no section swallows the page a LATER section opens on. \chapter
    # forces a page break, so chapter two's opening page belongs to beta alone.
    assert ranges["one/alpha"][1] < ranges["two/beta"][0]

    # a chapter's first section opens ON the chapter page
    assert ranges["two/beta"][0] > ranges["one/alpha"][0]


@pytest.mark.pdf
@needs_tex
def test_pagemap_package_does_not_clash_with_the_class(tmp_path):
    # A \newcommand collision is masked by nonstopmode and silently renders the
    # OTHER definition, so gate on "LaTeX Error" rather than only on
    # "Undefined control sequence".
    root = tmp_path / "pagemap-test"
    (root / "chapters" / "one").mkdir(parents=True)
    (root / "chapters" / "two").mkdir(parents=True)
    (root / "parody.yaml").write_text(PARODY_YAML)
    (root / "chapters" / "one" / "lead-in.md").write_text("Intro.\n")
    (root / "chapters" / "one" / "alpha.md").write_text("# Alpha\n\nBody.\n")
    (root / "chapters" / "two" / "beta.md").write_text("# Beta\n\nBody.\n")
    build_pdf(root)
    log = (root / "build" / "print" / "main.log").read_text(
        encoding="utf-8", errors="replace")
    assert "LaTeX Error" not in log
    assert "already defined" not in log


def test_shared_is_not_selectable_as_a_profile():
    from parody.writers.latex import resolve_profile
    # "_shared" holds support files, not a profile; a bare "_shared" must be
    # treated as a filesystem path (and so not resolve to the bundled dir).
    assert resolve_profile("_shared").name == "_shared"
    assert "profiles" not in str(resolve_profile("_shared").parent)
