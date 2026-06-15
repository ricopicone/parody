"""Book-metadata plugin: normalization of both shapes, placeholder dropping,
idempotency, the artifact hook, and the migrator's staleness guard."""

import json

import yaml

from parody.build import build_project
from parody.cli import main
from parody.migrate.meta_book import MetaBookMigrator
from parody.plugins import artifact_hooks
from parody.plugins.bookmeta import make_artifact_hook, normalize_book

# meta book-defs.json shape (rtc-like): editions is a dict, hyphenated keys,
# the base edition has real data; a second edition has placeholders.
META_RAW = {
    "book-name": "Real-Time Computing for Mechanical Engineers",
    "book-short-name": "RTC for MEs",
    "url-companion": "https://rtcbook.org",
    "editions": {
        "0": {
            "series": "", "series-name": "", "edition": "1",
            "description": "myRIO target", "v-ts": "T1", "v-ds": "D1",
            "json-file-raw": "common/book-json/book-0-raw.json",
            "year": "2024", "publisher": "MIT Press",
            "url-publisher": "https://mitpress.mit.edu/x",
            "isbn": "9780262548762",
        },
        "ep1": {
            "series": "ep", "series-name": "Economy series", "edition": "1",
            "year": "2023", "publisher": "TBD",
            "isbn": "000-0-00-000000-0",  # placeholder -> dropped
        },
    },
}


def test_normalize_meta_shape_drops_internal_and_placeholders():
    book = normalize_book(META_RAW)
    assert book["name"].startswith("Real-Time Computing")
    assert book["short_name"] == "RTC for MEs"
    assert book["companion_url"] == "https://rtcbook.org"
    base, econ = book["editions"]
    assert base == {
        "id": "0", "edition": "1", "description": "myRIO target",
        "year": "2024", "publisher": "MIT Press", "isbn": "9780262548762",
        "url_publisher": "https://mitpress.mit.edu/x",
        "v_ts": "T1", "v_ds": "D1",
    }
    assert "json-file-raw" not in base and "json_file_raw" not in base
    # placeholders dropped: TBD publisher and all-zero isbn gone
    assert "isbn" not in econ and "publisher" not in econ
    assert econ["series_name"] == "Economy series"


def test_v_key_maps_to_edition():
    book = normalize_book({"book-name": "X", "editions": {"0": {"v": "1"}}})
    assert book["editions"][0]["edition"] == "1"


def test_normalize_is_idempotent():
    once = normalize_book(META_RAW)
    assert normalize_book(once) == once  # parody (list) shape round-trips


def test_hook_emits_book(tmp_path):
    hook = make_artifact_hook(META_RAW, tmp_path)
    out = hook({"chapters": []})
    assert out["book"]["short_name"] == "RTC for MEs"
    assert len(out["book"]["editions"]) == 2


def test_hook_noop_on_empty():
    assert "book" not in make_artifact_hook(True, ".")({"chapters": []})
    assert "book" not in make_artifact_hook({}, ".")({"chapters": []})


def test_plugin_registered_as_artifact_hook():
    hooks = artifact_hooks({"book": META_RAW}, ".")
    assert len(hooks) == 1


def test_build_pipeline_emits_book(tmp_path):
    project_dir = tmp_path / "bbook"
    assert main(["init", str(project_dir), "--title", "B", "--author", "Z"]) == 0
    meta = yaml.safe_load((project_dir / "parody.yaml").read_text())
    meta["schema"] = 2
    meta["book"] = normalize_book(META_RAW)
    (project_dir / "parody.yaml").write_text(yaml.safe_dump(meta))
    artifact = build_project(project_dir, tmp_path / "a.json",
                             convert_jupytext=False)
    assert artifact["book"]["name"].startswith("Real-Time Computing")
    assert artifact["book"]["editions"][0]["isbn"] == "9780262548762"


def _migrator(tmp_path, book_name, title):
    """Minimal migrator instance with a src/common/book-defs.json."""
    src = tmp_path / "src"
    (src / "common").mkdir(parents=True)
    (src / "common" / "book-defs.json").write_text(json.dumps({
        "book-name": book_name, "editions": {"0": {"edition": "1"}},
    }))
    dst = tmp_path / "dst"
    dst.mkdir()
    m = MetaBookMigrator.__new__(MetaBookMigrator)
    m.src, m.dst = src, dst
    return m


def test_migrator_skips_stale_template(tmp_path):
    # book-defs names a different book than the destination title -> skipped
    m = _migrator(tmp_path, "Engineering Computing for Design", "System Dynamics")
    assert m.book_metadata("System Dynamics") is None


def test_migrator_accepts_matching_title(tmp_path):
    m = _migrator(tmp_path, "Real-Time Computing for MEs", "Real-Time Computing")
    book = m.book_metadata("Real-Time Computing")
    assert book["name"] == "Real-Time Computing for MEs"
