"""Section → print-PDF page ranges: placing the page marks."""

from parody.writers.pagemap import (build_ranges, insert_section_mark,
                                    read_pagemap)

MARK = "\\parodypagemark{one/alpha}"


def test_mark_goes_after_the_first_sectioning_command():
    tex = "\\section{Alpha}\n\\label{sec:alpha}\n\nBody.\n"
    out = insert_section_mark(tex, "one/alpha")
    assert out.startswith("\\section{Alpha}" + MARK)
    assert "\\label{sec:alpha}" in out


def test_starred_and_deeper_levels_are_recognised():
    for cmd in ("section*", "subsection", "subsubsection", "lab"):
        tex = "\\%s{T}\nBody.\n" % cmd
        out = insert_section_mark(tex, "one/alpha")
        assert out.startswith("\\%s{T}%s" % (cmd, MARK)), cmd


def test_braces_in_the_title_do_not_end_the_argument():
    tex = "\\section{The \\texttt{argv} array}\nBody.\n"
    out = insert_section_mark(tex, "one/alpha")
    assert out.startswith("\\section{The \\texttt{argv} array}" + MARK)


def test_math_and_escaped_braces_in_the_title():
    tex = "\\section{Sets $\\{x\\}$ and \\$5}\nBody.\n"
    out = insert_section_mark(tex, "one/alpha")
    assert out.startswith("\\section{Sets $\\{x\\}$ and \\$5}" + MARK)


def test_optional_argument_is_skipped():
    tex = "\\section[Short]{Long title}\nBody.\n"
    out = insert_section_mark(tex, "one/alpha")
    assert out.startswith("\\section[Short]{Long title}" + MARK)


def test_headless_section_gets_the_mark_at_the_top():
    # #576: a section whose markdown opens with no heading — its title comes
    # from parody.yaml. It still needs a page mark.
    tex = "Body text with no heading at all.\n"
    out = insert_section_mark(tex, "one/alpha")
    assert out.startswith(MARK)
    assert "Body text" in out


def test_unbalanced_braces_fail_safe_to_the_top():
    tex = "\\section{Never closed\nBody.\n"
    out = insert_section_mark(tex, "one/alpha")
    assert out.startswith(MARK)


def test_the_key_is_used_verbatim():
    out = insert_section_mark("\\section{A}\n", "ch-two/sub-sec")
    assert "\\parodypagemark{ch-two/sub-sec}" in out


# Reading the marks back ----------------------------------------------------

# Verified against TeX Live 2026 with a probe compile: zref-abspage records
# BOTH the printed page and the physical one, and they differ because front
# matter is roman-numbered and \mainmatter restarts the arabic count.
AUX = """\
\\relax
\\@writefile{toc}{\\contentsline {chapter}{One}{1}{}}
\\zref@newlabel{parodypage@one/lead-in}{\\default{1}\\page{1}\\abspage{3}}
\\zref@newlabel{parodypage@one/alpha}{\\default{1.1}\\page{2}\\abspage{4}}
\\zref@newlabel{parodypage@one/beta}{\\default{1.2}\\page{3}\\abspage{9}}
\\zref@newlabel{parodypage@@end}{\\default{1.2}\\page{3}\\abspage{11}}
\\newlabel{sec:alpha}{{1.1}{4}{Alpha}{section.1.1}{}}
\\gdef\\zref@default{}
"""


def test_read_pagemap_reads_abspage_not_printed_page(tmp_path):
    aux = tmp_path / "main.aux"
    aux.write_text(AUX)
    got = read_pagemap(aux)
    # \page{1} vs \abspage{3}: roman front matter makes them differ.
    assert got["one/lead-in"] == 3
    assert got["one/alpha"] == 4
    assert got["@end"] == 11


def test_read_pagemap_ignores_other_labels(tmp_path):
    aux = tmp_path / "main.aux"
    aux.write_text(AUX)
    assert "sec:alpha" not in read_pagemap(aux)


def test_read_pagemap_missing_file_is_empty(tmp_path):
    assert read_pagemap(tmp_path / "nope.aux") == {}


def test_sections_sharing_a_sheet_both_carry_it():
    # lead-in ends on page 4 and alpha starts on page 4: the shared sheet
    # belongs to both PDFs, which is the duplication the task accepts.
    order = ["one/lead-in", "one/alpha"]
    pages = {"one/lead-in": 3, "one/lead-in@end": 4,
             "one/alpha": 4, "one/alpha@end": 5}
    got = build_ranges(order, pages, end_page=5)
    assert got == {"one/lead-in": [3, 4], "one/alpha": [4, 5]}


def test_a_chapter_break_does_not_hand_over_the_next_chapters_page():
    # THE bug this rule exists for: \chapter forces a page break, so alpha's
    # content ends on 5 while the next chapter opens on 7. Taking the next
    # section's start outright would end alpha's PDF with chapter two's title
    # page. Page 6 (a blank verso) must still be covered, or printing every
    # section no longer reassembles the book.
    order = ["one/alpha", "two/beta"]
    pages = {"one/alpha": 4, "one/alpha@end": 5,
             "two/beta": 7, "two/beta@end": 7}
    got = build_ranges(order, pages, end_page=7)
    assert got["one/alpha"] == [4, 6]
    assert got["two/beta"] == [7, 7]


def test_the_book_is_covered_with_no_gaps():
    order = ["one/lead-in", "one/alpha", "two/beta"]
    pages = {"one/lead-in": 3, "one/lead-in@end": 4,
             "one/alpha": 4, "one/alpha@end": 5,
             "two/beta": 7, "two/beta@end": 7}
    got = build_ranges(order, pages, end_page=7)
    covered = set()
    for start, end in got.values():
        covered.update(range(start, end + 1))
    assert covered == set(range(3, 8))  # every body page, none missing


def test_a_section_with_no_end_mark_falls_back_to_its_start():
    order = ["one/alpha", "two/beta"]
    pages = {"one/alpha": 4, "two/beta": 7, "two/beta@end": 7}
    got = build_ranges(order, pages, end_page=7)
    assert got["one/alpha"] == [4, 6]


def test_ranges_skip_sections_that_produced_no_mark():
    order = ["one/lead-in", "one/missing", "one/beta"]
    pages = {"one/lead-in": 3, "one/lead-in@end": 4, "one/beta": 9}
    got = build_ranges(order, pages, end_page=11)
    assert "one/missing" not in got
    assert got["one/lead-in"] == [3, 8]


def test_a_backwards_end_never_produces_an_inverted_range():
    order = ["one/a", "one/b"]
    pages = {"one/a": 7, "one/b": 5}
    got = build_ranges(order, pages, end_page=9)
    assert got["one/a"] == [7, 7]


def test_empty_inputs_are_empty():
    assert build_ranges([], {}, end_page=1) == {}
