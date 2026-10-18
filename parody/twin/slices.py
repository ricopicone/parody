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
from .marks import sentence_starts


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


def _without_id(opener):
    return re.sub(r"\s*#[^\s}]+", "", opener).replace("{ ", "{")


def slice_chunk(text, language, start, end, english_boundaries):
    """Sentences ``[start, end)`` of a translated chunk (``end=None``: to its end)."""
    bounds = sentence_starts(text, language)
    approximate = len(bounds) != english_boundaries

    def offset(i):
        if i == 0:
            return 0
        j = i if not approximate else round(i * len(bounds) / max(english_boundaries, 1))
        return 0 if j <= 0 else bounds[min(j, len(bounds)) - 1] if bounds else 0

    a = offset(start)
    b = len(text) if end is None else offset(end)
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
