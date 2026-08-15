"""Print-target handling of notebook include directives (task #244).

include-py inlines the committed executed markdown (code -> minted, figures
resolved against the source tree, svg converted for LaTeX); include-code
inlines a file verbatim; link/download-code becomes a pointer note.
"""

import shutil
import textwrap

import pytest

from parody.writers.latex import section_to_latex

SVG = ('<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10">'
       '<rect width="10" height="10" fill="red"/></svg>')


@pytest.fixture
def notebook_chapter(tmp_path, monkeypatch):
    project = tmp_path / "proj"
    chapter = project / "chapter_demo"
    files = chapter / "analysis_files"
    files.mkdir(parents=True)
    (chapter / "analysis.py").write_text("# %%\nprint('hi')\n")
    (chapter / "analysis.md").write_text(textwrap.dedent("""\
        Some prose.

        ```python
        print('hi')
        ```

        ![A converted figure](plot.svg){#converted-figure}
        """))
    (files / "plot.svg").write_text(SVG)
    # the figure also exists directly in the chapter for bare-name fallback
    (chapter / "plot.svg").write_text(SVG)
    (chapter / "helper.py").write_text("x = 1\n")

    section = chapter / "sec.md"
    build = tmp_path / "build"
    (build / "svg-cache").mkdir(parents=True)
    monkeypatch.setenv("PARODY_PROJECT_DIR", str(project))
    monkeypatch.setenv("PARODY_NOTEBOOK_SLUG", "proj")
    monkeypatch.setenv("PARODY_CHAPTER_DIR", str(chapter))
    monkeypatch.setenv("PARODY_SVG_CACHE", str(build / "svg-cache"))
    return section, chapter


def render(section_path, body, tmp_path):
    section_path.write_text(body)
    out = tmp_path / "out.tex"
    section_to_latex(section_path, out, resource_dir=section_path.parent,
                     crossref=False)
    return out.read_text()


def test_include_py_inlines_executed_markdown(notebook_chapter, tmp_path):
    section, _ = notebook_chapter
    tex = render(section, '```{.include-py path="analysis.py"}\n```\n', tmp_path)
    assert "Some prose." in tex
    assert "\\begin{minted}" in tex and "print('hi')" in tex


@pytest.mark.skipif(not (shutil.which("rsvg-convert") or shutil.which("inkscape")),
                    reason="no svg converter available")
def test_include_py_resolves_and_converts_svg(notebook_chapter, tmp_path):
    section, _ = notebook_chapter
    tex = render(section, '```{.include-py path="analysis.py"}\n```\n', tmp_path)
    assert "\\includegraphics" in tex
    assert ".pdf}" in tex and ".svg}" not in tex
    # unprefixed figure ids get the fig: prefix crossrefs expect
    assert "{fig:converted-figure}" in tex
    # natural width capped at the line width
    assert "width=\\maxwidth" in tex


def test_include_code_inlines_verbatim(notebook_chapter, tmp_path):
    section, _ = notebook_chapter
    tex = render(section, '```{.include-code path="helper.py"}\n```\n', tmp_path)
    assert "x = 1" in tex and "{python}" in tex


def test_download_code_becomes_pointer_note(notebook_chapter, tmp_path):
    section, _ = notebook_chapter
    tex = render(section,
                 '```{.download-code path="helper.py" label="Get helper"}\n```\n',
                 tmp_path)
    assert "Get helper" in tex and "\\path{helper.py}" in tex
    assert "minted" not in tex


def test_a_longtable_inside_an_exercise_becomes_a_tabular():
    """xsim re-tokenizes an exercise body to collect it, and longtable's
    counter machinery does not survive: "No counter 'none' defined", and NO
    PDF is produced. Same family as the minted problem next door — except
    this one takes the whole build down rather than one block.
    """
    from parody.writers.latex import _detoxify_exercise_longtables

    tex = (
        "\\begin{exercise}[ID=x,hash=x]\n"
        "\\begin{longtable}[]{@{}ll@{}}\n"
        "a & b \\\\\n"
        "\\endhead\n"
        "1 & 2 \\\\\n"
        "\\end{longtable}\n"
        "\\end{exercise}\n")
    out = _detoxify_exercise_longtables(tex)
    assert "longtable" not in out
    assert "\\begin{tabular}" in out and "\\end{tabular}" in out
    assert "\\endhead" not in out
    assert "1 & 2" in out  # the content survives


def test_a_longtable_outside_an_exercise_is_untouched():
    from parody.writers.latex import _detoxify_exercise_longtables

    tex = "\\begin{longtable}[]{@{}ll@{}}\na & b \\\\\n\\end{longtable}\n"
    assert _detoxify_exercise_longtables(tex) == tex
