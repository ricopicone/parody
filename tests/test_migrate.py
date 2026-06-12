"""Migration toolkit: meta-book layout -> parody content repo, plus the
duplicate-hash re-key step. Exercises the md-backed paths only (the
exercises-tex conversion shells out to the source repo's own latex-to-md
pipeline and is covered by the real migrations; a rewritten converter is
planned before rtc)."""

import yaml

from parody.cli import main
from parody.migrate import migrate_meta_book, rehash_duplicates
from parody.migrate.rehash import used_hashes


def make_meta_src(tmp_path):
    src = tmp_path / "meta-src"
    (src / "chx-one").mkdir(parents=True)
    (src / "mini-0.tex").write_text(
        "\\input{chx-one/chx-one} % One\n"
        "\\input{chx-lists-of-figures-tables}\n")
    # nested-bracket toc arg exercises the header regex
    (src / "chx-one" / "chx-one-header.tex").write_text(
        "\\chapter[One [Draft]]{one}{q1}{One [Draft]}\n")
    (src / "chx-one" / "chx-one.tex").write_text(
        "\\input{chx-one/chx-one-header}\n"
        "\\includesection{q1-lead-in}\n"
        "\\includesection{ab}\n"
        "\\begin{exercises}{ex}\n"
        "\\includesection{ex}\n"
        "\\end{exercises}\n")
    versioned = src / "common" / "versioned"
    (versioned / "q1-lead-in").mkdir(parents=True)
    (versioned / "q1-lead-in" / "source.md").write_text(
        "Lead-in prose, headerless by design.\n")
    (versioned / "ab").mkdir()
    (versioned / "ab" / "source.md").write_text(
        "`\\clearpage`{=latex}\n"
        "\n"
        "# Widgets {#widgets h=\"ab\"}\n"
        "\n"
        "```include\n"
        "source/snip/main.md\n"
        "```\n"
        "\n"
        "![A widget](figures/widget/widget.png)\n"
        "\n"
        "![A plot](figures/plot/plot.pgf)\n"
        "\n"
        "![Gone](figures/gone/gone){.figure}\n"
        "\n"
        "```include\n"
        "source/missing/main.md\n"
        "```\n")
    (versioned / "ex").mkdir()
    (versioned / "ex" / "source.md").write_text(
        "::: {#q .exercise h=\"q\"}\n"
        "Do the thing.\n"
        ":::\n")
    (src / "source" / "snip").mkdir(parents=True)
    (src / "source" / "snip" / "main.md").write_text("Snippet body.\n")
    figs = src / "common" / "figures"
    (figs / "widget").mkdir(parents=True)
    (figs / "widget" / "widget.png").write_bytes(b"\x89PNG fake")
    (figs / "plot").mkdir()
    (figs / "plot" / "plot.pgf").write_text("% pgf")
    (figs / "plot" / "plot.svg").write_text("<svg/>")
    return src


def make_dest(tmp_path):
    dest = tmp_path / "mini-parody"
    assert main(["init", str(dest), "--title", "Mini", "--author", "A"]) == 0
    return dest


def test_migrate_meta_book(tmp_path):
    src = make_meta_src(tmp_path)
    dest = make_dest(tmp_path)
    n_chapters, n_sections = migrate_meta_book(src, dest)
    assert (n_chapters, n_sections) == (1, 3)

    ch = dest / "chapters" / "one"
    lead = (ch / "lead-in.md").read_text()
    assert "title: One [Draft]" in lead, "lead-in takes the chapter title"

    widgets = (ch / "widgets.md").read_text()
    assert "hash: ab" in widgets, "front matter hash from the h= attr"
    assert "Snippet body." in widgets, "include not inlined"
    assert "](widgets-widget.png)" in widgets, "figure not localized"
    assert (ch / "widgets-widget.png").is_file()
    assert (ch / "widgets-plot.pgf").is_file()
    assert (ch / "widgets-plot.svg").is_file(), "svg sibling not shipped"
    assert "TODO(migration): missing figure" in widgets
    assert "TODO(migration): missing include" in widgets

    problems = (ch / "problems.md").read_text()
    assert '# Problems {#one-problems h="ex"}' in problems, \
        "headerless exercises get a synthesized header"

    cfg = yaml.safe_load((dest / "parody.yaml").read_text())
    assert cfg["chapters"] == [{
        "slug": "one", "title": "One [Draft]",
        "sections": ["lead-in", "widgets", "problems"],
        "hash": "q1",
    }]


def test_rehash_duplicates(tmp_path):
    src = make_meta_src(tmp_path)
    dest = make_dest(tmp_path)
    migrate_meta_book(src, dest)

    losers = [
        ("chapters/one/widgets.md", None, "ab"),      # section level
        ("chapters/one/problems.md", "q", "q"),       # anchor level
    ]
    before = used_hashes(dest)
    assert rehash_duplicates(dest, losers, salt="mini") == 2

    widgets = (dest / "chapters" / "one" / "widgets.md").read_text()
    assert "hash: ab" not in widgets and 'h="ab"' not in widgets
    problems = (dest / "chapters" / "one" / "problems.md").read_text()
    assert 'h="q"' not in problems
    # the two contested hashes are replaced 1:1 by fresh ones drawn
    # outside the existing namespace
    after = used_hashes(dest)
    assert {"ab", "q"} <= before and not {"ab", "q"} & after
    assert len(after - before) == 2 and (after - before).isdisjoint(before)

    # idempotent: a second run finds nothing left to re-key
    assert rehash_duplicates(dest, losers, salt="mini") == 0


def test_cli_migrate_and_rehash(tmp_path):
    src = make_meta_src(tmp_path)
    dest = make_dest(tmp_path)
    assert main(["migrate", str(src), "--dest", str(dest)]) == 0

    scripts = dest / "scripts"
    scripts.mkdir()
    (scripts / "rehash_losers.yaml").write_text(yaml.safe_dump([
        {"file": "chapters/one/problems.md", "anchor": "q", "hash": "q"},
    ]))
    assert main(["rehash", "--dest", str(dest)]) == 0
    problems = (dest / "chapters" / "one" / "problems.md").read_text()
    assert 'h="q"' not in problems
