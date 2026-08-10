"""latex-to-md converter: meta sectioning pre-pass, parody-owned filter
(pinned pandoc — no luafilesystem), marker resolution, determinism."""

import textwrap

from parody.migrate.latex_to_md import convert_latex_file, postprocess, preprocess

SAMPLE_TEX = textwrap.dedent(r"""
    \section[Short]{memory-and-contents}{bk}{Memory and its contents}

    \myindex[start]{Memory}

    Prose with an inline index\myindex{Memory!bits} entry and math
    $$\begin{align}
      a &= b \\

      c &= d
    \end{align}$$ continues.

    \subsection{memory-organization}{h7}{Memory organization}\label{memorg}

    % \subsection{ghost}{zz}{Commented out}

    \subsection{pulled-in}{vv}

    \resource[Motor]{motor-apparatus}{5l}{Motor
    apparatus}

    Closing prose.
    """)


def convert(tmp_path):
    src = tmp_path / "src"
    src.mkdir(exist_ok=True)
    tex = src / "sample.tex"
    tex.write_text(SAMPLE_TEX)
    return convert_latex_file(tex, src)


def test_sectioning_and_markers(tmp_path):
    out = convert(tmp_path)
    lines = out.splitlines()
    headers = [ln for ln in lines if ln.startswith("#")]
    assert '# Memory and its contents {#memory-and-contents h="bk"}' in headers
    assert '## Memory organization {#memory-organization h="h7"}' in headers
    assert ('# Motor apparatus {#motor-apparatus .resource h="5l"}'
            in headers), "multi-line \\resource title"
    # commented-out command stays gone
    assert "ghost" not in out and "zz" not in out
    # 2-arg versioned pull becomes an include fence the migrator inlines
    fence = out.find("```include\ncommon/versioned/vv/source.md\n```")
    assert fence != -1
    # no marker debris
    assert "PARODYSECATTR" not in out and "PARODYVERSIONED" not in out


def test_myindex_spans(tmp_path):
    out = convert(tmp_path)
    assert "[Memory]{.index .start}" in out
    assert "[Memory!bits]{.index}" in out
    assert "\\myindex" not in out


def test_math_cleanup(tmp_path):
    out = convert(tmp_path)
    assert "\\begin{align}" not in out, "align demoted to aligned"
    assert "\\begin{aligned}" in out
    # the blank line inside the display span is collapsed
    assert "a &= b \\\\\n\n" not in out


def test_deterministic(tmp_path):
    assert convert(tmp_path) == convert(tmp_path)


# --- cloze package and the \maybe* family (task #542) ----------------------


def convert_src(tmp_path, tex, name="sample.tex"):
    src = tmp_path / "src"
    src.mkdir(exist_ok=True)
    path = src / name
    path.write_text(tex)
    return convert_latex_file(path, src)


CLOZE_TEX = textwrap.dedent(r"""
    \section[S]{cloze-sample}{bk}{Cloze sample}

    The damping ratio is \cloze{0.707} here.

    A nested one: \cloze{\keyword{stationary point}} ok.

    Inline math: $\tau = \cloze{RC}$ done.

    \begin{align}
      y &= \cloze{g(x)}
    \end{align}
    """)


def test_cloze_becomes_a_cloze_span(tmp_path):
    out = convert_src(tmp_path, CLOZE_TEX)
    assert "[0.707]{.cloze}" in out


def test_cloze_argument_survives_nested_braces(tmp_path):
    out = convert_src(tmp_path, CLOZE_TEX)
    # brace-naive extraction captured "\keyword{stationary point" and dropped
    # the closing brace, leaving an escaped literal in the span
    assert "stationary point" in out
    assert "{.cloze}" in out
    assert "{stationary point]" not in out, "argument truncated at first brace"
    assert "\\\\keyword" not in out, "argument left as an escaped raw string"


def test_cloze_argument_is_recursively_converted(tmp_path):
    out = convert_src(tmp_path, CLOZE_TEX)
    # the inner \keyword must become a .keyword span, not a raw string
    assert ".keyword" in out


def test_cloze_inside_math_is_left_alone(tmp_path):
    out = convert_src(tmp_path, CLOZE_TEX)
    assert r"\cloze{RC}" in out
    assert r"\cloze{g(x)}" in out


MAYB_TEX = textwrap.dedent(r"""
    \section[S]{mayb-sample}{bk}{Mayb sample}

    The answer is \mayb{42} and that is all.
    """)


def test_mayb_becomes_a_cloze_span(tmp_path):
    out = convert_src(tmp_path, MAYB_TEX)
    assert "[42]{.cloze}" in out
    assert "maybe" not in out
    assert "\\mayb" not in out


MAYBEEQ_TEX = textwrap.dedent(r"""
    \section[S]{maybeeq-sample}{bk}{Maybeeq sample}

    \maybeeq{%
    \begin{align*}
      v_k = \frac{Z_k}{Z_1 + Z_2} v_\text{in}.
    \end{align*}
    }
    """)


def test_maybeeq_becomes_a_cloze_div(tmp_path):
    out = convert_src(tmp_path, MAYBEEQ_TEX)
    # pandoc's markdown writer uses the compact single-class fence form
    # (`::: cloze`); it reads back to the same classes as `::: {.cloze}`.
    assert "::: cloze" in out
    assert "v_k" in out
    assert "\\maybeeq" not in out
    assert ".maybe" not in out


MAYBEEQN_TEX = textwrap.dedent(r"""
    \section[S]{eqn-sample}{bk}{Eqn sample}

    \maybeeqn{general impedance voltage divider}{eq:vdiv}{%
    For the output voltage across impedance $Z_k$ we have
    \begin{align*}
      v_k = \frac{Z_k}{Z_1 + Z_2} v_\text{in}.
    \end{align*}
    }

    \maybeeqn{piecewise linear diode model}{}{%
    \begin{align*}
      i_D = 0.
    \end{align*}
    }
    """)


def test_maybeeqn_becomes_a_titled_infobox(tmp_path):
    out = convert_src(tmp_path, MAYBEEQN_TEX)
    assert ".infobox" in out
    assert 'title="general impedance voltage divider"' in out
    assert "#eq:vdiv" in out


def test_maybeeqn_hides_only_its_contents(tmp_path):
    out = convert_src(tmp_path, MAYBEEQN_TEX)
    # the box survives; a cloze div nests inside it
    assert "cloze" in out
    assert "v_k" in out


def test_maybeeqn_empty_label_yields_no_identifier(tmp_path):
    out = convert_src(tmp_path, MAYBEEQN_TEX)
    assert 'title="piecewise linear diode model"' in out
    assert "#labelme" not in out


def test_maybeeqn_body_prose_survives(tmp_path):
    out = convert_src(tmp_path, MAYBEEQN_TEX)
    assert "For the output voltage" in out


def test_preprocess_postprocess_pure():
    pre = preprocess("\\section{slug-a}{q1}{Title A}\n")
    assert "\\section{Title A}" in pre
    assert "PARODYSECATTR slug-a q1" in pre
    md = postprocess("# Title A\n\nPARODYSECATTR slug-a q1\n")
    assert md.splitlines()[0] == '# Title A {#slug-a h="q1"}'
