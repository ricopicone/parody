"""Schema v2: rtc-style short-hash stable IDs on sections and anchors.

v1 extraction is pinned by golden parity with the ancestor, so everything
here is opt-in via ``schema: 2`` in parody.yaml / with_hashes=True.
"""


import pytest
import yaml

from parody.build import DuplicateHashError, build_project
from parody.cli import main
from parody.writers.artifact import extract_anchor_ids

SECTION_MD = """\
---
title: Widgets
slug: widgets
id: widgets
hash: w1
---

# Widgets {#widgets h="w1"}

## Inner Heading {#inner-heading h=ih}

::: {#chortle .exercise h="chortle"}
Exercise body.
:::

::: {#ex:demo .example h="x9"}
Example body.
:::

::: {.exercise h="ho"}
Hash-only exercise (no explicit #id) — keyed on its short hash.
:::

![A figure](fig.png){#fig:widget h=fw width=300}

::: {.exercise .lab h="ag"}
Lab problem — numbered L<chapter>.<n> by the web renderer.
:::

::: {.example .lab h="el"}
An example that happens to carry a .lab class — not an exercise, so it must
not be stamped "lab" on its anchor (task #499 F3).
:::
"""


def test_v2_extraction_captures_hashes():
    anchors = {a["id"]: a for a in extract_anchor_ids(SECTION_MD, with_hashes=True)}
    assert anchors["widgets"]["hash"] == "w1"
    assert anchors["inner-heading"]["hash"] == "ih"  # unquoted attr
    assert anchors["chortle"] == {
        "id": "chortle", "type": "exercise", "level": None, "title": None,
        "hash": "chortle",
    }  # id-first div, invisible to the v1 patterns
    assert anchors["ex:demo"]["type"] == "example"
    assert anchors["ex:demo"]["hash"] == "x9"
    # hash-only env (no #id): keyed on its hash so cross-refs can resolve it
    assert anchors["ho"] == {
        "id": "ho", "type": "exercise", "level": None, "title": None,
        "hash": "ho",
    }
    assert anchors["fig:widget"]["hash"] == "fw"


def test_v2_extraction_flags_lab_exercises():
    # ::: {.exercise .lab} is a lab problem ("Problem L4.1"); plain .exercise is
    # a chapter problem ("Problem 4.1"). They run on separate counters, so the
    # artifact has to carry the distinction (task #499).
    anchors = {a["id"]: a for a in extract_anchor_ids(SECTION_MD, with_hashes=True)}
    assert anchors["ag"] == {
        "id": "ag", "type": "exercise", "level": None, "title": None,
        "hash": "ag", "lab": True,
    }
    # the flag is omitted (not False) elsewhere, so non-lab artifacts are
    # byte-identical to before
    assert "lab" not in anchors["ho"]
    assert "lab" not in anchors["ex:demo"]
    # lab is exercise-only: a .lab class on a non-exercise env (::: {.example
    # .lab}) must not be stamped on the anchor, even though it is present in
    # the raw class list (task #499 F3)
    assert anchors["el"]["type"] == "example"
    assert "lab" not in anchors["el"]


def test_unwrap_web_markdown_blocks():
    from parody.writers.artifact import _unwrap_web_markdown_blocks
    md = ("Intro.\n\n"
          "```{=latex}\n\\begin{table}...\\end{table}\n```\n\n"
          "```{=markdown}\n| a | b |\n|:-:|:-:|\n| 1 | 2 |\n\n: Cap {#tbl:x}\n```\n\n"
          "Outro.\n")
    out = _unwrap_web_markdown_blocks(md)
    assert "```{=markdown}" not in out          # the web half is unwrapped
    assert "| a | b |" in out and "{#tbl:x}" in out
    assert "```{=latex}" in out                 # the print half is left for pandoc to drop


def test_raw_html_table_and_figure_ids_anchored():
    # single-source complex tables/figures written directly as HTML must still
    # be anchored (so they number and cross-refs resolve), in document order.
    md = (
        "Intro.\n\n"
        "![A figure](f.png){#fig:a}\n\n"
        '<table id="tbl:demo" class="notes-table"><caption>X</caption>\n'
        "<tbody><tr><td>1</td></tr></tbody></table>\n\n"
        '<figure id="fig:b"><img src="b.svg"></figure>\n'
    )
    anchors = extract_anchor_ids(md)
    by_id = {a["id"]: a for a in anchors}
    assert by_id["tbl:demo"]["type"] == "table"
    assert by_id["fig:b"]["type"] == "figure"
    # document order is preserved (numbering relies on it)
    assert [a["id"] for a in anchors] == ["fig:a", "tbl:demo", "fig:b"]


