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

import json
import re

import pypandoc

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
    # a heading is #s then a space: "#." opens an auto-numbered list item
    r"|^[ \t]*(?:\#{1,6}(?=[ \t]|$)|\||:::|\+-).*?$",  # headings, tables, div fences
    re.S | re.M)

_CLOSERS = "\"'”’»)］）」』"
_BOUNDARY = {
    # end . ? ! , any closers, whitespace, then a capital letter
    # (German closes a quotation with “ and ‘: „So.“ Dann)
    "cased": re.compile(rf"[.?!][{_CLOSERS}“‘]*([ \t]+|\n[ \t]*)(?=\S)"),
    "ko": re.compile(rf"[.?!][{_CLOSERS}]*([ \t]+|\n[ \t]*)(?=\S)"),
    "zh": re.compile(rf"[。！？][{_CLOSERS}]*[ \t]*\n?[ \t]*(?=\S)"),
}
_CASED = {"en", "de", "fr", "es"}
# A full stop that ends one of these is not a sentence end. Single letters
# ("z. B.", "d. h.", "p. ex.") are caught by rule, not listed. German needs
# this most: its nouns are capitalised, so "z. B. Spannung" reads like two
# sentence ends.
_ABBREVIATIONS = {
    "en": {"e.g", "i.e", "etc", "fig", "figs", "eq", "eqs", "vs", "cf", "dr", "mr", "mrs",
           "ms", "no", "approx", "resp", "ref", "refs", "sec", "ch"},
    "de": {"bzw", "ca", "vgl", "usw", "etc", "nr", "abb", "gl", "kap", "sog", "ggf", "evtl",
           "inkl", "bspw", "max", "min", "abs", "bd", "hrsg", "ff"},
    "fr": {"ex", "etc", "fig", "éq", "cf", "mme", "env", "chap", "c.-à-d", "cf"},
    "es": {"ej", "etc", "fig", "ec", "sr", "sra", "núm", "aprox", "cap", "pág"},
}
_WORD_BEFORE = re.compile(r"([^\s(\[{]+)$")

_DISPLAY_END = re.compile(r"[.?!。！？]\s*(?:\\end\{[^}]+\}\s*)*$")
_AFTER_DISPLAY = re.compile(r"\s+")
# "#." is pandoc's auto-numbered item: each one numbers itself from the item
# before, so a mark on its own line between two of them restarted the count.
_LIST_ITEM = re.compile(
    r"^[ \t]*(?:[-*+]|\(?(?:[0-9]{1,9}|[a-z]|[ivxlc]{1,6}|#)[.)]"
    r"|\(?(?:[A-Z]|[IVXLC]{1,6})[.)](?=[ \t]{2}))[ \t]+", re.M)
_MARKER_NUMBER = re.compile(r"[ \t]*\(?(?:\d{1,9}|[A-Za-z]|[ivxlcIVXLC]{1,6}|#)")
# [ \t]*, not \s*: a closing ":::" then a paragraph is not an opener.
_NESTED_OPEN = re.compile(r"^:{3,}[ \t]*[^\s:][^\n]*\n", re.M)
_BLANK_LINE = re.compile(r"\n[ \t]*\n\s*")

# A chunk opening with one of these must keep its head mark inline after it:
# on its own line the mark would split a list, a quote or a footnote.
# List markers as pandoc reads them: a number, one letter or a roman numeral;
# an uppercase marker needs two spaces after it (so "B. Russell" is prose).
_INLINE_HEAD = re.compile(
    r"^(?:[ \t]*(?:[-*+]|\(?(?:[0-9]{1,9}|[a-z]|[ivxlc]{1,6}|#)[.)]"
    r"|\(?(?:[A-Z]|[IVXLC]{1,6})[.)](?=[ \t]{2}))[ \t]+"
    r"|>[ \t]*|\[\^[^\]\s]+\]:[ \t]*|[:~][ \t]+)")

