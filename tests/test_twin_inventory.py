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
