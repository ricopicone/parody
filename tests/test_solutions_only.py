"""`.solutions-only` content must never reach a public build.

Print gates it with \\ifdefined\\issolution. The web has no solutions manual —
its answer-key surface is the owner-gated `solutions` bucket — so the web
filter drops the div outright unless it is rendering that bucket.

The load-bearing assertions here are the negative ones: anything this filter
emits into section html is fetchable by any reader.
"""

import os
from contextlib import contextmanager
from pathlib import Path

import pypandoc

FILTERS = Path(__file__).parent.parent / "parody" / "filters"

WEB_FROM = ("markdown-smart-markdown_in_html_blocks+raw_tex"
            "+tex_math_dollars+grid_tables")
PRINT_FROM = "markdown-markdown_in_html_blocks+raw_tex+tex_math_dollars"

# A solutions-manual listing as rtc writes them: captioned, id'd, and holding
# the answer code.
LISTING_MD = """\
::: {#lst:lab-6-main .listing .linenos .nofloat .solutions-only caption="The `main.c` file."}

``` c
int secret_answer(void) { return 42; }
```

:::
"""

# The same class on a plain div, to pin that the gate is about the class and
# not about listings.
PLAIN_MD = """\
::: {.solutions-only}
The answer is 42.
:::
"""


@contextmanager
def solutions_context(on):
    saved = os.environ.get("PARODY_SOLUTIONS")
    if on:
        os.environ["PARODY_SOLUTIONS"] = "1"
    else:
        os.environ.pop("PARODY_SOLUTIONS", None)
    try:
        yield
    finally:
        if saved is None:
            os.environ.pop("PARODY_SOLUTIONS", None)
        else:
            os.environ["PARODY_SOLUTIONS"] = saved


def web(md, solutions=False):
    with solutions_context(solutions):
        return pypandoc.convert_text(
            md, "html", format=WEB_FROM,
            extra_args=[f"--lua-filter={FILTERS / 'filter.lua'}", "--mathjax"])


def latex(md):
    return pypandoc.convert_text(
        md, "latex", format=PRINT_FROM,
        extra_args=[f"--lua-filter={FILTERS / 'print.lua'}"])


# --- web: the public section html ------------------------------------------

def test_web_drops_the_listing_entirely():
    out = web(LISTING_MD)
    assert "secret_answer" not in out
    assert "main.c" not in out          # the caption leaked before this fix
    assert "lst:lab-6-main" not in out  # …and with it a phantom listing number


def test_web_drops_a_plain_solutions_only_div():
    assert "The answer is 42." not in web(PLAIN_MD)


def test_web_keeps_unrelated_divs():
    out = web("::: {.listing caption=\"Ordinary.\"}\n\n``` c\nint x;\n```\n\n:::\n")
    assert 'class="listing"' in out
    assert "Ordinary." in out


# --- web: the owner-gated solutions bucket ---------------------------------

def test_web_keeps_it_in_solutions_context():
    out = web(LISTING_MD, solutions=True)
    assert "secret_answer" in out
    assert "lst:lab-6-main" in out


def test_solution_conversion_is_a_solutions_context():
    from parody.writers.artifact import convert_solution_to_html

    html = convert_solution_to_html(LISTING_MD, Path(__file__).parent,
                                    cloze_mode="full", solutions=True)
    assert "secret_answer" in html


def test_problem_conversion_is_not_a_solutions_context():
    from parody.writers.artifact import convert_solution_to_html

    html = convert_solution_to_html(LISTING_MD, Path(__file__).parent)
    assert "secret_answer" not in html


def test_solutions_flag_does_not_leak_into_later_runs():
    from parody.writers.artifact import convert_solution_to_html

    convert_solution_to_html(LISTING_MD, Path(__file__).parent, solutions=True)
    assert "secret_answer" not in web(LISTING_MD)


# --- print: unchanged ------------------------------------------------------

def test_print_still_gates_on_issolution():
    out = latex(LISTING_MD)
    assert "\\ifdefined\\issolution" in out
    assert "secret_answer" in out
