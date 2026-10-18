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


def test_mismatched_counts_cut_at_the_nearest_relative_position():
    english = "One is here. Two is there. Three is far. Four ends it."
    # an extra boundary early in the translation (an abbreviation, say)
    german = "Eins ist hier. Ab. Zwei ist da. Drei ist weit. Vier beendet es."
    s = slice_chunk(german, "de", 3, None, english)
    assert s.approximate and s.text == "Vier beendet es."


def test_a_cut_at_a_list_item_keeps_its_marker():
    text = "做这些：\n\n1.  它是什么？\n2.  为什么？"
    first = slice_chunk(text, "zh", 0, 2, 2)
    second = slice_chunk(text, "zh", 2, None, 2)
    assert first.text == "做这些：\n\n1.  它是什么？"
    assert second.text == "2.  为什么？"


def test_reopened_box_drops_h_and_only_real_ids():
    text = '::: {#box:x .infobox h="ex:1" title="Note #3 on Ohm"}\nEins. Zwei.\n:::'
    second = slice_chunk(text, "de", 1, None, 1)
    assert second.text.startswith('::: {.infobox title="Note #3 on Ohm"}\nZwei.')


def test_raw_html_divs_inside_a_box_are_closed_and_reopened_too():
    # Electronics examples wrap their text in <div>…</div> inside the fenced
    # div; closing only the fence printed a stray ":::" on the twin page.
    text = "::: example\n<div>\n\nEins. Zwei.\n\n</div>\n:::"
    first = slice_chunk(text, "de", 0, 1, 1)
    second = slice_chunk(text, "de", 1, None, 1)
    assert first.text == "::: example\n<div>\n\nEins.\n\n</div>\n\n:::"
    assert second.text == "::: example\n<div>\n\nZwei.\n\n</div>\n:::"


def test_a_cut_at_a_block_maps_to_the_same_block():
    # The translation keeps the English blocks one for one, so a cut at a
    # block (a figure, a paragraph) lands at that block even when the
    # sentence counts differ; proportionally, a figure slid onto the page
    # before and the next page's figure numbers fell one behind (robotics).
    # English runs long before the figure, the Chinese short: by relative
    # position the figure's cut fell in the Chinese after it.
    english = ("::: {.exercise}\nThe first sentence goes on for quite a while here. "
               "The second sentence also takes its time to finish.\n\n"
               "![A chain.](c.pdf){#fig:c}\n\nThe third.\n:::")
    chinese = ("::: {.exercise}\n第一句。第二句。第二句半。\n\n"
               "![链。](c.pdf){#fig:c}\n\n第三句话非常非常非常非常非常非常非常非常非常非常长。\n:::")
    before = slice_chunk(chinese, "zh", 0, 2, english)
    after = slice_chunk(chinese, "zh", 2, None, english)
    assert "![" not in before.text and before.text.endswith("第二句半。\n\n:::")
    assert after.text.startswith("::: {.exercise}\n![链。]")


def test_a_cut_inside_a_block_stays_inside_it():
    english = "One. Two. Three.\n\nFour. Five."
    german = "Eins. Zwei. Zwei b. Drei.\n\nVier. Fünf."
    # English boundary 4 is "Five", inside the second block
    assert slice_chunk(german, "de", 4, None, english).text == "Fünf."
    # boundary 2 ("Three") stays in the first block, never moving to "Vier"
    assert slice_chunk(german, "de", 0, 2, english).text.count("Vier") == 0


# A page that starts inside an indented block: the rest of the block keeps
# its indentation in the slice, and at the top of a page four spaces are a
# code block (robotics 1.3, both twins: a definition's nested list printed
# verbatim, colons and all).

NESTED = """Kameras

:   nehmen ein *Bild* auf. Die Verarbeitung ist schwer.

    Kantendetektion

    :   findet Kanten.

    Segmentierung

    :   gliedert ein Bild in Bereiche, die
        jeweils einem Objekt entsprechen.

Danach geht es weiter.
"""

NESTED_EN = """Cameras

:   capture an *image*. Processing is hard.

    Edge detection

    :   finds edges.

    Segmentation

    :   organizes an image into sections that
        correspond to an object.

Then it goes on.
"""


def test_a_cut_at_a_nested_term_outdents_the_rest_of_its_list():
    s = slice_chunk(NESTED, "de", 2, None, NESTED_EN)
    assert s.text == ("Kantendetektion\n\n:   findet Kanten.\n\nSegmentierung\n\n"
                      ":   gliedert ein Bild in Bereiche, die\n"
                      "    jeweils einem Objekt entsprechen.\n\nDanach geht es weiter.")


def test_a_cut_inside_a_definition_outdents_by_its_marker():
    # mid-line in the definition's own text: its content sits 4 in, past ":   "
    s = slice_chunk(NESTED, "de", 1, None, NESTED_EN)
    assert s.text.startswith("Die Verarbeitung ist schwer.\n\nKantendetektion\n\n:   findet")
    assert "\n    :" not in s.text


def test_a_nested_list_item_cut_keeps_its_marker_and_loses_the_indent():
    text = "- Eins. Mehr dazu.\n\n    - Zwei ist hier.\n      und geht weiter.\n\n- Drei."
    en = "- One. More on it.\n\n    - Two is here.\n      and goes on.\n\n- Three."
    s = slice_chunk(text, "de", 2, None, en)
    assert s.text == "- Zwei ist hier.\n  und geht weiter.\n\n- Drei."


def test_a_top_level_cut_is_left_alone():
    # a paragraph's own continuation line keeps whatever indent it had
    text = "Eins ist hier. Zwei ist da.\n    Weiter im Absatz."
    assert slice_chunk(text, "de", 1, None, 2).text == "Zwei ist da.\n    Weiter im Absatz."


def test_a_cut_in_a_nested_definition_outdents_its_siblings_by_the_outer_block():
    # robotics 1.4 (zh): cut inside the text of a definition nested in a
    # definition; the next term belongs to the OUTER definition's content
    text = ("Motoren\n\n:   Es gibt zwei Arten.\n\n    Induktion\n\n"
            "    :   nutzt Induktion. Die Drehzahl wird geregelt.\n\n"
            "    Synchron\n\n    :   dreht synchron, ohne\n        Schlupf.\n\nDanach.\n")
    en = ("Motors\n\n:   There are two kinds.\n\n    Induction\n\n"
          "    :   uses induction. The speed is controlled.\n\n"
          "    Synchronous\n\n    :   turns in sync, without\n        slip.\n\nThen.\n")
    from parody.twin.marks import sentence_starts
    i = 1 + next(k for k, b in enumerate(sentence_starts(en, "en")) if en[b:].startswith("The speed"))
    s = slice_chunk(text, "de", i, None, en)
    assert s.text == ("Die Drehzahl wird geregelt.\n\nSynchron\n\n:   dreht synchron, ohne\n"
                      "    Schlupf.\n\nDanach.")
