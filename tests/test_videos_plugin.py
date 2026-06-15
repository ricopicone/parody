"""Videos plugin: normalization of both shapes, dangling-link filtering
against the build (in-book + apocrypha), and the artifact-hook hookup."""

import yaml

from parody.build import build_project
from parody.cli import main
from parody.plugins import artifact_hooks
from parody.plugins.videos import (
    make_artifact_hook,
    normalize_videos,
    video_hashes,
)

# meta videos.json shape: edition -> {playlist, indices: {hash: idx|[idx]}}
META_RAW = {
    "0": {
        "playlist": "PLxyz",
        "indices": {"61": 1, "ha": [3, 4], "uu": 2, "zz": 9},
    },
}


def test_normalize_meta_shape_preserves_order_and_lists():
    eds = normalize_videos(META_RAW)
    assert len(eds) == 1
    ed = eds[0]
    assert ed["edition"] == "0" and ed["playlist"] == "PLxyz"
    # source (playlist) order preserved, single ints widened to lists
    assert [s["hash"] for s in ed["sections"]] == ["61", "ha", "uu", "zz"]
    assert ed["sections"][1]["indices"] == [3, 4]
    assert ed["sections"][0]["indices"] == [1]


def test_normalize_is_idempotent():
    once = normalize_videos(META_RAW)
    assert normalize_videos(once) == once  # parody (list) shape round-trips


def test_video_hashes():
    assert video_hashes(normalize_videos(META_RAW)) == {"61", "ha", "uu", "zz"}


def test_hook_drops_dangling_links(tmp_path):
    (tmp_path / "videos.yaml").write_text(
        yaml.safe_dump(normalize_videos(META_RAW)))
    hook = make_artifact_hook(True, tmp_path)
    # '61' is an in-book section hash; 'uu' is an in-book anchor; 'ha' is an
    # apocrypha (online-only) hash; 'zz' is in neither -> dropped.
    artifact = {
        "chapters": [{"slug": "c", "sections": [
            {"slug": "s", "hash": "61", "anchors": [{"id": "x", "hash": "uu"}]}]}],
        "apocrypha": [{"hash": "ha", "id": "h", "title": "H", "type": "section"}],
    }
    out = hook(artifact)
    hashes = {s["hash"] for ed in out["videos"] for s in ed["sections"]}
    assert hashes == {"61", "uu", "ha"}
    assert "zz" not in hashes


def test_hook_noop_when_all_dangling(tmp_path):
    (tmp_path / "videos.yaml").write_text(
        yaml.safe_dump(normalize_videos(META_RAW)))
    hook = make_artifact_hook(True, tmp_path)
    # nothing in the build matches -> no videos key (stale-copy case)
    out = hook({"chapters": [{"slug": "c", "sections": [
        {"slug": "s", "hash": "qq", "anchors": []}]}]})
    assert "videos" not in out


def test_hook_noop_without_source(tmp_path):
    assert "videos" not in make_artifact_hook(True, tmp_path)({"chapters": []})


def test_plugin_registered_as_artifact_hook(tmp_path):
    (tmp_path / "videos.yaml").write_text("[]")
    assert len(artifact_hooks({"videos": True}, tmp_path)) == 1


def test_build_pipeline_emits_videos(tmp_path):
    project_dir = tmp_path / "vidbook"
    assert main(["init", str(project_dir), "--title", "V", "--author", "Z"]) == 0
    meta = yaml.safe_load((project_dir / "parody.yaml").read_text())
    meta["schema"] = 2
    meta["videos"] = True
    (project_dir / "parody.yaml").write_text(yaml.safe_dump(meta))
    (project_dir / "videos.yaml").write_text(
        yaml.safe_dump(normalize_videos(META_RAW)))
    (project_dir / "chapters/introduction/overview.md").write_text(
        '---\ntitle: O\nslug: overview\nid: overview\nhash: "61"\n---\n\n'
        '# Overview {#overview h="61"}\n\nBody.\n')
    artifact = build_project(project_dir, tmp_path / "a.json",
                             convert_jupytext=False)
    hashes = {s["hash"] for ed in artifact["videos"] for s in ed["sections"]}
    assert hashes == {"61"}  # only the in-book section's video survives
