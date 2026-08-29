"""A section can be authored and numbered but not yet released.

The chapter is not always the right unit: a chapter can be finished but for one
section, and a chapter still in development can hold one section that is ready
and wanted. `draft:` in a section's front matter says so; absent, the section
inherits its chapter.

See docs/superpowers/specs/2026-08-29-section-level-drafts-design.md (parody-web).
"""
import pytest
import yaml

from parody.build import build_project
from parody.writers.artifact import resolve_section_draft
from parody.writers.latex import build_pdf


def _book(tmp_path, chapter_drafts=(), section_drafts=None):
    """A two-chapter book, two sections each.

    `chapter_drafts` names chapters marked draft in parody.yaml;
    `section_drafts` maps "<ch>/<sec>" to the explicit front-matter value.
    """
    section_drafts = section_drafts or {}
    root = tmp_path / "bk"
    layout = {"one": ("one-a", "one-b"), "two": ("two-a", "two-b")}
    for ch, secs in layout.items():
        (root / "chapters" / ch).mkdir(parents=True)
        for sec in secs:
            fm = {"title": sec.replace("-", " ").title(), "slug": sec}
            declared = section_drafts.get(f"{ch}/{sec}")
            if declared is not None:
                fm["draft"] = declared
            (root / "chapters" / ch / f"{sec}.md").write_text(
                "---\n" + yaml.safe_dump(fm, sort_keys=False) + "---\n\n"
                f"Prose in {sec}.\n")
    chapters = []
    for ch, secs in layout.items():
        entry = {"slug": ch, "title": ch.title(), "sections": list(secs)}
        if ch in chapter_drafts:
            entry["draft"] = True
        chapters.append(entry)
    (root / "parody.yaml").write_text(yaml.safe_dump({
        "title": "Bk", "slug": "bk", "authors": ["A. Author"], "schema": 2,
        "chapters": chapters,
    }, sort_keys=False))
    return root


def _sections(art, chapter):
    ch = next(c for c in art["chapters"] if c["slug"] == chapter)
    return {s["slug"]: s for s in ch["sections"]}


def test_resolve_is_the_one_rule():
    """Absent inherits; declared overrides, in both directions."""
    assert resolve_section_draft(None, False) is False
    assert resolve_section_draft(None, True) is True
    assert resolve_section_draft(True, False) is True    # hide out of a release
    assert resolve_section_draft(False, True) is False   # publish out of a draft


def test_a_declared_draft_section_is_marked(tmp_path):
    root = _book(tmp_path, section_drafts={"one/one-b": True})
    art = build_project(root, tmp_path / "bk.json", convert_jupytext=False)
    secs = _sections(art, "one")
    assert secs["one-b"]["draft"] is True
    # Absent rather than False, so a book that marks nothing draft produces a
    # byte-identical artifact and an older consumer meets no key it cannot read.
    assert "draft" not in secs["one-a"]


def test_sections_inherit_a_draft_chapter(tmp_path):
    root = _book(tmp_path, chapter_drafts=("two",))
    art = build_project(root, tmp_path / "bk.json", convert_jupytext=False)
    assert all(s["draft"] is True for s in _sections(art, "two").values())
    assert all("draft" not in s for s in _sections(art, "one").values())


def test_a_draft_chapter_says_so_on_every_one_of_its_sections(tmp_path):
    """Never silently — see the comment in build_project. An artifact built
    before this feature marks the chapter and says nothing about its sections,
    so the importer must be able to tell the two apart."""
    root = _book(tmp_path, chapter_drafts=("two",),
                 section_drafts={"two/two-a": False})
    art = build_project(root, tmp_path / "bk.json", convert_jupytext=False)
    assert all("draft" in s for s in _sections(art, "two").values())
    # A released chapter still says nothing about its released sections.
    assert all("draft" not in s for s in _sections(art, "one").values())


def test_a_published_section_survives_a_draft_chapter(tmp_path):
    """The override that makes the feature worth having: one ready section
    released out of a chapter still in development."""
    root = _book(tmp_path, chapter_drafts=("two",),
                 section_drafts={"two/two-a": False})
    art = build_project(root, tmp_path / "bk.json", convert_jupytext=False)
    secs = _sections(art, "two")
    # Explicitly false, not absent: inside a draft chapter, silence is what an
    # artifact built before 0.55.0 says about EVERY section, and a consumer
    # reading that as "released" would publish the whole unreleased chapter.
    assert secs["two-a"]["draft"] is False
    assert secs["two-b"]["draft"] is True
    # The chapter keeps its own flag: it still drives the staff badge and
    # print's whole-chapter skip.
    ch = next(c for c in art["chapters"] if c["slug"] == "two")
    assert ch["draft"] is True


