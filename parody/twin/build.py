"""Build a translated twin of the English print PDF, page for page (task #825).

1. The published English PDF (built here unless given).
2. The marked English build and its inventory, gated page by page against
   the published PDF.
3. Paginate the chosen chapters; compose each page's translated Markdown and
   convert it exactly as the English sections are converted.
4. Pass 1: every page fitted from scale 1.0, logging the scale it needs.
   The language's base scale is the 10th percentile of those, so nearly
   every page sets at one type size.
5. Pass 2: every page fitted from the base scale. A denser page squeezes
   further, without limit, and is reported.
"""

import json
import math
import os
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from ..config import load_project, resolve_cloze_mode
from ..translate.store import TranslationFile, translation_path
from ..writers.latex import (
    SHARED_PROFILE_DIR,
    build_pdf,
    print_env,
    run_latexmk,
    section_prints_a_heading,
    section_to_latex,
    synthesize_section_heading,
)
from .compose import align_translation, english_sections, page_markdown
from .inventory import TWINMARKS_FLAG, build_inventory
from .languages import TWIN_LANGUAGES, twin_preamble
from .marks import MARK_MACRO, decode
from .paginate import paginate

_TWINFIT = re.compile(r"TWINFIT page=(-?\d+) scale=([0-9.]+)")
_SKIP_COUNTERS = {"page", "mpfootnote"}
_FLOAT = re.compile(r"\\begin\{(figure\*?|table\*?|longtable)\}(\[[^\]]*\])?")
_TABLE_LINE = re.compile(r"^\s*(\|.*\||\+[-=+:]+\+)\s*$", re.M)


@dataclass
class TwinReport:
    language: str
    base_scale: float = 1.0
    squeezed: list = field(default_factory=list)  # [(page, scale)] below the base
    approximate: list = field(default_factory=list)  # pages with a proportional cut
    untranslated: int = 0
    stale: int = 0
    mismatched_pages: list = field(default_factory=list)
    unsupported: list = field(default_factory=list)
    pages: int = 0
    abspages: list = field(default_factory=list)  # the English pages the twin pages twin
    english_pdf: Path | None = None
    shipped_pages: int = 0  # pages the twin PDF actually has; must equal pages
    tex_errors: list = field(default_factory=list)  # errors the twin (or a mark) introduced
    inherited_errors: list = field(default_factory=list)  # errors the English build has too
    coverage: list = field(default_factory=list)  # text on no twin page, or on two
    references: list = field(default_factory=list)  # labels/refs the twin gets wrong
    notes: list = field(default_factory=list)
    sections: dict = field(default_factory=dict)  # "chapter/section" → [first, last] twin page


SIDECAR_SCHEMA = 1

# parody's latexmkrc runs lualatex with -file-line-error, so an error reads
# "file:line: message", not "! message"; both are read. LuaTeX also wraps its
# log, message lines included: at 79 columns, and its file:line error lines at
# 80 (both measured in the electronics book's log). Joining every line of
# exactly that length to the next is deliberate: TeX marks no wrap, and a
# message that happens to be 79 or 80 long only loses its context token.
_ERROR_HEAD = re.compile(r"^(?:! (?P<bang>.*)|(?P<file>\S+?\.tex):(?P<line>\d+): (?P<msg>.*))$")
_CONTEXT = re.compile(r"^l\.\d+ (.*)$")
_LOG_WIDTHS = (79, 80)


@dataclass(frozen=True)
class TexError:
    message: str
    context: str  # the last token TeX had read: the undefined macro, say
    file: str | None = None
    line: int | None = None

    def __str__(self):
        where = f"{self.file}:{self.line}: " if self.file else "! "
        return f"{where}{self.message} ({self.context})"


def _unwrap(log):
    out, buf = [], ""
    for line in log.splitlines():
        buf += line
        if len(line) not in _LOG_WIDTHS:
            out.append(buf)
            buf = ""
    if buf:
        out.append(buf)
    return out


