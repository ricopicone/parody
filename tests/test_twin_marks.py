"""Sentence boundaries and the marks that map English pages (task #825)."""

import pytest

from parody.translate.chunks import split_chunks
from parody.twin.marks import decode, mark_section, sentence_starts


def _words_at(text, offsets):
    return [text[o:].split()[0] for o in offsets]


def test_english_boundaries():
    text = "One. Two! Three? four. $a. B$ Five."
    # "four." is followed by lowercase and "$a. B$" is maths: neither starts one.
    assert _words_at(text, sentence_starts(text)) == ["Two!", "Three?"]


def test_newline_boundary():
    text = "word.\nNext one."
    assert _words_at(text, sentence_starts(text)) == ["Next"]


def test_closing_quote_and_bracket():
    text = 'He said "stop." Then (it ended.) After.'
    assert _words_at(text, sentence_starts(text)) == ["Then", "After."]


@pytest.mark.parametrize("text", [
    "$$x. Yes$$ more",
    "`a. B` more",
    "![A. B](x.pdf) more",
    "[x]{title=\"A. B\"} more",
    "# Heading. Two",
    "| a. B | c |",
    "\\begin{align}x. Y\\end{align} more",
])
def test_protected_regions(text):
    assert sentence_starts(text) == []


def test_chinese_boundaries():
    text = "第一句。第二句！第三句"
    assert _words_at(text, sentence_starts(text, "zh")) == ["第二句！第三句", "第三句"]


def test_korean_boundaries():
    text = "첫 문장이다. 둘째 문장."
    assert _words_at(text, sentence_starts(text, "ko")) == ["둘째"]


def test_german_needs_uppercase_after():
    text = "Das ist z. b. gut. Der Rest."
    assert _words_at(text, sentence_starts(text, "de")) == ["Der"]


def test_mark_section_paragraph_head_is_own_block():
    assert mark_section("First. Second.", 2).startswith(
        "\\parodys{2001000}\n\nFirst. \\parodys{2001001}Second.")


def test_mark_section_list_head_is_inline():
    assert mark_section("- a item.\n\n- b item.", 1) == (
        "- \\parodys{1001000}a item.\n\n- \\parodys{1002000}b item.\n\n\\parodysoff")


@pytest.mark.parametrize("start", ["> quoted.", "[^3]: A note.", "1.  numbered.",
                                   "a.  lettered.", ":   a definition."])
def test_mark_section_inline_heads(start):
    marked = mark_section(start, 1)
    # inline after the marker, so a list, quote or footnote is not broken up
    assert "\\parodys{1001000}" in marked and not marked.startswith("\\parodys")


def test_mark_section_sentences():
    marked = mark_section("Intro.\n\nOne. Two. Three.", 3)
    assert "Two. \\parodys{3002002}Three." in marked
    assert "\\parodys{3002000}\n\nOne. \\parodys{3002001}Two." in marked


def test_marks_keep_the_chunk_count():
    body = "# H\n\nPara one. Two.\n\n- a.\n\n- b.\n\n::: definition\n\nX. Y.\n\n:::"
    plain = split_chunks(body)
    marked = [c for c in split_chunks(mark_section(body, 1))
              if not c.startswith("\\parodys")]
    assert len(marked) == len(plain)


def test_decode():
    assert decode(3002005) == (3, 1, 5)
    assert decode(1001000) == (1, 0, 0)


def test_limits_raise():
    with pytest.raises(ValueError):
        mark_section("\n\n".join(f"P{i}." for i in range(1000)), 1)
    with pytest.raises(ValueError):
        mark_section("x", 2148)


def test_a_sentence_is_not_a_list_marker():
    assert mark_section("One. Two.", 1).startswith("\\parodys{1001000}\n\nOne.")
    assert mark_section("B. Russell wrote it.", 1).startswith("\\parodys{1001000}\n\nB.")


def test_mark_section_ends_with_the_mark_cleared():
    # Otherwise the section's last mark rides on into the next chapter's
    # heading and the back matter.
    assert mark_section("Only. Two.", 1).endswith("\n\n\\parodysoff")


def test_div_head_mark_goes_inside_the_div():
    # A breakable box is rebuilt at a page break; a head mark outside the div
    # would not be re-run, and the box's opening lines would carry no mark.
    # After the first word, not before it: as the box's first token the mark
    # changed the box's layout (lines moved between pages in electronics).
    assert mark_section("::: {#c .definition}\nElectric charge is. Then more.\n:::", 1) == (
        "::: {#c .definition}\nElectric \\parodys{1001000}charge is. "
        "\\parodys{1001001}Then more.\n:::\n\n\\parodysoff")


def test_div_opening_with_a_block_keeps_its_head_outside():
    # Structural divs (subfigures) must hold only their own blocks: print.lua
    # reads each one as an image.
    assert mark_section("::: {.subfigures}\n![a](a.pdf)\n\n![b](b.pdf)\n:::", 1).startswith(
        "\\parodys{1001000}\n\n::: {.subfigures}\n![a](a.pdf)")
    assert mark_section("::: example\n\n$$x$$\n\n:::", 1).startswith(
        "\\parodys{1001000}\n\n::: example")


def test_div_opening_with_raw_html_keeps_its_head_outside():
    # A mark after "<div>" became "\noindent \parodys{…}" + a blank line: an
    # empty paragraph that grew the box and moved lines to the next page.
    assert mark_section("::: example\n<div>\n\nAnswer this. Then that.\n\n</div>\n:::", 1).startswith(
        "\\parodys{1001000}\n\n::: example\n<div>")


def test_only_box_divs_take_their_head_inside():
    # print.lua parses some divs (further reading) structurally; a mark inside
    # one made it print the raw citations.
    assert mark_section("::: freadinglist\nHorowitz and Hill. More.\n:::", 1).startswith(
        "\\parodys{1001000}\n\n::: freadinglist")
    assert "Some \\parodys{1001000}text" in mark_section("::: {#t .theorem}\nSome text.\n:::", 1)
    assert "Some \\parodys{1001000}text" in mark_section("::: example\nSome text.\n:::", 1)
