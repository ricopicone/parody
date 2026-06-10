"""Destination resolution for execution-time figure moves.

The mover must place figures (and the md image refs derived from the same
function) under media/notebooks/<slug>/<chapter>/<stem>_files for every
supported source layout.
"""

from pathlib import Path

import pytest

from parody.readers.figure_mover import determine_destination_path


def test_homepage_legacy_tree_resolves_from_path():
    dest = determine_destination_path(
        Path("/x/teaching/notebooks-source/heat-transfer/chapter_conduction/examples.py")
    )
    assert dest == Path("media/notebooks/heat-transfer/chapter_conduction/examples_files")


def test_content_repo_chapters_layout_uses_env_slug(monkeypatch):
    monkeypatch.setenv("PARODY_NOTEBOOK_SLUG", "my-book")
    dest = determine_destination_path(Path("/repo/chapters/intro/sim.py"))
    assert dest == Path("media/notebooks/my-book/intro/sim_files")


def test_content_repo_legacy_layout_uses_env_slug_and_chapter_dir(monkeypatch):
    # Standalone content repo that kept the homepage chapter_*/ structure
    # (no notebooks-source/ ancestor): slug must come from the env var.
    monkeypatch.setenv("PARODY_NOTEBOOK_SLUG", "sample-notebook")
    dest = determine_destination_path(
        Path("/repo/chapter_python-examples/simple_code.py")
    )
    assert dest == Path(
        "media/notebooks/sample-notebook/chapter_python-examples/simple_code_files"
    )


def test_unparseable_path_without_env_falls_back_to_unknown(monkeypatch):
    monkeypatch.delenv("PARODY_NOTEBOOK_SLUG", raising=False)
    dest = determine_destination_path(Path("/somewhere/else/script.py"))
    assert dest == Path("media/notebooks/unknown/script_files")
