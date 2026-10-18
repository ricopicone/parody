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
_LIST_ITEM = re.compile(
    r"^[ \t]*(?:[-*+]|\(?(?:[0-9]{1,9}|[a-z]|[ivxlc]{1,6})[.)]"
    r"|\(?(?:[A-Z]|[IVXLC]{1,6})[.)](?=[ \t]{2}))[ \t]+", re.M)
_MARKER_NUMBER = re.compile(r"[ \t]*\(?(?:\d{1,9}|[A-Za-z]|[ivxlcIVXLC]{1,6})")
_NESTED_OPEN = re.compile(r"^:{3,}\s*[^\s:][^\n]*\n", re.M)
_BLANK_LINE = re.compile(r"\n[ \t]*\n\s*")

# A chunk opening with one of these must keep its head mark inline after it:
# on its own line the mark would split a list, a quote or a footnote.
# List markers as pandoc reads them: a number, one letter or a roman numeral;
# an uppercase marker needs two spaces after it (so "B. Russell" is prose).
_INLINE_HEAD = re.compile(
    r"^(?:[ \t]*(?:[-*+]|\(?(?:[0-9]{1,9}|[a-z]|[ivxlc]{1,6})[.)]"
    r"|\(?(?:[A-Z]|[IVXLC]{1,6})[.)](?=[ \t]{2}))[ \t]+"
    r"|>[ \t]*|\[\^[^\]\s]+\]:[ \t]*|[:~][ \t]+)")


_DIV_HEAD = re.compile(r"^:{3,}\s*[^\s:]")
# A line that opens a block of its own, where an inline mark cannot go.
_BLOCK_START = re.compile(r"^(?:\$\$|!\[|```|~~~|:::|#|\||\\begin\{|[-*+] |\d+[.)] |>)")


# The breakable boxes (parody-environments.sty), rebuilt at a page break.
# Other divs keep their head outside: print.lua parses some structurally.
_BOX_CLASSES = {"definition", "theorem", "lemma", "corollary", "proposition",
                "example", "infobox"}


def _is_box(chunk):
    m = re.match(r"^:{3,}\s*(?:\{([^}]*)\}|([\w-]+))", chunk)
    if not m:
        return False
    names = m.group(2) and [m.group(2)] or re.findall(r"\.([\w-]+)", m.group(1) or "")
    return any(n in _BOX_CLASSES for n in names)


def _is_prose(text):
    """Whether ``text`` opens ordinary prose: a letter or digit, or emphasis,
    a link or a quote; not raw HTML or a block marker."""
    return bool(text) and (text[0].isalnum() or text[0] in "*_[(\"'“‘") \
        and not _BLOCK_START.match(text)


def _opens_with_text(div_chunk):
    """Whether the line after a div's opener is ordinary text."""
    return _is_prose(div_chunk.partition("\n")[2])


def _first_letter(text, offset):
    """The first character at ``offset`` past opening markup ([ * _ quotes brackets)."""
    m = re.match(r"[\[*_\"'“‘(]*(.)", text[offset:offset + 12], re.S)
    return m.group(1) if m else ""


def _starts_a_sentence(text, offset):
    """Whether a sentence, not a footnote mark or a closing fence, follows."""
    rest = text[offset:]
    return bool(rest.strip()) and not rest.startswith("[^") and not re.match(r":{3,}", rest)


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
            if kind == "cased" and not _first_letter(text, m.end()).isupper():
                continue
            word = _WORD_BEFORE.search(text, 0, m.start())
            if word:
                token = word.group(1).lower()
                if (len(token) == 1 and token.isalpha()) or token in abbreviations:
                    continue
            if not _starts_a_sentence(text, m.end()):
                continue
            line = text[text.rfind("\n", 0, m.start()) + 1:m.start()]
            if _MARKER_NUMBER.fullmatch(line) or _LIST_ITEM.match(text, m.end()):
                continue  # a list marker's own full stop, or a break onto an item
            starts.append(m.end())
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
    for m in _BLANK_LINE.finditer(text):
        rest = text[m.end():]
        if (not any(a <= m.start() < b for a, b in spans[:-1])
                and _starts_a_sentence(text, m.end())
                and (rest.startswith("$$") or _is_prose(rest))):
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
    return sorted(set(starts))


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
        elif _is_box(marked) and _opens_with_text(marked):
            # Inside the div, so it is re-run when a breakable box is rebuilt
            # at a page break (in the output routine, where marks are off).
            # Only inline in text: a structural div (subfigures) must hold
            # nothing but its own blocks.
            # After the first word: as the box's very first token the mark
            # changed the box's layout and moved lines between pages.
            opener, _, rest = marked.partition("\n")
            m_word = re.match(r"\S+[ \t]+", rest)
            cut = m_word.end() if m_word and "\n" not in m_word.group(0) else len(rest.split("\n", 1)[0])
            parts.append(f"{opener}\n{rest[:cut]}{head}{rest[cut:]}")
        else:
            parts.append(f"{head}\n\n{marked}")
    # Cleared at the end, or the last mark rides on into whatever follows the
    # section: the next chapter's heading, the back matter.
    parts.append(f"\\{MARK_MACRO}off")
    return "\n\n".join(parts)