# A chunk that is one item of a definition list: its term, then the marker
# that opens the definition. A head on its own line before the term would end
# the list there, so it goes inline after the marker.
_DEFINITION_HEAD = re.compile(r"^[^\s:~][^\n]*\n(?:[ \t]*\n)?[:~][ \t]+")


_DIV_HEAD = re.compile(r"^:{3,}[ \t]*[^\s:]")
# A line that opens a block of its own, where an inline mark cannot go.
_BLOCK_START = re.compile(r"^(?:\$\$|!\[|```|~~~|:::|#|\||\\begin\{|[-*+] |\d+[.)] |>)")


# The breakable boxes (parody-environments.sty), rebuilt at a page break.
# Other divs keep their head outside: print.lua parses some structurally.
_BOX_CLASSES = {"definition", "theorem", "lemma", "corollary", "proposition",
                "example", "infobox"}


# Divs whose figures are units of their own (a paragraph-level mark before
# them is safe). Not structural divs like subfigures, which print.lua reads
# as nothing but images.
_FIGURE_UNIT_CLASSES = _BOX_CLASSES | {"exercise", "labexercise"}


def _div_classes(chunk):
    m = re.match(r"^:{3,}[ \t]*(?:\{([^}]*)\}|([\w-]+))", chunk)
    if not m:
        return []
    return [m.group(2)] if m.group(2) else re.findall(r"\.([\w-]+)", m.group(1) or "")


def _figures_are_units(chunk):
    return any(c in _FIGURE_UNIT_CLASSES for c in _div_classes(chunk))


def _innermost_div_takes_figures(text, offset):
    """Whether the div immediately around ``offset`` is one whose figures are
    units: not a subfigures div nested inside a box."""
    stack = []
    for line in text[:offset].split("\n"):
        if re.match(r"^:{3,}\s*[^\s:]", line):
            stack.append(line)
        elif re.match(r"^:{3,}\s*$", line) and stack:
            stack.pop()
    return bool(stack) and _figures_are_units(stack[-1])


_FIGURE_DIV_CLASSES = {"figure", "subfigures"}
_TABLE_CAPTION = re.compile(r"^[ \t]*Table:.*$", re.M)


def _no_mark_zones(text):
    """Spans no mark may fall in: a figure div from its opener to its closer
    (its caption is a moving argument, where a mark is a TeX error, and a cut
    inside would split the figure), and a table's caption line (a mark before
    ``Table:`` undoes the caption)."""
    zones, stack, offset = [], [], 0
    for line in text.split("\n"):
        if re.match(r"^:{3,}\s*[^\s:]", line):
            classes = set(_div_classes(line))
            stack.append((offset, bool(classes & _FIGURE_DIV_CLASSES)))
        elif re.match(r"^:{3,}\s*$", line) and stack:
            start, is_figure = stack.pop()
            if is_figure:
                zones.append((start, offset + len(line)))
        offset += len(line) + 1
    zones += [(m.start(), m.end()) for m in _TABLE_CAPTION.finditer(text)]
    return zones


def _is_box(chunk):
    return any(c in _BOX_CLASSES for c in _div_classes(chunk))


def _is_prose(text):
    """Whether ``text`` opens ordinary prose: a letter or digit, or emphasis,
    a link or a quote; not raw HTML or a block marker."""
    return bool(text) and (text[0].isalnum() or text[0] in "*_[(\"'“‘") \
        and not _BLOCK_START.match(text) and not _LIST_ITEM.match(text)


def _opens_with_text(div_chunk):
    """Whether the line after a div's opener is ordinary text."""
    return _is_prose(div_chunk.partition("\n")[2])


def _first_letter(text, offset):
    """The first character at ``offset`` past opening markup ([ * _ quotes brackets,
    and the openers „ ‚ « ‹ ¿ ¡ of German, French and Spanish)."""
    m = re.match(r"[\[*_\"'“‘(„‚«‹¿¡]*(.)", text[offset:offset + 12], re.S)
    return m.group(1) if m else ""


