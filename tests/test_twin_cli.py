"""The `parody twin` command (task #825)."""

from pathlib import Path

import pytest

from parody.cli import main
from parody.twin.build import TwinReport


def test_cli_twin_requires_lang(tmp_path):
    with pytest.raises(SystemExit) as exc:
        main(["twin", str(tmp_path)])
    assert exc.value.code == 2


def _fake_build(report):
    calls = {}

    def build(project_dir, language, chapters=None, published_pdf=None, out=None, build_dir=None):
        calls.update(project_dir=project_dir, language=language, chapters=chapters, out=out)
        Path(out).write_bytes(b"%PDF-1.4")
        return Path(out), report
    return build, calls


def test_cli_twin_reports_and_builds_side_by_side(tmp_path, monkeypatch, capsys):
    import parody.twin.build as B
    import parody.twin.sidebyside as S
    report = TwinReport(language="de", base_scale=0.88, squeezed=[(12, 0.81)], approximate=[14],
                        pages=3, abspages=[5, 6, 7], english_pdf=tmp_path / "en.pdf")
    build, calls = _fake_build(report)
    monkeypatch.setattr(B, "build_twin", build)
    seen = {}
    monkeypatch.setattr(S, "side_by_side",
                        lambda en, tw, pages, out: seen.update(en=en, tw=tw, pages=pages, out=out) or out)
    code = main(["twin", str(tmp_path), "--lang", "de", "--chapter", "fundamentals",
                 "-o", str(tmp_path / "t.pdf"), "--side-by-side", str(tmp_path / "s.pdf")])
    assert code == 0
    assert calls["chapters"] == ["fundamentals"] and calls["language"] == "de"
    assert seen["pages"] == [5, 6, 7] and seen["en"] == tmp_path / "en.pdf"
    out = capsys.readouterr().out
    assert "base scale 0.88 (9.7 pt)" in out
    assert "page 12 at 0.81 (8.9 pt)" in out
    assert "approximate" in out and "14" in out


def test_cli_twin_fails_on_tex_errors_or_page_gate(tmp_path, monkeypatch):
    import parody.twin.build as B
    for report in (TwinReport(language="de", tex_errors=["! Undefined control sequence."]),
                   TwinReport(language="de", mismatched_pages=[13])):
        build, _ = _fake_build(report)
        monkeypatch.setattr(B, "build_twin", build)
        assert main(["twin", str(tmp_path), "--lang", "de", "-o", str(tmp_path / "t.pdf")]) == 1


def test_cli_twin_fails_when_a_page_spilled(tmp_path, monkeypatch, capsys):
    import parody.twin.build as B
    import parody.twin.sidebyside as S
    report = TwinReport(language="de", pages=28, shipped_pages=30, abspages=list(range(5, 33)),
                        english_pdf=tmp_path / "en.pdf")
    build, _ = _fake_build(report)
    monkeypatch.setattr(B, "build_twin", build)
    monkeypatch.setattr(S, "side_by_side", lambda *a: pytest.fail("must not pair mismatched pages"))
    assert main(["twin", str(tmp_path), "--lang", "de", "-o", str(tmp_path / "t.pdf"),
                 "--side-by-side", str(tmp_path / "s.pdf")]) == 1
    assert "30 pages for 28 English pages" in capsys.readouterr().out
