"""Section → print-PDF page ranges.

The print PDF is built once; each section's PDF is the page range cut out of
it, never a separate compilation. A separately compiled section would start at
page 1, replace the book's float placement, and reset every counter, which
destroys the property the feature exists for: print one section at a time and
it becomes the whole book.

This module owns the three steps that turn a LaTeX build into a range table:

    insert_section_mark   place a \\parodypagemark in a generated section .tex
    read_pagemap          read the marks' absolute pages back out of main.aux
    build_ranges          turn start pages into inclusive [start, end] ranges
"""

import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path

# print.lua's headerer_latex emits these; \lab is the MIT-class-private lab
# heading. Longer names first so \subsection is not matched as \section.
_SECTIONING = re.compile(
    r"\\(?:subsubsection|subsection|section|chapter|lab)\*?\s*(?=[\[{])")


def _skip_group(tex, i, open_ch, close_ch):
    """Index just past the balanced group starting at ``i``, or None.

    Honours TeX escaping: ``\\{`` is a literal brace, not a nesting level.
    """
    if i is None or i >= len(tex) or tex[i] != open_ch:
        return None
    depth = 0
    while i < len(tex):
        c = tex[i]
        if c == "\\":
            i += 2  # an escaped character, whatever it is
            continue
        if c == open_ch:
            depth += 1
        elif c == close_ch:
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return None


def insert_section_mark(tex, key):
    """Return ``tex`` with ``\\parodypagemark{key}`` after its first heading.

    The mark must land *after* the sectioning command, not before it: a mark in
    vertical mode ahead of a heading can be carried to the previous page by the
    page builder, which would start the range one page late and silently drop
    the section's first page. After the heading it always reports the page the
    heading itself landed on.

    Sections with no heading of their own (#576) take the mark at the top,
    which is the correct start for them.
    """
    mark = "\\parodypagemark{%s}" % key
    m = _SECTIONING.search(tex)
    if m is None:
        return mark + "%\n" + tex
    i = m.end()
    if i < len(tex) and tex[i] == "[":
        i = _skip_group(tex, i, "[", "]")
    i = _skip_group(tex, i, "{", "}")
    if i is None:
        return mark + "%\n" + tex
    return tex[:i] + mark + tex[i:]


# zref-abspage writes one record per mark. \page is the PRINTED page number
# (roman in front matter, restarted at \mainmatter); \abspage is the physical
# one. Extraction needs the physical one.
_ZREF_RECORD = re.compile(
    r"\\zref@newlabel\{parodypage@(?P<key>[^}]*)\}\{(?P<body>[^\n]*)\}")
_ABSPAGE = re.compile(r"\\abspage\{(\d+)\}")


def read_pagemap(aux_path):
    """``{key: absolute page}`` for every page mark recorded in ``main.aux``.

    Returns ``{}`` when the aux file is absent — a build that skipped LaTeX
    (no latexmk installed) must degrade to "no page map", never to a crash.
    """
    path = Path(aux_path)
    if not path.is_file():
        return {}
    text = path.read_text(encoding="utf-8", errors="replace")
    pages = {}
    for m in _ZREF_RECORD.finditer(text):
        abspage = _ABSPAGE.search(m.group("body"))
        if abspage:
            pages[m.group("key")] = int(abspage.group(1))
    return pages


def build_ranges(order, pages, end_page):
    """Inclusive ``[start, end]`` page ranges, keyed ``"<chapter>/<section>"``.

    ``pages`` holds both marks per section: ``key`` (at the heading) and
    ``key@end`` (after the section's last content).

    The end is ``max(own_end, next_start - 1)``, which threads between two
    failure modes:

    - Taking ``next_start`` outright would be wrong at a chapter boundary.
      ``\\chapter`` forces a page break, so the next section's first page can
      belong wholly to it — the last section of every chapter would end with
      the *next* chapter's title page.
    - Taking ``own_end`` outright would drop the blank verso pages between a
      section's last page and the next chapter's opening, so printing every
      section would no longer reassemble the book.

    So: when a section genuinely shares its last sheet with the next one,
    ``own_end == next_start`` and both PDFs carry that sheet — the duplication
    the task accepts. When it does not, the range stops just short of the next
    section, still covering any blank pages in between.

    Sections whose mark never reached the aux (a build error, a section that
    emitted nothing) are omitted rather than guessed at.
    """
    known = [k for k in order if k in pages]
    ranges = {}
    for i, key in enumerate(known):
        start = pages[key]
        own_end = pages.get(f"{key}@end", start)
        if i + 1 < len(known):
            end = max(own_end, pages[known[i + 1]] - 1)
        else:
            end = max(own_end, end_page)
        # max(): a backwards end would mean a stale aux; clamp rather than
        # emit an inverted range the slicer would reject.
        ranges[key] = [start, max(start, end)]
    return ranges


SIDECAR_SCHEMA = 1


def pdf_page_count(pdf_path):
    """Page count via poppler's ``pdfinfo``, or None when it is unavailable.

    poppler is already a build dependency (content-repo CI installs
    poppler-utils for figure conversion). A missing pdfinfo degrades the
    sidecar's ``pages`` field to null; the ranges are unaffected.
    """
    exe = shutil.which("pdfinfo")
    if not exe:
        return None
    try:
        out = subprocess.run([exe, str(pdf_path)], capture_output=True,
                             text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None
    for line in out.stdout.splitlines():
        if line.startswith("Pages:"):
            try:
                return int(line.split(":", 1)[1].strip())
            except ValueError:
                return None
    return None


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sidecar_path(pdf_path):
    """Where the page map for ``pdf_path`` lives: book.pdf → book.pages.json."""
    return Path(pdf_path).with_suffix(".pages.json")


def write_sidecar(pdf_path, ranges, cloze_mode="blank", solutions=False):
    """Write the page-map sidecar beside the PDF. Returns its path."""
    pdf_path = Path(pdf_path)
    path = sidecar_path(pdf_path)
    payload = {
        "schema": SIDECAR_SCHEMA,
        "pdf": pdf_path.name,
        "pages": pdf_page_count(pdf_path),
        "sha256": sha256_file(pdf_path),
        "cloze_mode": cloze_mode,
        "solutions": bool(solutions),
        "sections": ranges,
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path
