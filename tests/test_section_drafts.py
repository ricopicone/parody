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


def test_a_published_section_survives_a_draft_chapter(tmp_path):
    """The override that makes the feature worth having: one ready section
    released out of a chapter still in development."""
    root = _book(tmp_path, chapter_drafts=("two",),
                 section_drafts={"two/two-a": False})
    art = build_project(root, tmp_path / "bk.json", convert_jupytext=False)
    secs = _sections(art, "two")
    assert "draft" not in secs["two-a"]
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
