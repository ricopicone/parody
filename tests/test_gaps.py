"""Source gap scan: code fences, display equations, callout boxes."""

from parody.gaps import (
    _numbered_eq_by_section,
    format_gaps,
    reference_listings,
    scan,
    triage_listings,
)


def _write(root, rel, text):
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def test_scan_flags_code_and_math(tmp_path):
    _write(tmp_path, "chapters/ch1/a.md", (
        "Intro.\n\n"
        "```c\nint x = 1;\n```\n\n"
        "A display equation:\n\n"
        "$$ y = m x + b $$\n\n"
        "```python\nprint('hi')\n```\n"
    ))
    rep = scan(tmp_path)
    assert len(rep.code_fences) == 2
    langs = sorted(h.detail for h in rep.code_fences)
    assert langs == ["c", "python"]
    assert len(rep.display_math) == 1
    out = format_gaps(rep)
    assert "plain code blocks" in out and "display equations" in out


def test_scan_skips_math_inside_code_and_counts_boxes(tmp_path):
    _write(tmp_path, "chapters/ch1/b.md", (
        "::: {#x .infobox}\nA note.\n:::\n\n"
        "```text\nnot math: $$ ignore $$\n```\n\n"
        "\\freadinglist{a, b}\n"
    ))
    rep = scan(tmp_path)
    # the $$ inside the fenced code block must not be counted as display math
    assert rep.display_math == []
    assert len(rep.infoboxes) == 1
    assert len(rep.freading) == 1
    # the code block itself is still a listing candidate
    assert len(rep.code_fences) == 1


def test_scan_uses_project_root_without_chapters(tmp_path):
    _write(tmp_path, "loose.md", "```\ncode\n```\n")
    rep = scan(tmp_path)
    assert len(rep.code_fences) == 1


REF_TEXT = (
    "Some prose mentioning the program.\n"
    "Listing 0.1 The sandbox program.\n"
    "int sandbox_cube(int n) { return n*n*n; }\n"
    "printf(\"cube\");\n"
    "\n"
    "Figure 0.2 Something else.\n"
    "and later see Listing 0.1 again for a cross-reference.\n"
)


def test_reference_listings_parses_caption_and_code():
    listings = reference_listings(REF_TEXT)
    assert len(listings) == 1  # the cross-reference mention is not a caption
    num, cap, code = listings[0]
    assert num == "0.1" and cap == "The sandbox program."
    assert "sandbox_cube" in code
    assert "Something else" not in code  # stops at the next labelled object


def test_triage_matches_source_block_by_code_overlap(tmp_path):
    _write(tmp_path, "chapters/ch0/s.md",
           "```c\nint sandbox_cube(int n) { return n*n*n; }\nprintf(\"cube\");\n```\n\n"
           "```c\nint unrelated_widget(void) { return 0; }\n```\n")
    rep = scan(tmp_path)
    matches = triage_listings(rep, REF_TEXT)
    assert len(matches) == 1
    m = matches[0]
    assert m.number == "0.1"
    assert m.path.endswith("ch0/s.md")
    assert m.line == 1               # the sandbox block, not the widget one
    assert m.score > 0.3


def test_numbered_eq_by_section():
    text = "eq (1.1) and (1.2) then chapter four (4.5), (4.6), (4.7)."
    assert _numbered_eq_by_section(text) == {"1": 2, "4": 3}
