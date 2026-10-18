"""Composing the twin pages and building the twin PDF (task #825)."""

from pathlib import Path

import pytest

from parody.translate.chunks import chunk_hash, split_chunks, split_frontmatter
from parody.translate.store import TranslationFile, translation_path
from parody.twin.build import base_scale, build_twin, parse_twinfit, restore_code
from parody.twin.compose import SectionSource, align_translation, page_markdown
from parody.twin.paginate import Piece, TwinPage
from parody.writers.latex import have_tool

needs_tex = pytest.mark.skipif(not (have_tool("latexmk") and have_tool("lualatex")),
                               reason="needs TeX")


def V(section, chunk, sentence=0):
    return section * 1_000_000 + (chunk + 1) * 1000 + sentence


def _section(chunks, index=1):
    return SectionSource(index=index, key="ch/s", chapter=None, slug="s", source=Path("s.md"),
                         meta={"title": "S"}, chunks=chunks, title="S")


def _tf(en_chunks, translate, title="S-de"):
    return TranslationFile(language="de", source="chapters/ch/s.md", title=title,
                           title_hash=chunk_hash("S"),
                           chunks=[(chunk_hash(c), translate(c)) for c in en_chunks])


EN = ["# S {#sec:s}", "One alpha. Two alpha. Three alpha.", "::: {#def:x .definition}\nDef one. Def two.\n:::",
      "Has a note.[^1]", "[^1]: The note alpha."]


def test_align_translation_states():
    tf = _tf(EN[:3] + EN[4:], lambda c: c.replace("alpha", "Alpha-DE"))  # chunk 3 missing
    tr = align_translation(_section(EN), tf)
    assert tr.states == ["current", "current", "current", "missing", "current"]
    assert tr.texts[1] == "One Alpha-DE. Two Alpha-DE. Three Alpha-DE."


def test_page_markdown_whole_and_split_chunks():
    tr = align_translation(_section(EN), _tf(EN, lambda c: c.replace("alpha", "Alpha-DE")))
    page = TwinPage(5, 1, pieces=[Piece(1, 0, 0, None), Piece(1, 1, 0, 2)])
    groups, notes = page_markdown(page, {1: _section(EN)}, {1: tr}, "de", {})
    (index, md), = groups
    assert index == 1
    assert "# S {#sec:s}" in md and "One Alpha-DE. Two Alpha-DE." in md
    assert "Three" not in md
    assert "[^1]: The note Alpha-DE." in md  # footnote definitions always come along
    assert notes == []


def test_page_markdown_untranslated_uses_english_with_marker():
    tr = align_translation(_section(EN), None)
    groups, notes = page_markdown(TwinPage(5, 1, pieces=[Piece(1, 1, 0, None)]),
                                  {1: _section(EN)}, {1: tr}, "de", {})
    assert "\\parodyuntranslated\n\nOne alpha. Two alpha." in groups[0][1]
    assert any("untranslated" in n for n in notes)


def test_page_markdown_stale_uses_old_translation():
    old = EN[:1] + ["One alpha. Two. Three alpha."] + EN[2:]
    tf = _tf(old, lambda c: c.replace("alpha", "Alpha-DE"))
    tr = align_translation(_section(EN), tf)
    groups, notes = page_markdown(TwinPage(5, 1, pieces=[Piece(1, 1, 0, None)]),
                                  {1: _section(EN)}, {1: tr}, "de", {})
    assert "\\parodystale\n\nOne Alpha-DE. Two. Three Alpha-DE." in groups[0][1]
    assert any("stale" in n for n in notes)


def test_reopened_box_steps_its_counter_back():
    tr = align_translation(_section(EN), _tf(EN, lambda c: c))
    counters = {V(1, 2, 0): {"thmctr": 3, "equation": 1}, V(1, 2, 1): {"thmctr": 4, "equation": 1}}
    groups, _ = page_markdown(TwinPage(6, 2, pieces=[Piece(1, 2, 1, None)]),
                              {1: _section(EN)}, {1: tr}, "de", counters)
    md = groups[0][1]
    assert "\\addtocounter{thmctr}{-1}" in md
    assert md.index("\\addtocounter{thmctr}{-1}") < md.index("::: {.definition}")


def test_base_scale_is_10th_percentile():
    scales = [1.0] * 18 + [0.9, 0.8]
    assert base_scale(scales) == 0.9
    assert base_scale([1.0, 1.0]) == 1.0
    assert base_scale([0.93] * 10) == 0.93


def test_parse_twinfit():
    log = "x\nTWINFIT page=12 scale=0.91\nTWINFIT page=13 scale=1\n"
    assert parse_twinfit(log) == [(12, 0.91), (13, 1.0)]


