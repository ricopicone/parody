"""Box and problem names are macros, so a twin can say them in its language (task #825)."""

from pathlib import Path

ENV = Path(__file__).parent.parent / "parody" / "profiles" / "memoir" / "parody-environments.sty"

NAMES = {
    "parodydefinitionname": "Definition", "parodytheoremname": "Theorem",
    "parodylemmaname": "Lemma", "parodycorollaryname": "Corollary",
    "parodypropositionname": "Proposition", "parodyexamplename": "Example",
    "parodyboxname": "Box", "parodyproblemname": "Problem",
    "parodylabexercisename": "Lab Exercise", "parodylabsolutionname": "Lab Solution",
}


def test_names_default_to_english():
    sty = ENV.read_text()
    for macro, word in NAMES.items():
        assert f"\\newcommand{{\\{macro}}}{{{word}}}" in sty


def test_literals_are_gone():
    sty = ENV.read_text()
    for literal in ("{Definition~", "{Theorem~", "{Lemma~", "{Corollary~", "{Proposition~",
                    "={Box~", "={Example~", "exercise/name=Problem", "exercise-name=Lab Exercise",
                    "labexercise/name = Problem"):
        assert literal not in sty, literal


import pytest  # noqa: E402

from parody.writers.latex import build_pdf, have_tool  # noqa: E402


@pytest.mark.skipif(not (have_tool("latexmk") and have_tool("lualatex")), reason="needs TeX")
def test_english_book_still_prints_the_english_names(tmp_path):
    import pypdf
    book = tmp_path / "b"
    (book / "chapters" / "one").mkdir(parents=True)
    (book / "parody.yaml").write_text(
        "title: T\nslug: t\nauthors: [X]\nchapters:\n  - slug: one\n    title: One\n"
        "    sections: [s, problems]\n")
    (book / "chapters" / "one" / "s.md").write_text(
        "---\ntitle: S\n---\n\n::: {.definition #def:a}\nA thing.\n:::\n\n"
        "::: {.example #ex:a}\nAn example.\n:::\n\n::: {.infobox #box:a title=\"Note\"}\nNoted.\n:::\n")
    (book / "chapters" / "one" / "problems.md").write_text(
        "---\ntitle: Problems\n---\n\n::: {.exercise #exe:one}\nDo it.\n:::\n")
    pdf = build_pdf(book, output_pdf=tmp_path / "b.pdf")
    text = " ".join(p.extract_text() for p in pypdf.PdfReader(str(pdf)).pages)
    for words in ("Definition 1.1", "Example 1.1", "Box 1.1", "Problem 1.1"):
        assert words in " ".join(text.split()), words