def test_label_equations_anchored_in_document_order():
    # display equations migrated from LaTeX keep a raw \label{eq:..} inside the
    # math (pandoc doesn't turn it into an id); they must still be registered as
    # equation anchors so they number and cross-refs resolve — interleaved with
    # the {#eq:..} attribute form in document order.
    md = (
        "First $$ x = 1 $$ {#eq:attr-form}\n\n"
        "Then $$\\label{eq:label-form}\n  y = 2.$$\n\n"
        "An aligned block $$\\begin{aligned} a &= b \\label{eq:in-aligned} \\\\\n"
        "  c &= d. \\end{aligned}$$\n"
    )
    anchors = extract_anchor_ids(md, with_hashes=True)
    eqs = [a for a in anchors if a["type"] == "equation"]
    assert [a["id"] for a in eqs] == [
        "eq:attr-form", "eq:label-form", "eq:in-aligned"]


def test_post_process_anchors_and_keeps_math_label():
    from parody.writers.artifact import _post_process_html_for_anchors
    html = ('<span class="math display">\\[\\label{eq:foo}\n x = 1\\]</span>'
            ' rest')
    out = _post_process_html_for_anchors(html)
    assert '<span id="eq:foo"></span>' in out   # scroll/cross-ref carrier
    assert "\\label{eq:foo}" in out             # kept; renderer turns it into \tag
    assert "x = 1" in out


def test_post_process_keeps_labels_in_multi_label_block():
    # a multi-label aligned block keeps its \label{eq:..}s in place so the web
    # renderer can drop a per-line \tag at each numbered row; it still emits one
    # trailing anchor per label (in document order) as scroll/cross-ref carriers.
    from parody.writers.artifact import _post_process_html_for_anchors
    html = ('<span class="math display">\\[\\begin{align}'
            ' a &= b \\label{eq:a}\\\\ c &= d \\label{eq:b} \\end{align}\\]</span>')
    out = _post_process_html_for_anchors(html)
    assert "\\label{eq:a}" in out and "\\label{eq:b}" in out   # kept for \tag
    assert out.index('<span id="eq:a"></span>') < out.index('<span id="eq:b"></span>')


def test_unwrap_subequations_to_fenced_div():
    # \begin{subequations} is dropped by pandoc; rewrite it as a fenced div the
    # web renderer numbers. A labelled group keeps its parent label as the id; an
    # unlabelled group gets a synthetic id (Nth unlabelled group, in order).
    from parody.writers.artifact import _unwrap_subequations
    md = ("\\begin{subequations}\\label{eq:grp}\n\\begin{align}\n"
          "a &= b\n\\end{align}\n\\end{subequations}\n\n"
          "\\begin{subequations}\n\\begin{align}\nc &= d\n\\end{align}\n"
          "\\end{subequations}\n")
    out = _unwrap_subequations(md)
    assert "::: {.subequations #eq:grp}" in out
    assert "::: {.subequations #eq:subeqs-1}" in out
    assert "\\begin{subequations}" not in out          # wrapper gone (renders now)
    assert "\\begin{align}" in out                      # inner math kept


def test_subequations_parent_anchored_in_document_order():
    # the subequations parent is ONE equation anchor, placed in document order
    # between the surrounding plain equations; its inner \label is a member.
    md = ("First $$ x = 1 $$ {#eq:pre}\n\n"
          "\\begin{subequations}\\label{eq:grp}\n\\begin{align}\n"
          "a &= b \\\\\n c &= d \\label{eq:row}\n\\end{align}\n"
          "\\end{subequations}\n\n"
          "Last $$ y = 2 $$ {#eq:post}\n")
    eqs = [a["id"] for a in extract_anchor_ids(md, with_hashes=True)
           if a["type"] == "equation"]
    assert eqs == ["eq:pre", "eq:grp", "eq:row", "eq:post"]
    # the parent \label is consumed by the subequations branch, not also taken as
    # a separate plain equation (which would double-count it).
    assert eqs.count("eq:grp") == 1


def test_infobox_div_anchored_with_title():
    md = ('::: {#box:design .infobox h=vg title="Control System Design Problem"}\n'
          "Body.\n:::\n")
    by_id = {a["id"]: a for a in extract_anchor_ids(md, with_hashes=True)}
    assert by_id["box:design"]["type"] == "infobox"
    assert by_id["box:design"]["title"] == "Control System Design Problem"
    assert by_id["box:design"]["hash"] == "vg"


def test_v1_extraction_unchanged():
    anchors = {a["id"]: a for a in extract_anchor_ids(SECTION_MD)}
    # attr-laden headings and id-first divs stay invisible (golden parity)
    assert "widgets" not in anchors
    assert "inner-heading" not in anchors
    assert "chortle" not in anchors
    assert "ex:demo" not in anchors
    # typed anchors still match, but carry no hash key
    assert "hash" not in anchors["fig:widget"]


