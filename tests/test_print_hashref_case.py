r"""An untyped cross-ref key capitalized for sentence case.

parody-web reads `[Quadrilateral]{.hashref}` as "capitalize the label" and looks
the key up case-insensitively. LaTeX labels are case-SENSITIVE, so print used to
answer `\cref{Quadrilateral}` — an undefined reference for a cross-reference
that worked on the web.
"""

from pathlib import Path

import pypandoc

FILTER = Path(__file__).parent.parent / "parody" / "filters" / "print.lua"
PANDOC_FROM = "markdown-markdown_in_html_blocks+raw_tex+tex_math_dollars"


def latex(md):
    return pypandoc.convert_text(md, "latex", format=PANDOC_FROM,
                                 extra_args=[f"--lua-filter={FILTER}"])


def test_a_capitalized_untyped_key_lowercases_and_capitalizes_the_name():
    out = latex("[Quadrilateral]{.hashref} considers the same system.")
    assert "\\Cref{quadrilateral}" in out
    assert "Quadrilateral}" not in out


def test_a_lowercase_key_is_untouched():
    out = latex("see [quadrilateral]{.hashref}.")
    assert "\\cref{quadrilateral}" in out


def test_a_typed_key_still_works():
    out = latex("see [Fig:widget]{.hashref}.")
    assert "\\Cref{fig:widget}" in out
