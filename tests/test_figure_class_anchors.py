"""A figure whose id carries no `fig:` prefix is still a figure.

The typed-anchor scan keys off the id prefix, so an image written
`![cap](x.pdf){#brew_1 .figure}` — the form a migrated notebook figure takes
when the author labelled it without a prefix — got no anchor at all: no
number, and no cross-reference target, while print numbered it normally from the
same source. The `.figure` class is the declaration; honour it.
"""

from parody.writers.artifact import extract_anchor_ids


def _by_id(md, **kw):
    return {a["id"]: a for a in extract_anchor_ids(md, **kw)}


BARE = ('![Confidence interval versus confidence.](problems-brew_1.pdf)'
        '{#brew_1 .figure h="brew_1"\n'
        'caption_plain="Confidence interval versus confidence."}\n')


def test_a_class_declared_figure_is_anchored():
    assert _by_id(BARE)["brew_1"]["type"] == "figure"


def test_it_carries_its_hash_in_v2():
    assert _by_id(BARE, with_hashes=True)["brew_1"]["hash"] == "brew_1"


def test_a_prefixed_figure_is_unaffected():
    md = '![Cap](p.pdf){#fig:plot .figure}\n'
    assert _by_id(md)["fig:plot"]["type"] == "figure"
    assert len(extract_anchor_ids(md)) == 1, "no duplicate anchor"


def test_an_image_without_the_class_is_not_a_figure():
    md = '![Cap](p.pdf){#decoration width=50%}\n'
    assert _by_id(md).get("decoration", {}).get("type") != "figure"


def test_document_order_is_preserved():
    md = ('![A](a.pdf){#fig:a .figure}\n\n'
          '![B](b.pdf){#bare_b .figure}\n\n'
          '![C](c.pdf){#fig:c .figure}\n')
    assert [a["id"] for a in extract_anchor_ids(md)] == [
        "fig:a", "bare_b", "fig:c"]
