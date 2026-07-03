"""Measure parity between a parody-built PDF and a reference (original) PDF.

The goal (see the "second printing" use case) is to tell how close the parody
output is to the original and, more usefully, to surface *where* they differ so
the differences can be triaged into intentional changes (errata, content edits)
versus regressions (conversion/rendering bugs).

Approach — page numbers shift between the two, so nothing is aligned by page:

1. Extract text from both PDFs with ``pdftotext``.
2. Split each into sections by detecting numbered headings ("3.7 The root
   locus", "L2.1 Introduction", ...).
3. Align sections between the two by normalized title (titles are stable even
   when numbering shifts or prose is edited).
4. Report, per aligned section, a text-similarity ratio; list sections that are
   missing / extra / low-similarity for review.
5. Report structural counts (captioned figures/tables, problems, algorithms,
   listings, boxes, examples) as a coarse "nothing dropped" check.

This is a triage aid, not a pass/fail gate: differences are expected.
"""

from __future__ import annotations

import difflib
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

# A heading line: a section number (1, 3.7, 1.14.2, L2.1) then a title, alone on
# the line. Kept fairly strict (title starts uppercase, not too long) to avoid
# catching cross-references or prose that merely begins with a number.
_HEADING = re.compile(r"^(L?\d+(?:\.\d+){0,3})\s+([A-Z][^\n]{0,75})$")

# Caption / labelled-object patterns for the structural counts. Figures and
# tables are counted by their caption ("Figure 3.2 ..." / "Table 3.2 ..."); the
# xsim/theorem-like objects by their run-in label.
_STRUCTURAL = {
    "figure": re.compile(r"\bFigure\s+\d+\.\d+\b"),
    "table": re.compile(r"\bTable\s+\d+\.\d+\b"),
    "problem": re.compile(r"\bProblem\s+L?\d+\.\d+\b"),
    "algorithm": re.compile(r"\bAlgorithm\s+\d+\.\d+\b"),
    "listing": re.compile(r"\bListing\s+\d+\.\d+\b"),
    "box": re.compile(r"\bBox\s+\d+\.\d+\b"),
    "example": re.compile(r"\bExample\s+\d+\.\d+\b"),
    "equation": re.compile(r"\(\d+\.\d+\)"),
}

# Lines that are running heads / page numbers / other chrome we drop before
# comparing prose, so pagination noise doesn't depress similarity.
_CHROME = re.compile(r"^\s*(\d+|[ivxlc]+)\s*$", re.IGNORECASE)


def _have(tool: str) -> bool:
    return shutil.which(tool) is not None


def extract_text(pdf: Path) -> str:
    """Return the text of *pdf* via pdftotext (raw reading order)."""
    if not _have("pdftotext"):
        raise RuntimeError("pdftotext (poppler) is required for parity checks")
    out = subprocess.run(
        ["pdftotext", "-q", str(pdf), "-"],
        capture_output=True, text=True, check=True,
    )
    return out.stdout


def page_count(pdf: Path) -> int:
    if not _have("pdfinfo"):
        return 0
    out = subprocess.run(["pdfinfo", str(pdf)], capture_output=True, text=True)
    m = re.search(r"^Pages:\s+(\d+)", out.stdout, re.MULTILINE)
    return int(m.group(1)) if m else 0


def structural_counts(text: str) -> dict[str, int]:
    """Count labelled objects. Counts *mentions*, so ref/candidate are only
    comparable to each other, not an absolute object count."""
    return {name: len(rx.findall(text)) for name, rx in _STRUCTURAL.items()}


@dataclass
class Section:
    number: str
    title: str
    body: str = ""
    page: int = 1  # 1-based page the heading falls on (for the visual pass)

    @property
    def key(self) -> str:
        """Alignment key: normalized title (numbering may differ)."""
        return _norm_title(self.title)


def _norm_title(title: str) -> str:
    t = re.sub(r"\s+", " ", title).strip().lower()
    # drop trailing page-number dots/leaders a TOC line might carry
    t = re.sub(r"[.\s]+\d*$", "", t)
    return t


