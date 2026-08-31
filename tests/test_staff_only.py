"""`.staff-only` — content that ships in the artifact and is gated per reader.

This is the mirror image of `.solutions-only`, and the difference is the whole
point of the class existing.

    .solutions-only is a BUILD-time gate.  filter.lua deletes the div unless
                                           PARODY_SOLUTIONS is set, so the
                                           content never enters the artifact a
                                           student's site loads.

    .staff-only is a SERVE-time mark.      The div MUST survive into the
                                           artifact with its class intact,
                                           because one artifact serves both
                                           audiences and only the serving site
                                           knows who is reading.

So the load-bearing web assertions here are positive ones — the opposite of
test_solutions_only.py, where they are negative. What keeps the content off a
student's screen is parody-web's `can_view_staff_notes` policy hook; parody's
job is to not eat the mark on the way through.

Print has no per-reader anything, so there the gate is the one that already
exists: the solutions manual is the only staff artifact, and `.staff-only`
rides `\\ifdefined\\issolution` exactly as `.solutions-only` does.
"""

import os
from contextlib import contextmanager
from pathlib import Path

import pypandoc

FILTERS = Path(__file__).parent.parent / "parody" / "filters"

WEB_FROM = ("markdown-smart-markdown_in_html_blocks+raw_tex"
            "+tex_math_dollars+grid_tables")
PRINT_FROM = "markdown-markdown_in_html_blocks+raw_tex+tex_math_dollars"

PLAIN_MD = """\
::: {.staff-only}
Insist on the sign; half credit for the magnitude alone.
:::
"""

# The shape the robotics notes actually write: the access class beside a
# presentational one, inside a solution.
IN_SOLUTION_MD = """\
::: {.exercise #exe:screw title="Screw axis"}
Find the screw axis.

::: {.exercise-solution}
The axis is the one through the contact point.

::: {.staff-only .grading-notes}
GRADER-EYES-ONLY
:::
:::
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
        extra_args=[f"--lua-filter={FILTERS / 'print.lua'}", "--wrap=none"])


# --- web: the mark has to survive ------------------------------------------

def test_the_div_reaches_the_html_with_its_class():
    out = web(PLAIN_MD)
    assert "staff-only" in out
    assert "Insist on the sign" in out


def test_a_second_class_survives_beside_it():
    # The notes write `.staff-only .grading-notes`: one class is the access
    # mark, the other is presentational. Losing either breaks something.
    out = web("::: {.staff-only .grading-notes}\nX.\n:::\n")
    assert "staff-only" in out
    assert "grading-notes" in out


def test_it_survives_inside_a_solution():
    from parody.writers.artifact import (convert_solution_to_html,
                                         extract_exercise_solutions)

    _, solutions = extract_exercise_solutions(IN_SOLUTION_MD)
    md = solutions["exe:screw"]["content"]
    assert "GRADER-EYES-ONLY" in md

    html = convert_solution_to_html(md, Path(__file__).parent,
                                    cloze_mode="full", solutions=True)
    assert "staff-only" in html
    assert "GRADER-EYES-ONLY" in html


def test_it_is_not_confused_with_solutions_only():
    # `.solutions-only` is dropped from public web html; `.staff-only` is not.
    # The two classes look alike and behave oppositely, so pin it.
    assert "The answer" not in web("::: {.solutions-only}\nThe answer.\n:::\n")
    assert "The answer" in web("::: {.staff-only}\nThe answer.\n:::\n")


# --- print: the solutions manual is the only staff artifact ----------------

def test_print_gates_it_on_issolution():
    out = latex(PLAIN_MD)
    assert "\\ifdefined\\issolution" in out
    assert "Insist on the sign" in out


def test_print_gates_a_second_class_too():
    out = latex("::: {.staff-only .grading-notes}\nMARKER.\n:::\n")
    assert "\\ifdefined\\issolution" in out
    assert "MARKER" in out
