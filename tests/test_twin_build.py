"""Composing the twin pages and building the twin PDF (task #825)."""

from pathlib import Path

import pytest

from parody.translate.chunks import chunk_hash, split_chunks, split_frontmatter
from parody.translate.store import TranslationFile, translation_path
from parody.twin.build import (TwinReport, _page_tex, base_scale, build_twin, log_errors,
                               mark_errors, pdf_pages, reference_problems,
                               parse_twinfit, restore_code, section_ranges, twin_errors,
                               write_twin_sidecar)
from parody.twin.compose import SectionSource, align_translation, page_markdown
from parody.twin.paginate import Piece, TwinPage
from parody.writers.latex import have_tool

needs_tex = pytest.mark.skipif(not (have_tool("latexmk") and have_tool("lualatex")),
                               reason="needs TeX")


def V(section, chunk, sentence=0):
    return section * 1_000_000 + (chunk + 1) * 1000 + sentence


def _section(chunks, index=1):
    return SectionSource(index=index, key="ch/s", chapter=None, slug="s", source=Path("s.md"),
                         meta={"title": "S"}, chunks=chunks, title="S")


def _tf(en_chunks, translate, title="S-de"):
    return TranslationFile(language="de", source="chapters/ch/s.md", title=title,
                           title_hash=chunk_hash("S"),
                           chunks=[(chunk_hash(c), translate(c)) for c in en_chunks])


EN = ["# S {#sec:s}", "One alpha. Two alpha. Three alpha.", "::: {#def:x .definition}\nDef one. Def two.\n:::",
      "Has a note.[^1]", "[^1]: The note alpha."]


def test_align_translation_states():
    tf = _tf(EN[:3] + EN[4:], lambda c: c.replace("alpha", "Alpha-DE"))  # chunk 3 missing
    tr = align_translation(_section(EN), tf)
    assert tr.states == ["current", "current", "current", "missing", "current"]
    assert tr.texts[1] == "One Alpha-DE. Two Alpha-DE. Three Alpha-DE."


def test_page_markdown_whole_and_split_chunks():
    tr = align_translation(_section(EN), _tf(EN, lambda c: c.replace("alpha", "Alpha-DE")))
    page = TwinPage(5, 1, pieces=[Piece(1, 0, 0, None), Piece(1, 1, 0, 2)])
    groups, notes = page_markdown(page, {1: _section(EN)}, {1: tr}, "de", {})
    (index, md), = groups
    assert index == 1
    assert "# S {#sec:s}" in md and "One Alpha-DE. Two Alpha-DE." in md
    assert "Three" not in md
    assert "[^1]: The note Alpha-DE." in md  # footnote definitions always come along
    assert notes == []


def test_page_markdown_untranslated_uses_english_with_marker():
    tr = align_translation(_section(EN), None)
    groups, notes = page_markdown(TwinPage(5, 1, pieces=[Piece(1, 1, 0, None)]),
                                  {1: _section(EN)}, {1: tr}, "de", {})
    assert "\\parodyuntranslated\n\nOne alpha. Two alpha." in groups[0][1]
    assert any("untranslated" in n for n in notes)


def test_page_markdown_stale_uses_old_translation():
    old = EN[:1] + ["One alpha. Two. Three alpha."] + EN[2:]
    tf = _tf(old, lambda c: c.replace("alpha", "Alpha-DE"))
    tr = align_translation(_section(EN), tf)
    groups, notes = page_markdown(TwinPage(5, 1, pieces=[Piece(1, 1, 0, None)]),
                                  {1: _section(EN)}, {1: tr}, "de", {})
    assert "\\parodystale\n\nOne Alpha-DE. Two. Three Alpha-DE." in groups[0][1]
    assert any("stale" in n for n in notes)


def test_a_stale_translation_whose_maths_or_labels_changed_sets_the_english():
    # the English renamed a label and corrected an equation since: the old
    # translation would print the old maths and leave the new label undefined,
    # which refused the whole language until someone re-translated
    en = ["Prose alpha.", "So $x = 2$ holds. {#eq:new}", "Refers to [@eq:new] alpha."]
    old = ["Prose alpha.", "So $x = 1$ holds. {#eq:old}", "Refers to [@eq:old] alpha."]
    typo = ["Prose alpah.", "So $x = 2$ holds. {#eq:new}", "Refers to [@eq:new] alpha."]
    tf = _tf(old, lambda c: c.replace("alpha", "Alpha-DE"))
    tr = align_translation(_section(en), tf)
    assert tr.states == ["current", "missing", "missing"]
    assert tr.texts[1:] == [None, None]
    # a prose edit keeps the older translation, marked as lagging
    tr = align_translation(_section(en), _tf(typo, lambda c: c.replace("alpah", "Alpha-DE")))
    assert tr.states == ["stale", "current", "current"]
    assert tr.texts[0] == "Prose Alpha-DE."


