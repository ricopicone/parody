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
from dataclasses import dataclass

from ..translate.chunks import _DIV_CLOSE, _DIV_OPEN, _FENCE_CLOSE, _FENCE_OPEN
from .marks import _LIST_ITEM, sentence_starts


@dataclass
class Slice:
    text: str
    approximate: bool = False
    reopened: bool = False


def _open_divs(text, upto):
    """Opener lines of the fenced divs still open at offset ``upto``."""
    stack, fence, pos = [], None, 0
    for line in text[:upto].split("\n"):
        pos += len(line) + 1
        if fence is not None:
            m = _FENCE_CLOSE.match(line)
            if m and m.group(1)[0] == fence[0] and len(m.group(1)) >= fence[1]:
                fence = None
            continue
        m = _FENCE_OPEN.match(line)
        if m:
            fence = (m.group(1)[0], len(m.group(1)))
        elif _DIV_OPEN.match(line):
            stack.append(line)
        elif _DIV_CLOSE.match(line) and stack:
            stack.pop()
    return stack


def _item_start(text, offset):
    """A cut just after a list marker moves to the start of the item's line,
    so the marker travels with its item."""
    line_start = text.rfind("\n", 0, offset) + 1
    m = _LIST_ITEM.match(text, line_start)
    return line_start if m and m.end() == offset else offset


def _without_id(opener):
    return re.sub(r"\s*#[^\s}]+", "", opener).replace("{ ", "{")


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
            target = en_bounds[min(i, len(en_bounds)) - 1] / en_len * len(text)
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
            piece = "\n".join(_without_id(o) for o in openers) + "\n" + piece
            reopened = True
    if end is not None:
        still_open = len(_open_divs(text, b))
        if still_open:
            piece += "\n\n" + "\n".join([":::"] * still_open)
    return Slice(piece, approximate and (start > 0 or end is not None), reopened)
