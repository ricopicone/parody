"""Two figures that share a basename must each be served from their own file.

A book whose figures live in directories — chapters/<ch>/<figure>/main.svg —
references every one of them as `…/<figure>/main.svg`. Resolving a ref by its
basename alone hands all of them the first `main.svg` the directory walk met,
so every such figure in the book shows the same drawing (mechatronics lab
manual v0.2.0: the diode-bridge chapter's five circuits were all the RLC
circuit). The ref carries the path; resolve by it.
"""

import json

from parody.build import _stage_referenced_media

SLUG = "book"


def _ref(chapter, figure):
    return f"notebooks/{SLUG}/chapters/{chapter}/{figure}/main.svg"


def _artifact(refs):
    return {"chapters": [{"slug": "c", "sections": [
        {"slug": "s", "html": "".join(
            f"<img src=\"{{% media '{r}' %}}\">" for r in refs)}]}]}


def _make_figures(book, figures):
    for chapter, figure, body in figures:
        d = book / "chapters" / chapter / figure
        d.mkdir(parents=True)
        (d / "main.svg").write_text(body)


def test_same_basename_in_different_figure_dirs_stays_distinct(tmp_path):
    book = tmp_path / SLUG
    figures = [("rlc", "rlc-circuit", "<svg id='rlc'/>"),
               ("diode", "rectifier1", "<svg id='rect1'/>"),
               ("diode", "rectifier2", "<svg id='rect2'/>")]
    _make_figures(book, figures)
    refs = [_ref(ch, fig) for ch, fig, _ in figures]
    art = _artifact(refs)
    media = tmp_path / "media"

    staged, missing = _stage_referenced_media(art, book, media)

    assert missing == []
    assert staged == 3
    for (_, _, body), ref in zip(figures, refs):
        assert (media / ref).read_text() == body, ref
    assert json.dumps(art).count("main.svg") == 3


def test_a_bare_ref_still_resolves_by_basename(tmp_path):
    """Meta-migrated books reference flat names; those keep resolving."""
    book = tmp_path / SLUG
    _make_figures(book, [("c", "fig", "<svg id='only'/>")])
    art = _artifact(["main.svg"])
    media = tmp_path / "media"

    staged, missing = _stage_referenced_media(art, book, media)

    assert missing == []
    assert (media / "main.svg").read_text() == "<svg id='only'/>"
