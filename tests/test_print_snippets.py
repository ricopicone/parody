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
    # a .freadinglist div routes through the \freadinglist macro (numbered
    # "Further Reading" box); its .plaincite items become brace-grouped
    # \textcite so their inner commas don't split the \docsvlist
    "\\freadinglist{{\\textcite[{}][{ch. 1, an overview}]{doe2020}}",
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
    # 'arm' has no Pygments lexer; remapped to nasm so the print build compiles
    "\\begin{minted}[autogobble,samepage]{nasm}",
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
    # both pgf src conventions resolve to the same \inputpgf (which appends .pgf)
    "\\inputpgf{figures/wave}",
    "\\inputpgf{figures/pulse}",
    # classless .pgf outside a figure div must not reach \includegraphics
    "\\inputpgf{figures/spike}",
    "\\tabcaption[][nofloat]{tbl:demo}{A caption}",
    # a top-level section with a companion hash drops a heading QR (profile
    # renders \parodyqr if defined; guarded so other profiles no-op)
    "\\ifcsname parodyqr\\endcsname\\parodyqr{hd}\\fi",
    # an image whose id is tbl:* is a table in the book numbering -> genuine
    # table float (caption above), not a figure, even though it's an image
    "\\begin{table}[H]%\n\\tabcaption[][nofloat]{tbl:asimage}{A table that is "
    "rendered as an image.}",
    # subfigures are native size by default...
    "\\noindent\\includegraphics{figures/plot.png}",
    # ...unless a scale=/width= opts them into scaling (third-party art)
    "\\noindent\\includegraphics[scale=0.8]{figures/plot.png}",
    "\\toprule",
    "\\section{Print Environments}",
    "\\label{sec:envs}",
    # inline code in a heading: escaped \texttt (moving-arg safe), NOT \mintinline.
    # underscore is escaped; \texorpdfstring keeps the PDF bookmark text plain
    "\\texorpdfstring{\\texttt{fgets\\_keypad()}}{fgets_keypad()}",
    "\\texorpdfstring{\\texttt{main}}{main}}",
    # same safe form inside a figure caption (also a moving argument)
    "naming \\texorpdfstring{\\texttt{a.out}}{a.out}",
    # a subfigure caption pandoc misread as a "(a)" list flattens to plain
    # text, never a list environment inside \figcaption (fatal in print)
    "{fig:subs}{(a) The left plot and (b) the right plot.}",
])
def test_environment_emission(needle):
    out = render(FIXTURES / "environments.md")
    assert needle in out, f"missing from print.lua LaTeX output: {needle}"


def test_subfigure_list_caption_not_an_environment():
    # the "(a) ... (b) ..." caption must not become \begin{enumerate} inside
    # the \figcaption moving argument (breaks lualatex with Incomplete \iffalse)
    out = render(FIXTURES / "environments.md")
    _, _, tail = out.partition("{fig:subs}{")
    assert "\\begin{enumerate}" not in tail.split("}\n")[0]


def test_raw_html_table_backslash_paren_math_not_leaked():
    # \(...\) math in a raw-HTML table's cells must parse as math, not escape
    # to \textbackslash( and leak as literal text (RawBlock re-read needs
    # tex_math_single_backslash). tbl:htmlmath cell is \(\dfrac{1}{K_q}\).
    out = render(FIXTURES / "environments.md")
    assert "\\textbackslash(" not in out
    assert "\\dfrac{1}{K_q}" in out  # cell: real math, not escaped \textbackslash
    assert "$q(t)$" in out  # caption: math renders too, not stringified to nothing
