"""Exercise solution/problem extraction across the authoring shapes in use.

Both extractors were ported from the ancestor, which identified exercises with
an explicit `#exe:` id and closed every div with exactly three colons. No
parody-native book writes that: they identify by short hash (`h="sc"`), add
classes (`.lab`), and open fences with three OR four colons. The result was
that every book built since the port shipped an empty `solutions` and
`problems` bucket.

The identity rule under test mirrors filter.lua's `exercise()`: the key is the
explicit identifier when there is one, otherwise the `h=` hash. It has to —
the key is used as an anchor link target back to the rendered exercise box.
"""

import pytest

from parody.writers.artifact import (extract_exercise_problems,
                                     extract_exercise_solutions)

# --- the shapes actually found in the corpus -------------------------------
# Counted across rtc / engineering-computing / math / systems.

ANCESTOR = """\
::: {.exercise #exe:reflex title="Reflex agent"}
State the rule.

::: {.exercise-solution}
ANSWER-ANCESTOR
:::
:::
"""

HASH = """\
::: {.exercise h="sc"}
Do the thing.

::: {.exercise-solution}
ANSWER-HASH
:::
:::
"""

HASH_LAB = """\
::: {.exercise .lab h="sc"}
Do the lab thing.

::: {.exercise-solution .lab}
ANSWER-LAB
:::
:::
"""

FOUR_COLON_UNQUOTED = """\
:::: {.exercise h=quarter}
Weigh it.

:::: {.exercise-solution}
ANSWER-QUARTER
::::
::::
"""


@pytest.mark.parametrize("md,key,answer", [
    (ANCESTOR, "exe:reflex", "ANSWER-ANCESTOR"),
    (HASH, "sc", "ANSWER-HASH"),
    (HASH_LAB, "sc", "ANSWER-LAB"),
    (FOUR_COLON_UNQUOTED, "quarter", "ANSWER-QUARTER"),
])
def test_solution_is_extracted_and_keyed_like_the_renderer(md, key, answer):
    stripped, sols = extract_exercise_solutions(md)
    assert list(sols) == [key]
    assert answer in sols[key]["content"]
    assert answer not in stripped          # …and taken out of the body


def test_ancestor_title_still_read():
    _, sols = extract_exercise_solutions(ANCESTOR)
    assert sols["exe:reflex"]["title"] == "Reflex agent"


def test_exercise_without_a_solution_is_left_alone():
    md = "::: {.exercise h=\"aa\"}\nJust a question.\n:::\n"
    stripped, sols = extract_exercise_solutions(md)
    assert sols == {}
    assert "Just a question." in stripped


def test_a_solutionless_exercise_between_two_others_does_not_merge_them():
    # The ancestor regex needed a negative lookahead for exactly this: without
    # it a match runs from the first exercise past the solutionless one and
    # swallows the next exercise's solution.
    md = (HASH
          + '\n::: {.exercise h="mid"}\nNo answer here.\n:::\n'
          + HASH_LAB.replace('h="sc"', 'h="zz"'))
    _, sols = extract_exercise_solutions(md)
    assert set(sols) == {"sc", "zz"}
    assert "mid" not in sols
    assert "ANSWER-HASH" in sols["sc"]["content"]
    assert "ANSWER-LAB" in sols["zz"]["content"]


def test_nested_div_inside_a_solution_does_not_break_the_fence_scan():
    md = """\
::: {.exercise h="nn"}
Question.

::: {.exercise-solution}
Before.

::: {.listing caption="Answer code."}

``` c
int x;
```

:::

After.
:::
:::

Trailing prose that must survive.
"""
    stripped, sols = extract_exercise_solutions(md)
    assert set(sols) == {"nn"}
    body = sols["nn"]["content"]
    assert "Before." in body and "After." in body and "int x;" in body
    assert "Trailing prose that must survive." in stripped
    assert "Before." not in stripped


# --- problems bucket: the same opener rule ---------------------------------

@pytest.mark.parametrize("md,key", [
    (ANCESTOR, "exe:reflex"),
    (HASH, "sc"),
    (HASH_LAB, "sc"),
    (FOUR_COLON_UNQUOTED, "quarter"),
])
def test_problem_body_is_extracted_for_every_shape(md, key):
    stripped, _ = extract_exercise_solutions(md)
    problems = extract_exercise_problems(stripped)
    assert list(problems) == [key]


def test_problem_body_excludes_the_solution():
    stripped, _ = extract_exercise_solutions(HASH_LAB)
    problems = extract_exercise_problems(stripped)
    assert "Do the lab thing." in problems["sc"]["content"]
    assert "ANSWER-LAB" not in problems["sc"]["content"]


# --- scanner robustness ----------------------------------------------------
# These shapes all appear in the books and each one silently blinded the
# earlier scanner for the remainder of the file.

def test_commented_out_code_fences_do_not_blind_the_scanner():
    md = """\
<!-- ``` c
char *fgets_keypad(char *buf) { return buf; }
``` -->

::: {.exercise h="af"}
Question.

::: {.exercise-solution}
ANSWER-AFTER-COMMENT
:::
:::
"""
    _, sols = extract_exercise_solutions(md)
    assert set(sols) == {"af"}
    assert "ANSWER-AFTER-COMMENT" in sols["af"]["content"]


def test_a_div_inside_an_html_comment_is_not_extracted():
    md = """\
<!--
::: {.exercise h="ghost"}
::: {.exercise-solution}
COMMENTED-OUT
:::
:::
-->

::: {.exercise h="real"}
Q.

::: {.exercise-solution}
REAL-ANSWER
:::
:::
"""
    _, sols = extract_exercise_solutions(md)
    assert set(sols) == {"real"}


def test_info_string_fence_inside_a_code_block_is_content():
    # ```{=latex} on a line inside an open block is NOT a closing fence.
    md = """\
::: {.exercise h="cf"}
Q.

::: {.exercise-solution}
```
```{=latex}
still inside
```

ANSWER-CF
:::
:::
"""
    _, sols = extract_exercise_solutions(md)
    assert set(sols) == {"cf"}
    assert "ANSWER-CF" in sols["cf"]["content"]


BRACELESS = """\
::: {#soldier .exercise h="soldier"}
Draw a linear graph.

::: center
![](fig.pdf)
:::

::: exercise-solution
ANSWER-BRACELESS
:::

:::
"""


def test_braceless_fence_shorthand_is_understood():
    # `::: exercise-solution` == `::: {.exercise-solution}`. An unrecognised
    # opener also mis-pairs the closer of the div AROUND it, so this shape
    # corrupted neighbouring structure, not just its own div.
    stripped, sols = extract_exercise_solutions(BRACELESS)
    assert set(sols) == {"soldier"}
    assert "ANSWER-BRACELESS" in sols["soldier"]["content"]
    assert "ANSWER-BRACELESS" not in stripped
    assert "Draw a linear graph." in stripped
    problems = extract_exercise_problems(stripped)
    assert set(problems) == {"soldier"}
    assert "ANSWER-BRACELESS" not in problems["soldier"]["content"]
