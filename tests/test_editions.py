"""Edition-aware build (P1): the ``editions:`` schema, per-section membership,
single-source-until-fork overlay, and one-artifact-per-edition output."""

import json

import pytest
import yaml

from parody.build import build_editions, build_project
from parody.cli import main
from parody.config import load_project, normalize_editions

DB = {
    "ts": {
        "T1": {"description": "first target", "target-computer": {"name": "myRIO"}},
        "T2": {"description": "second target", "target-computer": {"name": "Pi 5"}},
    },
    "ds": {
        "D1": {"description": "first dev"},
        "D2": {"description": "second dev"},
    },
}

EDITIONS = [
    {"id": "ed1", "title": "First edition", "tracks": {"ts": "T1", "ds": "D1"}},
    {"id": "ed2", "title": "Second edition", "tracks": {"ts": "T2", "ds": "D2"}},
]


def write_project(tmp_path, *, editions=EDITIONS, with_versioning=True):
    project_dir = tmp_path / "ebook"
    assert main(["init", str(project_dir), "--title", "E", "--author", "A"]) == 0
    (project_dir / "versions.yaml").write_text(yaml.safe_dump(DB))
    meta = yaml.safe_load((project_dir / "parody.yaml").read_text())
    if editions is not None:
        meta["editions"] = editions
    if with_versioning:
        # tracks are supplied per-edition; source path is shared
        meta["versioning"] = {"source": "versions.yaml", "tracks": {"ts": "T1"}}
    (project_dir / "parody.yaml").write_text(yaml.safe_dump(meta))
    return project_dir


def write_section(project_dir, chapter, slug, body, *, filename=None,
                  front=""):
    path = project_dir / "chapters" / chapter / (filename or f"{slug}.md")
    path.write_text(f"---\ntitle: {slug}\nslug: {slug}\nid: {slug}\n{front}---\n\n"
                    f"# {slug} {{#{slug}}}\n\n{body}\n")
    return path


# --- schema normalization ---------------------------------------------------

def test_normalize_defaults_latest():
    eds = normalize_editions(EDITIONS)
    assert [e["id"] for e in eds] == ["ed1", "ed2"]
    assert eds[0]["default"] is False
    assert eds[1]["default"] is True  # latest wins when none flagged


def test_normalize_honors_explicit_default():
    eds = normalize_editions([
        {"id": "a", "default": True}, {"id": "b"}])
    assert eds[0]["default"] is True and eds[1]["default"] is False


def test_normalize_requires_id():
    with pytest.raises(Exception):
        normalize_editions([{"tracks": {"ts": "T1"}}])


def test_normalize_draft_flag():
    eds = normalize_editions([
        {"id": "ed1"}, {"id": "ed2", "draft": True}])
    assert eds[0]["draft"] is False
    assert eds[1]["draft"] is True


def test_draft_flag_reaches_artifact(tmp_path):
    project_dir = write_project(tmp_path, editions=[
        {"id": "ed1", "tracks": {"ts": "T1", "ds": "D1"}},
        {"id": "ed2", "tracks": {"ts": "T2", "ds": "D1"}, "draft": True},
    ])
    write_section(project_dir, "introduction", "overview", "x")
    out_dir = tmp_path / "art"
    build_editions(project_dir, out_dir, convert_jupytext=False)
    ed2 = json.loads((out_dir / "ebook.ed2.json").read_text())
    assert ed2["edition"]["draft"] is True
    # the roster carries draft so the renderer can mark/hide siblings
    roster = {e["id"]: e["draft"] for e in ed2["editions"]}
    assert roster == {"ed1": False, "ed2": True}


def test_load_project_exposes_editions(tmp_path):
    project_dir = write_project(tmp_path)
    project = load_project(project_dir)
    assert [e["id"] for e in project.editions] == ["ed1", "ed2"]


# --- per-edition track substitution ----------------------------------------

def test_each_edition_substitutes_its_tracks(tmp_path):
    project_dir = write_project(tmp_path)
    write_section(project_dir, "introduction", "overview",
                  "Target []{.ts} dev []{.ds}: []{.T1-target-computer-name}"
                  " / []{.T2-target-computer-name}.")
    out_dir = tmp_path / "artifact"
    paths = build_editions(project_dir, out_dir, convert_jupytext=False)
    assert [p.name for p in paths] == ["ebook.ed1.json", "ebook.ed2.json"]

    ed1 = json.loads((out_dir / "ebook.ed1.json").read_text())
    ed2 = json.loads((out_dir / "ebook.ed2.json").read_text())
    html1 = ed1["chapters"][0]["sections"][0]["html"]
    html2 = ed2["chapters"][0]["sections"][0]["html"]
    assert "T1" in html1 and "D1" in html1 and "{.ts}" not in html1
    assert "T2" in html2 and "D2" in html2

    assert ed1["edition"]["id"] == "ed1" and ed1["edition"]["default"] is False
    assert ed2["edition"]["default"] is True
    # roster present on each artifact for the switcher
    assert [e["id"] for e in ed1["editions"]] == ["ed1", "ed2"]


# --- single-source overlay & membership ------------------------------------

