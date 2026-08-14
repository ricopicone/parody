"""`parody publish`: print then web, in that order, wired by the sidecar."""

import json
from pathlib import Path

import pytest

from parody.publish import publish

PARODY_YAML = """\
title: Publish Test
slug: publish-test
authors: [Tester]
schema: 2
chapters:
  - slug: one
    title: Chapter One
    sections: [lead-in, alpha]
"""

EDITION_YAML = PARODY_YAML + """\
editions:
  - id: ed1
    title: First
  - id: ed2
    title: Second
    default: true
"""


def _write_book(root, parody_yaml):
    (root / "chapters" / "one").mkdir(parents=True)
    (root / "parody.yaml").write_text(parody_yaml)
    (root / "chapters" / "one" / "lead-in.md").write_text(
        "---\ntitle: Chapter One\nslug: lead-in\n---\n\nIntro.\n")
    (root / "chapters" / "one" / "alpha.md").write_text(
        "---\ntitle: Alpha\nslug: alpha\n---\n\n# Alpha\n\nBody.\n")
    return root


@pytest.fixture
def project(tmp_path):
    return _write_book(tmp_path / "publish-test", PARODY_YAML)


def _fake_pdf(monkeypatch, ranges):
    """Stand in for a LaTeX build: drop a PDF + its sidecar and return it."""
    calls = []

    def fake_build_pdf(project_dir, output_pdf=None, **kw):
        from parody.writers.pagemap import sidecar_path
        calls.append({"project_dir": project_dir, "output_pdf": output_pdf, **kw})
        out = Path(output_pdf)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"%PDF-1.7\n")
        sidecar_path(out).write_text(json.dumps({
            "schema": 1, "pdf": out.name, "pages": 9, "sha256": "b" * 64,
            "cloze_mode": "blank", "solutions": False, "sections": ranges}))
        return out

    monkeypatch.setattr("parody.publish.build_pdf", fake_build_pdf)
    return calls


def test_publish_builds_the_pdf_before_the_artifact(project, tmp_path, monkeypatch):
    _fake_pdf(monkeypatch, {"one/lead-in": [1, 2], "one/alpha": [2, 9]})
    out = tmp_path / "out"
    written = publish(project, out, convert_jupytext=False)
    artifact = json.loads((out / "publish-test.json").read_text())
    secs = {s["slug"]: s for s in artifact["chapters"][0]["sections"]}
    assert secs["alpha"]["print"] == {"pages": [2, 9]}
    assert artifact["print"]["pages"] == 9
    assert (out / "publish-test.pdf") in written


def test_skip_pdf_reuses_an_existing_sidecar(project, tmp_path, monkeypatch):
    calls = _fake_pdf(monkeypatch, {"one/alpha": [2, 9]})
    out = tmp_path / "out"
    publish(project, out, convert_jupytext=False)
    calls.clear()
    publish(project, out, convert_jupytext=False, skip_pdf=True)
    assert calls == []
    artifact = json.loads((out / "publish-test.json").read_text())
    assert artifact["print"]["pages"] == 9


def test_pdf_only_writes_no_artifact(project, tmp_path, monkeypatch):
    _fake_pdf(monkeypatch, {"one/alpha": [2, 9]})
    out = tmp_path / "out"
    publish(project, out, convert_jupytext=False, pdf_only=True)
    assert (out / "publish-test.pdf").is_file()
    assert not (out / "publish-test.json").exists()


def test_each_edition_gets_its_own_pdf_and_artifact(tmp_path, monkeypatch):
    root = _write_book(tmp_path / "publish-test", EDITION_YAML)
    calls = _fake_pdf(monkeypatch, {"one/alpha": [2, 9]})
    out = tmp_path / "out"
    publish(root, out, convert_jupytext=False)
    assert {c["edition"]["id"] for c in calls} == {"ed1", "ed2"}
    for name in ("publish-test.ed1.pdf", "publish-test.ed2.pdf",
                 "publish-test.ed1.json", "publish-test.ed2.json"):
        assert (out / name).is_file(), name
