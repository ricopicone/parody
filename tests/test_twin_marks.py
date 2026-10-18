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
    assert mark_section("Only. Two.", 1).endswith("\\parodysoff")


def _blocks(text):
    import json

    import pypandoc
    return json.loads(pypandoc.convert_text(text, "json", format="markdown"))["blocks"]


def test_a_section_ending_in_a_paragraph_leaves_it_open():
    # The ordinary build leaves a section's last paragraph open at the end of
    # its file, so the page-map label after the \input lands inside it. Closed
    # by the clearing mark, the paragraph moved that label onto the page's
    # vertical list, and a page break after it came out a line different
    # (robotics §3.3/§3.4).
    marked = mark_section("First. Second.\n\nThe last one ends here.", 1)
    assert marked.endswith("The last one ends here.\n\\parodysoff")
    last = _blocks(marked)[-1]
    assert last["t"] == "Para" and last["c"][-1]["t"] == "RawInline"


@pytest.mark.parametrize("text", [
    "- a item.\n- b item.",                           # a list
    "Text.[^1]\n\n[^1]: The note.",                    # inside a footnote it would be local
    "Text.[^1]\n\n[^1]: The note.\n\n    More note.",
    "| a |\n|---|\n| 1 |\n\nTable: The caption.",      # it would join the caption
    "::: {.example}\nInside.\n:::",                    # a div: closed by its end anyway
])
def test_the_clearing_mark_stays_a_block_after_anything_but_a_paragraph(text):
    assert mark_section(text, 1).endswith("\n\n\\parodysoff")