def test_a_draft_section_does_not_renumber_the_book(tmp_path):
    """The regression that would silently break every cross-reference: every
    section is present, in order, whether or not it is a draft."""
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir()
    b.mkdir()
    orders = []
    for base, drafts in ((a, {}), (b, {"one/one-a": True, "two/two-b": True})):
        art = build_project(_book(base, section_drafts=drafts),
                            base / "bk.json", convert_jupytext=False)
        orders.append([(c["slug"], [s["slug"] for s in c["sections"]])
                       for c in art["chapters"]])
    assert orders[0] == orders[1]


@pytest.fixture
def no_tex(monkeypatch):
    """build_pdf writes the whole LaTeX tree before it calls latexmk, so the
    wiring is checkable by reading the generated sources with no TeX at all."""
    monkeypatch.setattr("parody.writers.latex.shutil.which", lambda *a, **k: None)


def test_print_omits_a_draft_section_but_keeps_its_number(tmp_path, no_tex):
    root = _book(tmp_path, section_drafts={"one/one-a": True})
    build_pdf(root)
    build = root / "build" / "print"
    main = (build / "main.tex").read_text()

    assert "\\chapter{One}" in main                        # the chapter prints
    assert "\\input{sections/one/one-b.tex}" in main
    assert "\\input{sections/one/one-a.tex}" not in main   # the draft does not
    assert not (build / "sections" / "one" / "one-a.tex").exists()
    assert "\\stepcounter{section}" in main                # but takes its number


def test_a_chapter_of_only_drafts_behaves_like_a_draft_chapter(tmp_path, no_tex):
    root = _book(tmp_path, section_drafts={"two/two-a": True, "two/two-b": True})
    build_pdf(root)
    main = (root / "build" / "print" / "main.tex").read_text()
    assert "\\chapter{Two}" not in main       # no heading
    assert "\\label{two}" not in main         # no label
    assert "\\stepcounter{chapter}" in main   # but it consumes its number


def test_a_published_section_prints_out_of_a_draft_chapter(tmp_path, no_tex):
    root = _book(tmp_path, chapter_drafts=("two",),
                 section_drafts={"two/two-a": False})
    build_pdf(root)
    main = (root / "build" / "print" / "main.tex").read_text()
    assert "\\chapter{Two}" in main
    assert "\\input{sections/two/two-a.tex}" in main
    assert "\\input{sections/two/two-b.tex}" not in main


def test_print_without_drafts_is_unchanged(tmp_path, no_tex):
    root = _book(tmp_path)
    build_pdf(root)
    main = (root / "build" / "print" / "main.tex").read_text()
    assert "\\stepcounter{section}" not in main
    assert "\\stepcounter{chapter}" not in main


def test_the_counter_steps_only_for_a_section_that_would_have_a_heading():
    r"""\stepcounter in place of a section that never emitted a \section would
    hand it a number it never had — synthesize_section_heading leaves a lead-in
    and a titleless, heading-less section alone."""
    from parody.writers.latex import section_prints_a_heading
    assert section_prints_a_heading("lead-in", {"title": "Intro"}, "text") is False
    assert section_prints_a_heading("s", {"title": "T"}, "text") is True
    assert section_prints_a_heading("s", {}, "text") is False
    assert section_prints_a_heading("s", {}, "# Own heading\n\ntext") is True
    assert section_prints_a_heading("s", {}, "## Own subheading\n\ntext") is True
    assert section_prints_a_heading("s", {}, "### Deeper only\n\ntext") is False


def test_a_draft_section_has_no_print_page_range(tmp_path, no_tex):
    """Which is what makes section_pdf 404 on the web without its own gate."""
    root = _book(tmp_path, section_drafts={"one/one-a": True})
    build_pdf(root, pagemap=True)
    main = (root / "build" / "print" / "main.tex").read_text()
    assert "\\parodypagemark{one/one-b}" in main
    assert "\\parodypagemark{one/one-a}" not in main
