"""Pinned external-toolchain versions.

Both ancestor systems were bitten by pandoc behavior changes between
versions (figure environments, table-row classes, attribute parsing).
Parody therefore depends on `pypandoc-binary`, which bundles an exact
pandoc; this module records the expected version and verifies it.
`parody check --toolchain` and the golden tests warn on mismatch.
"""

# The version the golden artifacts were produced with (homepage-django's
# build environment at the time of the Phase 1 port). Bundled by the
# pypandoc-binary pin in pyproject.toml; bump both together, with a golden
# re-baseline.
PANDOC_VERSION = "3.6.1"


def local_pandoc_version():
    """Return the pandoc version pypandoc will use, or None if unavailable."""
    try:
        import pypandoc

        return pypandoc.get_pandoc_version()
    except Exception:
        return None


def check_pandoc(warn=True):
    """Return (ok, local_version). ok is True when local matches the pin."""
    local = local_pandoc_version()
    ok = local == PANDOC_VERSION
    if warn and not ok:
        print(
            f"⚠️  pandoc version mismatch: pinned {PANDOC_VERSION}, "
            f"found {local or 'none'}. Output may differ from golden artifacts."
        )
    return ok, local