def test_div_head_mark_goes_inside_the_div():
    # A breakable box is rebuilt at a page break; a head mark outside the div
    # would not be re-run, and the box's opening lines would carry no mark.
    # After the first word, not before it: as the box's first token the mark
    # changed the box's layout (lines moved between pages in electronics).
    assert mark_section("::: {#c .definition}\nElectric charge is. Then more.\n:::", 1) == (
        "\\parodysctr{1001000}\n\n::: {#c .definition}\nElectric \\parodys{1001000}charge is. "
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


def test_a_display_ending_in_a_full_stop_ends_its_sentence():
    # "… equation is $$\begin{aligned} λ = F(i). \end{aligned}$$ An ideal …":
    # without this the display and the next sentence were one unit, and a page
    # break between them put the next sentence on the wrong twin page.
    text = "The equation is $$\\begin{aligned}\n  x = 1.\n\\end{aligned}$$ An ideal one follows."
    assert _words_at(text, sentence_starts(text)) == ["An"]
    # a display that does not end the sentence is not a boundary
    text = "We have $$x = 1,$$ Which is odd."
    assert sentence_starts(text) == []


def test_german_abbreviations_are_not_sentence_ends():
    # German nouns are capitalised, so "z. B. Spannung" looked like two sentence ends.
    text = "Größen (z. B. Spannung und Strom), d. h. Werte, vgl. Abb. 3. Der Rest folgt."
    assert _words_at(text, sentence_starts(text, "de")) == ["Der"]


def test_english_abbreviations_are_not_sentence_ends():
    text = "Use e.g. Ohm's law, cf. Fig. 2. Then stop."
    assert _words_at(text, sentence_starts(text)) == ["Then"]


def test_french_and_spanish_abbreviations():
    assert _words_at("Voir p. ex. Ohm. La suite.", sentence_starts("Voir p. ex. Ohm. La suite.", "fr")) == ["La"]
    assert _words_at("Ver p. ej. Ohm. Lo demás.", sentence_starts("Ver p. ej. Ohm. Lo demás.", "es")) == ["Lo"]


@pytest.mark.parametrize("text,lang", [
    ("Die Summe ist null.[^2]", "de"),
    ("各电压降之和为零。[^2]", "zh"),
    ("Erster Satz.\n:::", "de"),
    ("第一句。\n:::", "zh"),
])
def test_a_boundary_needs_a_sentence_after_it(text, lang):
    assert sentence_starts(text, lang) == []


def test_a_sentence_may_open_with_markup():
    text = "Choose the direction. [The physical situation]{.cloze} prescribes it. *Then* go."
    assert _words_at(text, sentence_starts(text)) == ["[The", "*Then*"]


def test_every_block_inside_a_chunk_starts_a_unit():
    # A figure or display between paragraphs of a box is a clean place to cut;
    # without this one unit ran from "Setting …" through a figure into the next
    # paragraph and went wholesale to the wrong page.
    text = ("::: example\nSetting it, we get\n\n$$x = 1.$$\n\n![a figure](a.pdf)\n\n"
            "now more text.\n\n:::")
    # in a box the figure is a unit too (marked as a paragraph of its own)
    assert _words_at(text, sentence_starts(text)) == ["$$x", "![a", "now"]
    assert _words_at(text, sentence_starts(text, "zh")) == ["$$x", "![a", "now"]


# (a list item is a unit, but after its marker: test_each_list_item_starts_a_unit_after_its_marker)
@pytest.mark.parametrize("block", ["```python\nx = 1\n```", "# Heading", "| a | b |",
                                   "![fig](a.pdf)", "\\begin{align}x\\end{align}",
                                   "<div>x</div>", "> quoted"])
def test_blocks_that_cannot_take_an_inline_mark_are_not_units(block):
    # (a div that is not a box: in a box a figure is a unit of its own)
    text = f"::: aside\nSome prose.\n\n{block}\n\n:::"
    assert sentence_starts(text) == []


def test_each_list_item_starts_a_unit_after_its_marker():
    text = "Answer these:\n\n1.  What is a?\n2.  What is b?\n\n- one\n- two"
    assert _words_at(text, sentence_starts(text)) == ["What", "What", "one", "two"]
    marked = mark_section(text, 1)  # chunks: the intro, the numbered list, the bullets
    assert "2.  \\parodys{1002001}What is b?" in marked
    assert "- \\parodys{1003001}two" in marked


def test_first_prose_line_in_a_nested_div_starts_a_unit():
    text = "::: example\nQuestion here\n\n::: {.example-solution}\nThe answer here\n:::\n:::"
    assert _words_at(text, sentence_starts(text)) == ["The"]


def test_list_units_line_up_between_languages():
    en = "Do these:\n\n1.  What is it?\n2.  Why is it?"
    zh = "做这些：\n\n1.  它是什么？\n2.  为什么？"
    assert len(sentence_starts(en)) == len(sentence_starts(zh, "zh")) == 2


def test_a_box_logs_its_counters_before_it_opens():
    # The inside head mark runs after \begin{definition} has stepped thmctr;
    # restored from it, a page opening on the box printed the next number.
    marked = mark_section("::: {#d .definition}\nVoltage is a thing. More.\n:::", 1)
    assert marked.startswith("\\parodysctr{1001000}\n\n::: {#d .definition}\nVoltage \\parodys{1001000}is")


def test_a_figure_inside_a_box_is_a_unit_of_its_own():
    text = "::: {.example}\nSee this.\n\n![a figure](a.pdf){#fig:a}\n\nThen more.\n:::"
    assert [text[o:o + 3] for o in sentence_starts(text)] == ["![a", "The"]
    assert "\\parodys{1001001}\n\n![a figure](a.pdf){#fig:a}" in mark_section(text, 1)


def test_a_figure_inside_a_subfigure_div_is_not_a_unit():
    text = "::: {.subfigures}\n![a](a.pdf)\n\n![b](b.pdf)\n:::"
    assert sentence_starts(text) == []


def test_a_figure_in_a_subfigure_div_nested_in_a_box_is_not_a_unit():
    # print.lua reads a subfigures div as nothing but images; a mark between
    # them crashed it (seen in the electronics problem sets).
    text = ("::: {.exercise}\nSolve it.\n\n::: {.subfigures}\n![a](a.pdf)\n\n![b](b.pdf)\n:::\n\n"
            "Then explain.\n:::")
    assert [text[o:o + 4] for o in sentence_starts(text)] == ["Then"]


def test_no_marks_inside_a_figure_div():
    # A mark in a figure's caption lands in \figcaption{…}, a moving argument
    # where it is a TeX error; and a cut there would split the figure.
    chunk = ('::: {#fig:real_sources .figure .subfigures rows=1}\n\n'
             '![Real voltage source model](a.pdf){#fig:a .subfigure .figure}\n\n'
             '![Real current source model.](b.pdf){#fig:b .subfigure .figure}\n\n'
             'Models for power-limited "real" sources. They sag under load.\n'
             ':::')
    assert sentence_starts(chunk) == []
    marked = mark_section(chunk, 1)
    caption = marked[marked.index("Models"):]
    assert "\\parodys{" not in caption.split(":::")[0]


def test_figure_div_inside_a_box_is_one_unit():
    chunk = ('::: {.example}\nFirst we look. Then we see.\n\n'
             '::: {#fig:x .figure .subfigures}\n\n![A.](a.pdf){#fig:xa .subfigure}\n\n'
             'The caption. More of it.\n:::\n\nAfter the figure.\n:::')
    starts = sentence_starts(chunk)
    fig_open, fig_close = chunk.index("::: {#fig:x"), chunk.index(":::\n\nAfter")
    assert not any(fig_open < s < fig_close for s in starts)
    assert chunk.index("After the figure.") in starts


def test_no_marks_in_a_table_caption():
    chunk = "| a | b |\n|---|---|\n| 1 | 2 |\n\nTable: Measured values. Taken at noon. {#tbl:m}"
    assert sentence_starts(chunk) == []


def test_a_definition_list_stays_one_list():
    # Each term and its definition is a chunk of its own. A head mark on its
    # own line before a term ended the list there: one description
    # environment per item, with list spacing between them, so the marked
    # English paginated differently from the published PDF (robotics §1.2).
    import json

    import pypandoc

    text = ("robots are cool\n\n:   One reason. Another.\n\n"
            "biology is cool\n\n:   A related reason.\n\n"
            "robots help\n:   Make things.")
    marked = mark_section(text, 1)
    blocks = json.loads(pypandoc.convert_text(marked, "json", format="markdown"))["blocks"]
    assert [b["t"] for b in blocks] == ["DefinitionList", "RawBlock"]  # then \parodysoff
    assert ":   \\parodys{1002000}A related reason." in marked
    assert "\\parodys{1001001}Another." in marked


def test_a_lettered_list_after_a_paragraph_stays_a_list():
    # A mark before "a." made it text: the list ran on as one paragraph.
    import json

    import pypandoc

    text = ("::: {.exercise}\nFor each device below:\n\n"
            "a.  give a verdict;\nb.  name what it lacks.\n:::")  # one chunk
    marked = mark_section(text, 1)
    blocks = json.loads(pypandoc.convert_text(marked, "json", format="markdown"))["blocks"]
    (div,) = [b for b in blocks if b["t"] == "Div"]
    assert [b["t"] for b in div["c"][1]] == ["Para", "OrderedList"]
    assert "\n\na.  \\parodys{1001001}give" in marked


def test_a_paragraph_after_a_closing_fence_is_not_a_nested_div():
    # ":::" then a blank line then prose read as a div opener whose first
    # line was the paragraph's, so its second line took a mark mid-sentence.
    text = ("::: inlinelist\n-   a datacenter.\n:::\n\n"
            "Part (d) is the point. If you cannot flip\nthe verdict, say so.")
    starts = [text[s:s + 6] for s in sentence_starts(text)]
    assert "the ve" not in starts
