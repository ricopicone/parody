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


def test_an_outdented_nested_list_does_not_run_on_into_the_outer_one():
    # electronics 3.3 (both twins): the page starts in a list nested under
    # item 6; outdented, it ran on into the outer item 7, which printed as 4
    import json

    import pypandoc

    from parody.twin.marks import sentence_starts
    from parody.writers.latex import PANDOC_FROM

    text = ("5.  Fünf.\n\n6.  Sechs ist hier. Dann:\n\n    1.  Eins ist hier.\n\n"
            "    2.  Zwei ist da.\n\n7.  Sieben.\n")
    en = ("5.  Five.\n\n6.  Six is here. Then:\n\n    1.  One is here.\n\n"
          "    2.  Two is there.\n\n7.  Seven.\n")
    i = 1 + next(k for k, b in enumerate(sentence_starts(en, "en")) if en[b:].startswith("One"))
    s = slice_chunk(text, "de", i, None, en)
    assert s.text.startswith("1.  Eins ist hier.")
    blocks = json.loads(pypandoc.convert_text(s.text, "json", format=PANDOC_FROM))["blocks"]
    lists = [(b["c"][0][0], len(b["c"][1])) for b in blocks if b["t"] == "OrderedList"]
    assert lists == [(1, 2), (7, 1)]


def _blocks_of(markdown):
    import json

    import pypandoc

    from parody.writers.latex import PANDOC_FROM
    return json.loads(pypandoc.convert_text(markdown, "json", format=PANDOC_FROM))["blocks"]


def _cut_at(en, sentence):
    from parody.twin.marks import sentence_starts
    return 1 + next(k for k, b in enumerate(sentence_starts(en, "en")) if en[b:].startswith(sentence))


def test_a_cut_inside_a_tight_item_keeps_the_next_item_an_item():
    # robotics 1.8 (zh): exercise parts with no blank line between them; the
    # page starts in part (a)'s text, and (b) and (c) ran in as plain text
    text = "a.  Erstens ist hier. Weiter\n    im Text.\nb.  Zweitens.\nc.  Drittens.\n"
    en = "a.  First is here. Going\n    in the text.\nb.  Second.\nc.  Third.\n"
    s = slice_chunk(text, "de", _cut_at(en, "Going"), None, en)
    assert s.text.startswith("Weiter\nim Text.")
    blocks = _blocks_of(s.text)
    assert [b["t"] for b in blocks if b["t"] != "RawBlock"] == ["Para", "OrderedList"]
    lst = next(b for b in blocks if b["t"] == "OrderedList")
    assert lst["c"][0][0] == 2 and len(lst["c"][1]) == 2


def test_a_cut_inside_a_tight_bullet_keeps_the_next_bullet_a_bullet():
    text = "- Eins ist hier. Weiter\n  im Text.\n- Zwei.\n- Drei.\n"
    en = "- One is here. Going\n  in the text.\n- Two.\n- Three.\n"
    s = slice_chunk(text, "de", _cut_at(en, "Going"), None, en)
    assert [b["t"] for b in _blocks_of(s.text)] == ["Para", "BulletList"]


def test_a_cut_in_a_tight_nested_item_keeps_its_outer_sibling_an_item():
    # the item that follows sits inside a block still open at the cut
    text = ("Begriff\n\n:   Es gibt:\n\n    1.  Eins ist hier. Weiter\n        im Text.\n"
            "    2.  Zwei.\n\nDanach.\n")
    en = ("Term\n\n:   There are:\n\n    1.  One is here. Going\n        in the text.\n"
          "    2.  Two.\n\nThen.\n")
    s = slice_chunk(text, "de", _cut_at(en, "Going"), None, en)
    lists = [(b["c"][0][0], len(b["c"][1])) for b in _blocks_of(s.text) if b["t"] == "OrderedList"]
    assert lists == [(2, 1)]


# A footnote defined inside the chunk that refers to it (an exercise, an
# example, a list item): the definition travelled with whichever slice held its
# text, so a page cut between them printed a literal [^x] on one page and lost
# the note on the next (robotics' differential-drive example, electronics'
# decibels exercise); a cut inside it made its tail body text.

NOTED = ("::: {.example}\nDer Wagen fährt.[^rad] Er dreht sich. Danach hält er.\n\n"
         "[^rad]: Das Rad rollt. Es gleitet nicht.\n\nZum Schluss steht er.\n:::\n")
NOTED_EN = ("::: {.example}\nThe cart rolls.[^rad] It turns. Then it stops.\n\n"
            "[^rad]: The wheel rolls. It does not slip.\n\nAt last it stands.\n:::\n")


def test_a_nested_footnote_definition_is_in_no_slice():
    from parody.twin.marks import sentence_starts
    n = len(sentence_starts(NOTED_EN, "en"))
    for cut in range(1, n + 1):
        left = slice_chunk(NOTED, "de", 0, cut, NOTED_EN).text
        right = slice_chunk(NOTED, "de", cut, None, NOTED_EN).text
        for piece in (left, right):
            assert "[^rad]:" not in piece, (cut, piece)
            assert "Es gleitet nicht" not in piece, (cut, piece)


def test_nested_footnote_definitions_are_collected_whole():
    from parody.twin.slices import footnote_definitions
    assert footnote_definitions(NOTED) == ["[^rad]: Das Rad rollt. Es gleitet nicht."]
    nested = ("a.  Erstens.[^x]\n\n    [^x]: Eine Notiz\n        über zwei Zeilen.\n\n"
              "        Und ein zweiter Absatz.\n\nb.  Zweitens.\n")
    assert footnote_definitions(nested) == [
        "[^x]: Eine Notiz\n    über zwei Zeilen.\n\n    Und ein zweiter Absatz."]
    assert footnote_definitions("Kein Fußnotentext.") == []


