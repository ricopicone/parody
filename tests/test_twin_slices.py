"""Cutting a translated chunk at the sentence where its English page broke (task #825)."""

from parody.twin.slices import slice_chunk


def test_whole_chunk():
    s = slice_chunk("Eins. Zwei. Drei.", "de", 0, None, 2)
    assert (s.text, s.approximate, s.reopened) == ("Eins. Zwei. Drei.", False, False)


def test_exact_slice():
    text = "Eins ist hier. Zwei ist da. Drei ist dort."
    assert slice_chunk(text, "de", 0, 1, 2).text == "Eins ist hier."
    assert slice_chunk(text, "de", 1, None, 2).text == "Zwei ist da. Drei ist dort."
    assert slice_chunk(text, "de", 1, 2, 2).text == "Zwei ist da."


def test_chinese_slice():
    text = "第一句。第二句。第三句。"
    assert slice_chunk(text, "zh", 2, None, 2).text == "第三句。"


def test_proportional_slice_when_counts_differ():
    # English had 3 boundaries (4 sentences), the translation merged two: 2 boundaries.
    text = "Eins. Zwei und drei. Vier."
    s = slice_chunk(text, "de", 2, None, 3)
    assert s.approximate
    assert s.text in ("Zwei und drei. Vier.", "Vier.")


def test_slice_never_cuts_inside_maths():
    text = "Wir haben $a. B$ hier. Dann $$x. Y$$ dort. Ende."
    for start in range(0, 4):
        piece = slice_chunk(text, "de", start, None, 3).text
        assert piece.count("$") % 2 == 0


def test_div_closed_and_reopened_without_id():
    text = "::: {#def:x .definition}\nErster Satz. Zweiter Satz.\n:::"
    first = slice_chunk(text, "de", 0, 1, 1)
    second = slice_chunk(text, "de", 1, None, 1)
    assert first.text == "::: {#def:x .definition}\nErster Satz.\n\n:::"
    assert second.reopened
    assert second.text == "::: {.definition}\nZweiter Satz.\n:::"


def test_nested_divs_reopen_in_order():
    text = "::: {.example}\n::: {#c .cloze}\nEins. Zwei.\n:::\n:::"
    second = slice_chunk(text, "de", 1, None, 1)
    assert second.text.startswith("::: {.example}\n::: {.cloze}\nZwei.")


def test_bare_div_name_reopens_as_is():
    second = slice_chunk("::: example\nEins. Zwei.\n:::", "de", 1, None, 1)
    assert second.text == "::: example\nZwei.\n:::"
