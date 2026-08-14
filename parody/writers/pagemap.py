"""Section → print-PDF page ranges.

The print PDF is built once; each section's PDF is the page range cut out of
it, never a separate compilation. A separately compiled section would start at
page 1, replace the book's float placement, and reset every counter, which
destroys the property the feature exists for: print one section at a time and
it becomes the whole book.

This module owns the three steps that turn a LaTeX build into a range table:

    insert_section_mark   place a \\parodypagemark in a generated section .tex
    read_pagemap          read the marks' absolute pages back out of main.aux
    build_ranges          turn start pages into inclusive [start, end] ranges
"""

import re

# print.lua's headerer_latex emits these; \lab is the MIT-class-private lab
# heading. Longer names first so \subsection is not matched as \section.
_SECTIONING = re.compile(
    r"\\(?:subsubsection|subsection|section|chapter|lab)\*?\s*(?=[\[{])")


def _skip_group(tex, i, open_ch, close_ch):
    """Index just past the balanced group starting at ``i``, or None.

    Honours TeX escaping: ``\\{`` is a literal brace, not a nesting level.
    """
    if i is None or i >= len(tex) or tex[i] != open_ch:
        return None
    depth = 0
    while i < len(tex):
        c = tex[i]
        if c == "\\":
            i += 2  # an escaped character, whatever it is
            continue
        if c == open_ch:
            depth += 1
        elif c == close_ch:
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return None


def insert_section_mark(tex, key):
    """Return ``tex`` with ``\\parodypagemark{key}`` after its first heading.

    The mark must land *after* the sectioning command, not before it: a mark in
    vertical mode ahead of a heading can be carried to the previous page by the
    page builder, which would start the range one page late and silently drop
    the section's first page. After the heading it always reports the page the
    heading itself landed on.

    Sections with no heading of their own (#576) take the mark at the top,
    which is the correct start for them.
    """
    mark = "\\parodypagemark{%s}" % key
    m = _SECTIONING.search(tex)
    if m is None:
        return mark + "%\n" + tex
    i = m.end()
    if i < len(tex) and tex[i] == "[":
        i = _skip_group(tex, i, "[", "]")
    i = _skip_group(tex, i, "{", "}")
    if i is None:
        return mark + "%\n" + tex
    return tex[:i] + mark + tex[i:]
