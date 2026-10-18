"""From the page inventory to what each twin page holds (task #825).

A *unit* is one mark value: a chunk's head (sentence 0) or one of its
sentences. Each unit goes to the page that holds most of its lines, so a
sentence that straddles a page break lands where most of its English is.
Ties go to the earlier page. Consecutive units of the same chunk on one page
merge into a *piece*: a whole chunk, or a run of its sentences.
"""

from collections import defaultdict
from dataclasses import dataclass, field

from .marks import decode


@dataclass(frozen=True)
class Piece:
    section: int
    chunk: int
    start: int  # first sentence (0 = the chunk's head)
    end: int | None  # sentence after the last; None = to the end of the chunk


@dataclass
class TwinPage:
    abspage: int
    page: int
    pieces: list = field(default_factory=list)
    counters: dict = field(default_factory=dict)  # the English counters at first_unit
    chapter_start: bool = False
    notes: list = field(default_factory=list)
    first_unit: int | None = None


def paginate(rows, counters, sections, first_section_of_chapter):
    """One ``TwinPage`` per page in the span of ``sections``, blank ones included."""
    lines = defaultdict(dict)  # unit → {abspage: lines}
    page_number = {}
    for abspage, page, value, n in rows:
        page_number.setdefault(abspage, page)
        if decode(value)[0] in sections:
            lines[value][abspage] = lines[value].get(abspage, 0) + n
    units = sorted({v for v in lines} | {v for v in counters if decode(v)[0] in sections})
    if not units:
        return []

    notes = defaultdict(list)
    placed = {}
    previous = None
    for v in units:
        here = lines.get(v)
        if here:
            most = max(here.values())
            page = min(p for p, n in here.items() if n == most)
        elif previous is not None:
            page = placed[previous]
            notes[page].append(f"unit {v} is not on any page; placed after its predecessor")
        else:
            continue
        if previous is not None and page < placed[previous]:
            notes[placed[previous]].append(f"unit {v} on page {page} is out of order; kept after its predecessor")
            page = placed[previous]
        placed[v] = page
        previous = v

    last_sentence = defaultdict(int)  # (section, chunk) → highest sentence seen
    for v in placed:
        s, c, n = decode(v)
        last_sentence[(s, c)] = max(last_sentence[(s, c)], n)

    pages = []
    first, last = min(placed.values()), max(placed.values())
    for abspage in range(first, last + 1):
        on_page = [v for v in placed if placed[v] == abspage]
        number = page_number.get(abspage)
        if number is None:
            number = pages[-1].page + 1 if pages else 0
        page = TwinPage(abspage, number, notes=notes.get(abspage, []))
        for v in on_page:
            s, c, n = decode(v)
            prev = page.pieces[-1] if page.pieces else None
            if prev and (prev.section, prev.chunk) == (s, c):
                page.pieces[-1] = Piece(s, c, prev.start, n + 1)
            else:
                page.pieces.append(Piece(s, c, n, n + 1))
            if c == 0 and n == 0 and s in first_section_of_chapter:
                page.chapter_start = True
        page.pieces = [Piece(p.section, p.chunk, p.start,
                             None if p.end > last_sentence[(p.section, p.chunk)] else p.end)
                       for p in page.pieces]
        if on_page:
            page.first_unit = on_page[0]
            page.counters = dict(counters.get(on_page[0], {}))
        pages.append(page)
    return pages
