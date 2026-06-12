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
    headers = [l for l in lines if l.startswith("#")]
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


def test_preprocess_postprocess_pure():
    pre = preprocess("\\section{slug-a}{q1}{Title A}\n")
    assert "\\section{Title A}" in pre
    assert "PARODYSECATTR slug-a q1" in pre
    md = postprocess("# Title A\n\nPARODYSECATTR slug-a q1\n")
    assert md.splitlines()[0] == '# Title A {#slug-a h="q1"}'
