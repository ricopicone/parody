"""The preservation check every translated chunk must pass (task #825).

The fixture is Electronics Primer §1.3 *Voltage dividers*, the section the
trial ran on: inline and display maths, blanks in prose and in maths, a key
term, a figure and its reference, a section link, a footnote and two
definition boxes.
"""

from pathlib import Path

from parody.translate.check import (
    add_keyword_glosses,
    chunk_facts,
    compare_chunks,
)
from parody.translate.chunks import split_chunks, split_frontmatter

FIXTURE = Path(__file__).parent / "translate_fixtures" / "voltage-dividers.md"


def _chunks():
    _, body = split_frontmatter(FIXTURE.read_text(encoding="utf-8"))
    return split_chunks(body)


def _edit(chunks, needle, replacement):
    i = next(k for k, t in enumerate(chunks) if needle in t)
    out = list(chunks)
    out[i] = out[i].replace(needle, replacement, 1)
    return i, out


def test_facts_one_per_chunk():
    c = _chunks()
    facts = chunk_facts(c)
    assert len(facts) == len(c)
    assert sum(sum(f.math.values()) for f in facts) == 34
    assert sum(f.cloze for f in facts) == 3
    assert [k for f in facts for k in f.keywords] == ["voltage divider"]


def test_identical_chunks_pass():
    c = _chunks()
    assert compare_chunks(c, c) == {}


def test_one_space_in_maths_fails_for_that_chunk_only():
    c = _chunks()
    i, t = _edit(c, r"\frac{R_2} {R_1+R_2}", r"\frac{R_2}{R_1+R_2}")
    problems = compare_chunks(c, t)
    assert list(problems) == [i]
    assert any("maths" in p for p in problems[i])


def test_dropped_cloze_fails():
    c = _chunks()
    i, t = _edit(c, "[the relative resistances]{.cloze}", "the relative resistances")
    assert any("blank" in p for p in compare_chunks(c, t)[i])


def test_dropped_keyword_fails():
    c = _chunks()
    i, t = _edit(c, "[voltage divider]{.keyword}", "voltage divider")
    assert any("key term" in p for p in compare_chunks(c, t)[i])


def test_translated_hashref_fails():
    c = _chunks()
    i, t = _edit(c, "[uy]{.hashref}", "[ui]{.hashref}")
    assert any("section link" in p for p in compare_chunks(c, t)[i])


def test_dropped_figure_id_fails():
    c = _chunks()
    i, t = _edit(c, "{#fig:voltage_divider_demo", "{")
    assert any("id" in p for p in compare_chunks(c, t)[i])


def test_dropped_cross_reference_fails():
    c = _chunks()
    i, t = _edit(c, "[@fig:voltage_divider_demo]", "the figure")
    assert any("cross-reference" in p for p in compare_chunks(c, t)[i])


def test_extra_paragraph_fails():
    c = _chunks()
    t = list(c)
    t[0] = t[0] + "\n\nAn extra paragraph."
    assert any("block" in p for p in compare_chunks(c, t)[0])


def test_unclosed_div_is_attributed_to_its_chunk():
    c = _chunks()
    i = next(k for k, t in enumerate(c) if t.startswith("::: definition"))
    t = list(c)
    t[i] = t[i].rsplit(":::", 1)[0]  # drop the closing fence
    problems = compare_chunks(c, t)
    assert i in problems


def test_en_attr_is_ignored():
    c = _chunks()
    _, t = _edit(c, "[voltage divider]{.keyword}",
                 '[voltage divider]{.keyword en="voltage divider"}')
    assert compare_chunks(c, t) == {}


def test_footnote_definition_chunk():
    c = _chunks()
    facts = chunk_facts(c)
    i = next(k for k, t in enumerate(c) if t.startswith("[^3]:"))
    assert facts[i].blocks == 0
    assert sum(f.notes for f in facts) == 1


def test_add_keyword_glosses():
    assert add_keyword_glosses("[分压器]{.keyword}是…", ["voltage divider"]) == (
        '[分压器]{.keyword en="voltage divider"}是…')


def test_add_keyword_glosses_count_mismatch_is_unchanged():
    assert add_keyword_glosses("[分压器]{.keyword}", ["a", "b"]) == "[分压器]{.keyword}"


def test_add_keyword_glosses_keeps_existing_en_and_other_spans():
    text = '[x]{.cloze} [分压器]{.keyword en="voltage divider"}'
    assert add_keyword_glosses(text, ["voltage divider"]) == text


def test_add_keyword_glosses_replaces_double_quotes():
    assert add_keyword_glosses("[a]{.keyword}", ['the "b" law']) == (
        '[a]{.keyword en="the ”b” law"}')
