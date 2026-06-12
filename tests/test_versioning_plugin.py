"""Versioning plugin: track substitution, variant inheritance, parameter
flattening, and the build-pipeline hookup."""

import textwrap

import pytest
import yaml

from parody.build import build_project
from parody.cli import main
from parody.plugins import content_transforms
from parody.plugins.versioning import (
    _slug_key,
    flatten_versions,
    make_transform,
)

DB = {
    "ts": {
        "T1": {
            "description": "first target system",
            "target-computer": {
                "name": "NI myRIO 1900",
                "System on a chip (SoC)": "Xilinx Z-7010",
            },
            "variants": {
                "T1.1": {
                    "description": "first revision",
                    # target-computer inherited from T1
                },
            },
        },
        "T2": {
            "description": "second-edition target system",
            "target-computer": {"name": "Raspberry Pi 5"},
        },
    },
    "ds": {
        "D1": {"description": "first development system"},
    },
}


def write_project(tmp_path, tracks, db=DB):
    project_dir = tmp_path / "vbook"
    assert main(["init", str(project_dir), "--title", "V", "--author", "A"]) == 0
    (project_dir / "versions.yaml").write_text(yaml.safe_dump(db))
    meta = yaml.safe_load((project_dir / "parody.yaml").read_text())
    meta["versioning"] = {"tracks": tracks}
    (project_dir / "parody.yaml").write_text(yaml.safe_dump(meta))
    return project_dir


def test_slug_key():
    assert _slug_key("System on a chip (SoC)") == "soc"
    assert _slug_key("Microprocessor architecture") == "microprocessor-architecture"


def test_flatten_inherits_variants():
    flat = flatten_versions(DB)
    assert flat["T1.1"]["parent"] == "T1"
    assert flat["T1"]["children"] == ["T1.1"]
    assert flat["T1.1"]["description"] == "first revision"  # override kept
    assert flat["T1.1"]["target-computer"]["name"] == "NI myRIO 1900"  # inherited


def test_two_track_transform(tmp_path):
    project_dir = write_project(tmp_path, {"ts": "T1", "ds": "D1"})
    meta = yaml.safe_load((project_dir / "parody.yaml").read_text())
    transform = content_transforms(meta, project_dir)[0]
    text = textwrap.dedent("""\
        The []{.ts} target and []{.ds} development systems.
        Margin: []{.tsicon} and the computer []{.T1-target-computer-name}
        with []{.T1-target-computer-soc}. Unknown: []{.T1-bogus-key}.
        Not versioning's: []{.someother-span}.""")
    out = transform(text)
    assert "The T1 target and D1 development systems." in out
    assert "[T1]{.version-icon .ts}" in out
    assert "NI myRIO 1900" in out
    assert "Xilinx Z-7010" in out
    assert "[]{.T1-bogus-key}" in out, "unknown param left as-is (warned)"
    assert "[]{.someother-span}" in out, "non-versioning spans untouched"


def test_second_edition_is_config_only(tmp_path):
    project_dir = write_project(tmp_path, {"ts": "T2", "ds": "D1"})
    meta = yaml.safe_load((project_dir / "parody.yaml").read_text())
    transform = content_transforms(meta, project_dir)[0]
    out = transform("[]{.ts} with []{.T2-target-computer-name}")
    assert out == "T2 with Raspberry Pi 5"


def test_single_track(tmp_path):
    db = {"v": {"1.0": {"description": "first"}, "2.0": {"description": "second"}}}
    project_dir = write_project(tmp_path, {"v": "2.0"}, db=db)
    meta = yaml.safe_load((project_dir / "parody.yaml").read_text())
    transform = content_transforms(meta, project_dir)[0]
    assert transform("Version []{.v} ships.") == "Version 2.0 ships."


def test_unknown_active_version_errors(tmp_path):
    project_dir = write_project(tmp_path, {"ts": "T9"})
    with pytest.raises(ValueError, match="T9"):
        make_transform({"tracks": {"ts": "T9"}}, project_dir)


def test_build_pipeline_applies_transform(tmp_path):
    project_dir = write_project(tmp_path, {"ts": "T1", "ds": "D1"})
    (project_dir / "chapters/introduction/overview.md").write_text(
        "---\ntitle: O\nslug: overview\nid: overview\n---\n\n"
        "# Overview {#overview}\n\nBuilt for []{.ts} on []{.ds}.\n")
    artifact = build_project(project_dir, tmp_path / "a.json",
                             convert_jupytext=False)
    html = artifact["chapters"][0]["sections"][0]["html"]
    assert "T1" in html and "D1" in html
    assert "{.ts}" not in html