def test_an_untranslated_footnote_is_marked_and_counted():
    # a footnote added after the translation was set in English with no
    # marker, and the report did not count it
    tf = _tf(EN[:4], lambda c: c.replace("alpha", "Alpha-DE"))  # the definition is new
    tr = align_translation(_section(EN), tf)
    groups, notes = page_markdown(TwinPage(5, 1, pieces=[Piece(1, 3, 0, None)]),
                                  {1: _section(EN)}, {1: tr}, "de", {})
    assert "[^1]: \\parodyuntranslated The note alpha." in groups[0][1]
    assert "untranslated: ch/s chunk 4" in notes


def test_reopened_box_steps_its_counter_back():
    tr = align_translation(_section(EN), _tf(EN, lambda c: c))
    counters = {V(1, 2, 0): {"thmctr": 3, "equation": 1}, V(1, 2, 1): {"thmctr": 4, "equation": 1}}
    groups, _ = page_markdown(TwinPage(6, 2, pieces=[Piece(1, 2, 1, None)]),
                              {1: _section(EN)}, {1: tr}, "de", counters)
    md = groups[0][1]
    assert "\\addtocounter{thmctr}{-1}" in md
    assert md.index("\\addtocounter{thmctr}{-1}") < md.index("::: {.definition}")


def test_base_scale_is_10th_percentile():
    scales = [1.0] * 18 + [0.9, 0.8]
    assert base_scale(scales) == 0.9
    assert base_scale([1.0, 1.0]) == 1.0
    assert base_scale([0.93] * 10) == 0.93


def test_parse_twinfit():
    log = "x\nTWINFIT page=12 scale=0.91\nTWINFIT page=13 scale=1\n"
    assert parse_twinfit(log) == [(12, 0.91), (13, 1.0)]


def test_restore_code_skips_internal_counters():
    code = restore_code({"chapter": 1, "page": 7, "mpfootnote": 2, "tcb@cnt@x": 3, "thmctr": 4})
    assert code == "\\parodytwinset{chapter}{1}\\parodytwinset{thmctr}{4}"


def test_restore_code_restores_the_current_label():
    code = restore_code({"chapter": 1, "section": 2, "@currentlabel": "1.2"})
    assert code == "\\parodytwinset{chapter}{1}\\parodytwinset{section}{2}\\parodytwinlabel{1.2}"


def test_floats_on_a_twin_page_are_set_here():
    # a float inside the twin page's minipage is "Not in outer par mode"
    # (System Dynamics 1.4's captioned pipe tables); and here is where the
    # English put it, on the page this twin page twins
    from parody.twin.build import floats_here
    tex = ("\\begin{table}\n\\tabcaption{x}\n\\end{table}\n\\begin{figure}[htbp]\n\\end{figure}\n"
           "\\begin{table}[H]\n\\end{table}\n\\begin{figure*}\n\\end{figure*}\n\\begin{longtable}{l}\n")
    assert floats_here(tex) == (
        "\\begin{table}[H]\n\\tabcaption{x}\n\\end{table}\n\\begin{figure}[H]\n\\end{figure}\n"
        "\\begin{table}[H]\n\\end{table}\n\\begin{figure*}\n\\end{figure*}\n\\begin{longtable}{l}\n")


def test_float_units_are_the_marks_of_floats_latex_may_move():
    # the mark before a float and those in it go where LaTeX puts the float;
    # one set here does not move
    from parody.twin.build import float_units
    tex = ("\\parodys{1001000}\nText.\n\n\\parodys{1002000}\n\n\\begin{table}\n"
           "\\tabcaption{A \\parodys{1002001}caption.}\n\\end{table}\n\n"
           "\\parodys{1003000}\n\\begin{figure}[H]\nhere\n\\end{figure}\n"
           "\\parodys{1004000}\n\\begin{figure*}\nwide\n\\end{figure*}\n")
    assert float_units(tex) == {1002000, 1002001, 1004000}


