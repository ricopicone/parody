"""Parts-list plugin: general-catalog generation, marker parsing, and the
pipeline-aware transform (expand for artifact, drop for print)."""

import yaml

from parody.plugins import content_transforms
from parody.plugins.partslist import (
    generate_general_catalog,
    generate_general_catalog_tex,
    generate_parts_data,
    make_artifact_hook,
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


# --- LaTeX (print) general catalog -----------------------------------------


def test_generate_general_catalog_tex_structure():
    tex = generate_general_catalog_tex(_flat(), "T1")
    # standard sectioning with hashref labels for cross-refs (not meta's 3-arg)
    assert r"\section{General T1 target system}" in tex
    assert r"\label{general-target-system-T1}" in tex and r"\label{wp}" in tex
    assert r"\label{a6}" in tex  # target-computer subsystem hashref
    # component specs become \item rows; suppliers/quantity are skipped
    assert r"\item System on a chip (SoC): Xilinx Z-7010" in tex
    assert "ni.com" not in tex and "Total quantity" not in tex
    # every \begin{enumerate} is matched (an imbalance would break the build)
    assert tex.count(r"\begin{enumerate}") == tex.count(r"\end{enumerate}")


def test_generate_general_catalog_tex_ds_blurb():
    tex = generate_general_catalog_tex(_flat(), "D1")
    assert r"\section{General D1 development system}" in tex
    assert "Eclipse" in tex
    assert r"\begin{enumerate}" not in tex  # DS general is a blurb, no enumeration


def test_transform_expands_input_for_print(tmp_path):
    (tmp_path / "versions.yaml").write_text(yaml.safe_dump(DB))
    md = "intro\n\n```{=latex}\n\\input{sec-versions-list-ed1-T1-general}\n```\n"
    prn = make_transform(_project_meta()["parts_list"], tmp_path, target="print")
    out = prn(md)
    assert "\\input{" not in out  # the include is replaced...
    assert r"\section{General T1 target system}" in out  # ...with the catalog
    # the same include is left untouched for the web pipeline
    art = make_transform(_project_meta()["parts_list"], tmp_path, target="artifact")
    assert "\\input{sec-versions-list-ed1-T1-general}" in art(md)


# --- structured systems catalog (P3) ---------------------------------------

PARTS_DB = {
    "ts": {
        "T1": {
            "description": "first target system",
            "target-computer": {
                "name": "NI myRIO 1900", "kind": "single-board computer",
                "description": "An SBC.", "hash": "tc", "quantity": "1",
                "System on a chip (SoC)": "Xilinx Z-7010",
                "suppliers": {"NI": {"url": "https://ni.com"}},
            },
            "ui": {
                "keypad": {
                    "kind": "input", "name": "Keypad", "hash": "kp", "Keys": "16",
                    "specific": {"0": {
                        "name": "Grayhill 88BB2", "hash": "g8",
                        "description": "A 16-key keypad.",
                        "suppliers": {"Digi-Key": {"url": "https://digikey.com/x"},
                                      "Mouser": {"url": "https://mouser.com/y"}},
                    }},
                },
            },
            "prototyping": {
                "nand": {
                    "kind": "NAND IC", "name": "A NAND IC", "hash": "nd",
                    "unspecific": {"0": {
                        "name": "TI SN7438N", "hash": "sn",
                        "suppliers": {"Mouser": {"url": "https://mouser.com/z"}},
                    }},
                },
            },
        },
        "T2": {"description": "second target",
               "target-computer": {"name": "Raspberry Pi 5", "hash": "pi"}},
    },
    "ds": {"D1": {"description": "first dev"}, "D2": {"description": "second dev"}},
}


def _parts_flat():
    from parody.plugins.versioning import flatten_versions
    return flatten_versions(PARTS_DB)


def test_generate_parts_data_shape():
    systems = generate_parts_data(_parts_flat(), ts_version="T1", ds_version="D1")
    assert [s["version"] for s in systems] == ["T1", "D1"]
    ts = systems[0]
    assert ts["track"] == "ts" and ts["title"] == "T1 target system"
    comps = {c["subsystem"]: c for c in ts["components"]}
    # subsystem-as-component (target-computer) carries name + specs + suppliers
    tc = comps["target-computer"]
    assert tc["name"] == "NI myRIO 1900"
    assert ["System on a chip (SoC)", "Xilinx Z-7010"] in tc["specs"]
    assert {"name": "NI", "url": "https://ni.com"} in tc["suppliers"]
    # grouped component (ui-keypad) with a specific choice + its suppliers
    kp = comps["ui-keypad"]
    assert kp["name"] == "Keypad" and kp["subsystem_title"] == "user interface subsystem"
    choice = kp["choices"][0]
    assert choice["kind"] == "specific" and choice["name"] == "Grayhill 88BB2"
    assert len(choice["suppliers"]) == 2
    # unspecific choices are captured too
    nand = comps["prototyping-nand"]
    assert nand["choices"][0]["kind"] == "unspecific"


def test_artifact_hook_attaches_parts(tmp_path):
    (tmp_path / "versions.yaml").write_text(yaml.safe_dump(PARTS_DB))
    hook = make_artifact_hook({"tracks": {"ts": "T1", "ds": "D1"}}, tmp_path)
    artifact = hook({"chapters": []})
    assert [s["version"] for s in artifact["parts"]] == ["T1", "D1"]


def test_parts_are_per_edition(tmp_path):
    """Each edition's artifact carries its own active version's parts."""
    import json

    from parody.build import build_editions
    from parody.cli import main
    project_dir = tmp_path / "pbook"
    assert main(["init", str(project_dir), "--title", "P", "--author", "A"]) == 0
    (project_dir / "versions.yaml").write_text(yaml.safe_dump(PARTS_DB))
    meta = yaml.safe_load((project_dir / "parody.yaml").read_text())
    meta["parts_list"] = {"source": "versions.yaml", "tracks": {"ts": "T1"}}
    meta["editions"] = [
        {"id": "ed1", "tracks": {"ts": "T1", "ds": "D1"}},
        {"id": "ed2", "tracks": {"ts": "T2", "ds": "D2"}},
    ]
    (project_dir / "parody.yaml").write_text(yaml.safe_dump(meta))
    out = tmp_path / "art"
    build_editions(project_dir, out, convert_jupytext=False)
    ed1 = json.loads((out / "pbook.ed1.json").read_text())
    ed2 = json.loads((out / "pbook.ed2.json").read_text())
    assert [s["version"] for s in ed1["parts"]] == ["T1", "D1"]
    assert [s["version"] for s in ed2["parts"]] == ["T2", "D2"]
