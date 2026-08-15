"""A section's title must reach print even when its markdown omits the heading.

The convention across parody books is that a section's title lives in front
matter and the CONSUMER renders it — parody-web's template does exactly that
(`title_in_html`). The print writer never learned to, so a book that follows
the convention lost every section heading, its TOC entries, its numbering
level (subsections fell to 1.0.x), and its cross-reference targets — silently,
because nothing consumed the print PDF.

Found on the Electronics Primer, whose section headings were removed in
d71fe79 to stop the WEB rendering each title twice.
"""

import pytest

from parody.writers.latex import build_pdf

PARODY_YAML = """\
title: Heading Test
slug: heading-test
authors: [Tester]
chapters:
  - slug: one
    title: Chapter One
    sections: [lead-in, headless, subs-only, owns-heading]
"""

FM = "---\ntitle: {title}\nslug: {slug}\n{extra}---\n\n"


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.setattr("parody.writers.latex.shutil.which", lambda *a, **k: None)
    root = tmp_path / "heading-test"
    ch = root / "chapters" / "one"
    ch.mkdir(parents=True)
    (root / "parody.yaml").write_text(PARODY_YAML)
    (ch / "lead-in.md").write_text(
        FM.format(title="Chapter One", slug="lead-in", extra="")
        + "Chapter intro prose.\n")
    # the shape the convention produces: title only in front matter
    (ch / "headless.md").write_text(
        FM.format(title="Voltage dividers", slug="headless",
                  extra="id: lec:voltage_dividers\nhash: o5\n")
        + "Body prose with no heading at all.\n")
    # same, but carrying subheadings — these must not be mistaken for the
    # section's own heading (they render as \\subsection)
    (ch / "subs-only.md").write_text(
        FM.format(title="Sources", slug="subs-only", extra="hash: 8j\n")
        + "Intro prose.\n\n## Ideal voltage sources\n\nMore prose.\n")
    # a book that still writes its heading in the body must not get two
    (ch / "owns-heading.md").write_text(
        FM.format(title="Owns It", slug="owns-heading", extra="")
        + "# Owns It {#owns-it}\n\nBody.\n")
    return root


def tex(project, slug):
    return (project / "build" / "print" / "sections" / "one"
            / f"{slug}.tex").read_text()


def test_a_headless_section_gets_its_front_matter_title(project):
    build_pdf(project)
    out = tex(project, "headless")
    assert "\\section{Voltage dividers}" in out
    assert out.index("\\section{Voltage dividers}") < out.index("Body prose")


def test_a_headless_section_keeps_its_cross_reference_targets(project):
    # frontmatter id and hash are live \cref targets; without a heading to
    # carry them the section had no \label at all and refs dangled
    build_pdf(project)
    out = tex(project, "headless")
    assert "\\label{lec:voltage_dividers}" in out
    assert "\\label{o5}" in out


def test_subheadings_do_not_count_as_the_sections_own_heading(project):
    build_pdf(project)
    out = tex(project, "subs-only")
    assert "\\section{Sources}" in out
    assert "\\subsection{Ideal voltage sources}" in out
    assert out.index("\\section{Sources}") < out.index("\\subsection{")


def test_a_section_that_owns_its_heading_is_not_given_a_second(project):
    build_pdf(project)
    out = tex(project, "owns-heading")
    assert out.count("\\section{") == 1


def test_the_chapter_lead_in_gets_no_section_heading(project):
    # its heading is the \chapter itself, exactly as parody-web renders it
    build_pdf(project)
    assert "\\section{" not in tex(project, "lead-in")


def test_the_page_mark_still_follows_the_heading(project):
    build_pdf(project)
    out = tex(project, "headless")
    assert out.index("\\section{Voltage dividers}") < out.index("\\parodypagemark")


def test_the_synthesized_heading_reaches_the_document(project):
    build_pdf(project)
    main = (project / "build" / "print" / "main.tex").read_text()
    # chapter heading still comes from build_pdf, not from the lead-in
    assert "\\chapter{Chapter One}" in main
