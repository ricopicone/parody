"""Two ways source can reach no reader without the build saying a word.

Both shipped to live sites before anyone noticed:

* A bare LaTeX macro left in the markdown by migration parses as raw TeX and
  pandoc's HTML writer discards it. Thévenin's theorem on the Electronics
  Primer read "can be reproduced exactly by a single ." because
  ``\\emph{voltage source ... in series with a resistor ...}`` was dropped whole.
* Two environments sharing an ``#id``: the second is skipped by anchor
  extraction, taking its short hash with it, so it gets no number and no
  cross-reference target. RTC shipped two
  ``::: {#exa:operator-precedence-2 .example}`` blocks; the second went
  unnumbered on rtcbook.org.

Neither failed anything. These tests are the "say something" half.
"""

import subprocess
from pathlib import Path

import pypandoc
import pytest

from parody.writers.artifact import extract_anchor_ids

FILTER = Path(__file__).resolve().parents[1] / "parody" / "filters" / "filter.lua"


def _convert(markdown):
    """Run the real web filter over `markdown`, returning (html, stderr)."""
    proc = subprocess.run(
        [pypandoc.get_pandoc_path(), "-f", "markdown", "-t", "html",
         f"--lua-filter={FILTER}"],
        input=markdown, capture_output=True, text=True)
    return proc.stdout, proc.stderr


# ---- dropped raw LaTeX ----------------------------------------------------

def test_bare_macro_is_reported():
    html, err = _convert(
        "The equivalent is a single \\emph{voltage source in series}.\n")
    # still dropped — reporting it, not repairing it
    assert "voltage source in series" not in html
    assert "dropped raw LaTeX" in err
    assert "\\emph{voltage source in series}" in err


def test_block_level_macro_is_reported():
    _, err = _convert("\\oldsubsubsection{Using the open-loop gain}\n")
    assert "dropped raw LaTeX" in err
    assert "oldsubsubsection" in err


def test_declared_latex_span_is_not_reported():
    # `\foo`{=latex} is a deliberate print-only aside; pandoc marks it "latex"
    # rather than the inferred "tex". Warning about these would train everyone
    # to ignore the warning.
    _, err = _convert("A deliberate `\\raggedleft`{=latex} span.\n")
    assert "dropped raw LaTeX" not in err


def test_math_is_not_reported():
    # \frac and friends live inside math, which survives to MathJax
    _, err = _convert("Inline $\\frac{a}{b}$ and $$\\sqrt{x}$$ are fine.\n")
    assert "dropped raw LaTeX" not in err


def test_the_report_names_the_chapter(monkeypatch):
    monkeypatch.setenv("PARODY_CHAPTER_SLUG", "fundamentals")
    proc = subprocess.run(
        [pypandoc.get_pandoc_path(), "-f", "markdown", "-t", "html",
         f"--lua-filter={FILTER}"],
        input="Text \\emph{gone missing} here.\n", capture_output=True, text=True)
    assert "fundamentals" in proc.stderr


def test_clean_markdown_is_silent():
    _, err = _convert("Ordinary *emphasis* and **strong** and `code`.\n")
    assert "dropped raw LaTeX" not in err


# ---- duplicate ids --------------------------------------------------------

DUPES = """
::: {#exa:precedence .example h="fh"}
First example.
:::

::: {#exa:precedence .example h="vp"}
Second example, same id.
:::
"""


def test_duplicate_id_is_reported(capsys):
    extract_anchor_ids(DUPES, with_hashes=True)
    err = capsys.readouterr().err
    assert "id 'exa:precedence' is declared 2 times" in err


def test_duplicate_id_still_drops_the_later_anchor(capsys):
    # the warning documents existing behaviour; it does not change it, because
    # which of the two should be renamed is the author's call
    anchors = extract_anchor_ids(DUPES, with_hashes=True)
    ids = [a["id"] for a in anchors]
    assert ids.count("exa:precedence") == 1
    # and the dropped one took its hash with it — the point of the warning
    assert [a.get("hash") for a in anchors if a["id"] == "exa:precedence"] == ["fh"]


