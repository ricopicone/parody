"""The twin page environment and the language preambles (task #825)."""

import shutil
import subprocess
from pathlib import Path

import pytest

from parody.twin import languages as L
from parody.writers.latex import BUNDLED_PROFILES, SHARED_PROFILE_DIR, _tool_env, have_tool

needs_tex = pytest.mark.skipif(not have_tool("lualatex"), reason="needs lualatex")


def test_every_language_names_every_box():
    box_macros = {"parodydefinitionname", "parodytheoremname", "parodylemmaname",
                  "parodycorollaryname", "parodypropositionname", "parodyexamplename",
                  "parodyboxname", "parodyproblemname", "parodylabexercisename",
                  "parodylabsolutionname"}
    for code, spec in L.TWIN_LANGUAGES.items():
        assert box_macros <= set(spec["names"]), code
        assert {"untranslated", "stale"} <= set(spec["notes"]), code
        assert {"figure", "table", "equation", "definition", "examplectr", "exercise"} <= set(spec["cref"]), code


def test_preamble_is_complete_for_german():
    pre = L.twin_preamble("de")
    assert "\\usepackage[ngerman,shorthands=off]{babel}" in pre
    assert "\\renewcommand{\\parodytheoremname}{Satz}" in pre
    assert "\\crefname{figure}{Abbildung}{Abbildungen}" in pre
    assert "\\usepackage{parody-twin}" in pre


def test_cjk_font_missing_raises_with_install_hint(monkeypatch):
    monkeypatch.setattr(L, "_installed_families", lambda: {"Helvetica"})
    with pytest.raises(RuntimeError, match="Noto Serif CJK SC"):
        L.cjk_font("zh")


def test_cjk_font_picks_first_installed(monkeypatch):
    monkeypatch.setattr(L, "_installed_families", lambda: {"Songti SC", "Source Han Serif SC"})
    assert L.cjk_font("zh") == "Source Han Serif SC"


def _compile(tmp_path, body, language="de", runs=1):
    for f in (BUNDLED_PROFILES / "memoir").iterdir():
        if f.suffix in (".cls", ".sty"):
            shutil.copy2(f, tmp_path / f.name)
    shutil.copy2(SHARED_PROFILE_DIR / "parody-twin.sty", tmp_path / "parody-twin.sty")
    (tmp_path / "t.tex").write_text(
        "\\documentclass[11pt]{parody-memoir}\n\\def\\clozemode{blank}\n"
        "\\usepackage{parody-theme-default}\n\\usepackage{parody-environments}\n"
        + L.twin_preamble(language) + "\n\\begin{document}\n\\mainmatter\n" + body
        + "\n\\end{document}\n", encoding="utf-8")
    for _ in range(runs):
        subprocess.run(["lualatex", "-interaction=nonstopmode", "t.tex"], cwd=tmp_path,
                       env=_tool_env(), capture_output=True)
    log = (tmp_path / "t.log").read_text(encoding="utf-8", errors="replace")
    assert "\n! " not in log, log[log.index("\n! "):][:300]
    return tmp_path / "t.pdf", log


def _text(pdf):
    import pypdf
    return [" ".join((p.extract_text() or "").split()) for p in pypdf.PdfReader(str(pdf)).pages]


@needs_tex
def test_twinpage_restores_counters_and_page_numbers(tmp_path):
    body = (
        "\\begin{twinpage}{12}{1.0}{\\setcounter{chapter}{1}\\setcounter{equation}{4}}"
        "{\\setcounter{chapter}{1}\\chaptermark{Grundlagen}}{}\n"
        "Erster Text. \\refstepcounter{equation}Gleichung \\theequation.\n\\end{twinpage}\n"
        "\\begin{twinpage}{13}{1.0}{\\setcounter{chapter}{1}\\setcounter{equation}{4}}{}{}\n"
        "Zweiter Text. \\refstepcounter{equation}Gleichung \\theequation.\n\\end{twinpage}\n")
    pdf, log = _compile(tmp_path, body)
    pages = _text(pdf)
    assert len(pages) == 2
    assert "Gleichung 1.5" in pages[0] and "Gleichung 1.5" in pages[1]
    assert pages[0].startswith("12") or pages[0].endswith("12") or " 12 " in f" {pages[0]} "
    assert "TWINFIT page=12 scale=1" in log and "TWINFIT page=13 scale=1" in log


@needs_tex
def test_twinpage_squeezes_to_fit_and_ships_one_page(tmp_path):
    lots = " ".join(["Ein langer deutscher Satz, der die Seite füllt."] * 400)
    pdf, log = _compile(tmp_path, f"\\begin{{twinpage}}{{7}}{{1.0}}{{}}{{}}{{}}\n{lots}\n\\end{{twinpage}}\n")
    assert len(_text(pdf)) == 1
    scale = float(log.split("TWINFIT page=7 scale=")[1].split()[0])
    assert scale < 0.6


@needs_tex
def test_chapter_start_page(tmp_path):
    body = ("\\begin{twinpage}{1}{1.0}{\\setcounter{chapter}{1}}{}{}[Grundlagen]\n"
            "Text nach der Kapitelüberschrift.\n\\end{twinpage}\n")
    pdf, log = _compile(tmp_path, body)
    pages = _text(pdf)
    assert len(pages) == 1 and "Grundlagen" in pages[0] and "Kapitel" in pages[0]


@needs_tex
def test_footnotes_are_numbered_like_the_english(tmp_path):
    body = ("\\begin{twinpage}{3}{1.0}{\\setcounter{chapter}{1}\\setcounter{footnote}{2}}{}{}\n"
            "Text.\\footnote{Eine Fußnote.}\n\\end{twinpage}\n")
    pdf, _ = _compile(tmp_path, body)
    assert "3EineFußnote." in _text(pdf)[0].replace(" ", "")


@needs_tex
def test_chinese_twinpage_compiles(tmp_path):
    try:
        L.cjk_font("zh")
    except RuntimeError:
        pytest.skip("no CJK font")
    body = ("\\begin{twinpage}{5}{1.0}{\\setcounter{chapter}{1}}{}{}\n"
            "\\begin{definition}{}{}分压器是一种电路。\\end{definition}\n\\end{twinpage}\n")
    pdf, log = _compile(tmp_path, body, language="zh")
    assert "定义 1.1" in _text(pdf)[0].replace("\u00a0", " ") or "定义1.1" in _text(pdf)[0]


@needs_tex
def test_a_tight_fit_is_still_one_page(tmp_path):
    # A box whose first line is tiny gets \topskip glue above it; measured
    # without it, a tight page spilled onto a second sheet (electronics p. 20).
    body = ("\\begin{twinpage}{9}{1.0}{}{}{}\n"
            "\\noindent\\rule{1pt}{1pt}\\par\\nointerlineskip"
            "\\noindent\\rule{1pt}{\\dimexpr\\textheight-3pt\\relax}\n\\end{twinpage}\n")
    pdf, log = _compile(tmp_path, body)
    assert len(_text(pdf)) == 1


@needs_tex
def test_paragraphs_keep_the_books_indent(tmp_path):
    # minipage zeroes \parindent and \parskip; the twin's paragraphs must look
    # like the English ones.
    body = ("\\typeout{DOC-PI=\\the\\parindent}\n\\begin{twinpage}{9}{1.0}{}{}{}\n"
            "One.\\par Two.\\typeout{TWIN-PI=\\the\\parindent}\n\\end{twinpage}\n")
    pdf, log = _compile(tmp_path, body)
    doc = log.split("DOC-PI=")[1].split()[0]
    assert doc != "0.0pt"
    assert f"TWIN-PI={doc}" in log