def _looks_like_title(title: str) -> bool:
    """Reject body lines that merely start like a heading (table rows, hex
    dumps, values): real titles carry a lowercase letter and don't end in
    sentence/label punctuation."""
    t = title.strip()
    return bool(re.search(r"[a-z]", t)) and not t.endswith((".", ":", ";", ","))


def split_sections(text: str) -> list[Section]:
    """Split *text* into sections at numbered headings, tracking the page each
    heading falls on (pdftotext separates pages with form feeds). Text before
    the first heading is attached to a synthetic front section."""
    sections: list[Section] = [Section("", "(front matter)")]
    for pageno, page_text in enumerate(text.split("\f"), start=1):
        for line in page_text.splitlines():
            m = _HEADING.match(line.rstrip())
            if m and _looks_like_title(m.group(2)):
                sections.append(Section(m.group(1), m.group(2).strip(),
                                        page=pageno))
            else:
                sections[-1].body += line + "\n"
    return sections


def _tokens(body: str) -> list[str]:
    lines = [ln for ln in body.splitlines() if not _CHROME.match(ln)]
    return re.findall(r"[a-z0-9]+", " ".join(lines).lower())


def similarity(a: str, b: str) -> float:
    """Word-level similarity in [0, 1] (difflib ratio, autojunk off)."""
    ta, tb = _tokens(a), _tokens(b)
    if not ta and not tb:
        return 1.0
    if not ta or not tb:
        return 0.0
    return difflib.SequenceMatcher(None, ta, tb, autojunk=False).ratio()


# ----- visual pass: section-aligned page rendering + coarse image diff -------
# Robust to pagination shifts because pages are compared per aligned *section*
# (its heading page), not by absolute page number. Catches layout/figure
# differences that a text diff misses (and vice-versa).

def _render_page(pdf: Path, page: int, dpi: int = 80):
    """Render one PDF page to a PIL grayscale image via pdftoppm."""
    from PIL import Image  # local import: only needed for --visual
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        stem = str(Path(td) / "pg")
        subprocess.run(
            ["pdftoppm", "-r", str(dpi), "-f", str(page), "-l", str(page),
             "-gray", "-png", "-singlefile", str(pdf), stem],
            capture_output=True, check=True,
        )
        return Image.open(stem + ".png").convert("L")


def _page_diff(img_a, img_b) -> float:
    """Mean absolute pixel difference in [0, 1] after scaling both to a common
    small size (structure over detail)."""
    from PIL import Image, ImageChops
    size = (120, 160)
    a = img_a.resize(size, Image.BILINEAR)
    b = img_b.resize(size, Image.BILINEAR)
    hist = ImageChops.difference(a, b).histogram()
    total = sum(value * count for value, count in enumerate(hist))
    return total / (size[0] * size[1] * 255)


@dataclass
class SectionDiff:
    number: str
    title: str
    status: str            # "matched" | "missing" | "extra"
    similarity: float = 1.0
    ref_page: int = 0
    cand_page: int = 0
    visual: float | None = None   # 0 (identical) .. 1 (very different); None if not run


@dataclass
class ParityReport:
    reference: str
    candidate: str
    ref_pages: int
    cand_pages: int
    ref_counts: dict[str, int]
    cand_counts: dict[str, int]
    sections: list[SectionDiff] = field(default_factory=list)

    @property
    def matched(self) -> list[SectionDiff]:
        return [s for s in self.sections if s.status == "matched"]

    @property
    def mean_similarity(self) -> float:
        m = self.matched
        return sum(s.similarity for s in m) / len(m) if m else 0.0


