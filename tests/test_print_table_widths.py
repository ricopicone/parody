r"""A wide table wraps instead of running off the page.

print.lua rebuilt every table as `\begin{tabular}{lll…}` — natural-width
columns that cannot wrap — and threw away the widths pandoc had measured. Four
of System Dynamics' tables ran off the page, one by 719pt, roughly three times
the measure.
"""

from pathlib import Path

import pypandoc

FILTER = Path(__file__).parent.parent / "parody" / "filters" / "print.lua"
PANDOC_FROM = "markdown-markdown_in_html_blocks+raw_tex+tex_math_dollars"

WIDE = """\
| a | b | c |
|:---|:---|:---|
| %s | %s | %s |
""" % ("prose " * 30, "prose " * 30, "prose " * 30)

NARROW = """\
| a | b |
|:--|:--|
| 1 | 2 |
"""


def latex(md):
    return pypandoc.convert_text(md, "latex", format=PANDOC_FROM,
                                 extra_args=[f"--lua-filter={FILTER}"])


def test_a_wide_table_gets_wrapping_columns():
    out = latex(WIDE)
    assert "\\begin{tabular}{>{\\raggedright" in out, out[:400]
    assert "p{\\dimexpr" in out
    assert "\\linewidth" in out
    assert "\\tabcolsep" in out


def test_a_narrow_table_is_left_alone():
    out = latex(NARROW)
    assert "\\begin{tabular}{ll}" in out, out[:300]


def test_the_widths_are_shares_of_the_measure():
    import re
    out = latex(WIDE)
    shares = [int(n) for n in re.findall(r"\\linewidth\*(\d+)/10000", out)]
    assert len(shares) == 3, out[:400]
    assert 9000 < sum(shares) <= 10000, shares
