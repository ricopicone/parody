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


import pypandoc  # noqa: E402

WEB_FROM = ("markdown-smart-markdown_in_html_blocks+raw_tex"
            "+tex_math_dollars+grid_tables")
PRINT_FROM = "markdown-markdown_in_html_blocks+raw_tex+tex_math_dollars"


def web(md, mode="blank", cwd=None):
    with cloze_mode(mode):
        return pypandoc.convert_text(
            md, "html", format=WEB_FROM,
            extra_args=[f"--lua-filter={FILTERS / 'filter.lua'}", "--mathjax"],
            cworkdir=str(cwd) if cwd else None,
        )


# --- web: inline spans -----------------------------------------------------

SPAN_MD = "The damping ratio is [0.707]{.cloze}."


def test_web_blank_hides_the_answer():
    out = web(SPAN_MD, "blank")
    assert "0.707" not in out
    assert 'class="cloze-blank"' in out
    assert "--cloze-w:" in out


def test_web_key_shows_the_answer_marked():
    out = web(SPAN_MD, "key")
    assert "0.707" in out
    assert "cloze-key" in out


def test_web_full_leaves_no_trace():
    out = web(SPAN_MD, "full")
    assert "0.707" in out
    assert "cloze" not in out


def test_web_default_mode_is_blank():
    with cloze_mode(None):
        out = pypandoc.convert_text(
            SPAN_MD, "html", format=WEB_FROM,
            extra_args=[f"--lua-filter={FILTERS / 'filter.lua'}"])
    assert "0.707" not in out


def test_web_manual_blank_named_size():
    out = web("Sketch it: []{.blank size=lg}", "blank")
    assert "--cloze-w: 10em" in out


def test_web_manual_blank_explicit_width_wins():
    out = web("[]{.blank size=lg width=4cm}", "blank")
    assert "--cloze-w: 4cm" in out


def test_web_manual_blank_defaults_to_md():
    out = web("[]{.blank}", "blank")
    assert "--cloze-w: 5em" in out


def test_web_manual_blank_dropped_in_full():
    out = web("Sketch it: []{.blank size=lg}", "full")
    assert "cloze-blank" not in out


def test_web_manual_blank_survives_in_key():
    """Nothing is hidden behind a manual blank, so key still needs the rule."""
    assert "cloze-blank" in web("[]{.blank size=lg}", "key")


def _cloze_width(html):
    return float(html.split("--cloze-w: ")[1].split("em")[0])


def test_web_blank_width_scales_with_the_answer():
    short = web("[a]{.cloze}", "blank")
    long = web("[a much longer hidden answer]{.cloze}", "blank")
    assert _cloze_width(short) < _cloze_width(long)


def test_web_blank_width_is_clamped():
    assert _cloze_width(web("[x]{.cloze}", "blank")) >= 2.0
    assert _cloze_width(web("[" + "x" * 400 + "]{.cloze}", "blank")) <= 14.0


def test_web_cloze_inside_a_box():
    """Clozes inside .example/.exercise bodies are rewritten too."""
    md = "::: {.example h=\"c4\"}\nThe ratio is [0.707]{.cloze}.\n:::"
    out = web(md, "blank")
    assert "0.707" not in out
    assert "cloze-blank" in out


# --- web: block forms ------------------------------------------------------

def test_web_manual_block_blank():
    out = web("::: {.blank lines=6}\n:::", "blank")
    assert 'class="cloze-lines"' in out
    assert 'data-lines="6"' in out


def test_web_manual_block_defaults_to_four_lines():
    assert 'data-lines="4"' in web("::: {.blank}\n:::", "blank")


def test_web_manual_block_dropped_in_full():
    assert "cloze-lines" not in web("::: {.blank lines=6}\n:::", "full")


def test_web_hidden_block_hides_its_text():
    md = "::: {.cloze}\nA whole hidden paragraph of derivation.\n:::"
    out = web(md, "blank")
    assert "derivation" not in out
    assert 'class="cloze-lines"' in out


def test_web_hidden_block_shows_text_in_key_and_full():
    md = "::: {.cloze}\nA whole hidden paragraph of derivation.\n:::"
    assert "derivation" in web(md, "key")
    assert "cloze-key-block" in web(md, "key")
    full = web(md, "full")
    assert "derivation" in full
    assert "cloze" not in full


def test_web_hidden_block_line_count_grows_with_content():
    def lines(html):
        return int(html.split('data-lines="')[1].split('"')[0])
    short = web("::: {.cloze}\nshort\n:::", "blank")
    long = web("::: {.cloze}\n" + "word " * 200 + "\n:::", "blank")
    assert lines(short) == 1
    assert lines(long) > 1


