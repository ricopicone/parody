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
