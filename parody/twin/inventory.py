"""Which sentence of the English sits on which page (task #825).

The twin build builds the English a second time with zero-node marks (see
``marks``) and reads back two side files:

- ``main.twin``: one row per (page, mark value), with the number of lines
  the value occupies on that page;
- ``main.twinctr``: every LaTeX counter's value at each mark.
"""

from dataclasses import dataclass, field
from pathlib import Path

from ..writers.latex import SHARED_PROFILE_DIR

TWINMARKS_SUPPORT = [SHARED_PROFILE_DIR / "parody-twinmarks.sty",
                     SHARED_PROFILE_DIR / "parody-twinmarks.lua"]
TWINMARKS_FLAG = "\\usepackage{parody-twinmarks}"


def read_rows(path):
    """``[(abspage, page number, value, lines)]`` from a ``.twin`` file."""
    rows = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(tuple(int(x) for x in line.split("\t")))
    return rows


def read_counters(path):
    """``{value: {counter: value}}`` from a ``.twinctr`` file; the first write wins.

    A mark inside measured material (a blank sized to its answer, say) is
    expanded more than once; the first expansion is the one in reading order.
    """
    counters = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if "|" not in line:
            continue
        value, _, rest = line.partition("|")
        pairs, has_label, label = rest.partition("|")
        value = int(value)
        if value in counters:
            continue
        counters[value] = {name: int(n) for name, _, n in
                           (p.partition("=") for p in pairs.split(",") if "=" in p)}
        if has_label:
            # \@currentlabel there, as a \label would record it (restore_code)
            counters[value]["@currentlabel"] = label.strip()
    return counters


def normalize_page_text(text):
    """A page's text with all whitespace and end-of-line hyphenation removed.

    A mark may move a hyphenation point or a word space within a line (seen
    once in 113 pages) without moving any line to another page. Page
    membership is all the inventory needs.
    """
    return "".join(text.replace("-\n", "").split())


def page_texts(pdf):
    """Each page's extracted text."""
    try:
        import pypdf
    except ImportError as e:  # pragma: no cover - exercised by the install, not tests
        raise RuntimeError("twin pages need pypdf: pip install 'parody[twin]'") from e
    return [page.extract_text() or "" for page in pypdf.PdfReader(str(pdf)).pages]


def compare_pages(published, marked, extract=page_texts):
    """1-based pages whose text differs between the published and marked PDFs.

    The twin of such a page is built from an inventory that may not describe
    the page readers have, so the report names it.
    """
    a, b = extract(published), extract(marked)
    differ = [i for i, (x, y) in enumerate(zip(a, b), 1)
              if normalize_page_text(x) != normalize_page_text(y)]
    differ += list(range(min(len(a), len(b)) + 1, max(len(a), len(b)) + 1))
    return differ


@dataclass
class Inventory:
    rows: list
    counters: dict
    section_index: dict  # "chapter/section" → 1-based index in parody.yaml order
    marked_pdf: Path
    mismatched_pages: list = field(default_factory=list)


def section_indices(project):
    """``{"chapter/section": index}``, 1-based, in parody.yaml order."""
    out = {}
    for chapter in project.chapters:
        for slug in chapter.section_slugs:
            out[f"{chapter.slug}/{slug}"] = len(out) + 1
    return out


def build_inventory(project_dir, build_dir, published_pdf):
    """Build the marked English and read back where every sentence fell."""
    from ..config import load_project
    from ..writers.latex import build_pdf
    from .marks import _value, mark_section

    project = load_project(project_dir)
    index = section_indices(project)
    by_path = {}
    for chapter in project.chapters:
        for slug in chapter.section_slugs:
            by_path[(chapter.directory / f"{slug}.md").resolve()] = index[f"{chapter.slug}/{slug}"]

    def hook(md_path, body):
        i = by_path.get(Path(md_path).resolve())
        return mark_section(body, i) if i else body

    def prefix(md_path):
        # The section's counters, logged before its \input: ahead of the
        # \section the build writes for a section titled in front matter,
        # which precedes every mark in the body. The first log of a value
        # wins, so the head mark's own log comes too late to count. The % keeps
        # the line end out of the previous section's paragraph, still open here.
        i = by_path.get(Path(md_path).resolve())
        return f"\\parodysctr{{{_value(i, 0, 0)}}}%" if i else ""

    # Every other option as the ordinary build has it (page map included), so
    # the only difference from the published PDF is the marks themselves.
    build_dir = Path(build_dir)
    marked = build_pdf(project_dir, output_pdf=build_dir / "marked.pdf", build_dir=build_dir,
                       section_hook=hook, extra_support=TWINMARKS_SUPPORT,
                       extra_flags=[TWINMARKS_FLAG], section_prefix=prefix)
    if marked is None:
        raise RuntimeError("the marked English build produced no PDF (is TeX installed?)")
    return Inventory(
        rows=read_rows(build_dir / "main.twin"),
        counters=read_counters(build_dir / "main.twinctr"),
        section_index=index,
        marked_pdf=Path(marked),
        mismatched_pages=compare_pages(published_pdf, marked),
    )
