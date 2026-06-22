"""Parody — unified book/notebook authoring toolchain.

A play on *parity*: keeping the print and web versions of a work in parity.
One pandoc-markdown source (with executed jupytext code), many targets:
schema-versioned JSON artifact, standalone HTML preview, print PDF.
"""

from importlib.metadata import PackageNotFoundError, version as _version

try:
    # Single source of truth: the version declared in pyproject.toml, read from
    # the installed package metadata so __version__ and pyproject can't drift.
    __version__ = _version("parody")
except PackageNotFoundError:  # running from a source tree without an install
    __version__ = "0.0.0+unknown"