@pytest.fixture
def v2_project(tmp_path):
    project_dir = tmp_path / "hash-book"
    assert main([
        "init", str(project_dir),
        "--title", "Hash Book", "--author", "Test Author",
    ]) == 0
    meta = yaml.safe_load((project_dir / "parody.yaml").read_text())
    meta["schema"] = 2
    (project_dir / "parody.yaml").write_text(yaml.safe_dump(meta))
    (project_dir / "chapters/introduction/overview.md").write_text(SECTION_MD)
    return project_dir


def test_v2_build_emits_hashes_and_validates(v2_project, tmp_path):
    out = tmp_path / "artifact.json"
    artifact = build_project(v2_project, out, convert_jupytext=False)
    assert artifact["schema_version"] == 2
    section = artifact["chapters"][0]["sections"][0]
    assert section["hash"] == "w1"
    hashes = {a["id"]: a.get("hash") for a in section["anchors"]}
    assert hashes["chortle"] == "chortle"
    assert hashes["inner-heading"] == "ih"
    assert main(["check", str(out)]) == 0


def test_v2_emits_appendix_flag(v2_project, tmp_path):
    meta = yaml.safe_load((v2_project / "parody.yaml").read_text())
    meta["chapters"][0]["appendix"] = True
    (v2_project / "parody.yaml").write_text(yaml.safe_dump(meta))
    artifact = build_project(v2_project, tmp_path / "artifact.json",
                             convert_jupytext=False)
    assert artifact["chapters"][0]["appendix"] is True


def test_v1_omits_appendix_flag(tmp_path):
    project_dir = tmp_path / "plain-appendix"
    assert main(["init", str(project_dir), "--title", "P", "--author", "A"]) == 0
    meta = yaml.safe_load((project_dir / "parody.yaml").read_text())
    meta["chapters"][0]["appendix"] = True  # v1: flag present but not emitted
    (project_dir / "parody.yaml").write_text(yaml.safe_dump(meta))
    (project_dir / "chapters/introduction/overview.md").write_text(SECTION_MD)
    artifact = build_project(project_dir, tmp_path / "a.json",
                             convert_jupytext=False)
    assert "appendix" not in artifact["chapters"][0]


def test_chapter_start_emitted_when_set(v2_project, tmp_path):
    # chapter_start: 0 (RTC's "Chapter 0") rides along on the artifact so the
    # web renderer can offset its numbering; default 1 is omitted (next test).
    meta = yaml.safe_load((v2_project / "parody.yaml").read_text())
    meta["chapter_start"] = 0
    (v2_project / "parody.yaml").write_text(yaml.safe_dump(meta))
    out = tmp_path / "artifact.json"
    artifact = build_project(v2_project, out, convert_jupytext=False)
    assert artifact["chapter_start"] == 0
    assert main(["check", str(out)]) == 0  # schema accepts it


def test_chapter_start_omitted_at_default(v2_project, tmp_path):
    # No chapter_start (or the default of 1) → key absent; renderer defaults to 1.
    artifact = build_project(v2_project, tmp_path / "artifact.json",
                             convert_jupytext=False)
    assert "chapter_start" not in artifact


def test_v2_duplicate_hashes_are_a_build_error(v2_project, tmp_path):
    dup = SECTION_MD.replace("hash: w1", "hash: w2") \
                    .replace('{#widgets h="w1"}', '{#gadgets h="w2"}') \
                    .replace("slug: widgets", "slug: gadgets") \
                    .replace("id: widgets", "id: gadgets") \
                    .replace("{#chortle", "{#chuckle")  # same h= -> collision
    (v2_project / "chapters/introduction/gadgets.md").write_text(dup)
    meta = yaml.safe_load((v2_project / "parody.yaml").read_text())
    meta["chapters"][0]["sections"].append("gadgets")
    (v2_project / "parody.yaml").write_text(yaml.safe_dump(meta))

    with pytest.raises(DuplicateHashError) as exc:
        build_project(v2_project, tmp_path / "artifact.json",
                      convert_jupytext=False)
    assert "chortle" in str(exc.value)


def test_v1_build_still_default(tmp_path):
    project_dir = tmp_path / "plain-book"
    assert main([
        "init", str(project_dir),
        "--title", "Plain Book", "--author", "Test Author",
    ]) == 0
    (project_dir / "chapters/introduction/overview.md").write_text(SECTION_MD)
    out = tmp_path / "artifact.json"
    artifact = build_project(project_dir, out, convert_jupytext=False)
    assert artifact["schema_version"] == 1
    section = artifact["chapters"][0]["sections"][0]
    assert "hash" not in section
    assert all("hash" not in a for a in section["anchors"])
    assert main(["check", str(out)]) == 0