# --- web: math -------------------------------------------------------------

def test_web_math_cloze_hidden():
    out = web(r"The constant is $\tau = \cloze{RC}$.", "blank")
    assert "RC" not in out
    assert "underline" in out


def test_web_math_cloze_nested_braces():
    r"""A brace-matching scanner, not a regex: \cloze{\sqrt{k/m}} nests."""
    out = web(r"$\omega_n = \cloze{\sqrt{k/m}}$", "blank")
    assert "sqrt" not in out
    assert "k/m" not in out


def test_web_math_cloze_key():
    out = web(r"$\tau = \cloze{RC}$", "key")
    assert "RC" in out
    assert r"\class{cloze-key}" in out


def test_web_math_cloze_full():
    out = web(r"$\tau = \cloze{RC}$", "full")
    assert "RC" in out
    assert "cloze" not in out


def test_web_math_manual_blank():
    out = web(r"$y(t) = \clozeblank{3em}$", "blank")
    assert "3em" in out
    assert "underline" in out


def test_web_math_manual_blank_dropped_in_full():
    out = web(r"$y(t) = \clozeblank{3em}$", "full")
    assert "blank" not in out
    assert "3em" not in out


def test_web_display_math_cloze():
    out = web(r"$$x = \cloze{\frac{a}{b}}$$", "blank")
    assert "frac" not in out


def test_web_math_without_cloze_untouched():
    out = web(r"$E = mc^2$", "blank")
    assert "mc^2" in out


# --- print -----------------------------------------------------------------

def latex(md, mode="blank"):
    with cloze_mode(mode):
        return pypandoc.convert_text(
            md, "latex", format=PRINT_FROM,
            extra_args=[f"--lua-filter={FILTERS / 'print.lua'}", "--biblatex",
                        "--wrap=none"])


def test_print_cloze_span():
    assert "\\cloze{0.707}" in latex("The ratio is [0.707]{.cloze}.")


def test_print_manual_blank_named_size():
    assert "\\clozeblank{10em}" in latex("Sketch: []{.blank size=lg}")


def test_print_manual_blank_explicit_width():
    assert "\\clozeblank{4cm}" in latex("[]{.blank width=4cm}")


def test_print_manual_blank_defaults_to_md():
    assert "\\clozeblank{5em}" in latex("[]{.blank}")


def test_print_block_blank():
    assert "\\clozelines{6}" in latex("::: {.blank lines=6}\n:::")


def test_print_hidden_block():
    out = latex("::: {.cloze}\nHidden derivation.\n:::")
    assert "\\begin{clozeblock}" in out
    assert "\\end{clozeblock}" in out
    assert "Hidden derivation." in out  # TeX decides; the mode is a \def


def test_print_math_cloze_passes_through():
    r"""Math needs no filter work in print: TeX defines \cloze itself."""
    assert "\\cloze{RC}" in latex(r"$\tau = \cloze{RC}$")


def test_print_cloze_inside_a_box():
    """interior_filter must reach spans and divs nested in environments."""
    md = ("::: {.exercise h=\"8y\"}\n"
          "The ratio is [0.707]{.cloze}.\n\n"
          "::: {.blank lines=3}\n:::\n"
          ":::")
    out = latex(md)
    assert "\\cloze{0.707}" in out
    assert "\\clozelines{3}" in out


# --- print: real LaTeX compile ---------------------------------------------

CLOZE_TEX_SNIPPET = r"""
Text cloze: \cloze{0.707} and manual \clozeblank{10em}.

Math cloze: $\tau = \cloze{RC}$ and $y = \clozeblank{3em}$.

\clozelines{3}

\begin{clozeblock}
A whole hidden paragraph that should blank to its own height.
\end{clozeblock}
"""


