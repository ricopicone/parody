"""Which pieces of which chunks each twin page holds (task #825)."""

from parody.twin.paginate import Piece, paginate


def V(section, chunk, sentence=0):
    return section * 1_000_000 + (chunk + 1) * 1000 + sentence


def _ctr(*values):
    return {v: {"chapter": 1, "equation": i} for i, v in enumerate(values)}


def test_whole_chunks_per_page():
    rows = [(5, 1, V(1, 0), 3), (5, 1, V(1, 1), 4), (6, 2, V(1, 2), 5)]
    pages = paginate(rows, _ctr(V(1, 0), V(1, 1), V(1, 2)), {1}, {1})
    assert [(p.abspage, p.page) for p in pages] == [(5, 1), (6, 2)]
    assert pages[0].pieces == [Piece(1, 0, 0, None), Piece(1, 1, 0, None)]
    assert pages[1].pieces == [Piece(1, 2, 0, None)]
    assert pages[0].chapter_start and not pages[1].chapter_start


def test_straddling_sentence_goes_to_page_with_more_lines():
    # chunk 0: head + sentences 1 and 2; sentence 1 has 1 line on p5, 3 on p6
    rows = [(5, 1, V(1, 0, 0), 4), (5, 1, V(1, 0, 1), 1), (6, 2, V(1, 0, 1), 3),
            (6, 2, V(1, 0, 2), 2)]
    pages = paginate(rows, _ctr(V(1, 0, 0), V(1, 0, 1), V(1, 0, 2)), {1}, set())
    assert pages[0].pieces == [Piece(1, 0, 0, 1)]
    assert pages[1].pieces == [Piece(1, 0, 1, None)]
    assert pages[1].counters == {"chapter": 1, "equation": 1}
    assert pages[1].first_unit == V(1, 0, 1)


def test_tie_goes_to_the_earlier_page():
    rows = [(5, 1, V(1, 0, 0), 2), (6, 2, V(1, 0, 0), 2)]
    assert paginate(rows, _ctr(V(1, 0, 0)), {1}, set())[0].pieces == [Piece(1, 0, 0, None)]


def test_unit_without_lines_lands_on_its_first_page():
    rows = [(5, 1, V(1, 0), 4), (6, 2, V(1, 1), 0), (7, 3, V(1, 1), 0), (7, 3, V(1, 2), 2)]
    pages = paginate(rows, _ctr(V(1, 0), V(1, 1), V(1, 2)), {1}, set())
    assert pages[1].abspage == 6 and pages[1].pieces == [Piece(1, 1, 0, None)]


def test_missing_unit_inherits_predecessor_page():
    rows = [(5, 1, V(1, 0), 4), (6, 2, V(1, 2), 2)]
    pages = paginate(rows, _ctr(V(1, 0), V(1, 1), V(1, 2)), {1}, set())
    assert pages[0].pieces == [Piece(1, 0, 0, None), Piece(1, 1, 0, None)]
    assert any("not on any page" in n for n in pages[0].notes)


def test_blank_page_is_kept_with_its_number():
    rows = [(5, 1, V(1, 0), 4), (7, 3, V(1, 1), 2)]
    pages = paginate(rows, _ctr(V(1, 0), V(1, 1)), {1}, set())
    assert [(p.abspage, p.page, p.pieces) for p in pages][1] == (6, 2, [])


def test_order_is_clamped():
    # a later unit reported on an earlier page stays after its predecessor
    rows = [(6, 2, V(1, 0), 4), (5, 1, V(1, 1), 3)]
    pages = paginate(rows, _ctr(V(1, 0), V(1, 1)), {1}, set())
    assert [p.abspage for p in pages if p.pieces] == [6]
    assert pages[-1].pieces == [Piece(1, 0, 0, None), Piece(1, 1, 0, None)]
    assert any("order" in n for n in pages[-1].notes)


def test_other_sections_are_left_out():
    rows = [(5, 1, V(1, 0), 4), (5, 1, V(2, 0), 2), (6, 2, V(2, 1), 4)]
    pages = paginate(rows, _ctr(V(1, 0), V(2, 0), V(2, 1)), {2}, {2})
    assert [p.pieces for p in pages] == [[Piece(2, 0, 0, None)], [Piece(2, 1, 0, None)]]
    assert pages[0].chapter_start