def compare(reference: Path, candidate: Path, low: float = 0.90,
            visual: bool = False) -> ParityReport:
    """Compare *candidate* against *reference*; ``low`` is the similarity below
    which a matched section is flagged. With ``visual``, also render each aligned
    section's heading page in both PDFs and record a coarse image difference."""
    ref_text, cand_text = extract_text(reference), extract_text(candidate)
    ref_secs, cand_secs = split_sections(ref_text), split_sections(cand_text)

    # Align by title. A title can repeat (e.g. "Summary", "Problems" — one per
    # chapter); among same-title candidates pick the one whose section number
    # matches (both books number similarly), so repeats don't cross-pair.
    cand_by_key: dict[str, list[Section]] = {}
    for s in cand_secs:
        cand_by_key.setdefault(s.key, []).append(s)

    diffs: list[SectionDiff] = []
    matched_cand: set[int] = set()
    for rs in ref_secs:
        pool = cand_by_key.get(rs.key)
        if pool:
            exact = [c for c in pool if c.number == rs.number]
            cs = exact[0] if exact else pool[0]
            pool.remove(cs)
            matched_cand.add(id(cs))
            vis = None
            if visual:
                try:
                    vis = _page_diff(_render_page(reference, rs.page),
                                     _render_page(candidate, cs.page))
                except Exception:
                    vis = None
            diffs.append(SectionDiff(rs.number, rs.title, "matched",
                                     similarity(rs.body, cs.body),
                                     ref_page=rs.page, cand_page=cs.page,
                                     visual=vis))
        else:
            diffs.append(SectionDiff(rs.number, rs.title, "missing"))
    for cs in cand_secs:
        if id(cs) not in matched_cand and cs.key:
            diffs.append(SectionDiff(cs.number, cs.title, "extra"))

    return ParityReport(
        reference=str(reference), candidate=str(candidate),
        ref_pages=page_count(reference), cand_pages=page_count(candidate),
        ref_counts=structural_counts(ref_text),
        cand_counts=structural_counts(cand_text),
        sections=diffs,
    )


def format_report(r: ParityReport, low: float = 0.90) -> str:
    lines: list[str] = []
    a = lines.append
    a(f"Parity: {Path(r.candidate).name}  vs  {Path(r.reference).name}")
    a("=" * 66)
    a(f"pages         reference {r.ref_pages:>5}   candidate {r.cand_pages:>5}")
    matched, missing, extra = (
        len(r.matched),
        sum(s.status == "missing" for s in r.sections),
        sum(s.status == "extra" for s in r.sections),
    )
    a(f"sections      matched {matched:>4}   missing {missing:>3}   extra {extra:>3}")
    a(f"mean section text similarity: {r.mean_similarity*100:5.1f}%")
    a("")
    a("structural counts (mentions)      reference  candidate   delta")
    for name in _STRUCTURAL:
        ro, co = r.ref_counts.get(name, 0), r.cand_counts.get(name, 0)
        flag = "" if ro == co else "  <-"
        a(f"  {name:<12}                    {ro:>7}    {co:>7}   {co-ro:>+5}{flag}")
    a("")

    flagged = sorted(
        (s for s in r.matched if s.similarity < low),
        key=lambda s: s.similarity,
    )
    if flagged:
        a(f"low-similarity sections (< {low*100:.0f}%) — review for edits vs bugs:")
        for s in flagged[:40]:
            a(f"  {s.similarity*100:5.1f}%  {s.number:<8} {s.title}")
        if len(flagged) > 40:
            a(f"  ... and {len(flagged) - 40} more")
        a("")
    visual = [s for s in r.matched if s.visual is not None]
    if visual:
        mean_vis = sum(s.visual for s in visual) / len(visual)
        a(f"mean section visual difference: {mean_vis*100:5.1f}%  "
          f"(0% = identical page image)")
        hi = sorted(visual, key=lambda s: -s.visual)
        a("most visually different sections (page layout/figures differ):")
        for s in hi[:20]:
            a(f"  {s.visual*100:5.1f}%  txt {s.similarity*100:4.0f}%  "
              f"p{s.ref_page}/{s.cand_page:<4} {s.number:<8} {s.title[:50]}")
        a("")

    miss = [s for s in r.sections if s.status == "missing"]
    if miss:
        a("sections in reference but not found in candidate:")
        for s in miss[:30]:
            a(f"  {s.number:<8} {s.title}")
        if len(miss) > 30:
            a(f"  ... and {len(miss) - 30} more")
    return "\n".join(lines)
