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

# How many units past one a page break is looked for in (``following``).
_LOOKAHEAD = 8


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


def paginate(rows, counters, sections, first_section_of_chapter, floats=frozenset(),
             footnotes=frozenset()):
    """One ``TwinPage`` per page in the span of ``sections``, blank ones included.

    ``floats`` are the units LaTeX may move: a float that went ahead of the
    text written after it stays with the text it was written in, instead of
    taking that text to its own page. ``footnotes`` are the units of footnote
    definitions, printed on their reference's page, often before the text
    written ahead of them: every twin page sets its section's footnotes, so
    that is not a move worth a note.
    """
    lines = defaultdict(dict)  # unit → {abspage: lines}
    page_number = {}
    for abspage, page, value, n in rows:
        page_number.setdefault(abspage, page)
        if decode(value)[0] in sections:
            lines[value][abspage] = lines[value].get(abspage, 0) + n
    units = sorted({v for v in lines} | {v for v in counters if decode(v)[0] in sections})
    if not units:
        return []

    def most_lines(v):
        here = lines[v]
        most = max(here.values())
        return min(p for p, n in here.items() if n == most)

    def following(i):
        """The earliest page of the text just after ``units[i]``: of the next
        few units with lines that are neither floats nor footnotes, which
        LaTeX may move. A few, not one: a run of moved units (a footnote's
        two sentences) ends before the text resumes."""
        pages = []
        for w in units[i + 1:]:
            if w in lines and w not in floats and w not in footnotes:
                pages.append(most_lines(w))
                if len(pages) == _LOOKAHEAD:
                    break
        return min(pages, default=None)

    notes = defaultdict(list)
    placed = {}
    previous = None
    for i, v in enumerate(units):
        here = lines.get(v)
        if here:
            page = most_lines(v)
            after = following(i) if previous is not None and page > placed[previous] else None
            if after is not None and after < page:
                # the text after it is on an earlier page. A unit that only
                # straddles the break (a box whose frame, rebuilt on the next
                # page, carries its head's mark) goes to the earlier page it
                # is on too. One that went ahead of the text (a float, a
                # footnote's sentences at the next page's foot) stays with
                # the text it was written in, rather than take that text on.
                earlier = [p for p in here if placed[previous] <= p <= after]
                if earlier and v not in floats:
                    page = max(earlier)
                else:
                    kind = "a float" if v in floats else "ahead of the text after it"
                    notes[placed[previous]].append(
                        f"unit {v}, {kind} on page {page_number.get(page, page)} in English, "
                        "is set with the text it was written in")
                    page = placed[previous]
        elif previous is not None:
            page = placed[previous]
            notes[page].append(f"unit {v} is not on any page; placed after its predecessor")
        else:
            continue
        if previous is not None and page < placed[previous]:
            if v not in footnotes:
                notes[placed[previous]].append(f"unit {v} on page {page_number.get(page, page)} "
                                               "is out of order; kept after its predecessor")
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
    _make_contiguous(pages)
    return pages


def _make_contiguous(pages):
    """Each chunk's pieces, in page order, run from its start to its end with
    no gap: a unit no mark reported (lost inside something print.lua
    stringifies, say) goes with the piece before it rather than nowhere."""
    by_chunk = defaultdict(list)
    for page in pages:
        for i, piece in enumerate(page.pieces):
            by_chunk[(piece.section, piece.chunk)].append((page, i))
    for slots in by_chunk.values():
        for n, (page, i) in enumerate(slots):
            piece = page.pieces[i]
            start = 0 if n == 0 else piece.start
            end = None if n == len(slots) - 1 else slots[n + 1][0].pieces[slots[n + 1][1]].start
            page.pieces[i] = Piece(piece.section, piece.chunk, start, end)
