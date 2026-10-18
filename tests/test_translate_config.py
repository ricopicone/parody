"""The `translations:` key in parody.yaml (task #825)."""

import pytest

from parody.config import ProjectLayoutError, load_project
from parody.translate.languages import LANGUAGES, normalize_translations


def test_absent_key_means_no_translations():
    assert normalize_translations(None) is None


def test_defaults():
    cfg = normalize_translations({"languages": ["zh", "de"]})
    assert cfg.languages == ("zh", "de")
    assert cfg.engine == "claude-code"
    assert cfg.model == "claude-opus-5-5"


def test_unknown_language_is_rejected():
    with pytest.raises(ProjectLayoutError, match="unknown translation language 'xx'"):
        normalize_translations({"languages": ["xx"]})


def test_unknown_engine_is_rejected():
    with pytest.raises(ProjectLayoutError, match="engine"):
        normalize_translations({"languages": ["zh"], "engine": "deepl"})


def test_empty_languages_is_rejected():
    with pytest.raises(ProjectLayoutError, match="languages"):
        normalize_translations({"languages": []})


def test_prompt_names():
    assert LANGUAGES["zh"] == "Simplified Chinese (Mandarin, as written in mainland China)"
    assert LANGUAGES["es"] == "Spanish (neutral international Spanish)"
    assert set(LANGUAGES) == {"zh", "ko", "de", "fr", "es"}


def test_load_project_reads_the_key(tmp_path):
    (tmp_path / "parody.yaml").write_text(
        "title: T\nslug: t\nchapters: []\ntranslations:\n  languages: [ko]\n")
    assert load_project(tmp_path).translations.languages == ("ko",)


def test_load_project_without_the_key(tmp_path):
    (tmp_path / "parody.yaml").write_text("title: T\nslug: t\nchapters: []\n")
    assert load_project(tmp_path).translations is None
