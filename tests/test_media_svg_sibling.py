"""A figure that already ships a browser-ready .svg beside it should be served
from that file, not re-derived.

Converting a .pgf needs lualatex and a .pdf needs pdftocairo. A CI runner has
neither, and the fallback there is to copy the SOURCE into the media tree and
point the artifact at it — so the page ends up with `<img src="…​.pgf">`, which
no browser renders, and nothing says so. The migrator ships an .svg sibling for
exactly this reason; use it.
"""

import json

from parody.build import _stage_referenced_media


def _artifact(ref):
    return {"chapters": [{"slug": "c", "sections": [
        {"slug": "s", "html": f"<img src=\"{{% media '{ref}' %}}\">"}]}]}


def _run(tmp_path, ref, sources):
    src_root = tmp_path / "book" / "chapters" / "c"
    src_root.mkdir(parents=True)
    for name, body in sources.items():
        (src_root / name).write_text(body)
    media = tmp_path / "media"
    art = _artifact(ref)
    staged, missing = _stage_referenced_media(art, tmp_path / "book", media)
    return art, media, staged, missing


def test_a_pgf_is_served_from_its_svg_sibling(tmp_path):
    art, media, staged, missing = _run(
        tmp_path, "plot.pgf",
        {"plot.pgf": "% pgf source", "plot.svg": "<svg/>"})
    assert missing == []
    assert (media / "plot.svg").read_text() == "<svg/>"
    assert not (media / "plot.pgf").exists(), "the unrenderable source shipped"
    assert "plot.svg" in json.dumps(art)


def test_a_pdf_is_served_from_its_svg_sibling(tmp_path):
    art, media, staged, missing = _run(
        tmp_path, "diagram.pdf",
        {"diagram.pdf": "%PDF-1.4 fake", "diagram.svg": "<svg id='d'/>"})
    assert (media / "diagram.svg").read_text() == "<svg id='d'/>"
    assert "diagram.svg" in json.dumps(art)


def test_a_plain_image_is_untouched(tmp_path):
    art, media, staged, missing = _run(
        tmp_path, "photo.png", {"photo.png": "fake-png"})
    assert (media / "photo.png").read_text() == "fake-png"
