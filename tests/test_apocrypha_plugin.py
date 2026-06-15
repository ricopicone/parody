"""Apocrypha plugin: normalization of both source shapes, online-only
filtering against the build, and the artifact-hook pipeline hookup."""

import yaml

from parody.build import build_project
from parody.cli import main
from parody.plugins import artifact_hooks
from parody.plugins.apocrypha import make_artifact_hook, normalize_entries

# meta apocrypha.json shape: hash -> subhash -> fields
META_RAW = {
    "zp": {"unversioned": {"type": "subsection", "hash": "zp",
                           "v-specific": "no", "id": "only-the-vertices-matter",
                           "title": "Only the vertices matter"}},
    "jk-online-resources": {"unversioned": {"id": "completing-online-resources",
                                            "hash": "jk-online-resources",
                                            "title": "Online resources for A.1.1",
                                            "v-specific": "no"}},
    "uv": {"T1D1": {"type": "section", "hash": "uv", "v-specific": "yes",
                    "id": "ui-functions", "title": "UI functions",
                    "v-ts": "T1", "v-ds": "D1"}},
}


def test_normalize_meta_shape():
    entries = normalize_entries(META_RAW)
    by_hash = {e["hash"]: e for e in entries}
    assert by_hash["zp"] == {
        "hash": "zp", "id": "only-the-vertices-matter",
        "title": "Only the vertices matter", "type": "subsection",
        "v_specific": False,
    }
    # composite online-resources hash preserved verbatim
    assert by_hash["jk-online-resources"]["id"] == "completing-online-resources"
    # versioned variant carries subhash + track codes, v-specific coerced True
    uv = by_hash["uv"]
    assert uv["subhash"] == "T1D1"
    assert uv["v_specific"] is True
    assert uv["v_ts"] == "T1" and uv["v_ds"] == "D1"


def test_normalize_is_sorted_and_idempotent():
    once = normalize_entries(META_RAW)
    # round-trip the parody-list shape back through the normalizer
    twice = normalize_entries(once)
    assert once == twice
    assert [e["hash"] for e in once] == sorted(e["hash"] for e in once)


def test_hook_filters_in_book_keeps_online_and_variants(tmp_path):
    source = tmp_path / "apocrypha.yaml"
    source.write_text(yaml.safe_dump(normalize_entries(META_RAW)))
    hook = make_artifact_hook(True, tmp_path)
    # 'zp' is in this build (an in-book anchor); 'uv' base hash is in-book too
    # but the apocrypha entry is a versioned variant (has subhash) -> kept.
    artifact = {"chapters": [{"slug": "c", "sections": [
        {"slug": "s", "hash": "zp", "anchors": [{"id": "x", "hash": "uv"}]}]}]}
    out = hook(artifact)
    hashes = {e["hash"] for e in out["apocrypha"]}
    assert "zp" not in hashes              # in-book, unversioned -> dropped
    assert "jk-online-resources" in hashes  # online-only -> kept
    assert "uv" in hashes                   # versioned variant -> kept


def test_hook_noop_without_source(tmp_path):
    hook = make_artifact_hook(True, tmp_path)  # no apocrypha.yaml on disk
    artifact = {"chapters": []}
    assert "apocrypha" not in hook(artifact)


def test_custom_source_name(tmp_path):
    (tmp_path / "extra.yaml").write_text(
        yaml.safe_dump(normalize_entries(META_RAW)))
    hook = make_artifact_hook({"source": "extra.yaml"}, tmp_path)
    out = hook({"chapters": []})
    assert any(e["hash"] == "zp" for e in out["apocrypha"])


def test_build_pipeline_emits_apocrypha(tmp_path):
    project_dir = tmp_path / "abook"
    assert main(["init", str(project_dir), "--title", "A", "--author", "Z"]) == 0
    meta = yaml.safe_load((project_dir / "parody.yaml").read_text())
    meta["schema"] = 2
    meta["apocrypha"] = True
    (project_dir / "parody.yaml").write_text(yaml.safe_dump(meta))
    (project_dir / "apocrypha.yaml").write_text(
        yaml.safe_dump(normalize_entries(META_RAW)))
    # one in-book section carrying hash 'zp' -> that apocrypha entry drops out
    (project_dir / "chapters/introduction/overview.md").write_text(
        '---\ntitle: O\nslug: overview\nid: overview\nhash: zp\n---\n\n'
        '# Overview {#overview h="zp"}\n\nBody.\n')
    artifact = build_project(project_dir, tmp_path / "a.json",
                             convert_jupytext=False)
    hashes = {e["hash"] for e in artifact["apocrypha"]}
    assert "jk-online-resources" in hashes
    assert "zp" not in hashes  # in-book section -> excluded from apocrypha


def test_plugin_registered_as_artifact_hook(tmp_path):
    (tmp_path / "apocrypha.yaml").write_text("[]")
    hooks = artifact_hooks({"apocrypha": True}, tmp_path)
    assert len(hooks) == 1
