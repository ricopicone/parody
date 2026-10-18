"""Cut a translated chunk at the sentence where the English page broke (task #825).

The translation keeps the English sentences in order, so the English
boundary i is normally the translation's boundary i. When the counts differ
(an abbreviation read as a full stop, two sentences merged), boundary i maps
to the proportional one and the slice is marked approximate. A cut never
falls inside maths, code or an attribute block, because boundaries are only
ever found outside them (``marks.sentence_starts``).

A cut inside a fenced div (a definition box that ran onto the next page)
closes the div on the first page and reopens it on the next, with its
``#id`` dropped so the id is not defined twice.
"""

import re
from bisect import bisect_right
from dataclasses import dataclass

from ..translate.chunks import _DIV_CLOSE, _DIV_OPEN, _FENCE_CLOSE, _FENCE_OPEN
from .marks import _BLANK_LINE, _LIST_ITEM, sentence_starts


@dataclass
class Slice:
    text: str
    approximate: bool = False
    reopened: bool = False


_HTML_DIV_OPEN = re.compile(r"^\s*<div(\s[^>]*)?>\s*$")
_HTML_DIV_CLOSE = re.compile(r"^\s*</div>\s*$")


def _open_divs(text, upto):
    """Opener lines of the divs still open at ``upto``, fenced (:::) or raw
    HTML (<div> on a line of its own, as the migrated examples have)."""
    stack, fence = [], None
    for line in text[:upto].split("\n"):
        if fence is not None:
            m = _FENCE_CLOSE.match(line)
            if m and m.group(1)[0] == fence[0] and len(m.group(1)) >= fence[1]:
                fence = None
            continue
        m = _FENCE_OPEN.match(line)
        if m:
            fence = (m.group(1)[0], len(m.group(1)))
        elif _DIV_OPEN.match(line) or _HTML_DIV_OPEN.match(line):
            stack.append(line)
        elif (_DIV_CLOSE.match(line) or _HTML_DIV_CLOSE.match(line)) and stack:
            stack.pop()
    return stack


def _closer(opener):
    return "</div>" if _HTML_DIV_OPEN.match(opener) else ":::"


def _item_start(text, offset):
    """A cut just after a list marker moves to the start of the item's line,
    so the marker travels with its item."""
    line_start = text.rfind("\n", 0, offset) + 1
    m = _LIST_ITEM.match(text, line_start)
    return line_start if m and m.end() == offset else offset


# Where a line's own content starts: its indentation, then a list or
# definition marker and the space after it.
_CONTENT_START = re.compile(r"[ ]*(?:(?:[-+*]|\d+[.)]|[A-Za-z][.)]|[:~])[ \t]+)?")


def _indent(line):
    return len(line) - len(line.lstrip(" "))


def _open_depths(text, a):
    """The content indentation of each indented block open at offset ``a``,
    outermost first: a nested list in a definition is two, the definition's
    and the nested item's. Found from the cut's own line up, through each
    line indented less than everything below it, to the top level."""
    start = text.rfind("\n", 0, a) + 1
    end = text.find("\n", start)
    line = text[start:end if end != -1 else len(text)]
    floor = _indent(line)
    # at the line's content a list marker stays with its item; inside its
    # text the block's content starts past the marker
    depths = {floor if a - start <= floor else _CONTENT_START.match(line).end()}
    pos = start
    while floor > 0 and pos > 0:
        above = text.rfind("\n", 0, pos - 1) + 1
        prev, pos = text[above:pos - 1], above
        if not prev.strip() or _indent(prev) >= floor:
            continue
        floor = _indent(prev)
        depths.add(_CONTENT_START.match(prev).end())
        depths.add(floor)
    return sorted(d for d in depths if d > 0)


def _outdented(text, a, piece):
    """``piece`` with the indentation of the blocks it was cut from taken off.

    A cut inside an indented block (a definition's nested list, a list item's
    continuation) leaves the rest of that block indented in the slice, and at
    the top of a page four spaces make it a code block: robotics 1.3's list of
    vision techniques printed verbatim, colons and all, in both twins. So each
    line loses the indentation of the innermost block still open at it, which
    keeps what is nested under it nested; the first line indented less than
    every open block ends them all, and it and what follows are left alone
    (an item there, or in a block still open, gets a blank line before it so
    it stays an item, and a numbered one a comment so it keeps its number).
    """
    depths = _open_depths(text, a)
    if not depths:
        return piece
    first, *rest = piece.split("\n")
    out = [first]
    for i, row in enumerate(rest):
        if not row.strip():
            out.append("")
            continue
        closed = False
        while depths and _indent(row) < depths[-1]:
            depths.pop()
            closed = True
        if closed and _LIST_ITEM.match(row):
            # an item after the text of the one the cut was inside: a blank
            # line first, or in a tight list it runs in to that text as words
            # (robotics 1.8: exercise parts b and c); and before a numbered
            # one a comment, or it runs on into an outdented numbered list
            # above it and takes its number (electronics 3.3: item 7 printed
            # as 4). Run-on bullets look the same, so they need no comment.
            out += [""] * (out[-1] != "")
            if row.lstrip()[0] not in "-*+":
                out += ["<!-- -->", ""]
        if not depths:
            out.extend(rest[i:])
            break
        out.append(row[depths[-1]:])
    return "\n".join(out)


