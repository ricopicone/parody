"""A keyword term may contain maths, and print has to keep the $…$.

keyworder stringified the span, which drops the delimiters — so
"[mean of means $\\overline{\\overline{X}_i}$]{.keyword}" reached LaTeX as
\\keyword{mean of means \\overline{\\overline{X}_i}}: "Missing $ inserted",
fatal, no PDF at all. Statistics names four terms that way.
"""

from pathlib import Path

import pypandoc

FILTER = Path(__file__).parent.parent / "parody" / "filters" / "print.lua"
PANDOC_FROM = "markdown-markdown_in_html_blocks+raw_tex+tex_math_dollars"


def render(md, tmp_path):
    p = tmp_path / "s.md"
    p.write_text(md, encoding="utf-8")
    return pypandoc.convert_file(
        str(p), "latex", format=PANDOC_FROM,
        extra_args=[f"--lua-filter={FILTER}", "--biblatex", "--wrap=none"],
        cworkdir=str(tmp_path))


def test_maths_in_a_keyword_keeps_its_delimiters(tmp_path):
    out = render(
        "The [mean of means $\\overline{X}_i$]{.keyword} is best.\n", tmp_path)
    assert "\\keyword{mean of means \\(\\overline{X}_i\\)}" in out \
        or "\\keyword{mean of means $\\overline{X}_i$}" in out, out


def test_a_plain_keyword_is_unchanged(tmp_path):
    out = render("A [line integral]{.keyword} is a thing.\n", tmp_path)
    assert "\\keyword{line integral}" in out, out
