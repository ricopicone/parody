"""Translating a whole book, and keeping it current (task #825).

The engine here is a fake that "translates" by rewriting a few known words,
so maths and markup survive and the preservation check passes, unless a
test tells it to break something.
"""

import re

import pytest

from parody.config import ProjectLayoutError, load_project
from parody.translate.chunks import chunk_hash, split_chunks, split_frontmatter
from parody.translate.engines import EngineError
from parody.translate.run import project_status, translate_project
from parody.translate.store import TranslationFile, glossary_path, load_glossary, translation_path

_MARKER = re.compile(r"^<<<chunk (\d+)>>>[ \t]*$", re.M)


def _english_of(user):
    section = user.split("<english-section>\n", 1)[1].split("\n</english-section>", 1)[0]
    pieces = _MARKER.split(section)
    return {int(pieces[k]): pieces[k + 1].strip("\n") for k in range(1, len(pieces), 2)}


def _todo_of(user):
    line = user.strip().rsplit("\n", 1)[-1]
    return [int(x) for x in line.split(":", 1)[1].split(",")]


def german(text):
    # Translates prose and a key term's text, never its en="…" attribute.
    return text.replace("alpha", "Alpha-DE").replace("[voltage divider]", "[Spannungsteiler]")


class FakeEngine:
    name = "fake"
    model = "fake-1"

    def __init__(self, transform=None, responses=None, raise_on_call=None):
        self.transform = transform or (lambda i, text: german(text))
        self.responses = list(responses or [])
        self.raise_on_call = raise_on_call or {}
        self.calls = []

    def complete(self, system, user):
        self.calls.append((system, user))
        n = len(self.calls)
        if n in self.raise_on_call:
            raise self.raise_on_call[n]
        if self.responses:
            return self.responses.pop(0)
        english, todo = _english_of(user), _todo_of(user)
        return "\n".join(f"<<<chunk {i}>>>\n{self.transform(i, english[i])}" for i in todo)


ONE = """---
title: One alpha
---

# One alpha {#sec:one}

The [voltage divider]{.keyword} splits alpha $v_\\text{in}$.

Paragraph alpha two with a blank: [divided]{.cloze}.

Paragraph alpha three, $$x = \\frac{a}{b}$$ done.

Paragraph alpha four.
"""

TWO = """---
title: Two
---

Alpha section two mentions the voltage divider again, $y$.
"""


def _book(tmp_path, one=ONE, two=TWO, extra_yaml="", draft_chapter=None):
    chapters = "chapters:\n- slug: ch\n  title: Ch\n  sections: [one, two]\n"
    if draft_chapter:
        chapters += ("- slug: dr\n  title: Draft\n  draft: true\n  sections: [three]\n")
        (tmp_path / "chapters" / "dr").mkdir(parents=True)
        (tmp_path / "chapters" / "dr" / "three.md").write_text(draft_chapter)
    (tmp_path / "parody.yaml").write_text(
        "title: T\nslug: t\n" + chapters
        + "translations:\n  languages: [de]\n" + extra_yaml)
    (tmp_path / "chapters" / "ch").mkdir(parents=True, exist_ok=True)
    (tmp_path / "chapters" / "ch" / "one.md").write_text(one)
    (tmp_path / "chapters" / "ch" / "two.md").write_text(two)
    return tmp_path


def _run(book, engine, **kw):
    return translate_project(load_project(book), engine, today="2026-10-17",
                             log=lambda *a: None, **kw)


def _file(book, sec="one"):
    return TranslationFile.read(translation_path(book, "de", "ch", sec))


def _body_chunks(text):
    return split_chunks(split_frontmatter(text)[1])


def test_first_run_translates_everything_and_writes_file(tmp_path):
    book = _book(tmp_path)
    states = _run(book, FakeEngine())
    assert {s.state for s in states} == {"translated"}
    f = _file(book)
    assert f.title == "One Alpha-DE" and f.title_hash == chunk_hash("One alpha")
    assert [h for h, _ in f.chunks] == [chunk_hash(c) for c in _body_chunks(ONE)]
    assert "Paragraph Alpha-DE two" in f.chunks[2][1]
    assert f.engine == "fake" and f.model == "fake-1" and f.updated == "2026-10-17"
    assert f.source == "chapters/ch/one.md"


