"""Page marks reach main.tex and the section .tex tree during a print build.

These run without TeX: build_pdf writes the whole LaTeX tree before it ever
calls latexmk, so the wiring is checkable by reading the generated sources.
"""

import pytest

from parody.writers.latex import build_pdf

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


def test_shared_is_not_selectable_as_a_profile():
    from parody.writers.latex import resolve_profile
    # "_shared" holds support files, not a profile; a bare "_shared" must be
    # treated as a filesystem path (and so not resolve to the bundled dir).
    assert resolve_profile("_shared").name == "_shared"
    assert "profiles" not in str(resolve_profile("_shared").parent)
