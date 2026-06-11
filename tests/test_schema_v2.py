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

![A figure](fig.png){#fig:widget h=fw width=300}
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
    assert anchors["fig:widget"]["hash"] == "fw"


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