def test_only_the_pages_the_twin_twins_must_match():
    # a twin of chapter 1 alone is not wrong because chapter 2's marked
    # English paginates differently (System Dynamics, Korean, chapter 1 only)
    from parody.twin.build import mismatches_that_matter
    assert mismatches_that_matter([89, 90, 103], [11, 12, 13]) == []
    assert mismatches_that_matter([12, 89], [11, 12, 13]) == [12]


YAML = """\
title: Twin Build
slug: twin-build
authors: [Tester]
chapters:
  - slug: one
    title: One
    sections: [first, second]
translations:
  languages: [de]
"""


def _para(n):
    return " ".join(f"Sentence number {i} of paragraph {n} says alpha things." for i in range(9))


def _write_tiny_book(tmp_path):
    book = tmp_path / "book"
    (book / "chapters" / "one").mkdir(parents=True)
    (book / "parody.yaml").write_text(YAML)
    first = "---\ntitle: First\n---\n\n# First {#sec:first}\n\n" + "\n\n".join(_para(i) for i in range(10)) + "\n"
    second = ("---\ntitle: Second\n---\n\n# Second {#sec:second}\n\n::: {#def:a .definition}\n"
              + _para(99) + "\n:::\n\n" + "\n\n".join(_para(i) for i in range(10, 16)) + "\n")
    (book / "chapters" / "one" / "first.md").write_text(first)
    (book / "chapters" / "one" / "second.md").write_text(second)
    for slug, text in (("first", first), ("second", second)):
        meta, body = split_frontmatter(text)
        chunks = split_chunks(body)
        TranslationFile(language="de", source=f"chapters/one/{slug}.md",
                        title=meta["title"] + " (de)", title_hash=chunk_hash(meta["title"]),
                        chunks=[(chunk_hash(c), c.replace("alpha", "Alpha-DE")) for c in chunks]
                        ).write(translation_path(book, "de", "one", slug))
    return book


@needs_tex
def test_build_twin_tiny_book(tmp_path):
    import pypdf
    book = _write_tiny_book(tmp_path)
    pdf, report = build_twin(book, "de", out=tmp_path / "twin.pdf")
    assert report.mismatched_pages == []
    assert report.tex_errors == []
    assert report.untranslated == 0 and report.stale == 0
    assert 0.5 < report.base_scale <= 1.0
    twin = pypdf.PdfReader(str(pdf))
    assert len(twin.pages) == report.pages >= 3
    for i, page in enumerate(twin.pages):
        text = " ".join(page.extract_text().split())
        assert "Alpha-DE" in text or i == 0
        assert "alpha " not in text
    texts = [" ".join(p.extract_text().split()) for p in twin.pages]
    # the chapter opens on the first twin page, as in the English
    assert "Kapitel 1 One" in texts[0] or "Kapitel1One" in texts[0].replace(" ", "")
    # a page where section 1.2 starts carries its translated title in the head
    assert any(t.startswith("1.2 Second (de)") for t in texts), [t[:30] for t in texts]
    # each section's twin pages, for the book site to slice: the first starts
    # on twin page 1, the second ends on the last, and they meet or touch
    first, second = report.sections["one/first"], report.sections["one/second"]
    assert first[0] == 1 and second[1] == report.pages
    assert second[0] in (first[1], first[1] + 1)
    assert any(t.startswith("1.2 Second (de)") for t in texts[second[0] - 1:second[0]])


def test_coverage_check_flags_a_gap():
    from parody.twin.build import coverage_problems
    pages = [TwinPage(5, 1, pieces=[Piece(1, 0, 0, 2)]), TwinPage(6, 2, pieces=[Piece(1, 0, 3, None)])]
    assert coverage_problems(pages) == ["section 1 chunk 0: sentences 2–3 are on no twin page"]
    ok = [TwinPage(5, 1, pieces=[Piece(1, 0, 0, 2)]), TwinPage(6, 2, pieces=[Piece(1, 0, 2, None)])]
    assert coverage_problems(ok) == []


def test_split_tables_and_wide_floats_are_reported():
    from parody.twin.build import unsupported_notes
    chunks = {1: _section(["| a | b |\n|---|---|\n| 1 | 2 |", "Prose here."])}
    rows = [(5, 1, V(1, 0, 0), 3), (6, 2, V(1, 0, 0), 2), (6, 2, V(1, 1, 0), 1)]
    notes = unsupported_notes(chunks, rows, {5: 1, 6: 2}, tex_by_section={1: "\\begin{figure*}x\\end{figure*}"})
    assert any("table" in n and "pages 1–2" in n for n in notes)
    assert any("figure*" in n for n in notes)