def test_second_run_makes_no_engine_calls(tmp_path):
    book = _book(tmp_path)
    _run(book, FakeEngine())
    engine = FakeEngine()
    states = _run(book, engine)
    assert engine.calls == []
    assert {s.state for s in states} == {"current"}


def test_mid_section_edit_sends_only_changed_chunks(tmp_path):
    book = _book(tmp_path)
    _run(book, FakeEngine())
    before = dict(_file(book).chunks)
    edited = (ONE.replace("Paragraph alpha two with a blank: [divided]{.cloze}.",
                          "A new alpha paragraph.\n\nParagraph alpha two with a blank: [divided]{.cloze}.")
                 .replace("Paragraph alpha three,", "Paragraph alpha three, edited,")
                 .replace("\nParagraph alpha four.\n", "\n"))
    (book / "chapters" / "ch" / "one.md").write_text(edited)
    engine = FakeEngine()
    _run(book, engine, sections=["ch/one"])
    assert len(engine.calls) == 1
    english = _body_chunks(edited)
    new_i = 1 + english.index("A new alpha paragraph.")
    edit_i = 1 + next(k for k, c in enumerate(english) if "edited" in c)
    assert _todo_of(engine.calls[0][1]) == [new_i, edit_i]
    after = _file(book)
    assert [h for h, _ in after.chunks] == [chunk_hash(c) for c in english]
    for h, text in after.chunks:
        if h in before:
            assert text == before[h]  # byte-identical
    assert not any("four" in t for _, t in after.chunks)


def test_draft_sections_are_skipped(tmp_path):
    one_draft = ONE.replace("title: One alpha", "title: One alpha\ndraft: true")
    released_in_draft = "---\ntitle: Three\ndraft: false\n---\n\nAlpha three.\n"
    book = _book(tmp_path, one=one_draft, draft_chapter=released_in_draft)
    states = {(s.chapter, s.section): s.state for s in _run(book, FakeEngine())}
    assert states[("ch", "one")] == "draft"
    assert states[("dr", "three")] == "translated"
    assert not translation_path(book, "de", "ch", "one").exists()


def test_section_in_draft_chapter_inherits_draft(tmp_path):
    book = _book(tmp_path, draft_chapter="---\ntitle: Three\n---\n\nAlpha.\n")
    states = {(s.chapter, s.section): s.state for s in _run(book, FakeEngine())}
    assert states[("dr", "three")] == "draft"


def _drop_maths_in(target):
    def transform(i, text):
        return german(text).replace("$", "") if i == target else german(text)
    return transform


def test_failing_chunk_is_retried_then_not_written(tmp_path):
    book = _book(tmp_path)
    engine = FakeEngine(transform=_drop_maths_in(2))
    states = {s.section: s for s in _run(book, engine, sections=["ch/one"])}
    assert len(engine.calls) == 3  # first try + 2 retries
    assert "Problems with your previous attempt:" in engine.calls[1][1]
    assert _todo_of(engine.calls[1][1]) == [2]
    assert states["one"].state == "partial"
    assert any("maths" in p for p in states["one"].problems)
    hashes = [h for h, _ in _file(book).chunks]
    assert chunk_hash(_body_chunks(ONE)[1]) not in hashes
    assert len(hashes) == len(_body_chunks(ONE)) - 1


def test_failing_stale_chunk_keeps_old_translation(tmp_path):
    book = _book(tmp_path)
    _run(book, FakeEngine())
    old = _file(book).chunks[1]
    (book / "chapters" / "ch" / "one.md").write_text(
        ONE.replace("splits alpha", "splits up alpha"))
    states = {s.section: s for s in _run(book, FakeEngine(transform=_drop_maths_in(2)),
                                         sections=["ch/one"])}
    assert states["one"].state == "failed"
    assert _file(book).chunks[1] == old


