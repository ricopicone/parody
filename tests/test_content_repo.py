"""Phase 2: content-repo layout — init scaffold, build, schema validity."""

import json

import pytest

from parody.cli import main
from parody.config import ProjectLayoutError, detect_layout, load_project


@pytest.fixture
def scaffold(tmp_path):
    project_dir = tmp_path / "my-book"
    assert main([
        "init", str(project_dir),
        "--title", "My Book", "--author", "Test Author",
    ]) == 0
    return project_dir


def test_init_creates_expected_layout(scaffold):
    for rel in [
        "parody.yaml",
        "README.md",
        "CONTRIBUTING.md",
        ".gitignore",
        ".github/workflows/build.yml",
        "chapters/introduction/overview.md",
        "chapters/introduction/example_code.py",
        "assets/.gitkeep",
    ]:
        assert (scaffold / rel).is_file(), f"missing {rel}"

    workflow = (scaffold / ".github/workflows/build.yml").read_text()
    assert "$parody_version" not in workflow, "placeholder not substituted"
    assert "startsWith(github.ref" in workflow, "GitHub expression mangled by templating"
    assert "parody==" in workflow


def test_init_refuses_nonempty_dir(tmp_path):
    (tmp_path / "junk.txt").write_text("x")
    with pytest.raises(SystemExit):
        main(["init", str(tmp_path)])


def test_layout_detection(scaffold, tmp_path):
    assert detect_layout(scaffold) == "parody"
    with pytest.raises(ProjectLayoutError):
        detect_layout(tmp_path / "nonexistent-ish")


def test_load_project(scaffold):
    project = load_project(scaffold)
    assert project.slug == "my-book"
    assert project.meta["title"] == "My Book"
    assert project.meta["author"] == ["Test Author"]
    assert [c.slug for c in project.chapters] == ["introduction"]
    assert project.chapters[0].section_slugs == ["overview"]


def test_build_no_execute_produces_valid_artifact(scaffold, tmp_path):
    artifact_path = tmp_path / "out" / "my-book.json"
    assert main(["build", str(scaffold), str(artifact_path), "--no-execute"]) == 0
    assert main(["check", str(artifact_path)]) == 0

    artifact = json.loads(artifact_path.read_text())
    assert artifact["slug"] == "my-book"
    assert artifact["generator"].startswith("parody ")
    section = artifact["chapters"][0]["sections"][0]
    assert section["slug"] == "overview"
    # Exercise solution extracted, not inlined
    assert section["has_solutions"] is True
    assert "exe:sample" in section["solutions"]
    assert "stripped from the public section body" not in section["html"]
    # Without execution, include-py falls back to showing the source code
    assert "jupytext-fallback" in section["html"]
    # Anchors picked up from frontmatter id and headings
    anchor_ids = {a["id"] for a in section["anchors"]}
    assert {"sec-overview", "getting-started", "exe:sample"} <= anchor_ids


@pytest.mark.execution
def test_build_with_execution_captures_figures(scaffold, tmp_path):
    artifact_path = tmp_path / "out" / "my-book.json"
    assert main(["build", str(scaffold), str(artifact_path)]) == 0
    assert main(["check", str(artifact_path)]) == 0

    artifact = json.loads(artifact_path.read_text())
    html = artifact["chapters"][0]["sections"][0]["html"]
    assert "jupytext-included" in html, "executed code not spliced into section"
    assert "sampled 200 points" in html, "cell output missing"
    # Figure media path carries the env-provided slug context (not 'unknown')
    assert "{% media 'notebooks/my-book/introduction/example_code_files/" in html
    # ...and the figure file actually landed there (media_root = project dir)
    figs = list((scaffold / "media" / "notebooks" / "my-book" / "introduction").rglob("autofig-*"))
    assert figs, "auto-captured figure not moved into the project media tree"
