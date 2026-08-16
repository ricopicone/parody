"""Cross-reference links must not print as boxes.

hyperref's default `/Border [0 0 1]` draws a rectangle around every link. On
screen that is a mild annoyance; in parody it is a defect, because the print
PDF is something readers PRINT — a section at a time from the web page, or the
whole book — and 259 cross-references in one book means 259 boxes on paper.

Two tests: the static one says both bundled profiles ask for it, and the
compile one proves the request survives into a real PDF (a `\\hypersetup` line
can be silently overridden by a later package, which the static test cannot
see).
"""

import pytest

from parody.writers.latex import (BUNDLED_PROFILES, build_pdf, have_tool,
                                  resolve_profile)
from tests.test_print_pdf import tiny_project  # noqa: F401  (pytest fixture)

needs_tex = pytest.mark.skipif(
    not (have_tool("latexmk") and have_tool("lualatex")),
    reason="TeX (latexmk + lualatex) not available",
)

PROFILE_STYLES = {
    "print": "print/parody-print.sty",
    "memoir": "memoir/parody-environments.sty",
}


@pytest.mark.parametrize("profile,style", sorted(PROFILE_STYLES.items()))
def test_profile_disables_link_borders(profile, style):
    text = (BUNDLED_PROFILES / style).read_text()
    assert "pdfborder={0 0 0}" in text, (
        f"the {profile} profile does not disable hyperref link borders"
    )


@pytest.mark.parametrize("profile", sorted(PROFILE_STYLES))
@needs_tex
def test_compiled_pdf_has_no_link_borders(tiny_project, profile):  # noqa: F811
    """The static check above can be defeated by load order, so read the
    annotations out of a PDF that LaTeX actually produced."""
    pypdf = pytest.importorskip("pypdf")

    pdf = build_pdf(tiny_project, profile_dir=profile)
    assert pdf is not None and pdf.exists()

    borders = []
    for page in pypdf.PdfReader(str(pdf)).pages:
        for annot in page.get("/Annots") or []:
            obj = annot.get_object()
            if obj.get("/Subtype") == "/Link":
                borders.append(list(obj.get("/Border") or [0, 0, 0]))

    boxed = [b for b in borders if len(b) > 2 and b[2]]
    assert not boxed, f"{len(boxed)} of {len(borders)} links print as a box"


def test_resolve_profile_covers_both_styled_profiles():
    """Guards the parametrisation above: if a profile is renamed, the border
    tests must fail loudly rather than quietly testing nothing."""
    for profile in PROFILE_STYLES:
        assert resolve_profile(profile).is_dir()