def test_restore_code_skips_internal_counters():
    code = restore_code({"chapter": 1, "page": 7, "mpfootnote": 2, "tcb@cnt@x": 3, "thmctr": 4})
    assert code == "\\parodytwinset{chapter}{1}\\parodytwinset{thmctr}{4}"


YAML = """\
title: Twin Build
slug: twin-build
authors: [Tester]
chapters:
  - slug: one
    title: One
    sections: [first, second]
translations:
  languages: [de]
"""


def _para(n):
    return " ".join(f"Sentence number {i} of paragraph {n} says alpha things." for i in range(9))


def _write_tiny_book(tmp_path):
    book = tmp_path / "book"
    (book / "chapters" / "one").mkdir(parents=True)
    (book / "parody.yaml").write_text(YAML)
    first = "---\ntitle: First\n---\n\n# First {#sec:first}\n\n" + "\n\n".join(_para(i) for i in range(10)) + "\n"
    second = ("---\ntitle: Second\n---\n\n# Second {#sec:second}\n\n::: {#def:a .definition}\n"
              + _para(99) + "\n:::\n\n" + "\n\n".join(_para(i) for i in range(10, 16)) + "\n")
    (book / "chapters" / "one" / "first.md").write_text(first)
    (book / "chapters" / "one" / "second.md").write_text(second)
    for slug, text in (("first", first), ("second", second)):
        meta, body = split_frontmatter(text)
        chunks = split_chunks(body)
        TranslationFile(language="de", source=f"chapters/one/{slug}.md",
                        title=meta["title"] + " (de)", title_hash=chunk_hash(meta["title"]),
                        chunks=[(chunk_hash(c), c.replace("alpha", "Alpha-DE")) for c in chunks]
                        ).write(translation_path(book, "de", "one", slug))
    return book


@needs_tex
def test_build_twin_tiny_book(tmp_path):
    import pypdf
    book = _write_tiny_book(tmp_path)
    pdf, report = build_twin(book, "de", out=tmp_path / "twin.pdf")
    assert report.mismatched_pages == []
    assert report.tex_errors == []
    assert report.untranslated == 0 and report.stale == 0
    assert 0.5 < report.base_scale <= 1.0
    twin = pypdf.PdfReader(str(pdf))
    assert len(twin.pages) == report.pages >= 3
    english = pypdf.PdfReader(str(tmp_path / "book" / "build" / "twin" / "english.pdf"))
    for i, page in enumerate(twin.pages):
        text = " ".join(page.extract_text().split())
        assert "Alpha-DE" in text or i == 0
        assert "alpha " not in text
    texts = [" ".join(p.extract_text().split()) for p in twin.pages]
    # the chapter opens on the first twin page, as in the English
    assert "Kapitel 1 One" in texts[0] or "Kapitel1One" in texts[0].replace(" ", "")
    # a page where section 1.2 starts carries its translated title in the head
    assert any(t.startswith("1.2 Second (de)") for t in texts), [t[:30] for t in texts]


def test_coverage_check_flags_a_gap():
    from parody.twin.build import coverage_problems
    pages = [TwinPage(5, 1, pieces=[Piece(1, 0, 0, 2)]), TwinPage(6, 2, pieces=[Piece(1, 0, 3, None)])]
    assert coverage_problems(pages) == ["section 1 chunk 0: sentences 2–3 are on no twin page"]
    ok = [TwinPage(5, 1, pieces=[Piece(1, 0, 0, 2)]), TwinPage(6, 2, pieces=[Piece(1, 0, 2, None)])]
    assert coverage_problems(ok) == []


def test_split_tables_and_wide_floats_are_reported():
    from parody.twin.build import unsupported_notes
    chunks = {1: _section(["| a | b |\n|---|---|\n| 1 | 2 |", "Prose here."])}
    rows = [(5, 1, V(1, 0, 0), 3), (6, 2, V(1, 0, 0), 2), (6, 2, V(1, 1, 0), 1)]
    notes = unsupported_notes(chunks, rows, {5: 1, 6: 2}, tex_by_section={1: "\\begin{figure*}x\\end{figure*}"})
    assert any("table" in n and "pages 1–2" in n for n in notes)
    assert any("figure*" in n for n in notes)


def test_reopened_box_step_back_with_real_counter_shape():
    # head written BEFORE the box opens (pre-step), first sentence inside after
    tr = align_translation(_section(EN), _tf(EN, lambda c: c))
    counters = {V(1, 2, 0): {"thmctr": 3}, V(1, 2, 1): {"thmctr": 4}}
    md = page_markdown(TwinPage(6, 2, pieces=[Piece(1, 2, 1, None)]), {1: _section(EN)},
                       {1: tr}, "de", counters)[0][0][1]
    assert "\\addtocounter{thmctr}{-1}" in md
