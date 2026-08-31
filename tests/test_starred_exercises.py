"""`::: {.exercise .starred}` — a mark on a problem, carried as data.

A book that wants to single out some problems (harder ones; the graduate
cohort's ones) had nowhere to put that but the words of the title, which is
prose no consumer can render a star from.

`starred` follows the road `.lab` already paved — filter.lua, print.lua, the
anchor, both artifact buckets — with one difference that the assertions below
exist to hold down:

    lab is a KIND of exercise.   It has its own counter and its own xsim type.
    starred is a MODIFIER.       It has neither, and it composes with lab.

A starred problem is still Problem 2.5, and the problem after it is still 2.6.
The tests that matter most here are the ones proving nothing new counts.
"""

from pathlib import Path

import pypandoc

from parody.writers.artifact import (extract_anchor_ids,
                                     extract_exercise_problems,
                                     extract_exercise_solutions)

FILTERS = Path(__file__).parent.parent / "parody" / "filters"

WEB_FROM = ("markdown-smart-markdown_in_html_blocks+raw_tex"
            "+tex_math_dollars+grid_tables")
PRINT_FROM = "markdown-markdown_in_html_blocks+raw_tex+tex_math_dollars"


def web(md):
    return pypandoc.convert_text(
        md, "html", format=WEB_FROM,
        extra_args=[f"--lua-filter={FILTERS / 'filter.lua'}", "--mathjax"])


def latex(md):
    return pypandoc.convert_text(
        md, "latex", format=PRINT_FROM,
        extra_args=[f"--lua-filter={FILTERS / 'print.lua'}", "--wrap=none"])


SECTION_MD = """\
::: {.exercise #exe:plain title="An ordinary problem"}
Ordinary.
:::

::: {.exercise .starred #exe:star title="A starred problem"}
Starred.

::: {.exercise-solution}
STARRED-ANSWER
:::
:::

::: {.exercise .lab .starred h="sl"}
A starred lab problem — both marks at once.
:::

::: {.example .starred #exa:nope}
An example carrying .starred. Not an exercise, so nothing may be stamped.
:::
"""


# --- the artifact anchor ---------------------------------------------------

def test_anchor_carries_starred():
    anchors = {a["id"]: a for a in extract_anchor_ids(SECTION_MD,
                                                      with_hashes=True)}
    assert anchors["exe:star"]["starred"] is True


def test_the_flag_is_omitted_not_false_when_absent():
    # Same posture as `lab`: an unstarred book's artifact stays byte-identical
    # to what it was before this feature existed.
    anchors = {a["id"]: a for a in extract_anchor_ids(SECTION_MD,
                                                      with_hashes=True)}
    assert "starred" not in anchors["exe:plain"]


def test_starred_is_exercise_only():
    # A .starred class on a non-exercise environment is in the raw class list
    # but must not reach the anchor — the same guard `lab` needs.
    anchors = {a["id"]: a for a in extract_anchor_ids(SECTION_MD,
                                                      with_hashes=True)}
    assert anchors["exa:nope"]["type"] == "example"
    assert "starred" not in anchors["exa:nope"]


def test_starred_composes_with_lab():
    anchors = {a["id"]: a for a in extract_anchor_ids(SECTION_MD,
                                                      with_hashes=True)}
    assert anchors["sl"]["lab"] is True
    assert anchors["sl"]["starred"] is True


def test_v1_extraction_is_unchanged():
    # starred rides the v2 attribute scan, as `lab` does; the v1 path does not
    # parse classes and never has.
    anchors = {a["id"]: a for a in extract_anchor_ids(SECTION_MD,
                                                      with_hashes=False)}
    assert "starred" not in anchors["exe:star"]


# --- the artifact buckets --------------------------------------------------

def test_problems_bucket_carries_starred():
    problems = extract_exercise_problems(SECTION_MD)
    assert problems["exe:star"]["starred"] is True
    assert problems["exe:plain"]["starred"] is False
    assert problems["sl"]["starred"] is True


