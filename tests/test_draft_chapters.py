"""A chapter can be authored and numbered but not yet released.

The Robotics book rolls out to a class chapter by chapter over a semester.
Dropping unready chapters from parody.yaml would renumber the book on every
release, so a cross-reference or a number spoken in class silently means
something different the following week. `draft: true` keeps the number and
withholds the content.
"""
import yaml

from parody.build import build_project
from parody.config import load_project


def _book(tmp_path, drafts=()):
    """A three-chapter book; `drafts` names the chapters marked draft."""
    root = tmp_path / "bk"
    names = ("one", "two", "three")
    for ch in names:
        (root / "chapters" / ch).mkdir(parents=True)
        (root / "chapters" / ch / f"{ch}-a.md").write_text(
            f"---\ntitle: {ch.title()} A\nslug: {ch}-a\n---\n\nProse in {ch}.\n")
    chapters = []
    for ch in names:
        entry = {"slug": ch, "title": ch.title(), "sections": [f"{ch}-a"]}
        if ch in drafts:
            entry["draft"] = True
        chapters.append(entry)
    (root / "parody.yaml").write_text(yaml.safe_dump({
        "title": "Bk", "slug": "bk", "authors": ["A. Author"], "schema": 2,
        "chapters": chapters,
    }, sort_keys=False))
    return root


def test_config_parses_draft(tmp_path):
    project = load_project(_book(tmp_path, drafts=("two",)))
    by = {c.slug: c for c in project.chapters}
    assert by["one"].draft is False
    assert by["two"].draft is True
    assert by["three"].draft is False


def test_artifact_carries_draft(tmp_path):
    root = _book(tmp_path, drafts=("two",))
    art = build_project(root, tmp_path / "bk.json", convert_jupytext=False)
    by = {c["slug"]: c for c in art["chapters"]}
    assert by["two"]["draft"] is True
    # Absent rather than False: a consumer built before this feature must not
    # meet a key it does not know, and the artifact stays diff-clean for books
    # that use no drafts at all.
    assert "draft" not in by["one"]


def test_draft_does_not_change_the_numbering_of_other_chapters(tmp_path):
    """The regression that would silently break every cross-reference in the
    book: chapter three must be chapter three whether or not two is a draft."""
    plain = tmp_path / "a"
    drafted = tmp_path / "b"
    plain.mkdir()
    drafted.mkdir()
    outs = []
    for base, drafts in ((plain, ()), (drafted, ("two",))):
        root = _book(base, drafts=drafts)
        art = build_project(root, base / "bk.json", convert_jupytext=False)
        outs.append([c["slug"] for c in art["chapters"]])
    assert outs[0] == outs[1] == ["one", "two", "three"]
