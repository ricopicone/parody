import os
from pathlib import Path

import pytest


def pytest_addoption(parser):
    parser.addoption(
        "--regen-golden", action="store_true", default=False,
        help="regenerate Phase 3 golden LaTeX snippets instead of comparing",
    )

# Source corpora live in the (private, local) homepage-django checkout until
# they migrate to content repos in Phase 2. Golden tests skip when absent.
DEFAULT_SOURCES = Path.home() / "homepage-django" / "teaching" / "notebooks-source"


@pytest.fixture(scope="session")
def corpus_root():
    root = Path(os.environ.get("PARODY_HOMEPAGE_SOURCES", DEFAULT_SOURCES))
    if not root.is_dir():
        pytest.skip(
            f"notebook source corpus not found at {root} "
            "(set PARODY_HOMEPAGE_SOURCES to the homepage-django "
            "teaching/notebooks-source directory)"
        )
    return root
