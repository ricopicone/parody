"""Filter behavior for bibliography cite spans and download-link directives.

These cover the notebook-corpus syntax normalization: sources use
[key]{.cite} spans (never raw Django tags), and .link-code/.download-code
accepts absolute media-hierarchy paths for shared assets.
"""

from pathlib import Path

import pypandoc
import pytest

FILTERS = Path(__file__).parent.parent / "parody" / "filters"


# Same format strings as the real pipelines (artifact.py / writers/latex.py).
WEB_FROM = "markdown-smart-markdown_in_html_blocks+raw_tex+tex_math_dollars+grid_tables"
PRINT_FROM = "markdown-markdown_in_html_blocks+raw_tex+tex_math_dollars"


def web(md, cwd=None):
    return pypandoc.convert_text(
        md, "html", format=WEB_FROM,
        extra_args=[f"--lua-filter={FILTERS / 'filter.lua'}"],
        cworkdir=str(cwd) if cwd else None,
    )


def latex(md):
    return pypandoc.convert_text(
        md, "latex", format=PRINT_FROM,
        extra_args=[f"--lua-filter={FILTERS / 'print.lua'}", "--biblatex",
                    "--wrap=none"],
    )


# --- web: [key]{.cite} -> {% cite %} ---------------------------------------

def test_cite_span_simple():
    assert '{% cite "bergman2019" %}' in web("[bergman2019]{.cite}")


def test_cite_span_with_note():
    out = web("[bergman2019|equation 12.37, p. 729]{.cite}")
    assert '{% cite "bergman2019" note="equation 12.37, p. 729" %}' in out


def test_cite_span_no_parentheses():
    out = web("[russell2020|ch. 2]{.cite .plain}")
    assert '{% cite "russell2020" "no-parentheses" note="ch. 2" %}' in out


def test_cite_span_multiple_keys():
    out = web("[a2020,b2021]{.cite}")
    assert '{% cite_many "a2020" "b2021" %}' in out


# --- print: [key]{.cite} -> biblatex ----------------------------------------

def test_cite_span_print_autocite():
    assert "\\autocite[{}]{bergman2019}" in latex("[bergman2019]{.cite}")


def test_cite_span_print_note_and_plain():
    # The print pipeline keeps pandoc smart typography, so the abbreviation
    # space arrives as a non-breaking space.
    out = latex("[russell2020|ch. 2]{.cite .plain}")
    assert "\\textcite[{ch. 2}]{russell2020}" in out


def test_cite_span_print_multiple_keys():
    assert "\\autocite[{}]{a2020,b2021}" in latex("[a2020, b2021]{.cite}")


# --- download-code path handling --------------------------------------------

DIRECTIVE = '```{{.download-code path="{path}" label="Get it"}}\n```\n'


def test_download_code_absolute_notebooks_path_passes_through():
    out = web(DIRECTIVE.format(path="notebooks/MLM/notes.pdf"))
    assert 'href="notebooks/MLM/notes.pdf"' in out
    assert 'label="Get it"' in out


def test_download_code_absolute_media_path_strips_media_prefix():
    out = web(DIRECTIVE.format(path="media/MLM/notes.pdf"))
    assert 'href="MLM/notes.pdf"' in out


def test_download_code_relative_path_gets_slug_prefix(tmp_path, monkeypatch):
    # Standalone content repo: slugs come from the env vars.
    monkeypatch.setenv("PARODY_NOTEBOOK_SLUG", "mech")
    monkeypatch.setenv("PARODY_CHAPTER_SLUG", "chapter_rc")
    out = web(DIRECTIVE.format(path="lab_03.zip"))
    assert 'href="notebooks/mech/chapter_rc/lab_03.zip"' in out
