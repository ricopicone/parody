"""Golden-parity tests: parody's artifact writer must reproduce the ancestor's
committed notebooks_data/*.json semantically (Phase 1 gate for the homepage
migration).

Builds run with convert_jupytext=False: the source corpus carries the
already-executed .md outputs, so these tests exercise the pandoc/JSON layer
deterministically without re-executing code cells. Execution-layer parity is
covered separately (tests/test_execution.py).
"""

import json
from pathlib import Path

import pytest

from parody.writers.artifact import convert_notebook

GOLDEN_DIR = Path(__file__).parent / "golden"

NOTEBOOK_SLUGS = [
    "sample-notebook",
    "general-topics",
    "mechatronics-lab-manual",
    "heat-transfer-lab-manual",
    "engineering-artificial-intelligence",
]

# Provenance keys vary by build (and older goldens predate some of them);
# the parity target is the content.
PROVENANCE_KEYS = {"schema_version", "generator", "source_commit", "built_at"}


def normalize(artifact):
    return {k: v for k, v in artifact.items() if k not in PROVENANCE_KEYS}


def diff_paths(a, b, path="", out=None, limit=20):
    """Collect up to `limit` JSON paths where a and b differ."""
    if out is None:
        out = []
    if len(out) >= limit:
        return out
    if type(a) is not type(b):
        out.append(f"{path}: type {type(a).__name__} != {type(b).__name__}")
    elif isinstance(a, dict):
        for k in sorted(set(a) | set(b)):
            if k not in a:
                out.append(f"{path}/{k}: missing in built")
            elif k not in b:
                out.append(f"{path}/{k}: missing in golden")
            else:
                diff_paths(a[k], b[k], f"{path}/{k}", out, limit)
    elif isinstance(a, list):
        if len(a) != len(b):
            out.append(f"{path}: list length {len(a)} != {len(b)}")
        for i, (x, y) in enumerate(zip(a, b)):
            diff_paths(x, y, f"{path}[{i}]", out, limit)
    elif a != b:
        if isinstance(a, str) and isinstance(b, str):
            # Locate first differing character for long strings (HTML bodies)
            i = next(
                (i for i, (c, d) in enumerate(zip(a, b)) if c != d),
                min(len(a), len(b)),
            )
            lo, hi = max(0, i - 60), i + 60
            out.append(
                f"{path}: strings differ at char {i}:\n"
                f"    built:  …{a[lo:hi]}…\n"
                f"    golden: …{b[lo:hi]}…"
            )
        else:
            out.append(f"{path}: {a!r} != {b!r}")
    return out


@pytest.mark.golden
@pytest.mark.parametrize("slug", NOTEBOOK_SLUGS)
def test_artifact_matches_golden(slug, corpus_root, tmp_path):
    source_dir = corpus_root / slug
    if not source_dir.is_dir():
        pytest.skip(f"source corpus for {slug} not found")

    output_path = tmp_path / f"{slug}.json"
    convert_notebook(source_dir, output_path, convert_jupytext=False)

    with open(output_path, encoding="utf-8") as f:
        built = normalize(json.load(f))
    with open(GOLDEN_DIR / f"{slug}.json", encoding="utf-8") as f:
        golden = normalize(json.load(f))

    diffs = diff_paths(built, golden)
    assert not diffs, (
        f"{slug}: built artifact differs from golden in {len(diffs)}+ places:\n"
        + "\n".join(diffs)
    )
