"""Phase 3 golden LaTeX-snippet tests.

The print.lua filter's LaTeX emission is pinned by a committed golden .tex
file, regenerated only deliberately:

    uv run pytest tests/test_print_snippets.py --regen-golden

Behavior reference: rtc-book common/filter.lua (the environments inventory
in the seed plan §Phase 3).
"""

from pathlib import Path

import pypandoc
import pytest

FIXTURES = Path(__file__).parent / "print_fixtures"
FILTER = Path(__file__).parent.parent / "parody" / "filters" / "print.lua"
PANDOC_FROM = "markdown-markdown_in_html_blocks+raw_tex+tex_math_dollars"


def render(md_path):
    return pypandoc.convert_file(
        str(md_path), "latex", format=PANDOC_FROM,
        extra_args=[f"--lua-filter={FILTER}", "--biblatex", "--wrap=none"],
        cworkdir=str(md_path.parent),
    )


def pytest_addoption_workaround():  # documented flag lives in conftest.py
    pass


def test_environments_snippet_matches_golden(request):
    md = FIXTURES / "environments.md"
    golden = FIXTURES / "environments.golden.tex"
    out = render(md)
    if request.config.getoption("--regen-golden"):
        golden.write_text(out, encoding="utf-8")
        pytest.skip("golden regenerated")
    assert golden.exists(), "golden missing — run with --regen-golden once"
    expected = golden.read_text(encoding="utf-8")
    assert out == expected, (
        "print.lua LaTeX emission changed; diff the output against "
        f"{golden} and regenerate deliberately if intended"
    )


@pytest.mark.parametrize("needle", [
    # one assertion per ported environment/span, so a failure names the
    # environment rather than just diffing a blob
    "\\begin{definition}{Limit}{def:limit}",
    "\\begin{theorem}{Big Theorem}{thm:big}",
    "\\begin{lemma}{}{lem:small}",
    "\\begin{corollary}{}{cor:tiny}",
    "\\begin{infobox}[label=box:note]{A Note}",
    "\\begin{exercise}[ID=e1,hash=e1]",
    "\\end{exercise}",
    "\\begin{solution}",
    "\\begin{myexample}[]{exm:demo}{x1}",
    "\\tcblower",
    "\\begin{listingsboxfloat}{clisting}{Hello in C}{lst:hello}{htbp}",
    "\\begin{listingsbox}{pythonlisting}{A script}{lst:script}",
    "\\begin{formattedoutput}",
    "\\begin{mintedwrapper}",
    "\\begin{minted}[autogobble,samepage]{python}",
    "\\keyword{important term}",
    "\\myindex[][][][]{convolution}",
    "\\indexc[][][cfun][true][]{c}{printf}",
    "\\path{/etc/hosts}",
    "\\mykeys{Ctrl+C}",
    "\\menu{File,Save}",
    "\\unicoder{λ}",
    # pygments accepts the 'py' alias; ancestor emits the original class too
    "\\mintinline{py}|x = 1|",
    "\\autocite[ p. 3]{doe2020}",
    "\\textcite[{cf.}][{ch. 2}]{doe2020}",
    "\\cref{sec:envs}",
    "\\Cref{sec:envs}",
    "\\lref{line:5}",
    "\\myurl[][]{https://example.org}{ab}",
    "\\myurlinline{https://example.org}{cd}",
    "\\figcaption",
    "\\includegraphics[width=3in]{figures/plot.png}",
    "\\tabcaption[][nofloat]{tbl:demo}{A caption}",
    "\\toprule",
    "\\section{Print Environments}",
    "\\label{sec:envs}",
])
def test_environment_emission(needle):
    out = render(FIXTURES / "environments.md")
    assert needle in out, f"missing from print.lua LaTeX output: {needle}"
