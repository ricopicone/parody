"""Source gap scan: code fences, display equations, callout boxes."""

from parody.gaps import format_gaps, scan


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