def log_errors(log):
    """Every TeX error in ``log``, in either style, as ``TexError``."""
    lines = _unwrap(log)
    errors = []
    for i, line in enumerate(lines):
        m = _ERROR_HEAD.match(line)
        if not m:
            continue
        context = ""
        for following in lines[i + 1:i + 8]:
            c = _CONTEXT.match(following)
            if c:
                context = (c.group(1).split() or [""])[-1]
                break
        if m.group("file"):
            errors.append(TexError(m.group("msg"), context, m.group("file"), int(m.group("line"))))
        else:
            errors.append(TexError(m.group("bang"), context))
    return errors


def twin_errors(twin_log, english_log):
    """``(new, inherited)``: the twin's errors, split by whether the English
    build has the same one (same message, same macro). An inherited error is
    the book's, and the published PDF already carries it; a new one is the
    twin's own."""
    english = {(e.message, e.context) for e in log_errors(english_log)}
    new, inherited = [], []
    for e in log_errors(twin_log):
        (inherited if (e.message, e.context) in english else new).append(str(e))
    return new, inherited


_NEWLABEL = re.compile(r"\\newlabel\{([^}@]+)\}\{\{([^}]*)\}")
_UNDEFINED_REF = re.compile(r"Reference `([^']+)' on page \S+ undefined")


_NEWLABEL_LINE = re.compile(r"^\\newlabel\{([^}]+)\}.*$", re.M)


def _read(path):
    return path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""


def _labels_tag(path):
    import hashlib
    return hashlib.sha256(path.read_bytes()).hexdigest()[:12] if path.is_file() else "none"


def english_labels(english_aux, twin_aux):
    """The English aux's ``\\newlabel`` lines for the labels the twin does not
    define, for the twin to read: a twin of some chapters references the
    others, and printed ?? for each (System Dynamics: up to four in a
    chapter), which refused the whole language. The English number is the
    right one to print — the twin pairs page for page with the English."""
    have = set(re.findall(r"^\\newlabel\{([^}]+)\}", twin_aux, re.M))
    lines = [m.group(0) for m in _NEWLABEL_LINE.finditer(english_aux) if m.group(1) not in have]
    return "\n".join(lines) + ("\n" if lines else "")


_BBL_ENTRY = re.compile(r"^\s*\\entry\{([^}]+)\}", re.M)


def english_citations(english_bbl):
    """The keys the English cites, from its ``.bbl``: the twin cites them all
    (``\\nocite``), or a twin of some chapters numbers each citation among
    its own and prints [2] where the English prints [12]."""
    return list(dict.fromkeys(_BBL_ENTRY.findall(english_bbl)))


def reference_problems(english_aux, twin_aux, english_log, twin_log):
    """What a reader would find wrong in the twin's references: a label the
    twin numbers differently from the English (counters are restored, so they
    must agree), and a reference the English resolves that prints ?? here."""
    english, twin = dict(_NEWLABEL.findall(english_aux)), dict(_NEWLABEL.findall(twin_aux))
    out = [f"label {k} is {twin[k] or '(empty)'} in the twin, {v} in the English"
           for k, v in english.items() if k in twin and twin[k] != v]
    resolved = set(_UNDEFINED_REF.findall("\n".join(_unwrap(english_log))))
    for k in sorted(set(_UNDEFINED_REF.findall("\n".join(_unwrap(twin_log)))) - resolved):
        out.append(f"reference {k} prints ?? in the twin (the English resolves it)")
    return out


def _context_tail(context):
    """An error's context, comparable across builds: TeX cuts a long input
    line at the front ("..."), and where depends on the line, which the marks
    lengthen."""
    return context.lstrip(".")[-12:]


def mark_errors(marked_log, marked_dir, published_log=""):
    """Errors of the marked English build on a line that carries a mark: a
    mark in a place it must not be (a moving argument, say). One the published
    English build has too (same message, same macro) is the book's own: the
    marks add lines, so only its line number moved (System Dynamics 2.1's
    unknown TikZ keys)."""
    published = {(e.message, _context_tail(e.context)) for e in log_errors(published_log)}
    out = []
    for e in log_errors(marked_log):
        if not e.file or (e.message, _context_tail(e.context)) in published:
            continue
        try:
            lines = (Path(marked_dir) / e.file).read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        if 0 < e.line <= len(lines) and f"\\{MARK_MACRO}" in lines[e.line - 1]:
            out.append(str(e))
    return out


