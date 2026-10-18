"""Translation files and glossaries in the book repo (task #825)."""

import pytest

from parody.translate.store import (
    TranslationFile,
    TranslationFileError,
    glossary_path,
    load_glossary,
    save_glossary,
    translation_path,
)


def _sample():
    return TranslationFile(
        language="zh",
        source="chapters/fundamentals/voltage-dividers.md",
        title="分压器",
        title_hash="1a2b3c4d5e6f",
        chunks=[
            ("3f2a9c01aa77", '# 分压器 {#lec:voltage_dividers h="o5"}'),
            ("0b1c2d3e4f50", "我们有 $$\\begin{aligned}\na &= b\n\nc &= d\\end{aligned}$$ 两个方程。"),
        ],
        engine="claude-code",
        model="claude-opus-5-5",
        updated="2026-10-17",
    )


def test_paths(tmp_path):
    assert translation_path(tmp_path, "zh", "fundamentals", "voltage-dividers") == (
        tmp_path / "translations" / "zh" / "fundamentals" / "voltage-dividers.md")
    assert glossary_path(tmp_path, "de") == tmp_path / "translations" / "de" / "glossary.yaml"


def test_round_trip(tmp_path):
    path = tmp_path / "t" / "x.md"
    _sample().write(path)
    assert TranslationFile.read(path) == _sample()
    text = path.read_text(encoding="utf-8")
    assert "title: 分压器" in text
    assert "<!-- parody:chunk h=3f2a9c01aa77 -->" in text


def test_other_comments_survive(tmp_path):
    f = _sample()
    f.chunks[1] = ("0b1c2d3e4f50", "Text <!-- an author's note --> more.")
    path = tmp_path / "x.md"
    f.write(path)
    assert TranslationFile.read(path).chunks[1][1] == "Text <!-- an author's note --> more."


def test_no_title(tmp_path):
    f = _sample()
    f.title = f.title_hash = None
    f.write(tmp_path / "x.md")
    got = TranslationFile.read(tmp_path / "x.md")
    assert got.title is None and got.title_hash is None


def test_text_before_first_marker_raises(tmp_path):
    path = tmp_path / "x.md"
    path.write_text("---\nlanguage: zh\nsource: s.md\n---\n\nstray text\n\n"
                    "<!-- parody:chunk h=3f2a9c01aa77 -->\n\nok\n", encoding="utf-8")
    with pytest.raises(TranslationFileError):
        TranslationFile.read(path)


def test_glossary_round_trip_is_sorted_unicode(tmp_path):
    path = tmp_path / "g.yaml"
    save_glossary(path, {"voltage divider": "分压器", "current": "电流"})
    text = path.read_text(encoding="utf-8")
    assert "分压器" in text
    assert text.index("current") < text.index("voltage divider")
    assert load_glossary(path) == {"voltage divider": "分压器", "current": "电流"}


def test_missing_glossary_is_empty(tmp_path):
    assert load_glossary(tmp_path / "nope.yaml") == {}