def test_solutions_bucket_carries_starred():
    _, solutions = extract_exercise_solutions(SECTION_MD)
    assert solutions["exe:star"]["starred"] is True
    assert "STARRED-ANSWER" in solutions["exe:star"]["content"]


# --- the web box -----------------------------------------------------------

def test_web_box_carries_the_class_and_data_attribute():
    out = web('::: {.exercise .starred #exe:s title="T"}\nBody.\n:::\n')
    assert "starred" in out
    assert 'data-starred="1"' in out


def test_web_box_is_unmarked_when_not_starred():
    out = web('::: {.exercise #exe:s title="T"}\nBody.\n:::\n')
    assert "starred" not in out


def test_web_box_carries_both_marks():
    out = web('::: {.exercise .lab .starred h="sl"}\nBody.\n:::\n')
    assert 'data-lab="1"' in out
    assert 'data-starred="1"' in out


# --- print -----------------------------------------------------------------

def test_print_marks_a_starred_exercise():
    out = latex('::: {.exercise .starred #exe:s}\nBody.\n:::\n')
    assert "\\parodystarmark" in out


def test_print_leaves_an_ordinary_exercise_alone():
    out = latex('::: {.exercise #exe:s}\nBody.\n:::\n')
    assert "\\parodystarmark" not in out


def test_print_introduces_no_new_environment():
    # The load-bearing one. A starred problem stays in the `exercise`
    # environment, so it keeps its place in the ordinary counter; a starred
    # LAB problem stays in `labexercise`, on the lab counter.
    out = latex('::: {.exercise .starred #exe:s}\nBody.\n:::\n')
    assert "\\begin{exercise}" in out
    assert "starredexercise" not in out

    lab = latex('::: {.exercise .lab .starred h="sl"}\nBody.\n:::\n')
    assert "\\begin{labexercise}" in lab
    assert "\\parodystarmark" in lab


def test_the_star_macro_is_defined_by_both_profiles():
    # print.lua emits \parodystarmark unconditionally when the class is there,
    # so a profile that never defines it fails the whole build at TeX time.
    profiles = Path(__file__).parent.parent / "parody" / "profiles"
    for sty in (profiles / "memoir" / "parody-environments.sty",
                profiles / "print" / "parody-print.sty"):
        assert "\\parodystarmark" in sty.read_text(), sty


# --- the real writer path --------------------------------------------------
# The extractors above are only half the journey: load_section REBUILDS each
# bucket entry around the converted html, so a key present on the extractor's
# dict can still be dropped before it reaches the artifact. It was — the unit
# tests above passed while the built artifact carried no `starred` at all, and
# only a real build caught it.

def test_the_built_artifact_carries_starred_on_both_buckets(tmp_path):
    from parody.writers.artifact import load_section

    (tmp_path / "starred.md").write_text(
        '---\ntitle: Starred\nslug: starred\nid: starred\n---\n\n'
        '# Starred {#starred}\n\n'
        '::: {.exercise .starred #exe:star title="Starred"}\n'
        'Do the harder thing.\n\n'
        '::: {.exercise-solution}\n'
        'The answer.\n'
        ':::\n'
        ':::\n\n'
        '::: {.exercise #exe:plain title="Plain"}\n'
        'Do the ordinary thing.\n\n'
        '::: {.exercise-solution}\n'
        'The other answer.\n'
        ':::\n'
        ':::\n')

    sec = load_section(tmp_path, "starred", with_hashes=True)

    assert sec["problems"]["exe:star"]["starred"] is True
    assert sec["solutions"]["exe:star"]["starred"] is True
    assert sec["problems"]["exe:plain"]["starred"] is False
    assert sec["solutions"]["exe:plain"]["starred"] is False

    anchors = {a["id"]: a for a in sec["anchors"]}
    assert anchors["exe:star"].get("starred") is True
    assert "starred" not in anchors["exe:plain"]
