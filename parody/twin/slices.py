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
