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


def test_ranges_are_inclusive_and_tile_the_book():
    order = ["one/lead-in", "one/alpha", "one/beta"]
    starts = {"one/lead-in": 3, "one/alpha": 4, "one/beta": 9}
    got = build_ranges(order, starts, end_page=11)
    assert got == {
        "one/lead-in": [3, 4],   # shares page 4 with alpha — tolerated
        "one/alpha": [4, 9],     # shares page 9 with beta
        "one/beta": [9, 11],
    }
    # the tiling invariant: each range ends where the next begins
    keys = list(got)
    for a, b in zip(keys, keys[1:]):
        assert got[a][1] == got[b][0]


def test_ranges_skip_sections_that_produced_no_mark():
    order = ["one/lead-in", "one/missing", "one/beta"]
    starts = {"one/lead-in": 3, "one/beta": 9}
    got = build_ranges(order, starts, end_page=11)
    assert "one/missing" not in got
    assert got["one/lead-in"] == [3, 9]


def test_a_backwards_end_never_produces_an_inverted_range():
    order = ["one/a", "one/b"]
    starts = {"one/a": 7, "one/b": 5}
    got = build_ranges(order, starts, end_page=9)
    assert got["one/a"] == [7, 7]


def test_empty_inputs_are_empty():
    assert build_ranges([], {}, end_page=1) == {}