def test_reopened_box_step_back_with_real_counter_shape():
    # head written BEFORE the box opens (pre-step), first sentence inside after
    tr = align_translation(_section(EN), _tf(EN, lambda c: c))
    counters = {V(1, 2, 0): {"thmctr": 3}, V(1, 2, 1): {"thmctr": 4}}
    md = page_markdown(TwinPage(6, 2, pieces=[Piece(1, 2, 1, None)]), {1: _section(EN)},
                       {1: tr}, "de", counters)[0][0][1]
    assert "\\addtocounter{thmctr}{-1}" in md


def test_section_ranges_from_pages():
    # twin pages are 1-based in the twin PDF; a section runs from the first
    # page holding any of its text to the last, blank pages between included
    pages = [TwinPage(5, 1, [Piece(1, 0, 0, None)]),
             TwinPage(6, 2, [Piece(1, 1, 0, None), Piece(2, 0, 0, None)]),
             TwinPage(7, 3, []),
             TwinPage(8, 4, [Piece(2, 1, 0, None)])]
    keys = {"one/a": 1, "one/b": 2, "two/c": 3}
    assert section_ranges(pages, keys) == {"one/a": [1, 2], "one/b": [2, 4]}


def test_sidecar_round_trip(tmp_path):
    import hashlib
    import json
    twin = tmp_path / "book-de.pdf"
    twin.write_bytes(b"%PDF twin")
    english = tmp_path / "book.pdf"
    english.write_bytes(b"%PDF en")
    report = TwinReport(language="de", base_scale=0.87, squeezed=[(22, 0.85)], approximate=[4],
                        abspages=[5, 6], english_pdf=english, sections={"one/a": [1, 2]})
    path = write_twin_sidecar(twin, report, tmp_path / "book-de-sbs.pdf")
    assert path == tmp_path / "book-de.twin.json"
    assert json.loads(path.read_text()) == {
        "schema": 1, "language": "de", "pdf": "book-de.pdf",
        "sha256": hashlib.sha256(b"%PDF twin").hexdigest(),
        "english_sha256": hashlib.sha256(b"%PDF en").hexdigest(),
        "side_by_side": "book-de-sbs.pdf", "sections": {"one/a": [1, 2]},
        "abspages": [5, 6], "base_scale": 0.87, "squeezed": [[22, 0.85]],
        "approximate": [4], "untranslated": 0, "stale": 0}
    no_sbs = write_twin_sidecar(twin, report)
    assert json.loads(no_sbs.read_text())["side_by_side"] is None


# parody runs lualatex with -file-line-error, so an error is "file:line: …",
# not "! …"; and LuaTeX wraps its log, message lines included. This line is
# copied from the electronics book's marked build, where it wrapped at 80.
_WRAPPED = "./sections/fundamentals/voltage-current-resistance-and-all-that.tex:456: Undefin"


def test_log_errors_reads_both_styles_and_unwraps():
    assert len(_WRAPPED) == 80
    log = "\n".join(["noise", "! Missing $ inserted.", "l.12 x^", "",
                     _WRAPPED, "ed control sequence.", "l.456 \\freadinglist", "   {{x}}",
                     "./pages/p14-0.tex:40: Undefined control sequence.", "l.40 \\freadinglist"])
    errors = log_errors(log)
    assert [(e.message, e.context, e.file, e.line) for e in errors] == [
        ("Missing $ inserted.", "x^", None, None),
        ("Undefined control sequence.", "\\freadinglist",
         "./sections/fundamentals/voltage-current-resistance-and-all-that.tex", 456),
        ("Undefined control sequence.", "\\freadinglist", "./pages/p14-0.tex", 40)]


def test_errors_the_english_has_too_are_inherited_not_new():
    english = "./sections/a.tex:456: Undefined control sequence.\nl.456 \\freadinglist\n"
    twin = ("./pages/p14-0.tex:40: Undefined control sequence.\nl.40 \\freadinglist\n"
            "./pages/p15-0.tex:7: Missing $ inserted.\nl.7 x^\n")
    new, inherited = twin_errors(twin, english)
    assert new == ["./pages/p15-0.tex:7: Missing $ inserted. (x^)"]
    assert inherited == ["./pages/p14-0.tex:40: Undefined control sequence. (\\freadinglist)"]


