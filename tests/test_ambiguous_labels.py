r"""A label two headings claim is not labelled in print.

A heading id only has to be unique inside its own file, but print.lua labels
every heading with that id and the whole book shares one LaTeX namespace. Three
sections opening "## Stability" all emitted \label{stability} — and so do
headings with NO id, because pandoc generates one from the title. "Multiply
defined" is a warning, so it shipped and a \ref took whichever came last.
System Dynamics had 16 of them.
"""

import pytest

from parody.writers.latex import build_pdf, drop_duplicate_labels

SEC_A = """\
---
title: Alpha
slug: alpha
hash: aa
---

# Alpha {#alpha h="aa"}

## Stability {#stability h="s1"}

### Lumping {-}

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

### Lumping {-}

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


def test_a_repeated_label_is_dropped_from_every_file(tmp_path):
    a = tmp_path / "a.tex"
    a.write_text(r"\section{A}\label{same}\label{one}")
    b = tmp_path / "b.tex"
    b.write_text(r"\section{B}\label{same}\label{two}")
    assert drop_duplicate_labels([a, b]) == {"same"}
    assert a.read_text() == r"\section{A}\label{one}"
    assert b.read_text() == r"\section{B}\label{two}"


def test_a_unique_label_is_left_alone(tmp_path):
    a = tmp_path / "a.tex"
    a.write_text(r"\label{only}")
    assert drop_duplicate_labels([a]) == set()
    assert a.read_text() == r"\label{only}"


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


def test_a_pandoc_generated_id_counts_too(project, no_tex):
    """"### Lumping {-}" declares no id at all; pandoc generates `lumping`
    from the title, and print.lua labels it. Counting the markdown could not
    see these — counting the emitted .tex does."""
    build_pdf(project)
    build = project / "build" / "print"
    for name in ("alpha", "beta"):
        assert "\\label{lumping}" not in (
            build / "sections" / "one" / f"{name}.tex").read_text()


def test_a_chapter_label_wins_over_a_section_heading(tmp_path):
    """A heading whose id is a chapter slug loses its label; the chapter, which
    is what a reader means by that name, keeps the one main.tex emits."""
    a = tmp_path / "a.tex"
    a.write_text(r"\section{Introduction}\label{introduction}\label{jx}")
    assert drop_duplicate_labels([a], reserved=["introduction"]) == {"introduction"}
    assert a.read_text() == r"\section{Introduction}\label{jx}"


def test_an_unambiguous_id_is_still_labelled(project, no_tex):
    build_pdf(project)
    a = (project / "build" / "print" / "sections" / "one" / "alpha.tex").read_text()
    assert "\\label{alpha}" in a


def test_the_build_says_which_labels_it_dropped(project, no_tex, capsys):
    build_pdf(project)
    out = capsys.readouterr().out
    assert "stability" in out and "lumping" in out
