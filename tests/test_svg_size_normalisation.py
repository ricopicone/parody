"""A figure's rendered size must not depend on which poppler built it.

pdftocairo writes the page box in points, but older builds emit the bare number
(``width="132.438"``) where newer ones emit ``width="132.438pt"``. A bare number
is user units — CSS px — so the same figure comes out 4/3 smaller. RTC's
published media holds both spellings (227 unitless against 10 with pt), which
means figures within one book differ in size by a third, and a CI build does not
match a local one.
"""

import pytest

from parody.writers.preview import _normalise_svg_size

# A pdftocairo figure, glyph ids and all: that fingerprint is what licenses
# reading a unitless width as points (see the fingerprint cases at the bottom).
HEAD = ('<?xml version="1.0" encoding="UTF-8"?>\n'
        '<svg xmlns="http://www.w3.org/2000/svg" {dims} '
        'viewBox="0 0 132.438 85.7788">\n'
        '<g id="glyph-0-0"><path d="M 0 0"/></g>\n</svg>\n')


def write(tmp_path, dims):
    p = tmp_path / "fig.svg"
    p.write_text(HEAD.format(dims=dims))
    return p


def test_points_become_css_px(tmp_path):
    p = write(tmp_path, 'width="132.438pt" height="85.7788pt"')
    _normalise_svg_size(p)
    out = p.read_text()
    assert 'width="176.5840px"' in out       # 132.438 * 96/72
    assert 'height="114.3717px"' in out


def test_the_bare_number_is_points_too(tmp_path):
    # the older poppler spelling. It must normalise to exactly what the pt
    # spelling gives — same figure, same size, whichever converter built it.
    bare = tmp_path / "bare.svg"
    bare.write_text(HEAD.format(dims='width="132.438" height="85.7788"'))
    pt = tmp_path / "pt.svg"
    pt.write_text(HEAD.format(dims='width="132.438pt" height="85.7788pt"'))
    _normalise_svg_size(bare)
    _normalise_svg_size(pt)
    assert bare.read_text() == pt.read_text()


def test_the_viewbox_is_left_alone(tmp_path):
    # it keeps the point-valued coordinate system; the larger width/height
    # scale it, which is the intent
    p = write(tmp_path, 'width="132.438pt" height="85.7788pt"')
    _normalise_svg_size(p)
    assert 'viewBox="0 0 132.438 85.7788"' in p.read_text()


def test_already_px_is_untouched(tmp_path):
    p = write(tmp_path, 'width="176.584px" height="114.372px"')
    before = p.read_text()
    _normalise_svg_size(p)
    assert p.read_text() == before


def test_no_viewbox_is_left_alone(tmp_path):
    # without a viewBox, width/height define the coordinate system rather than
    # scaling it, so rewriting them would resize the drawing, not the box
    p = tmp_path / "fig.svg"
    p.write_text('<svg xmlns="http://www.w3.org/2000/svg" '
                 'width="132.438pt" height="85.7788pt"><g/></svg>')
    before = p.read_text()
    _normalise_svg_size(p)
    assert p.read_text() == before


def test_is_idempotent(tmp_path):
    p = write(tmp_path, 'width="132.438pt" height="85.7788pt"')
    _normalise_svg_size(p)
    once = p.read_text()
    _normalise_svg_size(p)
    assert p.read_text() == once


def test_body_content_is_untouched(tmp_path):
    p = tmp_path / "fig.svg"
    p.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="10pt" '
                 'height="10pt" viewBox="0 0 10 10">'
                 '<rect width="10" height="10"/></svg>')
    _normalise_svg_size(p)
    out = p.read_text()
    # only the root tag's dimensions move; the rect keeps its user units
    assert '<rect width="10" height="10"/>' in out
    assert 'width="13.3333px"' in out


def test_a_missing_file_is_not_an_error(tmp_path):
    _normalise_svg_size(tmp_path / "nope.svg")     # must not raise


# ---- a bare number is only points when cairo wrote the file ---------------
# Books carry hand-drawn SVGs beside the converted ones — RTC has six Adobe
# Illustrator exports — and there a unitless width really is CSS px. Measured
# over RTC's 124 committed SVGs the rule below converts 118 and leaves 6.

CAIRO_BODY = '<g id="glyph-0-0"><path d="M 0 0"/></g>'
CLIP_BODY = '<clipPath id="clip-0"><path clip-rule="nonzero" d="M 0 0"/></clipPath>'
PLAIN_BODY = '<rect width="10" height="10"/>'


def svg(tmp_path, dims, body, name="fig.svg"):
    p = tmp_path / name
    p.write_text('<svg xmlns="http://www.w3.org/2000/svg" '
                 f'{dims} viewBox="0 0 132.438 85.7788">{body}</svg>')
    return p


@pytest.mark.parametrize("body,label", [(CAIRO_BODY, "glyph ids"),
                                        (CLIP_BODY, "clip ids, no text")])
def test_cairo_fingerprints_licence_a_bare_number(tmp_path, body, label):
    p = svg(tmp_path, 'width="132.438" height="85.7788"', body)
    _normalise_svg_size(p)
    assert 'width="176.5840px"' in p.read_text(), label


def test_a_bare_number_without_a_cairo_fingerprint_is_left_alone(tmp_path):
    # an Illustrator export: unitless really does mean CSS px here, and
    # converting would enlarge the drawing by a third
    p = svg(tmp_path, 'width="132.438" height="85.7788"',
            '<!-- Generator: Adobe Illustrator 27.7.0 -->' + PLAIN_BODY)
    before = p.read_text()
    _normalise_svg_size(p)
    assert p.read_text() == before


def test_an_explicit_pt_is_converted_whoever_wrote_it(tmp_path):
    # pt is unambiguous, so no fingerprint is needed
    p = svg(tmp_path, 'width="132.438pt" height="85.7788pt"',
            '<!-- Generator: Adobe Illustrator 27.7.0 -->' + PLAIN_BODY)
    _normalise_svg_size(p)
    assert 'width="176.5840px"' in p.read_text()


def test_an_unknown_generator_with_a_bare_number_is_left_alone(tmp_path):
    p = svg(tmp_path, 'width="468" height="305.58"', PLAIN_BODY)
    before = p.read_text()
    _normalise_svg_size(p)
    assert p.read_text() == before