def test_mark_errors_are_errors_on_a_marked_line(tmp_path):
    (tmp_path / "sections" / "ch").mkdir(parents=True)
    (tmp_path / "sections" / "ch" / "s.tex").write_text(
        "a\n\\figcaption[]{fig:x}{\\parodys{4011001}Models.}\nplain \\freadinglist\n")
    log = ("./sections/ch/s.tex:2: Illegal parameter number in definition of \\x.\nl.2 ...\n"
           "./sections/ch/s.tex:3: Undefined control sequence.\nl.3 plain \\freadinglist\n")
    assert mark_errors(log, tmp_path) == [
        "./sections/ch/s.tex:2: Illegal parameter number in definition of \\x. (...)"]


def test_a_marked_line_error_the_published_english_has_too_is_the_books(tmp_path):
    # System Dynamics 2.1: an unknown TikZ key in a sentence the marks wrap.
    # The published English has the same error (at another line: the marks
    # add lines), so the mark did not cause it, and it must not fail the twin.
    (tmp_path / "sections" / "ch").mkdir(parents=True)
    (tmp_path / "sections" / "ch" / "s.tex").write_text(
        "a\n\\parodys{4011001}Graphs \\tikz{\\draw[branch] (0,0);}.\n"
        "\\figcaption[]{fig:x}{\\parodys{4011002}Models.}\n")
    marked = ("./sections/ch/s.tex:2: Package pgfkeys Error: I do not know the key '/tikz/branch'.\n"
              "l.2 ...\\tikz{\\draw[branch]\n"
              "./sections/ch/s.tex:3: Illegal parameter number in definition of \\x.\nl.3 ...\n")
    published = ("./sections/ch/s.tex:1: Package pgfkeys Error: I do not know the key '/tikz/branch'.\n"
                 "l.1 Graphs \\tikz{\\draw[branch]\n")
    assert mark_errors(marked, tmp_path, published) == [
        "./sections/ch/s.tex:3: Illegal parameter number in definition of \\x. (...)"]
    assert len(mark_errors(marked, tmp_path)) == 2  # no published log: both stand


def test_an_unreadable_twin_pdf_has_no_page_count(tmp_path):
    # TeX that stops part-way (a fatal error that reaches only the terminal)
    # leaves a truncated main.pdf behind; the build must report it, not crash.
    bad = tmp_path / "t.pdf"
    bad.write_bytes(b"%PDF-1.5\n%truncated")
    assert pdf_pages(bad) is None
    assert pdf_pages(tmp_path / "absent.pdf") is None


def test_a_run_of_untranslated_chunks_gets_one_marker():
    # One marker per chunk made a partly translated page dense (315 in the
    # electronics book) and pulled the whole twin's type size down.
    tr = align_translation(_section(EN), _tf(EN[:2], lambda c: c.replace("alpha", "Alpha-DE")))
    pieces = [Piece(1, 0, 0, None), Piece(1, 1, 0, None), Piece(1, 2, 0, None), Piece(1, 3, 0, None)]
    groups, notes = page_markdown(TwinPage(5, 1, pieces=pieces), {1: _section(EN)}, {1: tr}, "de", {})
    md, _, footnotes = groups[0][1].partition("\n\n[^1]:")
    assert md.count("\\parodyuntranslated") == 1
    assert md.index("\\parodyuntranslated") < md.index("Def one")
    assert footnotes.startswith(" \\parodyuntranslated")  # the footnote, apart from the run
    assert sum(n.startswith("untranslated") for n in notes) == 3  # still counted per chunk
    # a translated chunk between two untranslated ones starts a new run
    tr = align_translation(_section(EN), _tf([EN[1]], lambda c: c.replace("alpha", "Alpha-DE")))
    pieces = [Piece(1, 0, 0, None), Piece(1, 1, 0, None), Piece(1, 2, 0, None)]
    groups, _ = page_markdown(TwinPage(5, 1, pieces=pieces), {1: _section(EN)}, {1: tr}, "de", {})
    assert groups[0][1].partition("\n\n[^1]:")[0].count("\\parodyuntranslated") == 2


def test_any_pdf_reader_failure_means_unreadable(tmp_path, monkeypatch):
    # pypdf raises more than its own errors on some truncations (ValueError,
    # struct.error); "unreadable" is the contract, whatever the cause.
    import pypdf
    path = tmp_path / "t.pdf"
    path.write_bytes(b"%PDF-1.5")

    def explode(*a, **k):
        raise ValueError("bad xref")
    monkeypatch.setattr(pypdf, "PdfReader", explode)
    assert pdf_pages(path) is None