def _starts_a_sentence(text, offset):
    """Whether a sentence, not a footnote mark or a closing fence, follows."""
    rest = text[offset:]
    return bool(rest.strip()) and not rest.startswith("[^") and not re.match(r":{3,}", rest)


def _quote_opens_next(text, m):
    """Where a Chinese sentence ending at ``m`` starts the next one.

    Straight quotes do not say which way they face: a ``"`` right after the
    stop closes a quotation only when one is open in the paragraph, and
    otherwise opens the next sentence's, which must not lose it.
    """
    quote = m.start() + 1
    if not text.startswith('"', quote):
        return m.end()
    paragraph = text.rfind("\n\n", 0, m.start()) + 1
    return quote if text.count('"', paragraph, m.start()) % 2 == 0 else m.end()


def sentence_starts(text, language="en"):
    """Offsets in ``text`` where a new sentence begins."""
    kind = "cased" if language in _CASED else language
    pattern = _BOUNDARY[kind]
    starts = []
    last = 0
    spans = [(m.start(), m.end()) for m in _PROTECTED.finditer(text)] + [(len(text), len(text))]
    abbreviations = _ABBREVIATIONS.get(language, set())
    for p_start, p_end in spans:
        for m in pattern.finditer(text, last, p_start):
            if m.end() >= p_start:
                continue
            end = _quote_opens_next(text, m) if kind == "zh" else m.end()
            if kind == "cased" and not _first_letter(text, end).isupper():
                continue
            word = _WORD_BEFORE.search(text, 0, m.start())
            if word:
                token = word.group(1).lower()
                if (len(token) == 1 and token.isalpha()) or token in abbreviations:
                    continue
            if not _starts_a_sentence(text, end):
                continue
            line = text[text.rfind("\n", 0, m.start()) + 1:m.start()]
            if _MARKER_NUMBER.fullmatch(line) or _LIST_ITEM.match(text, end):
                continue  # a list marker's own full stop, or a break onto an item
            starts.append(end)
        # A display whose maths ends in . ? or ! ends its sentence too.
        if text.startswith("$$", p_start) and _DISPLAY_END.search(text[p_start + 2:p_end - 2]):
            after = _AFTER_DISPLAY.match(text, p_end)
            if after and _starts_a_sentence(text, after.end()) and (
                    _is_prose(text[after.end():]) or text.startswith("$$", after.end())) and (
                    kind != "cased" or _first_letter(text, after.end()).isupper()):
                starts.append(after.end())
        last = p_end
    # Every block after a blank line starts a unit too: between paragraphs, or
    # before a figure or display inside a box, is the cleanest place to cut.
    # Only blocks a mark can open inline: prose, or a display. A mark before a
    # fence, heading, table, list marker or figure would break its syntax.
    figures = _figures_are_units(text)
    for m in _BLANK_LINE.finditer(text):
        rest = text[m.end():]
        if (not any(a <= m.start() < b for a, b in spans[:-1])
                and _starts_a_sentence(text, m.end())
                and (rest.startswith("$$") or _is_prose(rest)
                     or (figures and rest.startswith("![")
                         and _innermost_div_takes_figures(text, m.end())))):
            starts.append(m.end())
    # Each list item, just after its marker (the chunk's own first line has
    # its head mark there already), and the first prose line inside a nested
    # div: a box of questions or a worked solution is otherwise one unit.
    def protected(offset):
        return any(a <= offset < b for a, b in spans[:-1])
    for m in _LIST_ITEM.finditer(text):
        if m.start() > 0 and not protected(m.end()) and _starts_a_sentence(text, m.end()) \
                and _is_prose(text[m.end():]):
            starts.append(m.end())
    for m in _NESTED_OPEN.finditer(text):
        if m.start() > 0 and not protected(m.end()) and _is_prose(text[m.end():]):
            starts.append(m.end())
    zones = _no_mark_zones(text)
    return sorted({s for s in starts if not any(a <= s <= b for a, b in zones)})