def _published_log(published_pdf, build_dir):
    """The log of the build that made the published English PDF, where parody
    leaves it: the twin's own English build, or ``parody publish``'s
    ``print/main.log`` beside the PDF. Empty when there is none."""
    pdf = Path(published_pdf)
    own = Path(build_dir) / "english.pdf"
    candidates = ([Path(build_dir) / "english" / "main.log"] if pdf == own
                  else [pdf.parent / "print" / "main.log"])
    for log in candidates:
        if log.is_file():
            return log.read_text(encoding="utf-8", errors="replace")
    return ""


def section_ranges(pages, section_keys):
    """``{"chapter/section": [first, last]}``, 1-based pages of the twin PDF.

    A section runs from the first twin page holding any of its text to the
    last, so the page where one section ends and the next begins belongs to
    both, as it does in the English section PDFs. The twin starts at the first
    selected section, not at English page 1, which is why the English page
    ranges cannot slice it.
    """
    key_of = {i: key for key, i in section_keys.items()}
    out = {}
    for n, page in enumerate(pages, start=1):
        for piece in page.pieces:
            key = key_of.get(piece.section)
            if key is None:
                continue
            first, _ = out.get(key, (n, n))
            out[key] = [first, n]
    return out


def write_twin_sidecar(pdf, report, side_by_side=None):
    """Write ``<twin>.twin.json`` beside the twin PDF; returns its path.

    It names the English PDF the twin pairs with by sha256, so a book site
    can refuse a twin of an older English build.
    """
    from ..writers.pagemap import sha256_file

    pdf = Path(pdf)
    path = pdf.with_suffix(".twin.json")
    payload = {
        "schema": SIDECAR_SCHEMA,
        "language": report.language,
        "pdf": pdf.name,
        "sha256": sha256_file(pdf),
        "english_sha256": sha256_file(report.english_pdf),
        "side_by_side": Path(side_by_side).name if side_by_side else None,
        "sections": report.sections,
        "abspages": report.abspages,
        "base_scale": report.base_scale,
        "squeezed": [list(x) for x in report.squeezed],
        "approximate": report.approximate,
        "untranslated": report.untranslated,
        "stale": report.stale,
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def parse_twinfit(log):
    """``[(page, scale)]`` in the order the pages were set."""
    return [(int(p), float(s)) for p, s in _TWINFIT.findall(log)]


def base_scale(scales):
    """The 10th percentile of the required scales, floored to 0.01, at most 1."""
    if not scales:
        return 1.0
    ordered = sorted(scales)
    value = ordered[max(0, math.ceil(0.1 * len(ordered)) - 1)]
    return min(1.0, math.floor(value * 100 + 1e-9) / 100)


def _appendix_code(counters):
    """``\\appendix`` where the English was past it, so chapters print A, B, …"""
    return "\\appendix" if counters.get("@appendix") else ""


def restore_code(counters):
    """``\\parodytwinset`` calls restoring the document counters the English
    had, then ``\\parodytwinlabel`` restoring its current label (what a
    ``\\label`` there records), when the marks logged one. In an appendix,
    ``\\appendix`` first: it resets the chapter counter the calls then set."""
    code = _appendix_code(counters) + "".join(f"\\parodytwinset{{{name}}}{{{value}}}" for name, value in counters.items()
                   if name not in _SKIP_COUNTERS and "@" not in name)
    if "@currentlabel" in counters:
        code += f"\\parodytwinlabel{{{counters['@currentlabel']}}}"
    return code


_FLOAT_OPEN = re.compile(r"\\begin\{(figure|table)\}(\[[^\]]*\])?")


def floats_here(tex):
    """``tex`` with every figure and table set here (``[H]``).

    A twin page is set in a minipage, where a float is "Not in outer par
    mode"; and here is where the English put it, on the page this twin page
    twins. Starred floats and longtables are left as they are (and reported
    as unsupported).
    """
    return _FLOAT_OPEN.sub(lambda m: f"\\begin{{{m.group(1)}}}[H]", tex)


_MARK_TEX = re.compile(rf"\\{MARK_MACRO}\{{(\d+)\}}")
_FLOAT_BODY = re.compile(rf"((?:\\{MARK_MACRO}\{{\d+\}}\s*)*)"
                         r"\\begin\{(figure\*?|table\*?)\}(\[[^\]]*\])?(.*?)\\end\{\2\}", re.S)


def float_units(tex):
    """The mark values of the floats in a marked section's ``tex``.

    The mark just before a float and those inside it travel with it to the
    page LaTeX puts it on, which need not be the page of the text around it.
    A float set here ([H]) stays in the text.
    """
    units = set()
    for m in _FLOAT_BODY.finditer(tex):
        if m.group(3) != "[H]":
            units.update(int(v) for v in _MARK_TEX.findall(m.group(1) + m.group(4)))
    return units


def mismatches_that_matter(mismatched, abspages):
    """The mismatched English pages among those the twin twins: a twin of some
    chapters is not wrong because another chapter's marked English differs."""
    twinned = set(abspages)
    return [p for p in mismatched if p in twinned]


def _value(section, chunk, sentence):
    return section * 1_000_000 + (chunk + 1) * 1000 + sentence


def _read_translation(project_dir, language, section):
    path = translation_path(project_dir, language, section.chapter.slug, section.slug)
    return TranslationFile.read(path) if path.is_file() else None


def _chapter_titles(project_dir, language):
    import yaml
    path = Path(project_dir) / "translations" / language / "book.yaml"
    if not path.is_file():
        return {}
    chapters = (yaml.safe_load(path.read_text(encoding="utf-8")) or {}).get("chapters") or {}
    return {slug: entry.get("title") for slug, entry in chapters.items() if entry}


def _copy_support(src, dst):
    for f in Path(src).iterdir():
        if f.is_file() and f.name.startswith("parody-twinmarks"):
            continue
        if f.is_file() and (f.suffix in (".cls", ".sty", ".bib", ".png", ".ttc", ".ttf", ".otf")
                            or f.name == "latexmkrc"
                            # a book preamble given as .tex is \input from the
                            # preamble the twin reuses
                            or (f.suffix == ".tex" and f.name != "main.tex")):
            shutil.copy2(f, dst / f.name)
    shutil.copy2(SHARED_PROFILE_DIR / "parody-twin.sty", dst / "parody-twin.sty")


def coverage_problems(pages):
    """Every chunk on the twin pages exactly once, start to end, no gap or overlap."""
    problems = []
    by_chunk = {}
    for page in pages:
        for piece in page.pieces:
            by_chunk.setdefault((piece.section, piece.chunk), []).append(piece)
    for (section, chunk), pieces in sorted(by_chunk.items()):
        where = f"section {section} chunk {chunk}"
        if pieces[0].start != 0:
            problems.append(f"{where}: its opening (sentences 0–{pieces[0].start}) is on no twin page")
        for a, b in zip(pieces, pieces[1:]):
            if a.end is None or a.end > b.start:
                problems.append(f"{where}: sentences from {b.start} are on two twin pages")
            elif a.end < b.start:
                problems.append(f"{where}: sentences {a.end}–{b.start} are on no twin page")
        if pieces[-1].end is not None:
            problems.append(f"{where}: its end (from sentence {pieces[-1].end}) is on no twin page")
    return problems


def unsupported_notes(english, rows, page_numbers, tex_by_section):
    """What the twin cannot follow page for page, named with the pages it touches.

    A table whose English broke across pages is set whole on one twin page.
    A float that is not [H] (or is starred, or a longtable) may sit elsewhere.
    """
    notes = []
    for index, section in sorted(english.items()):
        for k, chunk in enumerate(section.chunks):
            if not _TABLE_LINE.search(chunk):
                continue
            base = index * 1_000_000 + (k + 1) * 1000
            abspages = sorted({a for a, _, v, n in rows if base <= v < base + 1000})
            if len(abspages) > 1:
                first, last = page_numbers.get(abspages[0]), page_numbers.get(abspages[-1])
                notes.append(f"unsupported: a table in {section.key} breaks across pages "
                             f"{first}–{last} in English; the twin sets it on one page")
        for kind, placement in _FLOAT.findall(tex_by_section.get(index, "")):
            if placement != "[H]" or kind.endswith("*") or kind == "longtable":
                notes.append(f"unsupported: {kind}{placement or ''} in {section.key} "
                             "may sit on another page")
    return notes


def _marks(page, english, translated, titles, counters):
    """One ``\\markboth`` for the running heads, as the English page had them.

    One mark, not \\chaptermark then \\sectionmark: \\rightmark is the FIRST
    mark on a page, and the chapter mark's right half is empty. When a section
    starts on the page, its title is the one in the head, numbered from the
    counters at its own head mark.
    """
    if page.first_unit is None:
        return ""
    starts = [p.section for p in page.pieces if p.chunk == 0 and p.start == 0]
    section = starts[0] if starts else page.first_unit // 1_000_000
    src = english[section]
    chapter_no = page.counters.get("chapter", 0)
    chapter_title = titles.get(src.chapter.slug) or src.chapter.title
    code = _appendix_code(page.counters) + f"\\parodytwinset{{chapter}}{{{chapter_no}}}"
    right = ""
    if section_prints_a_heading(src.slug, src.meta, src.source.read_text(encoding="utf-8")):
        if section in starts:
            number = (counters.get(_value(section, 0, 0)) or {}).get("section", 0) + 1
        else:
            number = page.counters.get("section", 0)
        title = translated[section].title or src.title or ""
        # the counter is set before \\markboth, which expands its arguments
        code += f"\\parodytwinset{{section}}{{{number}}}"
        right = f"\\thesection\\ \\ {title}"
    return code + f"\\markboth{{\\thechapter.\\ {chapter_title}}}{{{right}}}"


def _page_tex(page, inputs, scale, chapmark, secmark, chapter_title, chapter_labels=()):
    opt = f"[{chapter_title}]" if page.chapter_start and chapter_title else ""
    # the labels the English sets after \chapter (writers/latex.py), or every
    # reference to the chapter prints ?? in the twin
    labels = "".join(f"\\label{{{label}}}" for label in chapter_labels) if opt else ""
    head = f"\\def\\parodytwinchapterlabels{{{labels}}}" if labels else ""
    return (head + f"\\begin{{twinpage}}{{{page.page}}}{{{scale:.2f}}}{{{restore_code(page.counters)}}}"
            f"{{{chapmark}}}{{{secmark}}}{opt}\n" + "\n".join(inputs) + "\n\\end{twinpage}\n")


def build_twin(project_dir, language, chapters=None, published_pdf=None, out=None, build_dir=None):
    """Build the twin PDF; returns ``(pdf path, TwinReport)``."""
    if language not in TWIN_LANGUAGES:
        raise ValueError(f"no twin typesetting for {language!r} (known: {', '.join(TWIN_LANGUAGES)})")
    # absolute: pandoc and latexmk each run from directories of their own
    project_dir = Path(project_dir).resolve()
    project = load_project(project_dir)
    build_dir = Path(build_dir or project_dir / "build" / "twin").resolve()
    build_dir.mkdir(parents=True, exist_ok=True)
    if published_pdf is None:
        published_pdf = build_pdf(project_dir, output_pdf=build_dir / "english.pdf",
                                  build_dir=build_dir / "english")
    inv = build_inventory(project_dir, build_dir / "marked", published_pdf)

    index = inv.section_index
    wanted = set(chapters) if chapters else {c.slug for c in project.chapters}
    printed = {v // 1_000_000 for _, _, v, _ in inv.rows}
    selected = {i for key, i in index.items() if key.split("/")[0] in wanted} & printed
    firsts = set()
    for chapter in project.chapters:
        if chapter.slug in wanted:
            ids = [index[f"{chapter.slug}/{s}"] for s in chapter.section_slugs
                   if index[f"{chapter.slug}/{s}"] in printed]
            if ids:
                firsts.add(min(ids))
    english = english_sections(project, index)
    tex_by_section = {}
    for i in selected:
        tex = (build_dir / "marked" / "sections" / english[i].chapter.slug / f"{english[i].slug}.tex"
               if i in english else None)
        if tex and tex.is_file():
            tex_by_section[i] = tex.read_text(encoding="utf-8")
    floats = set().union(*map(float_units, tex_by_section.values()))
    definitions = {(i, k) for i in selected if i in english
                   for k, chunk in enumerate(english[i].chunks) if chunk.startswith("[^")}
    footnotes = {v for _, _, v, _ in inv.rows if decode(v)[:2] in definitions}
    pages = paginate(inv.rows, inv.counters, selected, firsts, floats, footnotes)

    translated = {i: align_translation(english[i], _read_translation(project_dir, language, english[i]))
                  for i in selected if i in english}
    titles = _chapter_titles(project_dir, language)

    twin_dir = build_dir / f"twin-{language}"
    (twin_dir / "pages").mkdir(parents=True, exist_ok=True)
    _copy_support(build_dir / "marked", twin_dir)
    page_numbers = {}
    for abspage, page_no, _, _ in inv.rows:
        page_numbers.setdefault(abspage, page_no)
    report = TwinReport(language=language,
                        mismatched_pages=mismatches_that_matter(
                            inv.mismatched_pages, [p.abspage for p in pages]),
                        pages=len(pages), abspages=[p.abspage for p in pages],
                        english_pdf=Path(published_pdf),
                        sections=section_ranges(pages, index),
                        coverage=coverage_problems(pages),
                        unsupported=unsupported_notes({i: english[i] for i in selected if i in english},
                                                      inv.rows, page_numbers, tex_by_section))

    cloze_mode = resolve_cloze_mode(project.meta)
    composed = []
    with print_env(project, project_dir, twin_dir, cloze_mode, project.meta) as online:
        for page in pages:
            groups, notes = page_markdown(page, english, translated, language, inv.counters)
            report.untranslated += sum(n.startswith("untranslated") for n in notes)
            report.stale += sum(n.startswith("stale") for n in notes)
            if any(n.startswith("approximate") for n in notes):
                report.approximate.append(page.page)
            report.notes += [f"page {page.page}: {n}" for n in notes + page.notes]
            inputs = []
            for k, (section, markdown) in enumerate(groups):
                src = english[section]
                md_path = twin_dir / "pages" / f"p{page.abspage}-{k}.md"
                md_path.write_text(markdown + "\n", encoding="utf-8")
                tex_path = md_path.with_suffix(".tex")
                os.environ["PARODY_CHAPTER_DIR"] = str(Path(src.chapter.directory).resolve())
                os.environ["PARODY_SECTION_URL"] = (f"{online}/{src.chapter.slug}/{src.slug}/"
                                                    if online else "")
                section_to_latex(md_path, tex_path, resource_dir=src.chapter.directory,
                                 input_root=twin_dir)
                if any(p.section == section and p.chunk == 0 and p.start == 0 for p in page.pieces):
                    meta = dict(src.meta)
                    meta["title"] = translated[section].title or src.title or meta.get("title")
                    tex = synthesize_section_heading(
                        tex_path.read_text(encoding="utf-8"), meta, src.slug)
                    # The section number as the English had it just before the
                    # heading: past any draft sections it skipped, which the
                    # twin page's own restore (its first section's) predates.
                    before = (inv.counters.get(_value(section, 0, 0)) or {}).get("section")
                    if before is not None:
                        tex = f"\\parodytwinset{{section}}{{{before}}}%\n" + tex
                    tex_path.write_text(tex, encoding="utf-8")
                tex_path.write_text(floats_here(tex_path.read_text(encoding="utf-8")),
                                    encoding="utf-8")
                inputs.append(f"\\input{{pages/{tex_path.name}}}")
            chapmark, secmark = _marks(page, english, translated, titles, inv.counters), ""
            chapter_title, chapter_labels = None, []
            if page.chapter_start and page.first_unit is not None:
                chapter = english[page.first_unit // 1_000_000].chapter
                chapter_title = titles.get(chapter.slug) or chapter.title
                chapter_labels = [chapter.slug] + (
                    [chapter.hash] if chapter.hash and chapter.hash != chapter.slug else [])
            composed.append((page, inputs, chapmark, secmark, chapter_title, chapter_labels))

    marked_main = (build_dir / "marked" / "main.tex").read_text(encoding="utf-8")
    preamble = marked_main.split("\\begin{document}")[0]
    preamble = preamble.replace(TWINMARKS_FLAG + "\n", "").replace("\\usepackage{parody-pagemap}\n", "")

    # The English's labels the twin does not define (english_labels): written
    # after the first run, read by every run after it.
    labels = twin_dir / "english-labels.tex"
    labels.unlink(missing_ok=True)

    cited = english_citations(_read(build_dir / "marked" / "main.bbl"))
    nocite = f"\\nocite{{{','.join(cited)}}}\n" if cited else ""

    def write_main(scale):
        body = "".join(_page_tex(page, inputs, scale, cm, sm, ct, cl)
                       for page, inputs, cm, sm, ct, cl in composed)
        (twin_dir / "main.tex").write_text(
            preamble + twin_preamble(language)
            # its hash, so latexmk runs again when the labels change: it does
            # not watch a file that was not there on its first run
            + f"\n% english-labels {_labels_tag(labels)}"
            + "\n\\makeatletter\\InputIfFileExists{english-labels.tex}{}{}\\makeatother"
            + "\n\\begin{document}\n" + nocite + "\\mainmatter\n"
            + body + "\\end{document}\n", encoding="utf-8")

    def fits():
        if run_latexmk(project, project_dir, twin_dir) is None:
            raise RuntimeError("the twin build needs TeX (latexmk + lualatex)")
        return parse_twinfit((twin_dir / "main.log").read_text(encoding="utf-8", errors="replace"))

    write_main(1.0)
    needed = [s for (p, s), (page, *_) in zip(fits(), composed) if page.pieces]
    labels.write_text(english_labels(
        _read(build_dir / "marked" / "main.aux"), _read(twin_dir / "main.aux")), encoding="utf-8")
    report.base_scale = base_scale(needed)
    write_main(report.base_scale)
    final = fits()
    report.squeezed = [(p, s) for p, s in final if s < report.base_scale - 1e-9]
    log = (twin_dir / "main.log").read_text(encoding="utf-8", errors="replace")
    marked_log = build_dir / "marked" / "main.log"
    marked_log = marked_log.read_text(encoding="utf-8", errors="replace") if marked_log.is_file() else ""
    report.tex_errors, report.inherited_errors = twin_errors(log, marked_log)
    report.tex_errors += [f"marked English: {e}" for e in
                          mark_errors(marked_log, build_dir / "marked",
                                      _published_log(published_pdf, build_dir))]

    def text(path):
        return path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""
    report.references = reference_problems(text(build_dir / "marked" / "main.aux"),
                                           text(twin_dir / "main.aux"), marked_log, log)

    out = Path(out or project_dir / f"{project.slug}-{language}.pdf")
    out.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(twin_dir / "main.pdf", out)
    try:
        import pypdf  # noqa: F401
    except ImportError:
        return out, report
    shipped = pdf_pages(out)
    if shipped is None:
        report.tex_errors.append(
            "the twin PDF is unreadable: TeX stopped part-way (see the latexmk output)")
    else:
        report.shipped_pages = shipped
    return out, report


def pdf_pages(path):
    """Pages in the PDF at ``path``, or None when it is missing or unreadable."""
    import pypdf
    try:
        return len(pypdf.PdfReader(str(path)).pages)
    except Exception:  # noqa: BLE001 - pypdf raises ValueError, struct.error… on truncations
        return None
