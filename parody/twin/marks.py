"""Marks that tell which sentence of the English sits on which page (task #825).

A twin page must hold exactly what its English page holds, so the build has
to learn, sentence by sentence, where the English pages broke. It builds the
English a second time with ``\\parodys{V}`` before every chunk and sentence.
That macro sets a LuaTeX attribute, which adds no node to the page, so the
lines and pages come out as they were (``inventory`` checks that). A shipout
callback then reads the attribute off every line.

``V = section * 1_000_000 + (chunk + 1) * 1000 + sentence``. Sentence 0 is the
chunk's head; sentence s starts after the chunk's s-th sentence boundary.
Chunks are the translate step's chunks, so the English page inventory and a
translation file speak of the same units.
"""

import re

from ..translate.chunks import split_chunks

MARK_MACRO = "parodys"
_SECTION = 1_000_000
_CHUNK = 1000
_MAX_SECTION = (2**31 - 1) // _SECTION - 1  # attribute values are 32-bit

# Where a full stop is not the end of a sentence.
_PROTECTED = re.compile(
    r"```.*?```|~~~.*?~~~"                       # code fences
    r"|\\begin\{(?P<env>[^}]+)\}.*?\\end\{(?P=env)\}"  # raw LaTeX environments
    r"|\$\$.*?\$\$|\$[^$]+?\$"                   # maths
    r"|`[^`\n]+`"                                # inline code
    r"|!\[(?:[^\[\]]|\[[^\]]*\])*\]\([^)]*\)(?:\{[^{}]*\})?"  # images
    r"|\{[^{}\n]*\}"                             # attribute blocks
    r"|\]\([^)\n]*\)"                            # link targets
    r"|^[ \t]*(?:#|\||:::|\+-).*?$",             # headings, tables, div fences
    re.S | re.M)

_CLOSERS = "\"'”’»)］）」』"
_BOUNDARY = {
    # end . ? ! , any closers, whitespace, then a capital letter
    "cased": re.compile(rf"[.?!][{_CLOSERS}]*([ \t]+|\n[ \t]*)(?=\S)"),
    "ko": re.compile(rf"[.?!][{_CLOSERS}]*([ \t]+|\n[ \t]*)(?=\S)"),
    "zh": re.compile(rf"[。！？][{_CLOSERS}]*[ \t]*\n?[ \t]*(?=\S)"),
}
_CASED = {"en", "de", "fr", "es"}

# A chunk opening with one of these must keep its head mark inline after it:
# on its own line the mark would split a list, a quote or a footnote.
# List markers as pandoc reads them: a number, one letter or a roman numeral;
# an uppercase marker needs two spaces after it (so "B. Russell" is prose).
_INLINE_HEAD = re.compile(
    r"^(?:[ \t]*(?:[-*+]|\(?(?:[0-9]{1,9}|[a-z]|[ivxlc]{1,6})[.)]"
    r"|\(?(?:[A-Z]|[IVXLC]{1,6})[.)](?=[ \t]{2}))[ \t]+"
    r"|>[ \t]*|\[\^[^\]\s]+\]:[ \t]*|[:~][ \t]+)")


def sentence_starts(text, language="en"):
    """Offsets in ``text`` where a new sentence begins."""
    kind = "cased" if language in _CASED else language
    pattern = _BOUNDARY[kind]
    starts = []
    last = 0
    spans = [(m.start(), m.end()) for m in _PROTECTED.finditer(text)] + [(len(text), len(text))]
    for p_start, p_end in spans:
        for m in pattern.finditer(text, last, p_start):
            if m.end() >= p_start:
                continue
            nxt = text[m.end()]
            if kind == "cased" and not nxt.isupper():
                continue
            starts.append(m.end())
        last = p_end
    return starts


def _value(section, chunk, sentence):
    return section * _SECTION + (chunk + 1) * _CHUNK + sentence


def decode(value):
    """``(section index, chunk index, sentence)`` of a mark value."""
    section, rest = divmod(value, _SECTION)
    chunk, sentence = divmod(rest, _CHUNK)
    return section, chunk - 1, sentence


def _mark(value):
    return f"\\{MARK_MACRO}{{{value}}}"


def mark_section(body, section_index):
    """The section body with a mark before every chunk and sentence."""
    if not 1 <= section_index <= _MAX_SECTION:
        raise ValueError(f"section index {section_index} out of range (1..{_MAX_SECTION})")
    chunks = split_chunks(body)
    if len(chunks) >= _CHUNK - 1:
        raise ValueError(f"section {section_index} has {len(chunks)} chunks; at most 998 can be marked")
    parts = []
    for k, chunk in enumerate(chunks):
        starts = sentence_starts(chunk)
        if len(starts) >= _CHUNK - 1:
            raise ValueError(f"chunk {k} of section {section_index} has too many sentences")
        pieces, last = [], 0
        for s, offset in enumerate(starts, 1):
            pieces += [chunk[last:offset], _mark(_value(section_index, k, s))]
            last = offset
        marked = "".join(pieces) + chunk[last:]
        head = _mark(_value(section_index, k, 0))
        m = _INLINE_HEAD.match(marked)
        if m:
            parts.append(marked[:m.end()] + head + marked[m.end():])
        else:
            parts.append(f"{head}\n\n{marked}")
    return "\n\n".join(parts)
