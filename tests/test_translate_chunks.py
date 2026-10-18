"""Splitting a section into chunks, and aligning them by hash (task #825)."""

from parody.translate.chunks import (
    align_chunks,
    chunk_hash,
    split_chunks,
    split_frontmatter,
)


def test_frontmatter():
    meta, body = split_frontmatter("---\ntitle: V\nhash: o5\n---\n\n# V\n")
    assert meta == {"title": "V", "hash": "o5"}
    assert body.strip() == "# V"


def test_no_frontmatter():
    assert split_frontmatter("# V\n\nText.") == ({}, "# V\n\nText.")


def test_paragraphs_split_on_blank_lines():
    assert split_chunks("A\nb.\n\nC.\n\n\nD.") == ["A\nb.", "C.", "D."]


def test_display_math_with_blank_line_is_one_chunk():
    head = "Text: $$\\begin{aligned}\na &= b\n\nc &= d\\end{aligned}$$\nafter."
    assert split_chunks(head + "\n\nNext.") == [head, "Next."]


def test_fenced_div_with_blank_lines_is_one_chunk():
    body = "::: definition\n\nFor $v$.\n\n$$x$$\n\n:::\n\nAfter."
    assert split_chunks(body) == ["::: definition\n\nFor $v$.\n\n$$x$$\n\n:::", "After."]


def test_nested_divs():
    body = "::: a\n\n::: b\n\nx\n\n:::\n\n:::\n\ny"
    assert split_chunks(body) == ["::: a\n\n::: b\n\nx\n\n:::\n\n:::", "y"]


def test_four_colon_closer_closes_the_div():
    # Exercises in the problem sets open with :::: and close with ::::.
    body = (":::: {#marmoset .exercise}\n\nQ.\n\n::: {.exercise-solution}\n\nA.\n\n:::\n\n"
            "::::\n\n::: {#kestrel .exercise}\n\nQ2.\n\n:::")
    assert split_chunks(body) == [
        ":::: {#marmoset .exercise}\n\nQ.\n\n::: {.exercise-solution}\n\nA.\n\n:::\n\n::::",
        "::: {#kestrel .exercise}\n\nQ2.\n\n:::"]


def test_code_fence_with_blank_lines_and_colons_is_one_chunk():
    body = "```python\nx = 1\n\n::: not a div\n```\n\nz"
    assert split_chunks(body) == ["```python\nx = 1\n\n::: not a div\n```", "z"]


def test_dollars_inside_code_fence_do_not_open_math():
    body = "```\ncost = $$5\n```\n\nNext."
    assert split_chunks(body) == ["```\ncost = $$5\n```", "Next."]


def test_footnote_continuation_stays_with_its_definition():
    body = "[^3]: Alternatively, we could\n\n    solve for all four.\n\nNice!"
    assert split_chunks(body) == [
        "[^3]: Alternatively, we could\n\n    solve for all four.", "Nice!"]


def test_hash_ignores_surrounding_whitespace():
    assert chunk_hash("abc\n") == chunk_hash("abc")
    assert len(chunk_hash("abc")) == 12


def test_align_insert_edit_delete():
    stored = ["h1", "h2", "h3", "h4"]
    english = ["h1", "NEW", "h2", "h3x", "h5"]
    got = align_chunks(english, stored)
    assert got[0] == (0, 0, "current")
    assert got[1] == (1, None, "missing")
    assert got[2] == (2, 1, "current")
    assert got[3] == (3, 2, "stale")
    assert got[4] == (4, 3, "stale")


def test_align_deleted_chunk_is_dropped():
    assert align_chunks(["h1", "h3"], ["h1", "h2", "h3"]) == [
        (0, 0, "current"), (1, 2, "current")]


def test_align_with_nothing_stored():
    assert align_chunks(["a", "b"], []) == [(0, None, "missing"), (1, None, "missing")]


def test_align_replace_with_more_english_than_stored():
    got = align_chunks(["a", "x", "y", "b"], ["a", "old", "b"])
    assert got == [(0, 0, "current"), (1, 1, "stale"), (2, None, "missing"),
                   (3, 2, "current")]


def test_definition_list_stays_with_its_term():
    # Split here, pandoc reads the indented definition text as a code block.
    body = "Jordan form\n\n:   When $q_i = 1$, the problem\n\n    has solutions.\n\nAfter."
    assert split_chunks(body) == [
        "Jordan form\n\n:   When $q_i = 1$, the problem\n\n    has solutions.", "After."]


def test_table_caption_stays_with_its_table():
    body = "| a | b |\n|---|---|\n| 1 | 2 |\n\nTable: Measurements.\n\nAfter."
    assert split_chunks(body) == ["| a | b |\n|---|---|\n| 1 | 2 |\n\nTable: Measurements.",
                                  "After."]
    body = "| a |\n|---|\n| 1 |\n\n: Measurements.\n\nAfter."
    assert split_chunks(body)[-1] == "After." and len(split_chunks(body)) == 2


def test_fenced_div_line_is_not_a_definition():
    assert split_chunks("Text.\n\n::: note\n\nx\n\n:::") == ["Text.", "::: note\n\nx\n\n:::"]
