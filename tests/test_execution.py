"""Execution-layer tests: jupytext → executed notebook → markdown.

Self-contained (no ancestor corpus needed): a small jupytext percent-format
file is executed through the same cached API path the artifact build uses.
"""

import textwrap

import pytest

from parody.readers.jupytext_converter_api import (
    convert_jupytext_with_api_execution,
    is_jupytext_file,
    needs_conversion,
)

JUPYTEXT_SOURCE = textwrap.dedent('''
    # %% [markdown]
    # # Tiny executed notebook
    #
    # Prose cell.

    # %%
    x = 6 * 7
    print(f"the answer is {x}")

    # %% [markdown]
    # A figure-producing cell:

    # %%
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots()
    ax.plot([0, 1], [0, 1])
    plt.show()
''').strip()


@pytest.fixture
def jupytext_file(tmp_path):
    py = tmp_path / "tiny_code.py"
    py.write_text(JUPYTEXT_SOURCE, encoding="utf-8")
    return py


def test_detects_percent_format(jupytext_file):
    assert is_jupytext_file(jupytext_file) == "percent"


@pytest.mark.execution
def test_executes_and_converts_to_markdown(jupytext_file, tmp_path):
    out_md = tmp_path / "tiny_code.md"
    success, result_path, was_cached = convert_jupytext_with_api_execution(
        jupytext_file, out_md, timeout=120
    )
    assert success and result_path == out_md and not was_cached

    md = out_md.read_text(encoding="utf-8")
    assert "the answer is 42" in md, "executed cell output missing from markdown"
    assert "autofig" in md.lower() or ".svg" in md, "auto-captured figure missing"
    # Injected helper machinery must not leak into the output
    assert "_autofig_capture" not in md
    assert "__AUTOFIG_CAPTURE__" not in md


@pytest.mark.execution
def test_cache_skips_reconversion(jupytext_file, tmp_path):
    out_md = tmp_path / "tiny_code.md"
    cache = {}
    success, _, was_cached = convert_jupytext_with_api_execution(
        jupytext_file, out_md, timeout=120, cache_data=cache
    )
    assert success and not was_cached
    assert not needs_conversion(jupytext_file, out_md, cache)
    success, _, was_cached = convert_jupytext_with_api_execution(
        jupytext_file, out_md, timeout=120, cache_data=cache
    )
    assert success and was_cached


# --- Flush timing (task #881) -----------------------------------------------
#
# ipykernel ships a cell's stdout in chunks on a timer (~0.2 s), so a program
# that prints while it computes can arrive as several `stream` outputs or as
# one, run to run. Each output rendered as its own block, so the same program
# printed a blank line mid-table in one build and not in the other — and the
# student and key artifacts of robotics v0.49.0 disagreed on that alone.


def _code_cell(outputs):
    import nbformat

    cell = nbformat.v4.new_code_cell("run()")
    cell.outputs = [nbformat.from_dict(o) for o in outputs]
    return cell


def _stream(text, name="stdout"):
    return {"output_type": "stream", "name": name, "text": text}


def _markdown_of(tmp_path, outputs, stem="nb"):
    import nbformat

    from parody.readers.jupytext_converter_api import (
        convert_notebook_to_markdown_api,
    )

    nb = nbformat.v4.new_notebook()
    nb.cells = [_code_cell(outputs)]
    out = tmp_path / f"{stem}.md"
    assert convert_notebook_to_markdown_api(nb, out)
    return out.read_text(encoding="utf-8")


def test_stream_chunks_render_as_one_output(tmp_path):
    """Two stdout chunks render exactly as the one output they add up to."""
    chunked = _markdown_of(
        tmp_path, [_stream("0.0775\n"), _stream("   0.695\n")], stem="chunked")
    whole = _markdown_of(
        tmp_path, [_stream("0.0775\n   0.695\n")], stem="whole")
    assert chunked == whole
    assert "0.0775\n       0.695" in chunked  # indented code block, no gap


def test_chunk_split_mid_line_joins_without_separator(tmp_path):
    """A chunk can end mid-line; the halves join with nothing added."""
    md = _markdown_of(tmp_path, [_stream("0.07"), _stream("75\n")])
    assert "0.0775" in md


def test_stdout_and_stderr_stay_separate(tmp_path):
    """Only consecutive outputs of the SAME stream merge."""
    md = _markdown_of(
        tmp_path, [_stream("out\n"), _stream("err\n", name="stderr")])
    assert "out\n\n" in md and "err" in md


def test_streams_either_side_of_other_output_stay_separate(tmp_path):
    """A result between two prints keeps the order prints, result, prints."""
    md = _markdown_of(tmp_path, [
        _stream("before\n"),
        {"output_type": "execute_result", "execution_count": 1,
         "data": {"text/plain": "42"}, "metadata": {}},
        _stream("after\n"),
    ])
    assert md.index("before") < md.index("42") < md.index("after")


PAUSING_PRINTER = textwrap.dedent('''
    # %%
    import time
    print("row 1")
    time.sleep(0.6)
    print("row 2")
''').strip()


@pytest.mark.execution
def test_program_pausing_between_prints_renders_without_gap(tmp_path):
    """The real failure: a cell that pauses past ipykernel's flush interval.

    The kernel delivers the two lines as two stream outputs; the rendered
    output must still be one block with no blank line between the rows.
    """
    py = tmp_path / "pause_code.py"
    py.write_text(PAUSING_PRINTER, encoding="utf-8")
    out_md = tmp_path / "pause_code.md"
    success, _, _ = convert_jupytext_with_api_execution(py, out_md, timeout=120)
    assert success
    md = out_md.read_text(encoding="utf-8")
    assert "row 1\n    row 2" in md, md