def test_shared_section_serves_all_editions(tmp_path):
    project_dir = write_project(tmp_path)
    write_section(project_dir, "introduction", "overview", "shared body")
    out_dir = tmp_path / "a"
    build_editions(project_dir, out_dir, convert_jupytext=False)
    for ed in ("ed1", "ed2"):
        art = json.loads((out_dir / f"ebook.{ed}.json").read_text())
        assert art["chapters"][0]["sections"][0]["slug"] == "overview"


def test_fork_shadows_shared_for_one_edition(tmp_path):
    project_dir = write_project(tmp_path)
    write_section(project_dir, "introduction", "overview", "SHARED text")
    write_section(project_dir, "introduction", "overview", "FORKED ed2 text",
                  filename="overview.ed2.md")
    out_dir = tmp_path / "a"
    build_editions(project_dir, out_dir, convert_jupytext=False)
    ed1 = json.loads((out_dir / "ebook.ed1.json").read_text())
    ed2 = json.loads((out_dir / "ebook.ed2.json").read_text())
    assert "SHARED" in ed1["chapters"][0]["sections"][0]["html"]
    assert "FORKED" in ed2["chapters"][0]["sections"][0]["html"]


def test_membership_frontmatter_restricts(tmp_path):
    project_dir = write_project(tmp_path)
    write_section(project_dir, "introduction", "overview", "ed1 only",
                  front="editions: [ed1]\n")
    out_dir = tmp_path / "a"
    build_editions(project_dir, out_dir, convert_jupytext=False)
    ed1 = json.loads((out_dir / "ebook.ed1.json").read_text())
    ed2 = json.loads((out_dir / "ebook.ed2.json").read_text())
    assert ed1["chapters"][0]["sections"]  # present
    # absent from ed2 -> its only chapter has no sections and is dropped
    assert ed2["chapters"] == []


def test_edition_only_new_section(tmp_path):
    """A section that exists only as a fork belongs only to that edition."""
    project_dir = write_project(tmp_path)
    write_section(project_dir, "introduction", "overview", "shared")
    # parody.yaml must list the slug for it to be considered
    meta = yaml.safe_load((project_dir / "parody.yaml").read_text())
    meta["chapters"][0]["sections"].append("whatsnew")
    (project_dir / "parody.yaml").write_text(yaml.safe_dump(meta))
    write_section(project_dir, "introduction", "whatsnew", "new in ed2",
                  filename="whatsnew.ed2.md")
    out_dir = tmp_path / "a"
    build_editions(project_dir, out_dir, convert_jupytext=False)
    ed1 = json.loads((out_dir / "ebook.ed1.json").read_text())
    ed2 = json.loads((out_dir / "ebook.ed2.json").read_text())
    assert [s["slug"] for s in ed1["chapters"][0]["sections"]] == ["overview"]
    assert [s["slug"] for s in ed2["chapters"][0]["sections"]] == \
        ["overview", "whatsnew"]


# --- CLI --------------------------------------------------------------------

def test_cli_builds_all_editions(tmp_path):
    project_dir = write_project(tmp_path)
    write_section(project_dir, "introduction", "overview", "[]{.ts}")
    out_dir = tmp_path / "out"
    assert main(["build", str(project_dir), str(out_dir / "ebook.json"),
                 "--no-execute"]) == 0
    assert (out_dir / "ebook.ed1.json").is_file()
    assert (out_dir / "ebook.ed2.json").is_file()


def test_cli_single_edition(tmp_path):
    project_dir = write_project(tmp_path)
    write_section(project_dir, "introduction", "overview", "[]{.ts}")
    out = tmp_path / "just_ed2.json"
    assert main(["build", str(project_dir), str(out),
                 "--edition", "ed2", "--no-execute"]) == 0
    art = json.loads(out.read_text())
    assert art["edition"]["id"] == "ed2"
    assert "T2" in art["chapters"][0]["sections"][0]["html"]


def test_cli_unknown_edition_errors(tmp_path):
    project_dir = write_project(tmp_path)
    write_section(project_dir, "introduction", "overview", "x")
    assert main(["build", str(project_dir), str(tmp_path / "o.json"),
                 "--edition", "nope", "--no-execute"]) == 1


# --- back-compat ------------------------------------------------------------

def test_no_editions_single_build_is_unchanged(tmp_path):
    project_dir = write_project(tmp_path, editions=None)
    write_section(project_dir, "introduction", "overview", "[]{.ts}")
    out = tmp_path / "plain.json"
    art = build_project(project_dir, out, convert_jupytext=False)
    assert "edition" not in art and "editions" not in art
    assert art["chapters"][0]["sections"][0]["slug"] == "overview"


def test_build_editions_requires_editions(tmp_path):
    project_dir = write_project(tmp_path, editions=None)
    with pytest.raises(ValueError, match="no editions"):
        build_editions(project_dir, tmp_path / "out", convert_jupytext=False)


def test_edition_artifact_validates_against_schema_v2(tmp_path):
    project_dir = write_project(tmp_path)
    meta = yaml.safe_load((project_dir / "parody.yaml").read_text())
    meta["schema"] = 2
    (project_dir / "parody.yaml").write_text(yaml.safe_dump(meta))
    write_section(project_dir, "introduction", "overview", "For []{.ts}.",
                  front="hash: zz\n")
    out = tmp_path / "ed2.json"
    assert main(["build", str(project_dir), str(out),
                 "--edition", "ed2", "--no-execute"]) == 0
    assert main(["check", str(out)]) == 0
