import json
from pathlib import Path

import pytest

from parody.cli import main

GOLDEN_DIR = Path(__file__).parent / "golden"


def test_version(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    assert capsys.readouterr().out.startswith("parody ")


def test_check_validates_golden_artifact(capsys):
    artifact = GOLDEN_DIR / "sample-notebook.json"
    assert main(["check", str(artifact)]) == 0
    assert "valid" in capsys.readouterr().out


def test_check_rejects_invalid_artifact(tmp_path, capsys):
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"title": "x", "author": "not-a-list"}))
    assert main(["check", str(bad)]) == 1