def test_a_page_opening_a_chapter_sets_its_labels():
    # as the English does after \chapter: the slug, and the hash when it differs
    page = TwinPage(15, 11, pieces=[Piece(2, 0, 0, None)], chapter_start=True)
    tex = _page_tex(page, ["\\input{pages/p15-0.tex}"], 0.9, "", "", "Schaltungsanalyse",
                    ["circuit-analysis", "uy"])
    assert tex.startswith("\\def\\parodytwinchapterlabels{\\label{circuit-analysis}\\label{uy}}")
    assert "[Schaltungsanalyse]" in tex
    plain = _page_tex(TwinPage(16, 12, pieces=[Piece(2, 1, 0, None)]), [], 0.9, "", "", None, [])
    assert "parodytwinchapterlabels" not in plain


def test_reference_problems_compare_the_twin_with_the_english():
    # Both shipped silently once: every exercise label numbered wrongly, and
    # every chapter reference printed ??. The build must say so.
    english_aux = ("\\newlabel{crumble}{{1.1}{24}{}{exercise.1.1}{}}\n"
                   "\\newlabel{crumble@cref}{{[exercise][1][1]1.1}{[1][24][]24}{}{}{}}\n"
                   "\\newlabel{uy}{{2}{29}{Circuit analysis}{chapter.2}{}}\n"
                   "\\newlabel{fig:a}{{1.4}{12}{}{figure.1.4}{}}\n")
    twin_aux = ("\\newlabel{crumble}{{}{24}{}{solution.1}{}}\n"
                "\\newlabel{fig:a}{{1.4}{12}{}{figure.1.4}{}}\n")
    english_log = "LaTeX Warning: Reference `nowhere' on page 3 undefined on input line 9.\n"
    twin_log = ("LaTeX Warning: Reference `uy' on page 11 undefined on input line 56.\n"
                "LaTeX Warning: Reference `nowhere' on page 3 undefined on input line 9.\n")
    assert reference_problems(english_aux, twin_aux, english_log, twin_log) == [
        "label crumble is (empty) in the twin, 1.1 in the English",
        "reference uy prints ?? in the twin (the English resolves it)"]
    assert reference_problems(english_aux, english_aux, english_log, english_log) == []


def test_an_exercise_reopened_inside_its_solution_steps_every_opener_back():
    # A reopened exercise re-runs its openers: xsim steps the exercise (and its
    # running total) again, and the solution too when the cut fell inside it.
    # Unstepped, every later exercise on the electronics twins was one too high.
    from parody.twin.marks import sentence_starts
    ex = ("::: {#gastro .exercise}\nDo it. Then more.\n\n::: solution\n"
          "Answer one. Answer two.\n:::\n:::")
    chunks = ["# S {#sec:s}", ex]
    cut = sentence_starts(ex).index(ex.index("Answer two")) + 1
    tr = align_translation(_section(chunks), _tf(chunks, lambda c: c))
    counters = {V(1, 1, 0): {"exercise": 3, "numberofexercises": 3, "solution": 2},
                V(1, 1, 1): {"exercise": 4, "numberofexercises": 4, "solution": 2},
                V(1, 1, cut): {"exercise": 4, "numberofexercises": 4, "solution": 3}}
    md = page_markdown(TwinPage(6, 2, pieces=[Piece(1, 1, cut, None)]), {1: _section(chunks)},
                       {1: tr}, "de", counters)[0][0][1]
    for name in ("exercise", "numberofexercises", "solution"):
        assert f"\\addtocounter{{{name}}}{{-1}}" in md, (name, md)
    assert md.index("\\addtocounter{exercise}{-1}") < md.index("::: {.exercise}")


