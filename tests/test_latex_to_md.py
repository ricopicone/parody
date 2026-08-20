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


def test_a_plain_subsection_sits_under_its_section(tmp_path):
    """A latex-only chapter may mix the meta 3-arg form with plain LaTeX.
    Only the meta forms were shifted to compensate for the filter's
    one-level promotion, so a plain \\subsection came out as an H1 — a peer
    of the sections around it. The Mathematics Reference appendix opened
    "Completing the square" that way, level with "Trigonometry"."""
    src = tmp_path / "plain"
    src.mkdir()
    tex = src / "plain.tex"
    tex.write_text(textwrap.dedent(r"""
        \section[Quadratic]{quadratic-forms}{0n}{Quadratic Forms}

        Prose.

        \subsection{Completing the square}

        More prose.

        \subsubsection*{A step}

        Even more.
        """))
    headers = [ln for ln in convert_latex_file(tex, src).splitlines()
               if ln.startswith("#")]
    assert headers[0].startswith("# Quadratic Forms ")
    assert headers[1].startswith("## Completing the square")
    assert headers[2].startswith("### A step")


def test_a_table_header_is_one_row_and_keeps_its_maths(tmp_path):
    """to_simple_table's `header` is ONE row — a list of cells. Iterating it
    as a list of rows gave every heading a row of its own, so the Laplace
    transform table opened with two one-cell rows and the z-score table with
    eleven, and stringify dropped the maths out of them as well."""
    src = tmp_path / "tbl"
    src.mkdir()
    tex = src / "tbl.tex"
    tex.write_text(textwrap.dedent(r"""
        \begin{tabular}{cc}
        $f(t)$ & $F(s)$ \\ \hline
        $\delta(t)$ & $1$ \\
        \end{tabular}
        """))
    out = convert_latex_file(tex, src)
    assert out.count("<th>") == 2, out
    assert out.count("<tr>") == 2, "one header row plus one body row"
    assert "$f(t)$" in out and "$F(s)$" in out, "maths dropped from the header"


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


UNHANDLED_TEX = textwrap.dedent(r"""
    \section[S]{unhandled}{bk}{Unhandled}

    A fixed blank: \clozeline[3cm] here.
    """)


def test_unhandled_cloze_macro_passes_through_with_a_warning(tmp_path, caplog):
    # pypandoc intercepts pandoc's stderr and re-emits it through logging,
    # so the warning surfaces in caplog rather than on the fd
    out = convert_src(tmp_path, UNHANDLED_TEX)
    assert "clozeline" in out          # left raw, not silently swallowed
    assert "latex-to-md" in caplog.text
    assert "clozeline" in caplog.text


def test_clozeset_is_dropped(tmp_path):
    out = convert_src(tmp_path, textwrap.dedent(r"""
        \section[S]{cset}{bk}{Cset}

        \clozeset{hide}

        Prose after.
        """))
    assert "clozeset" not in out
    assert "Prose after." in out


INLINE_POSITION_TEX = textwrap.dedent(r"""
    \section[S]{inline-pos}{bk}{Inline position}

    A sentence that runs straight into the macro with no blank line, so
    pandoc hands it to us as an inline rather than a block.
    \maybeeqn{a titled result}{eq:inline}{%
    \begin{align*}
      v = 1.
    \end{align*}
    }
    """)


def test_blockish_macro_in_inline_position(tmp_path):
    """An inline handler may not return a Block ('no __toinline metamethod').

    Found by running the real electronics-primer chapters, not by a fixture:
    ch03/ch04 put \\maybeeqn in a paragraph's inline stream. The Div is
    serialised to raw markdown, padded with blank lines so the fence still
    parses when the markdown is read back.
    """
    out = convert_src(tmp_path, INLINE_POSITION_TEX)
    assert 'title="a titled result"' in out
    assert "#eq:inline" in out
    assert "\\maybeeqn" not in out
    # the fence must start its own line, or it reads back as paragraph text
    assert any(ln.lstrip().startswith(":::") and ".infobox" in ln
               for ln in out.splitlines()), out


EXAMPLEMAYBE_TEX = textwrap.dedent(r"""
    \section[S]{ex-sample}{bk}{Ex sample}

    \examplemaybe{A title}{Find $\frac{a}{b}$ when $a=1$.}{Because
    $\frac{a}{b}$ is one half, the answer is $0.5$.}{ex:halves}
    """)


def test_examplemaybe_splits_nested_arguments(tmp_path):
    """Characterisation guard for the multi-arg `{.-}{(.-)}{.-}{.-}` split.

    Unlike clozer's `{(.-)}`, this pattern is followed by more groups, so Lua
    backtracks until it finds a consistent parse -- it handles balanced
    nesting correctly. Pinned so a future rewrite cannot regress it silently.
    """
    out = convert_src(tmp_path, EXAMPLEMAYBE_TEX)
    assert ".example" in out
    # the solution is not truncated at the \frac{a}{b} braces
    assert "the answer is" in out
    assert "ex:halves" in out


def test_preprocess_postprocess_pure():
    pre = preprocess("\\section{slug-a}{q1}{Title A}\n")
    assert "\\section{Title A}" in pre
    assert "PARODYSECATTR slug-a q1" in pre
    md = postprocess("# Title A\n\nPARODYSECATTR slug-a q1\n")
    assert md.splitlines()[0] == '# Title A {#slug-a h="q1"}'