def test_malformed_response_is_retried(tmp_path):
    book = _book(tmp_path, two="---\ntitle: Two\n---\n\nAlpha.\n")
    engine = FakeEngine(responses=["Sure! Here you go:\n<<<chunk 0>>>\nZwei\n<<<chunk 1>>>\nAlpha-DE."])
    states = {s.section: s for s in _run(book, engine, sections=["ch/two"])}
    assert len(engine.calls) == 2
    assert states["two"].state == "translated"


def test_engine_error_stops_the_run(tmp_path):
    # A usage limit is not a bad translation: don't retry it, don't tell the
    # model about it, and don't march on through every other section.
    book = _book(tmp_path)
    engine = FakeEngine(raise_on_call={1: EngineError("Usage limit reached")})
    states = _run(book, engine)
    assert len(engine.calls) == 1
    assert [(s.section, s.state) for s in states] == [("one", "stopped")]
    assert "Usage limit reached" in states[0].problems[0]


def test_engine_error_in_one_language_stops_the_others(tmp_path):
    import threading
    book = _book(tmp_path, extra_yaml="")
    (book / "parody.yaml").write_text((book / "parody.yaml").read_text().replace(
        "languages: [de]", "languages: [de, zh]"))
    failed = threading.Event()

    class Engine(FakeEngine):
        def complete(self, system, user):
            if "Simplified Chinese" in system:
                failed.set()
                raise EngineError("Usage limit reached")
            failed.wait(5)
            return super().complete(system, user)

    engine = Engine()
    states = _run(book, engine, jobs=2)
    german = [s for s in states if s.language == "de" and s.state == "translated"]
    assert len(german) <= 1  # the section in flight may finish; no new ones start


def test_unknown_section_is_an_error(tmp_path):
    with pytest.raises(ProjectLayoutError, match="ch/onee"):
        _run(_book(tmp_path), FakeEngine(), sections=["ch/onee"])


def test_relabelled_footnote_is_not_written(tmp_path):
    one = ONE.replace("Paragraph alpha four.", "Paragraph alpha four.[^n]\n\n[^n]: A note, alpha.")
    book = _book(tmp_path, one=one)
    english = _body_chunks(one)
    k = next(i for i, c in enumerate(english) if c.startswith("[^n]:"))
    engine = FakeEngine(transform=lambda i, t: german(t).replace("[^n]:", "[^m]:"))
    states = {s.section: s for s in _run(book, engine, sections=["ch/one"])}
    assert states["one"].state == "partial"
    assert chunk_hash(english[k]) not in [h for h, _ in _file(book).chunks]


def test_interrupted_run_resumes(tmp_path):
    book = _book(tmp_path)
    with pytest.raises(KeyboardInterrupt):
        _run(book, FakeEngine(raise_on_call={2: KeyboardInterrupt()}))
    assert translation_path(book, "de", "ch", "one").exists()
    assert not translation_path(book, "de", "ch", "two").exists()
    engine = FakeEngine()
    _run(book, engine)
    assert len(engine.calls) == 1 and "Alpha section two" in engine.calls[0][1]


def test_reordered_key_terms_gloss_and_glossary(tmp_path):
    two = "---\ntitle: Two\n---\n\nThe [voltage]{.keyword} and the [current]{.keyword}.\n"
    book = _book(tmp_path, two=two)

    def swap(i, text):  # a translator that puts the two terms the other way round
        m = re.findall(r"\[(\w+)\]\{([^}]*)\}", text)
        if len(m) == 2:
            (a, aa), (b, ba) = m
            return f"Der [{b.upper()}]{{{ba}}} und die [{a.upper()}]{{{aa}}}."
        return text

    _run(book, FakeEngine(transform=swap), sections=["ch/two"])
    body = _file(book, "two").chunks[0][1]
    assert '[CURRENT]{.keyword en="current"}' in body
    assert '[VOLTAGE]{.keyword en="voltage"}' in body
    assert load_glossary(glossary_path(book, "de")) == {"current": "CURRENT", "voltage": "VOLTAGE"}