def test_distinct_ids_are_silent(capsys):
    md = DUPES.replace('#exa:precedence .example h="vp"',
                       '#exa:precedence-2 .example h="vp"')
    anchors = extract_anchor_ids(md, with_hashes=True)
    assert capsys.readouterr().err == ""
    assert sorted(a["id"] for a in anchors) == ["exa:precedence",
                                                "exa:precedence-2"]


def test_a_commented_out_attribute_block_is_not_a_duplicate(capsys):
    # These books keep the superseded attribute block in a comment right under
    # the heading that replaced it. Counting those made a false duplicate of
    # nearly every migrated heading in RTC — 22 of them, against 0 real.
    md = ('## Introduction {#intro .unnumbered h="l7"}\n'
          '<!---{#intro h="l7"} --->\n\nBody.\n')
    extract_anchor_ids(md, with_hashes=True)
    assert capsys.readouterr().err == ""


def test_an_id_inside_a_fence_is_not_a_duplicate(capsys):
    # a ```{=markdown} fence holding a print-only variant of a figure div; the
    # HTML writer drops it, so it declares nothing
    md = ('```{=markdown}\n::: {#fig:x}\nprint-only variant\n:::\n```\n\n'
          '::: {#fig:x .figure}\nthe real one\n:::\n')
    extract_anchor_ids(md, with_hashes=True)
    assert capsys.readouterr().err == ""


def test_a_heading_and_a_div_sharing_an_id_is_a_duplicate(capsys):
    # the shape that actually bit the Electronics Primer: "## Voltage {#voltage}"
    # and "::: {#voltage .definition}". The heading is anchored first, so the
    # definition gets no number — it renders as a bare "Definition" while its
    # siblings read "Definition 1.1".
    md = ('## Voltage {#voltage h="cw"}\n\n'
          '::: {#voltage .definition}\nPotential difference.\n:::\n')
    extract_anchor_ids(md, with_hashes=True)
    assert "id 'voltage' is declared 2 times" in capsys.readouterr().err


@pytest.mark.parametrize("env", ["definition", "theorem", "comment",
                                 "exercise", "infobox"])
def test_duplicate_id_reported_for_every_environment(env, capsys):
    md = (f'::: {{#dup:x .{env} h="aa"}}\nOne.\n:::\n\n'
          f'::: {{#dup:x .{env} h="bb"}}\nTwo.\n:::\n')
    extract_anchor_ids(md, with_hashes=True)
    assert "id 'dup:x' is declared 2 times" in capsys.readouterr().err


# ---- only prose is worth reporting ----------------------------------------
# Across RTC's 120 chapters pandoc drops 478 raw TeX nodes; 271 are print-only
# spacing and most of the rest are math symbols leaking out of raw HTML tables.
# Reporting all of them is how a warning gets ignored.

@pytest.mark.parametrize("macro", ["\\noindent", "\\newpage", "\\pagebreak",
                                   "\\looseness=-2", "\\clearpage"])
def test_print_only_spacing_is_not_reported(macro):
    _, err = _convert(f"{macro}\nSome text.\n")
    assert "dropped raw LaTeX" not in err


@pytest.mark.parametrize("macro", ["\\circ", "\\top", "\\bot", "\\times",
                                   "\\infty", "\\lnot"])
def test_stray_math_symbols_are_not_reported(macro):
    # these leak out of raw HTML tables, where the markup passes through whole
    # and MathJax still renders them
    _, err = _convert(f"<tr><th>{macro} p</th></tr>\n")
    assert "dropped raw LaTeX" not in err


def test_single_word_argument_is_not_reported():
    # \mathit{RTOS}, \begin{subequations} — a lone token is a symbol or an
    # environment name, not a sentence
    _, err = _convert("A \\mathit{RTOS} reference.\n")
    assert "dropped raw LaTeX" not in err


def test_two_word_argument_is_reported():
    _, err = _convert("It is \\emph{globally defined} here.\n")
    assert "dropped raw LaTeX" in err
