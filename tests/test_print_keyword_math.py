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


# The migration escaped the whole \keyword{} argument, so four books carry their
# maths as literal text: "[inductance \$L\$]{.keyword}" reaches the filter as the
# Str "inductance $L$". stringify passed that through as raw LaTeX and it
# typeset; inlines_to_latex escapes it honestly, to \$L\$, and the PDF prints a
# raw dollar and unparsed maths. Rescue the pair back into real maths.

def test_escaped_maths_in_a_keyword_is_rescued(tmp_path):
    out = render("The [inductance \\$L\\$]{.keyword} is a slope.\n", tmp_path)
    assert "\\$" not in out, out
    assert "\\keyword{inductance \\(L\\)}" in out \
        or "\\keyword{inductance $L$}" in out, out


def test_escaped_maths_with_a_macro_is_rescued(tmp_path):
    out = render("The [flux linkage \\$\\\\lambda\\$]{.keyword} counts.\n",
                 tmp_path)
    assert "textbackslash" not in out, out
    assert "\\lambda" in out, out


def test_escaped_maths_in_a_cloze_is_rescued(tmp_path):
    out = render("The [\\$s\\$-plane]{.cloze} is complex.\n", tmp_path)
    assert "\\$" not in out, out
    assert "\\(s\\)-plane" in out or "$s$-plane" in out, out


def test_a_lone_dollar_stays_a_dollar(tmp_path):
    """RTC's problem tables price fruit in dollars — never rescue a lone one."""
    out = render("A [banana costs \\$0.50]{.keyword} today.\n", tmp_path)
    assert "\\keyword{banana costs \\$0.50}" in out, out
