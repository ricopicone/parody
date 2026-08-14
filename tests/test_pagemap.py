"""Section → print-PDF page ranges: placing the page marks."""

from parody.writers.pagemap import insert_section_mark

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
