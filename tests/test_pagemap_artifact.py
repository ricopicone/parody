"""The page-map sidecar reaches the artifact, keyed <chapter>/<section>."""

import json
from pathlib import Path

import pytest

from parody.build import build_project

PARODY_YAML = """\
title: Artifact Page Map
slug: artifact-pagemap
authors: [Tester]
schema: 2
chapters:
  - slug: one
    title: Chapter One
    sections: [lead-in, alpha]
"""

SIDECAR = {
    "schema": 1,
    "pdf": "artifact-pagemap.pdf",
    "pages": 42,
    "sha256": "a" * 64,
    "cloze_mode": "blank",
    "solutions": False,
    "sections": {"one/lead-in": [3, 4], "one/alpha": [4, 9]},
}


@pytest.fixture
def project(tmp_path):
    root = tmp_path / "artifact-pagemap"
    (root / "chapters" / "one").mkdir(parents=True)
    (root / "parody.yaml").write_text(PARODY_YAML)
    # build_project (unlike build_pdf) requires per-section frontmatter.
    (root / "chapters" / "one" / "lead-in.md").write_text(
        "---\ntitle: Chapter One\nslug: lead-in\n---\n\nIntro.\n")
    (root / "chapters" / "one" / "alpha.md").write_text(
        "---\ntitle: Alpha\nslug: alpha\n---\n\n# Alpha\n\nBody.\n")
    return root


@pytest.fixture
def sidecar(tmp_path):
    p = tmp_path / "artifact-pagemap.pages.json"
    p.write_text(json.dumps(SIDECAR))
    return p


def _sections(artifact):
    return {s["slug"]: s for s in artifact["chapters"][0]["sections"]}


def test_sections_carry_their_page_range(project, sidecar, tmp_path):
    art = build_project(project, tmp_path / "out.json",
                        convert_jupytext=False, print_pages=sidecar)
    secs = _sections(art)
    assert secs["lead-in"]["print"] == {"pages": [3, 4]}
    assert secs["alpha"]["print"] == {"pages": [4, 9]}


def test_book_level_print_metadata_is_carried(project, sidecar, tmp_path):
    art = build_project(project, tmp_path / "out.json",
                        convert_jupytext=False, print_pages=sidecar)
    assert art["print"] == {
        "pdf": "artifact-pagemap.pdf", "pages": 42, "sha256": "a" * 64}


def test_without_a_sidecar_no_print_keys_appear(project, tmp_path):
    art = build_project(project, tmp_path / "out.json", convert_jupytext=False)
    assert "print" not in art
    assert all("print" not in s for s in _sections(art).values())


def test_a_section_absent_from_the_sidecar_gets_no_print_key(project, tmp_path):
    partial = tmp_path / "partial.pages.json"
    partial.write_text(json.dumps(
        dict(SIDECAR, sections={"one/lead-in": [3, 4]})))
    art = build_project(project, tmp_path / "out.json",
                        convert_jupytext=False, print_pages=partial)
    secs = _sections(art)
    assert secs["lead-in"]["print"] == {"pages": [3, 4]}
    assert "print" not in secs["alpha"]


def test_a_missing_sidecar_file_is_an_error(project, tmp_path):
    with pytest.raises(FileNotFoundError):
        build_project(project, tmp_path / "out.json", convert_jupytext=False,
                      print_pages=tmp_path / "nope.json")


def test_the_artifact_still_validates(project, sidecar, tmp_path):
    import jsonschema

    out = tmp_path / "out.json"
    build_project(project, out, convert_jupytext=False, print_pages=sidecar)
    schema_path = (Path(__file__).parent.parent / "parody" / "schemas"
                   / "artifact-v2.json")
    schema = json.loads(schema_path.read_text())
    jsonschema.Draft202012Validator(schema).validate(json.loads(out.read_text()))