def test_keyword_gloss_and_glossary(tmp_path):
    book = _book(tmp_path)
    engine = FakeEngine()
    _run(book, engine)
    assert '[Spannungsteiler]{.keyword en="voltage divider"}' in _file(book).chunks[1][1]
    assert load_glossary(glossary_path(book, "de")) == {"voltage divider": "Spannungsteiler"}
    # Section two mentions the term, so its prompt carries the glossary entry.
    assert "- voltage divider → Spannungsteiler" in engine.calls[1][0]
    assert "voltage divider →" not in engine.calls[0][0]


def test_status_reports_without_an_engine(tmp_path):
    book = _book(tmp_path)
    _run(book, FakeEngine(), sections=["ch/one"])
    (book / "chapters" / "ch" / "one.md").write_text(ONE.replace("four", "4"))
    got = {s.section: s for s in project_status(load_project(book))}
    assert got["one"].state == "stale" and got["one"].todo == 1
    assert got["two"].state == "missing" and got["two"].todo == 2


def test_book_without_translations_key_is_refused(tmp_path):
    book = _book(tmp_path)
    (book / "parody.yaml").write_text("title: T\nslug: t\nchapters: []\n")
    with pytest.raises(ProjectLayoutError, match="translations"):
        _run(book, FakeEngine())


def test_editions_book_is_refused(tmp_path):
    book = _book(tmp_path, extra_yaml="editions:\n- id: ed1\n")
    with pytest.raises(ProjectLayoutError, match="edition"):
        _run(book, FakeEngine())


# --- the command -------------------------------------------------------------

from parody.cli import main  # noqa: E402


def _no_engine(config):
    raise AssertionError("--status must not build an engine")


def test_cli_status_needs_no_engine(tmp_path, monkeypatch, capsys):
    import parody.translate.engines as engines
    monkeypatch.setattr(engines, "make_engine", _no_engine)
    book = _book(tmp_path)
    assert main(["translate", str(book), "--status"]) == 0
    out = capsys.readouterr().out
    assert "de" in out and "missing" in out and "ch/one" in out


def test_cli_without_key_errors(tmp_path, capsys):
    (tmp_path / "parody.yaml").write_text("title: T\nslug: t\nchapters: []\n")
    assert main(["translate", str(tmp_path)]) == 1
    assert "no translations: key" in capsys.readouterr().err


def test_cli_translate_uses_engine(tmp_path, monkeypatch, capsys):
    import parody.translate.engines as engines
    monkeypatch.setattr(engines, "make_engine", lambda config: FakeEngine())
    book = _book(tmp_path)
    assert main(["translate", str(book), "--section", "ch/two"]) == 0
    assert translation_path(book, "de", "ch", "two").exists()
    assert not translation_path(book, "de", "ch", "one").exists()
    assert "✓ de ch/two" in capsys.readouterr().out


def test_cli_exit_code_on_failure(tmp_path, monkeypatch):
    import parody.translate.engines as engines
    monkeypatch.setattr(engines, "make_engine",
                        lambda config: FakeEngine(transform=lambda i, t: t.replace("$", "")))
    assert main(["translate", str(_book(tmp_path)), "--section", "ch/two"]) == 1


def test_cli_rejects_unknown_language(tmp_path, capsys):
    assert main(["translate", str(_book(tmp_path)), "--lang", "xx", "--status"]) == 1
    assert "xx" in capsys.readouterr().err


def test_cli_exit_code_when_the_engine_stops(tmp_path, monkeypatch, capsys):
    import parody.translate.engines as engines
    monkeypatch.setattr(engines, "make_engine", lambda config: FakeEngine(
        raise_on_call={1: EngineError("Usage limit reached")}))
    assert main(["translate", str(_book(tmp_path))]) == 1
    assert "re-run later" in capsys.readouterr().out