def _ends_in_paragraph(chunk):
    """Whether the ordinary build leaves the end of ``chunk`` inside a paragraph.

    Its last block is a paragraph whose own text ends the chunk: not a
    footnote's, which pandoc folds into the paragraph that cites it, and not a
    table caption's.
    """
    from ..writers.latex import PANDOC_FROM

    tail = re.split(r"\n[ \t]*\n", chunk.rstrip())[-1]
    if not tail or tail[0].isspace() or tail.startswith(("[^", ": ")) \
            or _TABLE_CAPTION.match(tail):
        return False
    blocks = json.loads(pypandoc.convert_text(chunk, "json", format=PANDOC_FROM))["blocks"]
    return bool(blocks) and blocks[-1]["t"] == "Para"


def _after_first_word(line):
    """Offset just past ``line``'s first word and the spaces after it, or its
    end. A word is whole spans, links, maths and code: a cut inside a key term
    puts the mark into the term's index entry."""
    depth, math, code, emph, seen = 0, False, False, False, False
    for i, ch in enumerate(line):
        if ch == "`" and not math:
            code = not code
        elif code:
            pass
        elif ch == "$":
            math = not math
        elif math:
            pass
        elif ch in "*_":
            # a run of * or _ opens or closes emphasis (a mark inside the group
            # would not outlast it)
            if line[i - 1:i] != ch:
                emph = not emph
        elif ch in "[({":
            depth += 1
        elif ch in "])}":
            depth = max(depth - 1, 0)
        elif ch in " \t" and depth == 0 and not emph and seen:
            m = re.match(r"[ \t]+", line[i:])
            return i + m.end()
        seen = True
    return len(line)


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
            mark = _mark(_value(section_index, k, s))
            if chunk.startswith("![", offset):
                mark += "\n\n"  # its own paragraph: inline, it would undo the figure
            pieces += [chunk[last:offset], mark]
            last = offset
        marked = "".join(pieces) + chunk[last:]
        head = _mark(_value(section_index, k, 0))
        m = _INLINE_HEAD.match(marked) or _DEFINITION_HEAD.match(marked)
        if m:
            parts.append(marked[:m.end()] + head + marked[m.end():])
        elif _is_box(marked) and _opens_with_text(marked):
            # Inside the div, so it is re-run when a breakable box is rebuilt
            # at a page break (in the output routine, where marks are off).
            # Only inline in text: a structural div (subfigures) must hold
            # nothing but its own blocks.
            # After the first word: as the box's very first token the mark
            # changed the box's layout and moved lines between pages.
            opener, _, rest = marked.partition("\n")
            cut = _after_first_word(rest.split("\n", 1)[0])
            # The counters, though, are logged BEFORE the box opens: inside,
            # the box has already stepped its number, and a twin page opening
            # on it would print the next one.
            parts.append(f"\\{MARK_MACRO}ctr{{{_value(section_index, k, 0)}}}\n\n"
                         f"{opener}\n{rest[:cut]}{head}{rest[cut:]}")
        else:
            parts.append(f"{head}\n\n{marked}")
    # Cleared at the end, or the last mark rides on into whatever follows the
    # section: the next chapter's heading, the back matter. Inside a closing
    # paragraph, which the ordinary build leaves open at the end of the file:
    # closed here, it moved the page-map label that follows onto the page's
    # vertical list, and a page break after it came out a line different.
    off = f"\\{MARK_MACRO}off"
    if chunks and _ends_in_paragraph(chunks[-1]):
        parts[-1] = parts[-1].rstrip() + "\n" + off
    else:
        parts.append(off)
    return "\n\n".join(parts)
