"""The .example environment renders as a box in HTML, as it already does in
print (print.lua's exampler -> \\begin{myexample}). Before this, example() only
stamped data-env-type and returned the div unchanged, so examples were boxed in
PDFs and bare on the web."""

from pathlib import Path

import pypandoc

FILTERS = Path(__file__).parent.parent / "parody" / "filters"
WEB_FROM = ("markdown-smart-markdown_in_html_blocks+raw_tex"
            "+tex_math_dollars+grid_tables")


def web(md):
    return pypandoc.convert_text(
        md, "html", format=WEB_FROM,
        extra_args=[f"--lua-filter={FILTERS / 'filter.lua'}", "--mathjax"])


EXAMPLE_MD = '::: {.example #exa:rotations}\nCompute $R_{ab}$.\n:::'


def test_example_is_marked_as_an_example_environment():
    out = web(EXAMPLE_MD)
    assert 'data-env-type="example"' in out


def test_example_keeps_its_identifier():
    assert 'id="exa:rotations"' in web(EXAMPLE_MD)


def test_example_renders_a_box_not_a_bare_div():
    out = web(EXAMPLE_MD)
    assert "numbered-environment" in out
    assert "border" in out


def test_example_has_a_header_h3_for_numbering():
    """The site's numbering pass rewrites the first <h3> inside the env div."""
    out = web(EXAMPLE_MD)
    assert "<h3" in out


def test_example_header_defaults_to_Example():
    assert "Example" in web(EXAMPLE_MD)


def test_example_title_attribute_wins():
    out = web('::: {.example #exa:t title="Rotating a frame"}\nBody.\n:::')
    assert "Rotating a frame" in out


def test_example_body_content_survives():
    assert "Compute" in web(EXAMPLE_MD)


def test_example_without_an_id_still_boxes():
    """A hash-only example (::: {.example h="c4"}) must still render a box."""
    out = web('::: {.example h="c4"}\nBody.\n:::')
    assert "numbered-environment" in out