_ATTR_TOKEN = re.compile(r'[^\s=]+="[^"]*"|[^\s=]+=\S+|\S+')


def _without_id(opener):
    """The opener without its #id and h= (both define labels; twice is a clash).

    Token by token, so a # or h= inside a quoted attribute value stays.
    """
    m = re.match(r"^(:{3,}\s*)\{(.*)\}\s*$", opener)
    if not m:
        return opener
    kept = [t for t in _ATTR_TOKEN.findall(m.group(2))
            if not t.startswith("#") and not t.startswith("h=")]
    return f"{m.group(1)}{{{' '.join(kept)}}}"


def _blocks(text):
    """Where each blank-line-separated block of ``text`` starts."""
    return [0] + [m.end() for m in _BLANK_LINE.finditer(text)]


def _in_same_block(e, english, bounds, text):
    """The translated boundary for English boundary offset ``e``, found in the
    same block: the translation keeps the English blocks one for one, so a cut
    at a block (a figure, a paragraph) is exact whatever the sentence counts,
    and one inside a block stays inside it. None when the blocks differ."""
    en_blocks, tr_blocks = _blocks(english), _blocks(text)
    if len(en_blocks) != len(tr_blocks):
        return None
    k = bisect_right(en_blocks, e) - 1
    lo = tr_blocks[k]
    hi = tr_blocks[k + 1] if k + 1 < len(tr_blocks) else len(text)
    if e == en_blocks[k]:
        return lo if lo in bounds else None
    inside = [b for b in bounds if lo < b < hi]
    if not inside:
        return None
    en_lo = en_blocks[k]
    en_hi = en_blocks[k + 1] if k + 1 < len(en_blocks) else len(english)
    target = lo + (e - en_lo) / max(en_hi - en_lo, 1) * (hi - lo)
    return min(inside, key=lambda b: abs(b - target))


def slice_chunk(text, language, start, end, english):
    """Sentences ``[start, end)`` of a translated chunk (``end=None``: to its end).

    ``english`` is the English chunk's text (or just its boundary count). When
    the counts differ, English boundary i maps to the translated boundary at
    the nearest relative position in the chunk: an extra boundary early on
    (an abbreviation read as a full stop) then shifts nothing after it.
    """
    bounds = sentence_starts(text, language)
    if isinstance(english, str):
        en_bounds = sentence_starts(english, "en")
        en_count, en_len = len(en_bounds), max(len(english), 1)
    else:
        en_bounds, en_count, en_len = None, english, 1
    approximate = len(bounds) != en_count

    def offset(i):
        if i == 0 or not bounds:
            return 0
        if not approximate:
            return bounds[i - 1]
        if en_bounds:
            e = en_bounds[min(i, len(en_bounds)) - 1]
            anchored = _in_same_block(e, english, bounds, text)
            if anchored is not None:
                return anchored
            target = e / en_len * len(text)
            return min(bounds, key=lambda b: abs(b - target))
        j = round(i * len(bounds) / max(en_count, 1))
        return 0 if j <= 0 else bounds[min(j, len(bounds)) - 1]

    a = _item_start(text, offset(start))
    b = len(text) if end is None else _item_start(text, offset(end))
    if end is not None and b < a:
        b = a
    piece = text[a:b].strip()
    if a > 0:
        piece = _outdented(text, a, piece)

    reopened = False
    if a > 0:
        openers = _open_divs(text, a)
        if openers:
            # a raw HTML opener needs a blank line before the Markdown it holds
            lines = [_without_id(o) + ("\n" if _HTML_DIV_OPEN.match(o) else "") for o in openers]
            piece = "\n".join(lines) + "\n" + piece
            reopened = True
    if end is not None:
        still_open = _open_divs(text, b)
        if still_open:
            closers = [_closer(o) for o in reversed(still_open)]
            piece += "\n\n" + "\n".join(c + ("\n" if c == "</div>" else "") for c in closers).rstrip("\n")
    return Slice(piece, approximate and (start > 0 or end is not None), reopened)
