r"""A label two headings claim is not labelled in print.

A heading id only has to be unique inside its own file, but print.lua labels
every heading with that id and the whole book shares one LaTeX namespace. Three
sections opening "## Stability" all emitted \label{stability}; "multiply
defined" is a warning, so it shipped and a \ref took whichever came last.
System Dynamics had 16 of them.
"""

import pytest

from parody.writers.latex import ambiguous_heading_labels, build_pdf

SEC_A = """\
---
title: Alpha
slug: alpha
hash: aa
---

# Alpha {#alpha h="aa"}

## Stability {#stability h="s1"}

Text.
"""

SEC_B = """\
---
title: Beta
slug: beta
hash: bb
---

# Beta {#beta h="bb"}

## Stability {#stability h="s2"}

More text.
"""

PARODY_YAML = """\
title: Clash Test
slug: clash
authors: [Tester]
chapters:
  - slug: one
    title: Chapter One
    sections: [alpha, beta]
"""


@pytest.fixture
def project(tmp_path):
    root = tmp_path / "clash"
    (root / "chapters" / "one").mkdir(parents=True)
    (root / "parody.yaml").write_text(PARODY_YAML)
    (root / "chapters" / "one" / "alpha.md").write_text(SEC_A)
    (root / "chapters" / "one" / "beta.md").write_text(SEC_B)
    return root


@pytest.fixture
def no_tex(monkeypatch):
    monkeypatch.setattr("parody.writers.latex.shutil.which", lambda *a, **k: None)


def test_the_census_finds_the_clash(project):
    found = ambiguous_heading_labels(
        [project / "chapters" / "one" / "alpha.md",
         project / "chapters" / "one" / "beta.md"], [("one", "c1")])
    assert "stability" in found
    # the unique ones are left alone
    assert "s1" not in found and "aa" not in found and "alpha" not in found


def test_a_heading_id_clashing_with_a_hash_counts(project):
    # System Dynamics had one: a section whose hash was "qa" also carried an
    # inner heading written {#qa}.
    (project / "chapters" / "one" / "beta.md").write_text(
        SEC_B.replace('{#stability h="s2"}', '{#aa h="s2"}'))
    found = ambiguous_heading_labels(
        [project / "chapters" / "one" / "alpha.md",
         project / "chapters" / "one" / "beta.md"], [])
    assert "aa" in found


def test_the_clashing_label_is_not_emitted(project, no_tex):
    build_pdf(project)
    build = project / "build" / "print"
    a = (build / "sections" / "one" / "alpha.tex").read_text()
    b = (build / "sections" / "one" / "beta.tex").read_text()
    assert "\\label{stability}" not in a
    assert "\\label{stability}" not in b
    # the short hash is unique per book and still carries the cross-reference
    assert "\\label{s1}" in a
    assert "\\label{s2}" in b


def test_an_unambiguous_id_is_still_labelled(project, no_tex):
    build_pdf(project)
    a = (project / "build" / "print" / "sections" / "one" / "alpha.tex").read_text()
    assert "\\label{alpha}" in a


def test_the_build_says_which_labels_it_dropped(project, no_tex, capsys):
    build_pdf(project)
    assert "stability" in capsys.readouterr().out
