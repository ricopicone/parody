"""Print-target handling of notebook include directives (task #244).

include-py inlines the committed executed markdown (code -> minted, figures
resolved against the source tree, svg converted for LaTeX); include-code
inlines a file verbatim; link/download-code becomes a pointer note.
"""

import shutil
import textwrap
from pathlib import Path

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


def test_verbatim_side_files_are_input_relative_to_the_build_root(tmp_path):
    # The twin compiles its pages from <twin>/pages/, not sections/<ch>/: the
    # \input of an exercise's externalized code must name where the file is.
    from parody.writers.latex import _externalize_exercise_verbatim
    tex = ("\\begin{exercise}\nRun\n\\begin{minted}{python}\nprint(1)\n\\end{minted}\n"
           "\\end{exercise}\n")
    out = tmp_path / "pages" / "p45-0.tex"
    out.parent.mkdir()
    got = _externalize_exercise_verbatim(tex, out, input_root=tmp_path)
    assert "\\input{pages/p45-0-verb1.tex}" in got
    assert "print(1)" in (tmp_path / "pages" / "p45-0-verb1.tex").read_text()
    # the book's own build keeps its sections/<ch>/ form
    sec = tmp_path / "sections" / "ch" / "s.tex"
    sec.parent.mkdir(parents=True)
    assert "\\input{sections/ch/s-verb1.tex}" in _externalize_exercise_verbatim(tex, sec)


def test_section_to_latex_accepts_a_relative_path(tmp_path, monkeypatch):
    # pypandoc runs pandoc from the section's own directory, so a relative
    # path (`parody twin .`) named a file that was not there.
    monkeypatch.chdir(tmp_path)
    (tmp_path / "build" / "sections" / "ch").mkdir(parents=True)
    (tmp_path / "build" / "sections" / "ch" / "s.md").write_text("Hello there.\n")
    out = section_to_latex(Path("build/sections/ch/s.md"), Path("build/sections/ch/s.tex"))
    assert "Hello there." in out.read_text()


# An include-py nested in a div that the print filter renders by walking its
# interior (an example, its solution, an exercise solution) went through
# interior_filter's CodeBlock, which called coder_latex directly and never
# dispatched the include classes: the fence, empty in the source, printed as
# nothing. robotics chapter 6 (2026-11-01) lost every program in its worked
# examples from the PDF while the web showed them.
@pytest.mark.parametrize("body", [
    '::: {.example #exa:demo title="demo"}\n::: {.exa_problem}\nDo it.\n:::\n\n'
    '::: {.exa_solution}\nThe program:\n\n```{.include-py path="analysis.py"}\n```\n:::\n:::\n',
    '::: {.exercise #exe:demo}\nDo it.\n\n::: {.exercise-solution}\n'
    '```{.include-py path="analysis.py"}\n```\n:::\n:::\n',
])
def test_include_py_inside_a_walked_div_inlines_executed_markdown(
        notebook_chapter, tmp_path, body):
    section, _ = notebook_chapter
    tex = render(section, body, tmp_path)
    assert "Some prose." in tex
    # an example holds its minted inline; a solution, collected for the key,
    # writes it to a side file and \\inputs it (verbatim cannot be collected)
    assert ("\\begin{minted}" in tex and "print('hi')" in tex) or (
        "\\begin{mintedwrapper}" in tex and "-verb1.tex}" in tex)


def test_include_code_inside_an_example_inlines_verbatim(notebook_chapter, tmp_path):
    section, _ = notebook_chapter
    body = ('::: {.example #exa:demo title="demo"}\n::: {.exa_solution}\n'
            '```{.include-code path="helper.py"}\n```\n:::\n:::\n')
    tex = render(section, body, tmp_path)
    assert "x = 1" in tex


def test_a_long_code_line_wraps_rather_than_running_off_the_page(notebook_chapter, tmp_path):
    """minted without breaklines set a 100-character line in one piece, past
    the right margin and off the page: robotics chapter 6's programs, once
    they printed at all. Breaks fall at spaces and after , ( and ., so a long
    call chain with no spaces wraps too."""
    section, _ = notebook_chapter
    tex = render(section, "```python\nx = 1\n```\n", tmp_path)
    opts = tex.split("\\begin{minted}[", 1)[1].split("]{", 1)[0]
    assert "breaklines" in opts
    assert "breakafter={,(.}" in opts