@needs_tex
def test_sections_titled_in_front_matter_number_as_in_the_english(tmp_path):
    # Robotics: headings the build writes from front matter, and a draft
    # section between two released ones. The English steps the section counter
    # for the draft; a twin page where the next section starts mid-page must
    # carry that step, and must not count the heading twice.
    book = tmp_path / "book"
    (book / "chapters" / "one").mkdir(parents=True)
    (book / "parody.yaml").write_text(YAML.replace("[first, second]", "[first, hidden, third]"))
    texts = {"first": "---\ntitle: First\nid: sec:first\n---\n\nAlpha one. Alpha two.\n",
             "hidden": "---\ntitle: Hidden\ndraft: true\n---\n\nNot printed.\n",
             "third": "---\ntitle: Third\nid: sec:third\n---\n\nAlpha three. See [@sec:first].\n"}
    for slug, text in texts.items():
        (book / "chapters" / "one" / f"{slug}.md").write_text(text)
    for slug in ("first", "third"):
        meta, body = split_frontmatter(texts[slug])
        TranslationFile(language="de", source=f"chapters/one/{slug}.md",
                        title=meta["title"] + " (de)", title_hash=chunk_hash(meta["title"]),
                        chunks=[(chunk_hash(c), c.replace("Alpha", "Alpha-DE"))
                                for c in split_chunks(body)]
                        ).write(translation_path(book, "de", "one", slug))
    pdf, report = build_twin(book, "de", out=tmp_path / "twin.pdf")
    assert report.mismatched_pages == [] and report.tex_errors == []
    assert report.references == []
    aux = (tmp_path / "book" / "build" / "twin" / "twin-de" / "main.aux").read_text()
    assert "\\newlabel{sec:first}{{1.1}" in aux and "\\newlabel{sec:third}{{1.3}" in aux


NOTED_EN = ["# S {#sec:s}",
            "::: {.example}\nThe cart rolls.[^rad] It turns. Then it stops.\n\n"
            "[^rad]: The wheel rolls. It does not slip.\n\nAt last it stands.\n:::"]


def test_a_nested_note_comes_with_every_page_of_its_section():
    # the reference on one page, the definition's sentences on the next: the
    # note was printed as a literal [^rad] on one and lost on the other
    tr = align_translation(_section(NOTED_EN), _tf(NOTED_EN, lambda c: c.replace("cart", "Wagen")))
    for page in (TwinPage(5, 1, pieces=[Piece(1, 0, 0, None), Piece(1, 1, 0, 2)]),
                 TwinPage(6, 2, pieces=[Piece(1, 1, 2, None)])):
        (_, md), = page_markdown(page, {1: _section(NOTED_EN)}, {1: tr}, "de", {})[0]
        assert md.count("[^rad]: The wheel rolls. It does not slip.") == 1, md


def test_a_whole_chunk_does_not_define_its_nested_note_twice():
    tr = align_translation(_section(NOTED_EN), _tf(NOTED_EN, lambda c: c))
    page = TwinPage(5, 1, pieces=[Piece(1, 0, 0, None), Piece(1, 1, 0, None)])
    (_, md), = page_markdown(page, {1: _section(NOTED_EN)}, {1: tr}, "de", {})[0]
    assert md.count("[^rad]:") == 1, md


YAML_TWO = """\
title: Twin Two
slug: twin-two
authors: [Tester]
chapters:
  - slug: one
    title: One
    sections: [first]
  - slug: two
    title: Two
    sections: [third]
translations:
  languages: [de]
"""


@needs_tex
def test_a_twin_of_some_chapters_resolves_references_to_the_others(tmp_path):
    # A twin of chapter one alone printed ?? for its reference to chapter two,
    # and the check refused the whole language for it (System Dynamics: up to
    # four such references in each later chapter)
    book = tmp_path / "book"
    (book / "chapters" / "one").mkdir(parents=True)
    (book / "chapters" / "two").mkdir(parents=True)
    (book / "parody.yaml").write_text(YAML_TWO)
    first = ("---\ntitle: First\n---\n\n# First {#sec:first}\n\nAs [@sec:third] shows, alpha holds. "
             + _para(1) + "\n")
    third = "---\ntitle: Third\n---\n\n# Third {#sec:third}\n\n" + _para(2) + "\n"
    (book / "chapters" / "one" / "first.md").write_text(first)
    (book / "chapters" / "two" / "third.md").write_text(third)
    meta, body = split_frontmatter(first)
    chunks = split_chunks(body)
    TranslationFile(language="de", source="chapters/one/first.md", title="First (de)",
                    title_hash=chunk_hash(meta["title"]),
                    chunks=[(chunk_hash(c), c.replace("alpha", "Alpha-DE")) for c in chunks]
                    ).write(translation_path(book, "de", "one", "first"))
    pdf, report = build_twin(book, "de", chapters=["one"], out=tmp_path / "twin.pdf")
    assert report.references == [], report.references
    assert report.tex_errors == [], report.tex_errors
    import pypdf
    text = " ".join(" ".join((p.extract_text() or "").split()) for p in pypdf.PdfReader(str(pdf)).pages)
    assert "??" not in text, text[:300]
    assert "2.1" in text, text[:300]


