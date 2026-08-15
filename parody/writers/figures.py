"""Build standalone figures from source, in one house style.

A standalone figure is its own LaTeX document, so left to itself each one
inherits whatever type size its source happened to declare — and a book ends
up with 9pt labels in one figure and 10pt in the next. The only remaining
lever is scaling the finished PDF, which changes a figure's SIZE to fix its
type size.

So parody compiles them itself: a figure source is a bare fragment (a
``tikzpicture``, a ``circuitikz``, whatever draws), and parody supplies the
class and the preamble — ``parody-standalone.sty``, which fixes the type size
at 8pt for every figure in the book. The figure then renders at its natural
size in print, with labels that already match.

Sources live beside the section that uses them, named for the figure they
produce::

    chapters/<chapter>/<name>.tex   ->   chapters/<chapter>/<name>.pdf
"""

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from .latex import SHARED_PROFILE_DIR, _tool_env, have_tool

# A fragment, not a document: parody supplies the class and preamble. A source
# that declares its own \documentclass is a full standalone document already
# and is left alone — rebuilding it would silently drop its preamble.
DOCUMENT_MARKERS = ("\\documentclass", "\\begin{document}")

# The book's preamble comes FIRST — it brings the drawing packages and styles
# the figure is written against, and several of them (circuitikz, pgfplots)
# take options that clash if something loads them first. parody-standalone
# comes LAST so its type size is the one that survives.
WRAPPER = """\\documentclass[border=2pt]{standalone}
%(extra)s\\usepackage{parody-standalone}
\\begin{document}
%(body)s
\\end{document}
"""


def is_fragment(path):
    """Whether this .tex is a bare figure fragment parody should compile."""
    head = Path(path).read_text(encoding="utf-8", errors="replace")[:2000]
    return not any(marker in head for marker in DOCUMENT_MARKERS)


def figure_sources(project):
    """Every figure fragment in the project, in chapter order."""
    out = []
    for chapter in project.chapters:
        for tex in sorted(Path(chapter.directory).glob("*.tex")):
            if is_fragment(tex):
                out.append(tex)
    return out


def _needs_build(source, pdf, extra_deps=()):
    if not pdf.is_file():
        return True
    stamp = pdf.stat().st_mtime
    return any(d.stat().st_mtime > stamp
               for d in (source, *extra_deps) if d.is_file())


def build_figure(source, style_dir=SHARED_PROFILE_DIR, extra_preamble=""):
    """Compile one fragment to a PDF beside it. Returns the PDF path or None."""
    # absolute: the compile runs in a temp cwd, so every TEXINPUTS entry
    # derived from this path has to be absolute to resolve
    source = Path(source).resolve()
    pdf = source.with_suffix(".pdf")
    body = source.read_text(encoding="utf-8").strip()
    doc = WRAPPER % {"body": body,
                     "extra": extra_preamble and extra_preamble + "\n" or ""}

    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        # A fixed name, NOT the source's: TEXINPUTS below puts the figure's own
        # directory on the search path, and kpathsea would resolve <name>.tex
        # back to the raw fragment there instead of the wrapped copy here.
        job = "parody-figure"
        (td / f"{job}.tex").write_text(doc, encoding="utf-8")
        shutil.copy2(style_dir / "parody-standalone.sty",
                     td / "parody-standalone.sty")
        env = _tool_env()
        # the figure's own directory, so a fragment can \input or
        # \includegraphics things that sit next to it
        # the figure's own directory (so a fragment can \input its
        # neighbours), plus the project root and its profile/ — where a book
        # keeps the .sty its figure preamble loads
        roots = [source.parent, source.parent.parent.parent,
                 source.parent.parent.parent / "profile"]
        env["TEXINPUTS"] = (os.pathsep.join(str(r) for r in roots) + os.pathsep
                            + env.get("TEXINPUTS", ""))
        result = subprocess.run(
            ["lualatex", "-interaction=nonstopmode", "-halt-on-error",
             f"{job}.tex"],
            cwd=td, env=env, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True)
        built = td / f"{job}.pdf"
        if not built.is_file():
            tail = "\n".join(result.stdout.splitlines()[-12:])
            print(f"⚠️  figure failed: {source.name}\n{tail}")
            return None
        shutil.copy2(built, pdf)
    return pdf


def book_preamble(project):
    """The book's own figure preamble, if it declares one.

    parody fixes the type size; a book still has its own drawing vocabulary —
    tikz styles, macros, the fonts its figures were drawn with. It points at a
    file holding them:

        figures:
          preamble: figures/preamble.tex

    Injected into every figure build, so a fragment stays a fragment.
    """
    rel = ((project.meta.get("figures") or {}).get("preamble") or "").strip()
    if not rel:
        return ""
    path = (Path(project.directory) / rel).resolve()
    if not path.is_file():
        print(f"⚠️  figures.preamble not found: {rel}")
        return ""
    return "\\input{%s}" % path.as_posix()


def build_figures(project, force=False, extra_preamble=""):
    """Compile every out-of-date figure fragment. Returns (built, skipped)."""
    extra_preamble = extra_preamble or book_preamble(project)
    if not have_tool("lualatex"):
        print("⚠️  lualatex not found — standalone figures not rebuilt")
        return [], []
    style = SHARED_PROFILE_DIR / "parody-standalone.sty"
    built, skipped, failed = [], [], []
    for source in figure_sources(project):
        pdf = source.with_suffix(".pdf")
        if not force and not _needs_build(source, pdf, (style,)):
            skipped.append(source)
            continue
        if build_figure(source, extra_preamble=extra_preamble):
            built.append(source)
        else:
            failed.append(source)
    if failed:
        # "0 built" alone reads like "nothing to do"; say which ones broke.
        print(f"⚠️  {len(failed)} figure(s) failed to build: "
              + ", ".join(f.name for f in failed[:5])
              + ("…" if len(failed) > 5 else ""))
    return built, skipped
