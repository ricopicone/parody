"""The marked English build and its page inventory (task #825)."""

from pathlib import Path

import pytest

from parody.twin.inventory import TWINMARKS_FLAG, TWINMARKS_SUPPORT, read_counters, read_rows
from parody.twin.marks import mark_section
from parody.writers.latex import build_pdf, have_tool, strip_frontmatter

needs_tex = pytest.mark.skipif(
    not (have_tool("latexmk") and have_tool("lualatex")),
    reason="TeX (latexmk + lualatex) not available",
)

YAML = """\
title: Twin Test
slug: twin-test
authors: [Tester]
chapters:
  - slug: one
    title: Chapter One
    sections: [first, second]
"""

FIRST = """---
title: First
---

# First {#sec:first}

Opening words here. A second sentence with $x^2$ maths.

$$y = mx + b$$ {#eq:line}

A closing paragraph. It has two sentences.
"""

SECOND = """---
title: Second
---

# Second {#sec:second}

- An item. More of it.

- Another item.
"""


def _book(tmp_path):
    book = tmp_path / "book"
    (book / "chapters" / "one").mkdir(parents=True)
    (book / "parody.yaml").write_text(YAML)
    (book / "chapters" / "one" / "first.md").write_text(FIRST)
    (book / "chapters" / "one" / "second.md").write_text(SECOND)
    return book


def _hook(path, body):
    return mark_section(body, {"first": 1, "second": 2}[Path(path).stem])


def test_strip_frontmatter_hook_runs_before_transform(tmp_path):
    src, dest = tmp_path / "a.md", tmp_path / "b.md"
    src.write_text("---\ntitle: T\n---\n\nBody.\n")
    strip_frontmatter(src, dest, transform=lambda raw: raw.replace("HOOK", "HOOK-then-transform"),
                      hook=lambda path, body: body + "\nHOOK")
    assert dest.read_text().strip() == "Body.\n\nHOOK-then-transform"


def test_build_pdf_without_twin_options_is_unchanged(tmp_path, monkeypatch):
    monkeypatch.setattr("parody.writers.latex.shutil.which", lambda *a, **k: None)
    book = _book(tmp_path)
    build_pdf(book)
    build = book / "build" / "print"
    assert "twinmarks" not in (build / "main.tex").read_text()
    assert "\\parodys" not in (build / "sections" / "one" / "first.md").read_text()
    assert not (build / "parody-twinmarks.sty").exists()


def test_build_pdf_hook_flags_and_support(tmp_path, monkeypatch):
    monkeypatch.setattr("parody.writers.latex.shutil.which", lambda *a, **k: None)
    book = _book(tmp_path)
    build_pdf(book, section_hook=_hook, extra_support=TWINMARKS_SUPPORT,
              extra_flags=[TWINMARKS_FLAG])
    build = book / "build" / "print"
    assert TWINMARKS_FLAG in (build / "main.tex").read_text()
    assert (build / "parody-twinmarks.sty").exists() and (build / "parody-twinmarks.lua").exists()
    assert "\\parodys{1001000}" in (build / "sections" / "one" / "first.md").read_text()
    assert "\\parodys{2002000}" in (build / "sections" / "one" / "second.md").read_text()


def test_read_rows_and_counters(tmp_path):
    (tmp_path / "main.twin").write_text("5\t1\t1001000\t2\n5\t1\t1001001\t1\n6\t2\t1001001\t3\n")
    (tmp_path / "main.twinctr").write_text(
        "1001000|page=1,chapter=1,equation=0,\n1001001|page=1,chapter=1,equation=1,\n"
        "1001000|page=1,chapter=1,equation=7,\n")
    assert read_rows(tmp_path / "main.twin") == [(5, 1, 1001000, 2), (5, 1, 1001001, 1),
                                                (6, 2, 1001001, 3)]
    counters = read_counters(tmp_path / "main.twinctr")
    assert counters[1001000] == {"page": 1, "chapter": 1, "equation": 0}  # first wins
    assert counters[1001001]["equation"] == 1


@needs_tex
def test_marked_build_inventory(tmp_path):
    book = _book(tmp_path)
    pdf = build_pdf(book, section_hook=_hook, extra_support=TWINMARKS_SUPPORT,
                    extra_flags=[TWINMARKS_FLAG], pagemap=False)
    assert pdf is not None
    build = book / "build" / "print"
    rows = read_rows(build / "main.twin")
    seen = {v for _, _, v, _ in rows}
    marked = (build / "sections" / "one" / "first.md").read_text() + \
        (build / "sections" / "one" / "second.md").read_text()
    import re
    inserted = {int(v) for v in re.findall(r"\\parodys\{(\d+)\}", marked)}
    assert inserted <= seen, sorted(inserted - seen)
    counters = read_counters(build / "main.twinctr")
    assert set(inserted) <= set(counters)
    assert {"chapter", "equation", "footnote"} <= set(counters[1001000])


# --- the inventory and its gate ------------------------------------------------

from parody.twin.inventory import build_inventory, compare_pages, normalize_page_text  # noqa: E402


