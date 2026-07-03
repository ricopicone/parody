"""Find structural-labeling gaps in the markdown source.

The parity check (``parody parity``) shows that the print output has fewer
numbered listings / boxes / equations than the original book — not a rendering
bug, but because the migrated markdown labels less structure. This scans the
source and reports the raw material for closing that gap:

* plain fenced code blocks that are not already listings (candidates to promote
  to a numbered ``listingsbox``),
* display equations written ``$$ ... $$`` (candidates to number as an
  ``equation``/``align`` environment),
* the current callout boxes (``.infobox`` divs, ``\\freadinglist``) as a count
  to compare against the target.

Output is file:line locations so each candidate can be reviewed and promoted by
hand — the decision of what *should* be numbered/boxed is the author's.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

_FENCE = re.compile(r"^(\s*)(`{3,}|~{3,})\s*([A-Za-z][\w+-]*)?\s*$")
# a fenced code block already promoted to a listing (a div wrapper or raw env)
_LISTING_MARK = re.compile(r"listingsbox|\{\.listing\b|\{=latex\}")
_DISPLAY_MATH = re.compile(r"\$\$")
_INFOBOX = re.compile(r"\{[^}]*\.infobox\b")
_FREADING = re.compile(r"\\freadinglist\b")


@dataclass
class Hit:
    path: str
    line: int
    detail: str = ""


@dataclass
class GapReport:
    root: str
    code_fences: list[Hit] = field(default_factory=list)
    display_math: list[Hit] = field(default_factory=list)
    infoboxes: list[Hit] = field(default_factory=list)
    freading: list[Hit] = field(default_factory=list)


def _iter_markdown(root: Path):
    for p in sorted(root.rglob("*.md")):
        if "build/" in p.as_posix():
            continue
        yield p


def _scan_file(path: Path, rel: str, rep: GapReport) -> None:
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    in_fence = False
    fence_marker = ""
    fence_start = 0
    fence_lang = ""
    window = ""  # a few lines around a fence open, to see if it's already a listing
    for i, line in enumerate(lines, start=1):
        # display math: count $$ toggles, record the opener line
        if not in_fence:
            for _ in _DISPLAY_MATH.findall(line):
                pass
        m = _FENCE.match(line)
        if m and (not in_fence or line.strip().startswith(fence_marker)):
            if not in_fence:
                in_fence = True
                fence_marker = m.group(2)[0] * 3
                fence_start = i
                fence_lang = m.group(3) or ""
                window = "\n".join(lines[max(0, i - 3): i + 1])
            else:
                in_fence = False
                # a code block just closed: is it already a listing?
                context = "\n".join(lines[max(0, fence_start - 4): fence_start])
                if not _LISTING_MARK.search(context + "\n" + window):
                    rep.code_fences.append(
                        Hit(rel, fence_start, fence_lang or "text"))
        if in_fence:
            continue
        if _INFOBOX.search(line):
            rep.infoboxes.append(Hit(rel, i))
        if _FREADING.search(line):
            rep.freading.append(Hit(rel, i))

    # display math openers (outside code): pair $$ across the whole file text
    text = path.read_text(encoding="utf-8", errors="replace")
    # remove fenced code so $$ inside code isn't counted
    text_nocode = re.sub(r"(?ms)^\s*(`{3,}|~{3,}).*?^\s*\1.*?$", "", text)
    offs = [m.start() for m in _DISPLAY_MATH.finditer(text_nocode)]
    for k in range(0, len(offs) - 1, 2):  # opener of each $$...$$ pair
        line_no = text_nocode.count("\n", 0, offs[k]) + 1
        rep.display_math.append(Hit(rel, line_no))


def scan(project_dir: Path) -> GapReport:
    root = Path(project_dir)
    src = root / "chapters" if (root / "chapters").is_dir() else root
    rep = GapReport(root=str(src))
    for p in _iter_markdown(src):
        _scan_file(p, p.relative_to(src).as_posix(), rep)
    return rep


def format_gaps(rep: GapReport, limit: int = 25) -> str:
    lines: list[str] = []
    a = lines.append
    a(f"Structural-labeling gaps under {rep.root}")
    a("=" * 66)
    a(f"plain code blocks (candidates for numbered Listings): {len(rep.code_fences)}")
    a(f"display equations $$...$$ (candidates to number)    : {len(rep.display_math)}")
    a(f"existing callout boxes: {len(rep.infoboxes)} .infobox "
      f"+ {len(rep.freading)} further-reading")
    a("")

    def _dump(title: str, hits: list[Hit], show_detail: bool = False):
        if not hits:
            return
        a(f"{title} ({len(hits)}):")
        by_file: dict[str, list[Hit]] = {}
        for h in hits:
            by_file.setdefault(h.path, []).append(h)
        shown = 0
        for path, hs in by_file.items():
            locs = ", ".join(
                (f"{h.line}:{h.detail}" if show_detail and h.detail else str(h.line))
                for h in hs)
            a(f"  {path}: {locs}")
            shown += 1
            if shown >= limit:
                a(f"  ... and {len(by_file) - shown} more files")
                break
        a("")

    _dump("plain code blocks", rep.code_fences, show_detail=True)
    _dump("display equations", rep.display_math)
    return "\n".join(lines)
