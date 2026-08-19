"""Anchors for labelled items inside a solution."""
import pytest
from parody.writers.artifact import load_section

SECTION = """---
title: Problems
slug: problems
hash: p1
---

# Problems {#problems h="p1"}

::: {#alpha .exercise h="alpha"}
State the thing.

::: {.exercise-solution}
### Matlab {#matlab h="zz"}

The linear graph is shown in [fig:sol-graph]{.hashref}.

![The linear graph.](graph.pdf){#fig:sol-graph .figure}

$$x = 1$$ {#eq:sol-answer}

![Another.](two.pdf){#fig:sol:02 .figure}
:::

:::
"""


@pytest.fixture
def section(tmp_path):
    d = tmp_path / "one"
    d.mkdir()
    (d / "problems.md").write_text(SECTION)
    return d / "problems.md"


def test_solution_anchors_are_extracted_and_tagged(section):
    out = load_section(section.parent, "problems", with_hashes=True)
    sol = [a for a in out["anchors"] if a.get("solution")]
    ids = {a["id"] for a in sol}
    assert "fig:sol-graph" in ids, out["anchors"]
    assert "eq:sol-answer" in ids
    assert {a["solution"] for a in sol} == {"alpha"}


def test_a_label_may_carry_its_own_colon(section):
    """A migrated book writes {#fig:totoro:01}; a label class without ':'
    recorded that as `fig:totoro`, so the reference never resolved and two
    figures in one section collapsed onto one anchor."""
    out = load_section(section.parent, "problems", with_hashes=True)
    ids = {a["id"] for a in out["anchors"]}
    assert "fig:sol:02" in ids
    assert "fig:sol" not in ids


def test_a_solutions_headings_are_not_collected(section):
    """Only numbered things become targets, and two solutions in one section
    routinely share a heading hash in a migrated book — collecting those would
    fail the build's duplicate-hash guard for nothing."""
    out = load_section(section.parent, "problems", with_hashes=True)
    assert not [a for a in out["anchors"]
                if a.get("solution") and a.get("type") == "heading"]


def test_section_anchors_are_untouched(section):
    out = load_section(section.parent, "problems", with_hashes=True)
    plain = [a for a in out["anchors"] if not a.get("solution")]
    assert any(a.get("id") == "alpha" for a in plain)
    # and the solution's figure is still absent from the section html
    assert "fig:sol-graph" not in out["html"]
