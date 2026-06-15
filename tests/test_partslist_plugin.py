"""Parts-list plugin: general-catalog generation, marker parsing, and the
pipeline-aware transform (expand for artifact, drop for print)."""

import textwrap

import yaml

from parody.plugins import content_transforms
from parody.plugins.partslist import (
    generate_general_catalog,
    make_transform,
)

DB = {
    "ts": {
        "T1": {
            "description": "first target system",
            "target-computer": {
                "name": "NI myRIO 1900",
                "description": "A single-board computer.",
                "hash": "tc",
                "quantity": "1",
                "System on a chip (SoC)": "Xilinx Z-7010",
                "suppliers": {"NI": {"url": "https://ni.com"}},
            },
            "ui": {
                "keypad": {"kind": "input", "name": "Grayhill 88BB2",
                           "hash": "kp", "Keys": "16"},
            },
        },
    },
    "ds": {
        "D1": {"description": "first dev system", "ide": "Eclipse"},
    },
}


def _flat():
    from parody.plugins.versioning import flatten_versions
    return flatten_versions(DB)


def test_generate_general_catalog_structure():
    md = generate_general_catalog(_flat(), ts_version="T1", ds_version="D1")
    # general TS heading + subsystem anchors with the canonical hashes
    assert '## General T1 target system {#general-target-system-T1 .ts .T1 h="wp"}' in md
    assert '{#target-computer .ts .T1 h="a6"}' in md
    assert "NI myRIO 1900" in md and "Xilinx Z-7010" in md
    assert '<div class="version-list-item">System on a chip (SoC): Xilinx Z-7010</div>' in md
    # suppliers/quantity are skipped in the general catalog
    assert "ni.com" not in md
    assert "Total quantity" not in md
    # general DS blurb with its IDE
    assert '## General D1 development system {#general-development-system-D1 .ds .D1 h="2b"}' in md
    assert "Eclipse" in md


def test_catalog_respects_active_version():
    md = generate_general_catalog(_flat(), ts_version="T1", ds_version=None)
    assert "General T1 target system" in md
    assert "development system" not in md  # ds not requested


def _project_meta():
    return {"parts_list": {"tracks": {"ts": "T1", "ds": "D1"}}}


def test_transform_expands_for_artifact(tmp_path):
    (tmp_path / "versions.yaml").write_text(yaml.safe_dump(DB))
    transform = make_transform(_project_meta()["parts_list"], tmp_path,
                               target="artifact")
    out = transform("before\n\n[]{.parts-list .ts}\n\nafter")
    assert "General T1 target system" in out
    assert "[]{.parts-list" not in out  # marker consumed
    assert "before" in out and "after" in out


def test_transform_drops_for_print(tmp_path):
    (tmp_path / "versions.yaml").write_text(yaml.safe_dump(DB))
    transform = make_transform(_project_meta()["parts_list"], tmp_path,
                               target="print")
    out = transform("before\n\n[]{.parts-list .ts}\n\nafter")
    assert "General T1 target system" not in out
    assert "[]{.parts-list" not in out  # marker removed, not expanded


def test_marker_selects_track(tmp_path):
    (tmp_path / "versions.yaml").write_text(yaml.safe_dump(DB))
    transform = make_transform(_project_meta()["parts_list"], tmp_path,
                               target="artifact")
    ts_only = transform("[]{.parts-list .ts}")
    assert "target system" in ts_only and "development system" not in ts_only
    ds_only = transform("[]{.parts-list .ds}")
    assert "development system" in ds_only and "target system" not in ds_only


def test_content_transforms_passes_target(tmp_path):
    (tmp_path / "versions.yaml").write_text(yaml.safe_dump(DB))
    text = "[]{.parts-list .ts}"
    art = content_transforms(_project_meta(), tmp_path, target="artifact")
    prn = content_transforms(_project_meta(), tmp_path, target="print")
    assert "General T1 target system" in art[0](text)
    assert prn[0](text).strip() == ""  # print drops it