# A cut inside inline emphasis left each half unbalanced: a literal "*" or
# "**" on the twin page (robotics zh/de exercise notes, electronics zh
# "**系统化方法。**").

def _cut_pair(text, lang, en, cut):
    return (slice_chunk(text, lang, 0, cut, en).text, slice_chunk(text, lang, cut, None, en).text)


def test_a_cut_before_the_closing_emphasis_moves_past_it():
    # the zh rule cuts after 。 with no space, so before the closing "**";
    # an English of as many sentences maps cut 1 onto exactly that boundary
    text = "2.  **系统化方法。** 现在完整地遵循方法。写出方程。\n"
    en = "2.  Systematic method. Now follow the method fully. Write the equations.\n"
    from parody.twin.marks import sentence_starts
    assert text[sentence_starts(text, "zh")[0]:].startswith("**")
    assert len(sentence_starts(text, "zh")) == len(sentence_starts(en, "en"))
    left, right = _cut_pair(text, "zh", en, 1)
    assert left.endswith("**系统化方法。**"), left
    assert right.startswith("现在"), right


def test_emphasis_open_at_a_cut_is_closed_and_reopened():
    text = "Bestimmen Sie $M'$.\n\n*Stützt sich auf [@sec:a]. Der Buchstabe stammt aus der Übung.*\n"
    en = "Find $M'$.\n\n*Draws on [@sec:a]. The letter comes from the exercise.*\n"
    left, right = _cut_pair(text, "de", en, 2)
    assert left.endswith("*Stützt sich auf [@sec:a].*"), left
    assert right == "*Der Buchstabe stammt aus der Übung.*", right


def test_bullets_and_maths_do_not_count_as_emphasis():
    text = "* Eins hat $a*b$ hier. Zwei folgt.\n* Drei.\n"
    en = "* One has $a*b$ here. Two follows.\n* Three.\n"
    left, right = _cut_pair(text, "de", en, 1)
    assert not left.endswith("*") and not right.startswith("*"), (left, right)


def test_an_under_indented_continuation_keeps_the_next_item_an_item():
    # robotics intro/problems: items whose continuation lines are indented 3
    # under content at 4. Pandoc reads them as the item's; the outdent read
    # them as ending it, and "d." ran in to the paragraph as words.
    text = "a.  Erstens ist hier. Weiter\n   im Text, zu wenig eingerückt.\nb.  Zweitens.\n"
    en = "a.  First is here. Going\n   on in the text, under-indented.\nb.  Second.\n"
    right = slice_chunk(text, "de", _cut_at(en, "Going"), None, en).text
    blocks = [b for b in _blocks_of(right) if b["t"] != "RawBlock"]
    assert [b["t"] for b in blocks] == ["Para", "OrderedList"], right


def test_an_example_list_marker_travels_with_its_item_and_its_number():
    # "@." was cut off its item (a literal "@." on the twin page), and every
    # twin page restarted the example numbers at 1
    text = "Beispiele:\n\n@. Ein Roomba.\n@. Ein Desktop-Computer.\n@. Ein Toaster.\n"
    en = "Examples:\n\n@. A Roomba.\n@. A desktop computer.\n@. A toaster.\n"
    left = slice_chunk(text, "de", 0, 2, en).text
    right = slice_chunk(text, "de", 2, None, en).text
    assert not left.rstrip().endswith("@."), left
    lists = [(b["c"][0][0], len(b["c"][1])) for b in _blocks_of(right) if b["t"] == "OrderedList"]
    assert lists == [(2, 2)], (right, lists)


def test_a_slice_opening_on_a_list_marker_mid_paragraph_keeps_it_as_text():
    # a wrapped line starting "(iii)": the boundary falls after it, the cut
    # moved back to the line start so the "marker" travelled, and the slice
    # began with "(iii)", which pandoc read as a list marker and dropped
    text = "Er ordnet ein: (i) gut, (ii) schlecht oder\n(iii) angemessen. Begründen Sie.\n"
    en = "He classifies: (i) good, (ii) bad or\n(iii) fair. Justify each.\n"
    from parody.twin.marks import sentence_starts
    starts = sentence_starts(text, "de")
    assert text[starts[0]:].startswith("angemessen") and len(starts) == len(sentence_starts(en, "en"))
    right = slice_chunk(text, "de", 1, None, en).text
    (block,) = _blocks_of(right)
    assert block["t"] == "Para", right
    assert block["c"][0] == {"t": "Str", "c": "(iii)"}, block["c"][:2]


def test_an_item_right_after_a_fence_is_an_item():
    # a list straight after "::: example-solution" is a list: escaping its
    # first marker made "1." text in every solution that opened a page
    text = "Frage eins?\n\n::: example-solution\n1.  Erstens ist es so.\n2.  Zweitens.\n:::\n"
    en = "Question one?\n\n::: example-solution\n1.  First it is so.\n2.  Second.\n:::\n"
    right = slice_chunk(text, "de", 1, None, en).text
    assert "\\\\" not in right, right
    lists = [b for b in _blocks_of(right) if b["t"] == "Div"]
    assert lists and lists[0]["c"][1][0]["t"] == "OrderedList", right
