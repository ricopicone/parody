"""Web-publication mechanism: online_only marking, per-section
online_resources, and the `build --online-only` partial artifact (rtcbook.org
subset). Renderer-agnostic — the dedicated Django book-host consumes this."""

import yaml

from parody.build import build_project, _filter_online_only
from parody.cli import main
from parody.writers.artifact import _heading_is_online_only


def test_heading_online_only_detection():
    assert _heading_is_online_only(
        '# Specific T1 systems {#x .online-only .ts h="ef"}\n\nbody')
    assert _heading_is_online_only(
        '<!-- comment -->\n\n## Foo {.online-only}\n')  # skips comments
    assert not _heading_is_online_only('# Plain heading {#x h="ab"}\n\nbody')
    assert not _heading_is_online_only('Just a paragraph, no heading.\n')


def _book(tmp_path):
    project_dir = tmp_path / "webbook"
    assert main(["init", str(project_dir), "--title", "W", "--author", "A"]) == 0
    meta = yaml.safe_load((project_dir / "parody.yaml").read_text())
    meta["schema"] = 2
    meta["chapters"] = [{
        "slug": "introduction", "title": "Intro",
        "sections": ["online-sec", "resourced-sec", "plain-sec"],
    }]
    (project_dir / "parody.yaml").write_text(yaml.safe_dump(meta))
    ch = project_dir / "chapters/introduction"
    # an online-only section (heading carries .online-only)
    (ch / "online-sec.md").write_text(
        '---\ntitle: Online Sec\nslug: online-sec\nid: online-sec\nhash: o1\n---\n\n'
        '# Online Sec {#online-sec .online-only h="o1"}\n\nWeb-licensed body.\n')
    # a normal section with per-section online resources
    (ch / "resourced-sec.md").write_text(
        '---\ntitle: Resourced\nslug: resourced-sec\nid: resourced-sec\nhash: r1\n---\n\n'
        '# Resourced {#resourced-sec h="r1"}\n\nCopyrighted body.\n')
    (ch / "resourced-sec.online.md").write_text(
        "Extra web-only links for this section.\n")
    # a plain section with neither (and a placeholder online file -> ignored)
    (ch / "plain-sec.md").write_text(
        '---\ntitle: Plain\nslug: plain-sec\nid: plain-sec\nhash: p1\n---\n\n'
        '# Plain {#plain-sec h="p1"}\n\nJust body.\n')
    (ch / "plain-sec.online.md").write_text("No online resources.\n")
    return project_dir


def test_artifact_marks_online_only_and_resources(tmp_path):
    art = build_project(_book(tmp_path), tmp_path / "a.json",
                        convert_jupytext=False)
    secs = {s["slug"]: s for s in art["chapters"][0]["sections"]}
    assert secs["online-sec"].get("online_only") is True
    assert "online_only" not in secs["resourced-sec"]
    assert "online_resources" in secs["resourced-sec"]
    assert "web-only links" in secs["resourced-sec"]["online_resources"]
    # placeholder 'No online resources.' is dropped
    assert "online_resources" not in secs["plain-sec"]
    assert "online_only" not in secs["plain-sec"]


def test_build_online_only_partial_artifact(tmp_path):
    out = tmp_path / "partial.json"
    art = build_project(_book(tmp_path), out, convert_jupytext=False,
                        online_only=True)
    secs = {s["slug"]: s for s in art["chapters"][0]["sections"]}
    # online-only section: kept in full
    assert "online-sec" in secs
    assert "Web-licensed body" in secs["online-sec"]["html"]
    # resourced section: kept as a resource-only page, body stripped (MIT-safe)
    assert "resourced-sec" in secs
    assert "html" not in secs["resourced-sec"]
    assert "online_resources" in secs["resourced-sec"]
    # plain section: dropped entirely
    assert "plain-sec" not in secs


def test_filter_drops_empty_chapters():
    output = {"chapters": [
        {"slug": "a", "title": "A", "sections": [
            {"slug": "s", "online_only": True, "html": "x"}]},
        {"slug": "b", "title": "B", "sections": [
            {"slug": "t", "html": "copyrighted"}]},  # nothing public -> drop ch
    ]}
    filtered = _filter_online_only(output)
    assert [c["slug"] for c in filtered["chapters"]] == ["a"]


def test_v1_does_not_emit_web_fields(tmp_path):
    # v1 (default schema) stays clean — online_only/online_resources are v2-only
    project_dir = tmp_path / "v1book"
    assert main(["init", str(project_dir), "--title", "V", "--author", "A"]) == 0
    ch = project_dir / "chapters/introduction"
    (ch / "overview.md").write_text(
        '---\ntitle: O\nslug: overview\nid: o\n---\n\n'
        '# O {.online-only}\n\nbody\n')
    (ch / "overview.online.md").write_text("web extra\n")
    art = build_project(project_dir, tmp_path / "a.json", convert_jupytext=False)
    sec = art["chapters"][0]["sections"][0]
    assert "online_only" not in sec and "online_resources" not in sec