@pytest.mark.parametrize("profile", ["memoir", "print"])
@pytest.mark.parametrize("mode", ["blank", "key", "full"])
def test_profile_macros_compile(tmp_path, profile, mode):
    """The four contract names must compile in every mode, in both profiles."""
    import shutil
    import subprocess

    from parody.writers.latex import _tool_env, have_tool

    if not have_tool("lualatex"):
        pytest.skip("no LaTeX toolchain")

    src = (Path(__file__).parent.parent / "parody" / "profiles" / profile)
    work = tmp_path / profile
    work.mkdir()
    for f in src.iterdir():
        if f.is_file() and f.name != "main.tex.template":
            shutil.copy2(f, work / f.name)

    template = (src / "main.tex.template").read_text(encoding="utf-8")
    preamble = template.split("$flags")[0]
    packages = "\n".join(
        line for line in template.split("\n")
        if line.startswith("\\usepackage{parody-"))
    (work / "main.tex").write_text(
        preamble
        + f"\\def\\clozemode{{{mode}}}\n"
        + packages
        + "\n\\begin{document}\n" + CLOZE_TEX_SNIPPET + "\n\\end{document}\n",
        encoding="utf-8")

    r = subprocess.run(
        ["lualatex", "-interaction=nonstopmode", "-shell-escape", "main.tex"],
        cwd=work, env=_tool_env(), capture_output=True, text=True)
    assert (work / "main.pdf").exists(), r.stdout[-3000:]
    # nonstopmode still emits a PDF over a LaTeX error, so the PDF's
    # existence proves nothing on its own — the log is the real gate. It must
    # catch name clashes too: \newcommand over an existing macro errors and
    # leaves the OTHER definition in force, which renders wrong but compiles.
    log = (work / "main.log").read_text(encoding="utf-8", errors="replace")
    assert "Undefined control sequence" not in log, log[-3000:]
    assert "LaTeX Error" not in log, log[-3000:]


# --- figures ---------------------------------------------------------------

@pytest.fixture
def figdir(tmp_path):
    for name in ("rl.pdf", "rl-blank.pdf", "bode.pdf", "bode-cloze.pdf",
                 "plain.pdf"):
        (tmp_path / name).write_bytes(b"%PDF-1.4\n")
    return tmp_path


@contextmanager
def chapter_dir(d):
    saved = os.environ.get("PARODY_CHAPTER_DIR")
    os.environ["PARODY_CHAPTER_DIR"] = str(d)
    try:
        yield
    finally:
        if saved is None:
            os.environ.pop("PARODY_CHAPTER_DIR", None)
        else:
            os.environ["PARODY_CHAPTER_DIR"] = saved


def test_web_explicit_cloze_variant(figdir):
    md = '![Root locus](rl.pdf){#fig:rl cloze="rl-blank.pdf"}'
    with chapter_dir(figdir):
        out = web(md, "blank", cwd=figdir)
    assert "rl-blank.pdf" in out
    assert "rl.pdf" not in out.replace("rl-blank.pdf", "")


def test_web_complete_artwork_in_key_and_full(figdir):
    md = '![Root locus](rl.pdf){#fig:rl cloze="rl-blank.pdf"}'
    for mode in ("key", "full"):
        with chapter_dir(figdir):
            out = web(md, mode, cwd=figdir)
        assert "rl-blank.pdf" not in out


def test_web_sibling_variant_autodetected(figdir):
    with chapter_dir(figdir):
        out = web("![Bode](bode.pdf){#fig:b}", "blank", cwd=figdir)
    assert "bode-cloze.pdf" in out


def test_web_no_variant_renders_complete(figdir):
    """No variant authored means the artwork isn't part of the exercise."""
    with chapter_dir(figdir):
        out = web("![Plain](plain.pdf){#fig:p}", "blank", cwd=figdir)
    assert "plain.pdf" in out


def test_print_explicit_cloze_variant(figdir):
    with chapter_dir(figdir):
        out = latex('![Root locus](rl.pdf){#fig:rl cloze="rl-blank.pdf"}')
    assert "rl-blank" in out


def test_print_sibling_variant_autodetected(figdir):
    with chapter_dir(figdir):
        out = latex("![Bode](bode.pdf){#fig:b}")
    assert "bode-cloze" in out


def test_print_complete_artwork_in_full(figdir):
    with chapter_dir(figdir):
        out = latex('![Root locus](rl.pdf){#fig:rl cloze="rl-blank.pdf"}',
                    "full")
    assert "rl-blank" not in out


# --- solutions -------------------------------------------------------------

def test_solution_clozes_always_render_full(tmp_path):
    """An answer key must not blank its own answers."""
    from parody.writers.artifact import convert_solution_to_html

    with cloze_mode("blank"):
        html = convert_solution_to_html(
            "The ratio is [0.707]{.cloze}.", str(tmp_path), cloze_mode="full")
    assert "0.707" in html
    assert "cloze-blank" not in html


def test_problem_bodies_keep_the_ambient_mode(tmp_path):
    from parody.writers.artifact import convert_solution_to_html

    with cloze_mode("blank"):
        html = convert_solution_to_html(
            "The ratio is [0.707]{.cloze}.", str(tmp_path))
    assert "0.707" not in html


def test_solution_override_is_restored(tmp_path):
    """The override must not leak into the rest of the build."""
    from parody.writers.artifact import convert_solution_to_html

    with cloze_mode("blank"):
        convert_solution_to_html("x", str(tmp_path), cloze_mode="full")
        assert os.environ["PARODY_CLOZE_MODE"] == "blank"