def test_normalize_ignores_whitespace_and_hyphen_breaks():
    assert normalize_page_text("resis-\ntance is  futile\n") == \
        normalize_page_text("re-\nsistance is futile")


def test_compare_pages_flags_moved_text():
    texts = {"pub": ["Page one.", "Page two ends here.", "Three."],
             "mark": ["Page one.", "Page two ends", "here. Three."]}
    assert compare_pages("pub", "mark", extract=texts.__getitem__) == [2, 3]


def test_compare_pages_different_page_count():
    texts = {"pub": ["a", "b", "c"], "mark": ["a", "b"]}
    assert compare_pages("pub", "mark", extract=texts.__getitem__) == [3]


@needs_tex
def test_build_inventory_on_tiny_book(tmp_path):
    book = _book(tmp_path)
    published = build_pdf(book, output_pdf=tmp_path / "en.pdf")
    inv = build_inventory(book, tmp_path / "twin-build", published)
    assert inv.mismatched_pages == []
    assert inv.section_index == {"one/first": 1, "one/second": 2}
    assert {v // 1_000_000 for _, _, v, _ in inv.rows} == {1, 2}
    assert inv.marked_pdf.exists()


@needs_tex
def test_lines_inside_a_box_are_counted_one_by_one(tmp_path):
    book = _book(tmp_path)
    long = " ".join(["This definition goes on for a good while so that it wraps."] * 6)
    (book / "chapters" / "one" / "first.md").write_text(
        f"---\ntitle: First\n---\n\nIntro.\n\n::: {{#def:x .definition}}\n{long}\n:::\n")
    published = build_pdf(book, output_pdf=tmp_path / "en.pdf")
    inv = build_inventory(book, tmp_path / "twin-build", published)
    # The box sits in a paragraph line of its own; counted as that one line,
    # every sentence in it would get 1. Its second sentence wraps onto two.
    second_sentence = 1_002_001  # section 1, chunk 1 (the definition), sentence 1
    assert sum(n for _, _, v, n in inv.rows if v == second_sentence) == 2


@needs_tex
def test_a_box_head_logs_the_number_before_the_box_takes_it(tmp_path):
    book = _book(tmp_path)
    (book / "chapters" / "one" / "first.md").write_text(
        "---\ntitle: First\n---\n\nIntro words.\n\n::: {#def:x .definition}\nVoltage is a thing. "
        "It has two sentences.\n:::\n")
    published = build_pdf(book, output_pdf=tmp_path / "en.pdf")
    inv = build_inventory(book, tmp_path / "twin-build", published)
    head, inside = inv.counters[1_002_000], inv.counters[1_002_001]
    assert head["thmctr"] == 0 and inside["thmctr"] == 1


@needs_tex
def test_a_section_head_logs_the_number_before_the_heading_takes_it(tmp_path):
    # A section titled only in front matter gets its \section from the build,
    # ahead of every mark in its body. Logged after it, the counters at the
    # section's head already had the section's number, and the twin, which
    # sets the heading again, numbered every section one too high (robotics).
    book = _book(tmp_path)
    (book / "chapters" / "one" / "first.md").write_text("---\ntitle: First\n---\n\nOpening words.\n")
    (book / "chapters" / "one" / "second.md").write_text("---\ntitle: Second\n---\n\nMore words.\n")
    published = build_pdf(book, output_pdf=tmp_path / "en.pdf")
    inv = build_inventory(book, tmp_path / "twin-build", published)
    assert inv.mismatched_pages == []
    assert inv.counters[1_001_000]["section"] == 0
    assert inv.counters[2_001_000]["section"] == 1


def test_read_counters_keeps_the_current_label(tmp_path):
    # the label a \label at the mark would record: the twin restores it, or a
    # label after an unnumbered heading or equation comes out empty
    (tmp_path / "main.twinctr").write_text(
        "1001000|page=1,chapter=1,|1\n1001001|page=1,chapter=1,section=2,|1.2\n"
        "1001002|page=1,chapter=1,\n")
    counters = read_counters(tmp_path / "main.twinctr")
    assert counters[1001000] == {"page": 1, "chapter": 1, "@currentlabel": "1"}
    assert counters[1001001]["@currentlabel"] == "1.2"
    assert "@currentlabel" not in counters[1001002]  # an older log: no label field


@needs_tex
def test_each_mark_logs_the_current_label(tmp_path):
    # System Dynamics' lead-in: unnumbered headings and equations right after
    # \chapter, whose labels the English numbers as the chapter
    book = _book(tmp_path)
    (book / "chapters" / "one" / "first.md").write_text(
        "---\ntitle: First\n---\n\nOpening words.\n\n## Unnumbered {.unnumbered #unn}\n\nMore words.\n")
    published = build_pdf(book, output_pdf=tmp_path / "en.pdf")
    inv = build_inventory(book, tmp_path / "twin-build", published)
    labels = {v["@currentlabel"] for k, v in inv.counters.items() if k // 1_000_000 == 1}
    assert labels and all(lab.strip() for lab in labels), labels
