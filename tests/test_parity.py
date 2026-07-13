"""Parity module: heading detection, section splitting, similarity, counts."""

from parody.parity import (
    ParityReport,
    SectionDiff,
    _looks_like_title,
    format_report,
    similarity,
    split_sections,
    structural_counts,
)


def test_split_sections_at_numbered_headings():
    text = (
        "intro before any heading\n"
        "3.7 The root locus\n"
        "body of 3.7\n"
        "L2.1 Introduction\n"
        "lab body\n"
    )
    secs = split_sections(text)
    assert [(s.number, s.title) for s in secs] == [
        ("", "(front matter)"),
        ("3.7", "The root locus"),
        ("L2.1", "Introduction"),
    ]
    assert "body of 3.7" in secs[1].body


def test_heading_heuristic_rejects_body_noise():
    # real titles carry a lowercase letter and don't end in sentence punctuation
    assert _looks_like_title("The root locus")
    assert _looks_like_title("Summary")
    assert not _looks_like_title("F0 20 E3")        # hex dump row (no lowercase)
    assert not _looks_like_title("V/us.")           # a value ending in a period
    assert not _looks_like_title("Qact: (cc/s) 453.")  # a table row ending in a period
    # a table row that starts like a heading must not split a section
    secs = split_sections("2.1 Sampling\nrow\n00 F0 20 E3\nmore\n")
    assert [s.title for s in secs] == ["(front matter)", "Sampling"]
    assert "00 F0 20 E3" in secs[1].body


def test_lab_headers_are_detected():
    text = "1.10 Something\nbody\nLab Exercise 1: Programming the High-Level UI\nlab body\n"
    secs = split_sections(text)
    titles = {s.number: s.title for s in secs}
    assert titles["1.10"] == "Something"
    assert titles["lab1"] == "Programming the High-Level UI"


def test_page_tracking_across_form_feeds():
    # pdftotext separates pages with a form feed; headings get the right page
    text = "front\n1.1 First\nbody\x0cmore\n1.2 Second\nbody two\n"
    secs = split_sections(text)
    pages = {s.title: s.page for s in secs}
    assert pages["First"] == 1
    assert pages["Second"] == 2


def test_page_diff_identical_vs_different():
    from PIL import Image
    from parody.parity import _page_diff
    white = Image.new("L", (200, 260), 255)
    black = Image.new("L", (200, 260), 0)
    half = Image.new("L", (200, 260), 128)
    assert _page_diff(white, white) == 0.0
    assert _page_diff(white, black) > 0.99
    assert 0.4 < _page_diff(white, half) < 0.6


def test_similarity_bounds():
    assert similarity("the quick brown fox", "the quick brown fox") == 1.0
    assert similarity("", "") == 1.0
    assert similarity("anything", "") == 0.0
    assert 0.0 < similarity("a b c d e", "a b x d e") < 1.0


def test_structural_counts_are_mentions():
    text = "see Figure 3.2 and Table 1.1; Problem 4.5; Problem L2.1; eq (6.3)."
    c = structural_counts(text)
    assert c["figure"] == 1 and c["table"] == 1
    assert c["problem"] == 2  # numeric and lab-numbered both counted
    assert c["equation"] == 1


def test_format_report_smoke():
    r = ParityReport(
        reference="orig.pdf", candidate="cand.pdf",
        ref_pages=503, cand_pages=492,
        ref_counts=structural_counts("Figure 1.1"),
        cand_counts=structural_counts("Figure 1.1 Figure 1.2"),
        sections=[
            SectionDiff("1.1", "Intro", "matched", 0.95),
            SectionDiff("1.2", "Deep dive", "matched", 0.40),
            SectionDiff("1.3", "Gone", "missing"),
        ],
    )
    out = format_report(r, low=0.90)
    assert "reference   503" in out and "candidate   492" in out
    assert "Deep dive" in out          # low-similarity section is listed
    assert "Gone" in out               # missing section is listed
    assert 60.0 < r.mean_similarity * 100 < 70.0  # (0.95 + 0.40) / 2