YAML_APPENDIX = YAML_TWO.replace("    sections: [third]\n", "    sections: [third]\n    appendix: true\n")


@needs_tex
def test_an_appendix_twin_numbers_as_the_english_does(tmp_path):
    # the English prints Appendix A and (A.1); twin pages never switched to
    # \appendix, so they printed 2 and (2.1) and the labels disagreed
    book = tmp_path / "book"
    (book / "chapters" / "one").mkdir(parents=True)
    (book / "chapters" / "two").mkdir(parents=True)
    (book / "parody.yaml").write_text(YAML_APPENDIX)
    first = "---\ntitle: First\n---\n\n# First {#sec:first}\n\n" + _para(1) + "\n"
    third = ("---\ntitle: Third\n---\n\n# Third {#sec:third}\n\nAlpha holds:\n\n"
             "$$x = 1$$ {#eq:alpha}\n\nBy [@eq:alpha], alpha holds. " + _para(2) + "\n")
    (book / "chapters" / "one" / "first.md").write_text(first)
    (book / "chapters" / "two" / "third.md").write_text(third)
    meta, body = split_frontmatter(third)
    chunks = split_chunks(body)
    TranslationFile(language="de", source="chapters/two/third.md", title="Third (de)",
                    title_hash=chunk_hash(meta["title"]),
                    chunks=[(chunk_hash(c), c.replace("Alpha", "Alpha-DE")) for c in chunks]
                    ).write(translation_path(book, "de", "two", "third"))
    pdf, report = build_twin(book, "de", chapters=["two"], out=tmp_path / "twin.pdf")
    assert report.references == [], report.references
    assert report.tex_errors == [], report.tex_errors
    import pypdf
    text = " ".join(" ".join((p.extract_text() or "").split()) for p in pypdf.PdfReader(str(pdf)).pages)
    assert "(A.1)" in text, text[:400]
    assert "(2.1)" not in text, text[:400]


def test_english_citations_are_the_keys_the_english_bbl_holds():
    from parody.twin.build import english_citations
    bbl = ("\\refsection{0}\n  \\datalist[entry]{nty/global//global/global/global}\n"
           "    \\entry{alpha1999}{book}{}{}\n      \\field{labelnumber}{1}\n    \\endentry\n"
           "    \\entry{zeta2001}{article}{}{}\n    \\endentry\n")
    assert english_citations(bbl) == ["alpha1999", "zeta2001"]
    assert english_citations("") == []


BIB_TWO = """\
@book{alpha1999, author={Aardvark, Ann}, title={Alpha}, year={1999}, publisher={P}}
@book{zeta2001, author={Zebra, Zed}, title={Zeta}, year={2001}, publisher={P}}
"""


@needs_tex
def test_a_twin_of_some_chapters_numbers_citations_as_the_english(tmp_path):
    # the English numbers a citation among all the book cites; a twin of some
    # chapters numbered it among its own (System Dynamics, Korean: [2] for [12])
    book = tmp_path / "book"
    (book / "chapters" / "one").mkdir(parents=True)
    (book / "chapters" / "two").mkdir(parents=True)
    (book / "parody.yaml").write_text(YAML_TWO)
    (book / "book.bib").write_text(BIB_TWO)
    first = "---\ntitle: First\n---\n\n# First {#sec:first}\n\nAs Zebra shows [@zeta2001], alpha holds. " \
        + _para(1) + "\n"
    third = "---\ntitle: Third\n---\n\n# Third {#sec:third}\n\nAs Aardvark shows [@alpha1999]. " \
        + _para(2) + "\n"
    (book / "chapters" / "one" / "first.md").write_text(first)
    (book / "chapters" / "two" / "third.md").write_text(third)
    meta, body = split_frontmatter(first)
    chunks = split_chunks(body)
    TranslationFile(language="de", source="chapters/one/first.md", title="First (de)",
                    title_hash=chunk_hash(meta["title"]),
                    chunks=[(chunk_hash(c), c.replace("alpha", "Alpha-DE")) for c in chunks]
                    ).write(translation_path(book, "de", "one", "first"))
    pdf, report = build_twin(book, "de", chapters=["one"], out=tmp_path / "twin.pdf")
    assert report.tex_errors == [], report.tex_errors
    import pypdf
    text = " ".join(" ".join((p.extract_text() or "").split()) for p in pypdf.PdfReader(str(pdf)).pages)
    assert "Zebra shows [2]" in text, text[:400]
