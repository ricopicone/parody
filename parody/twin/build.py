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
from .paginate import paginate

_TWINFIT = re.compile(r"TWINFIT page=(-?\d+) scale=([0-9.]+)")
_SKIP_COUNTERS = {"page", "mpfootnote"}
_FLOAT = re.compile(r"\\begin\{(figure|table)\}(\[[^\]]*\])?")


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
    tex_errors: list = field(default_factory=list)  # "! …" lines from the twin's log
    notes: list = field(default_factory=list)


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


def restore_code(counters):
    """``\\parodytwinset`` calls restoring the document counters the English had."""
    return "".join(f"\\parodytwinset{{{name}}}{{{value}}}" for name, value in counters.items()
                   if name not in _SKIP_COUNTERS and "@" not in name)


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
                            or f.name == "latexmkrc"):
            shutil.copy2(f, dst / f.name)
    shutil.copy2(SHARED_PROFILE_DIR / "parody-twin.sty", dst / "parody-twin.sty")


def _unsupported_floats(marked_dir, english, selected):
    """Sections with a float the twin cannot follow (anything but [H])."""
    notes = []
    for i in sorted(selected):
        sec = english.get(i)
        if sec is None:
            continue
        tex = Path(marked_dir) / "sections" / sec.chapter.slug / f"{sec.slug}.tex"
        if not tex.is_file():
            continue
        for kind, placement in _FLOAT.findall(tex.read_text(encoding="utf-8")):
            if placement not in ("[H]",):
                notes.append(f"unsupported: {kind}{placement or ''} in {sec.key} may sit on another page")
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
    code = f"\\parodytwinset{{chapter}}{{{chapter_no}}}"
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


def _page_tex(page, inputs, scale, chapmark, secmark, chapter_title):
    opt = f"[{chapter_title}]" if page.chapter_start and chapter_title else ""
    return (f"\\begin{{twinpage}}{{{page.page}}}{{{scale:.2f}}}{{{restore_code(page.counters)}}}"
            f"{{{chapmark}}}{{{secmark}}}{opt}\n" + "\n".join(inputs) + "\n\\end{twinpage}\n")


def build_twin(project_dir, language, chapters=None, published_pdf=None, out=None, build_dir=None):
    """Build the twin PDF; returns ``(pdf path, TwinReport)``."""
    if language not in TWIN_LANGUAGES:
        raise ValueError(f"no twin typesetting for {language!r} (known: {', '.join(TWIN_LANGUAGES)})")
    project_dir = Path(project_dir)
    project = load_project(project_dir)
    build_dir = Path(build_dir or project_dir / "build" / "twin")
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
    pages = paginate(inv.rows, inv.counters, selected, firsts)

    english = english_sections(project, index)
    translated = {i: align_translation(english[i], _read_translation(project_dir, language, english[i]))
                  for i in selected if i in english}
    titles = _chapter_titles(project_dir, language)

    twin_dir = build_dir / f"twin-{language}"
    (twin_dir / "pages").mkdir(parents=True, exist_ok=True)
    _copy_support(build_dir / "marked", twin_dir)
    report = TwinReport(language=language, mismatched_pages=list(inv.mismatched_pages),
                        pages=len(pages),
                        unsupported=_unsupported_floats(build_dir / "marked", english, selected))

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
                section_to_latex(md_path, tex_path, resource_dir=src.chapter.directory)
                if any(p.section == section and p.chunk == 0 and p.start == 0 for p in page.pieces):
                    meta = dict(src.meta)
                    meta["title"] = translated[section].title or src.title or meta.get("title")
                    tex_path.write_text(synthesize_section_heading(
                        tex_path.read_text(encoding="utf-8"), meta, src.slug), encoding="utf-8")
                inputs.append(f"\\input{{pages/{tex_path.name}}}")
            chapmark, secmark = _marks(page, english, translated, titles, inv.counters), ""
            chapter_title = None
            if page.chapter_start and page.first_unit is not None:
                chapter = english[page.first_unit // 1_000_000].chapter
                chapter_title = titles.get(chapter.slug) or chapter.title
            composed.append((page, inputs, chapmark, secmark, chapter_title))

    marked_main = (build_dir / "marked" / "main.tex").read_text(encoding="utf-8")
    preamble = marked_main.split("\\begin{document}")[0]
    preamble = preamble.replace(TWINMARKS_FLAG + "\n", "").replace("\\usepackage{parody-pagemap}\n", "")

    def write_main(scale):
        body = "".join(_page_tex(page, inputs, scale, cm, sm, ct)
                       for page, inputs, cm, sm, ct in composed)
        (twin_dir / "main.tex").write_text(
            preamble + twin_preamble(language) + "\n\\begin{document}\n\\mainmatter\n"
            + body + "\\end{document}\n", encoding="utf-8")

    def fits():
        if run_latexmk(project, project_dir, twin_dir) is None:
            raise RuntimeError("the twin build needs TeX (latexmk + lualatex)")
        return parse_twinfit((twin_dir / "main.log").read_text(encoding="utf-8", errors="replace"))

    write_main(1.0)
    needed = [s for (p, s), (page, *_) in zip(fits(), composed) if page.pieces]
    report.base_scale = base_scale(needed)
    write_main(report.base_scale)
    final = fits()
    report.squeezed = [(p, s) for p, s in final if s < report.base_scale - 1e-9]
    log = (twin_dir / "main.log").read_text(encoding="utf-8", errors="replace")
    report.tex_errors = [line for line in log.splitlines() if line.startswith("! ")]

    out = Path(out or project_dir / f"{project.slug}-{language}.pdf")
    out.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(twin_dir / "main.pdf", out)
    try:
        import pypdf
        shipped = len(pypdf.PdfReader(str(out)).pages)
        if shipped != len(pages):
            report.notes.append(f"the twin has {shipped} pages for {len(pages)} English pages")
    except ImportError:
        pass
    return out, report
