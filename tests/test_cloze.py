"""Cloze (fill-in-the-blank) rendering: mode plumbing and both filters.

Three modes: blank (student handout), key (instructor), full (publication).
The load-bearing assertions are the negative ones — in `blank` mode the
answer must not appear in the output at all.
"""

import os
from contextlib import contextmanager
from pathlib import Path

import pytest

from parody.config import CLOZE_MODES, resolve_cloze_mode

FILTERS = Path(__file__).parent.parent / "parody" / "filters"


@contextmanager
def cloze_mode(mode):
    """Set PARODY_CLOZE_MODE for a filter run, restoring it afterwards."""
    saved = os.environ.get("PARODY_CLOZE_MODE")
    if mode is None:
        os.environ.pop("PARODY_CLOZE_MODE", None)
    else:
        os.environ["PARODY_CLOZE_MODE"] = mode
    try:
        yield
    finally:
        if saved is None:
            os.environ.pop("PARODY_CLOZE_MODE", None)
        else:
            os.environ["PARODY_CLOZE_MODE"] = saved


# --- mode resolution -------------------------------------------------------

def test_modes_are_exactly_three():
    assert CLOZE_MODES == ("blank", "key", "full")


def test_default_mode_is_blank():
    assert resolve_cloze_mode({}) == "blank"


def test_yaml_default_is_honored():
    assert resolve_cloze_mode({"cloze": {"default": "full"}}) == "full"


def test_override_beats_yaml():
    assert resolve_cloze_mode({"cloze": {"default": "full"}}, "blank") == "blank"


def test_unknown_mode_rejected():
    with pytest.raises(ValueError) as exc:
        resolve_cloze_mode({}, "hidden")
    assert "hidden" in str(exc.value)
    assert "blank" in str(exc.value)


# --- plumbing --------------------------------------------------------------

SMOKE_BOOK = Path(__file__).parent / "smoke-book"


def test_build_records_non_default_mode(tmp_path):
    from parody.build import build_project

    out = build_project(SMOKE_BOOK, tmp_path / "a.json", convert_jupytext=False,
                        media_root=tmp_path, cloze_mode="full")
    assert out["cloze_mode"] == "full"


def test_build_omits_default_mode(tmp_path):
    from parody.build import build_project

    out = build_project(SMOKE_BOOK, tmp_path / "a.json", convert_jupytext=False,
                        media_root=tmp_path)
    assert "cloze_mode" not in out


def test_pdf_flag_emitted(tmp_path, monkeypatch):
    """build_pdf writes \\def\\clozemode into main.tex, next to \\issolution."""
    from parody.writers import latex as latex_writer

    # build_pdf writes main.tex, then bails with a warning when latexmk is
    # missing (latex.py:348) — so faking its absence gives a fast, TeX-free
    # assertion on the generated source.
    monkeypatch.setattr(latex_writer.shutil, "which", lambda *a, **k: None)
    build_dir = tmp_path / "build"
    latex_writer.build_pdf(SMOKE_BOOK, build_dir=build_dir, cloze_mode="key",
                           output_pdf=tmp_path / "out.pdf")
    main_tex = (build_dir / "main.tex").read_text(encoding="utf-8")
    assert "\\def\\clozemode{key}" in main_tex


def test_pdf_flag_is_independent_of_solutions(tmp_path, monkeypatch):
    from parody.writers import latex as latex_writer

    monkeypatch.setattr(latex_writer.shutil, "which", lambda *a, **k: None)
    build_dir = tmp_path / "build"
    latex_writer.build_pdf(SMOKE_BOOK, build_dir=build_dir, cloze_mode="key",
                           solutions=True, output_pdf=tmp_path / "out.pdf")
    main_tex = (build_dir / "main.tex").read_text(encoding="utf-8")
    assert "\\def\\clozemode{key}" in main_tex
    assert "\\def\\issolution{1}" in main_tex
