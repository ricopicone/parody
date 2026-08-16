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

Sources are tracked, built artwork is not::

    figures/<name>.tex        a fragment parody compiles      TRACKED
    figures/<name>.ai         Illustrator artwork             TRACKED
    figures/preamble.tex      the book's drawing vocabulary   TRACKED
    build/figures/<name>.pdf  for print                       gitignored
    build/figures/<name>.svg  for web                         gitignored

Illustrator artwork is a source like any other: a .ai IS a PDF, but one
carrying Illustrator's own private data alongside the drawing, so parody
flattens it rather than copying it (see flatten_pdf).

Figure sources kept beside their section (chapters/<chapter>/<name>.tex) are
still built, in place, so books predating this layout keep working.
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


# Artwork parody passes through rather than compiles. A .ai is a PDF, so both
# reach the same converter; anything else raster stays as it is.
ARTWORK_SUFFIXES = (".ai", ".pdf", ".png", ".jpg", ".jpeg")

FIGURES_DIRNAME = "figures"
BUILD_SUBPATH = ("build", "figures")


def figures_dir(project):
    return Path(project.directory) / FIGURES_DIRNAME


def figures_build_dir(project):
    return Path(project.directory).joinpath(*BUILD_SUBPATH)


def figure_sources(project):
    """Every figure source in the project.

    The canonical home is figures/. Fragments kept beside their section are
    still picked up so books predating that layout keep building.
    """
    out = []
    root = figures_dir(project)
    if root.is_dir():
        for path in sorted(root.iterdir()):
            if path.name == "preamble.tex":
                continue
            if path.suffix == ".tex" and is_fragment(path):
                out.append(path)
            elif path.suffix.lower() in ARTWORK_SUFFIXES:
                out.append(path)
    for chapter in project.chapters:
        for tex in sorted(Path(chapter.directory).glob("*.tex")):
            if is_fragment(tex):
                out.append(tex)
    return out


def output_dir_for(project, source):
    """Where this source's built PDF/SVG belong.

    figures/ sources build into build/figures/, which is gitignored. A source
    still living beside its section builds in place, where that book's
    references already point.
    """
    if source.parent == figures_dir(project):
        return figures_build_dir(project)
    return source.parent


def _needs_build(source, pdf, extra_deps=()):
    if not pdf.is_file():
        return True
    stamp = pdf.stat().st_mtime
    return any(d.stat().st_mtime > stamp
               for d in (source, *extra_deps) if d.is_file())


def build_figure(source, style_dir=SHARED_PROFILE_DIR, extra_preamble="",
                 out_dir=None):
    """Compile one fragment to a PDF. Returns the PDF path or None."""
    # absolute: the compile runs in a temp cwd, so every TEXINPUTS entry
    # derived from this path has to be absolute to resolve
    source = Path(source).resolve()
    out_dir = Path(out_dir).resolve() if out_dir else source.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    pdf = out_dir / (source.stem + ".pdf")
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


def _image_xobjects(path):
    """How many raster images a PDF embeds."""
    d = Path(path).read_bytes()
    return d.count(b"/Subtype /Image") + d.count(b"/Subtype/Image")


def warn_if_rasterized(source, dest):
    """Say so if a conversion turned drawing into pixels.

    Vector art must stay vector: a rasterized figure looks acceptable on
    screen and falls apart in print, and nothing else in the pipeline would
    mention it. Line art gains no raster images; a photo the artwork already
    embedded is not a regression, so compare counts rather than testing for
    any image at all.
    """
    dest = Path(dest)
    if dest.suffix.lower() == ".svg":
        body = dest.read_text(errors="replace")
        if "data:image" in body:
            print(f"⚠️  {dest.name}: the SVG embeds a raster image — vector "
                  "content was rasterized in conversion")
            return True
        # pdftocairo DROPS raster images on the way to SVG rather than
        # embedding them, so a figure that carried a photo comes out as an
        # empty <svg> — the right size and nothing in it. Silent on the web.
        if not any(tag in body for tag in
                   ("<path", "<image", "<text", "<rect", "<circle", "<ellipse",
                    "<line", "<polyline", "<polygon", "<use", "<g ")):
            print(f"⚠️  {dest.name}: the SVG has no drawing in it — the "
                  "converter dropped this figure's content")
            return True
        return False
    before, after = _image_xobjects(source), _image_xobjects(dest)
    if after > before:
        print(f"⚠️  {dest.name}: conversion added {after - before} raster "
              "image(s) — vector content was rasterized")
        return True
    return False


def flatten_pdf(source, dest):
    """Rewrite a PDF-shaped source, dropping what only its editor needs.

    An .ai saved "PDF compatible" carries Illustrator's own PGF stream
    ALONGSIDE the PDF rendering — five AIPrivateData objects and ~250kB of it
    in a drawing whose art is 11kB. Copying the file keeps all of that in the
    book.

    Ghostscript re-writes the page and leaves the private data behind.
    Measured on the electronics artwork: 259kB -> 12kB, and the rendered
    result is identical bar antialiasing (mean pixel delta 0.04, 68 pixels
    differing appreciably at 300dpi). pdftocairo goes smaller still but
    genuinely redraws — mean delta 4.76 with full-scale differences across
    5693 pixels — so it is not used here.

    Returns True when the rewrite happened; False leaves the caller to copy.
    """
    gs = shutil.which("gs", path=_tool_env()["PATH"])
    if not gs:
        return False
    result = subprocess.run(
        [gs, "-q", "-dNOPAUSE", "-dBATCH", "-sDEVICE=pdfwrite",
         # /prepress keeps images and vectors at full fidelity; the win here
         # is dropping the editor's private data, not recompressing art.
         "-dPDFSETTINGS=/prepress",
         # 1.5 keeps transparency NATIVE. Targeting 1.3 or lower makes
         # ghostscript flatten transparency groups, and flattening is where
         # vector art turns into pixels.
         "-dCompatibilityLevel=1.5",
         # If artwork does embed a photo, keep it as it was: no downsampling,
         # no re-encoding to JPEG.
         "-dDownsampleColorImages=false", "-dDownsampleGrayImages=false",
         "-dDownsampleMonoImages=false",
         "-dAutoFilterColorImages=false", "-dAutoFilterGrayImages=false",
         "-dColorImageFilter=/FlateEncode", "-dGrayImageFilter=/FlateEncode",
         f"-sOutputFile={dest}", str(source)],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if result.returncode != 0 or not Path(dest).is_file():
        print(f"⚠️  could not flatten {source.name}, copying as-is"
              f"{': ' + result.stdout.strip()[:120] if result.stdout.strip() else ''}")
        return False
    warn_if_rasterized(source, dest)
    return True


def place_artwork(source, out_dir):
    """Put ready artwork where the built figures live.

    A .ai IS a PDF — Illustrator writes PDF-compatible files — so it becomes
    the figure's .pdf, but flattened first (see flatten_pdf). Anything else is
    copied under its own name.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    is_pdfish = source.suffix.lower() in (".ai", ".pdf")
    suffix = ".pdf" if is_pdfish else source.suffix
    dest = out_dir / (source.stem + suffix)
    if is_pdfish:
        if flatten_pdf(source, dest):
            return dest
    if dest.resolve() != source.resolve():
        shutil.copy2(source, dest)
    return dest


def build_svg(pdf, svg=None):
    """The web form of a built figure. Returns the SVG path or None."""
    from .preview import _normalise_svg_size, _pdf_to_svg

    pdf = Path(pdf)
    if pdf.suffix.lower() != ".pdf":
        return None  # raster artwork is already web-ready
    svg = Path(svg) if svg else pdf.with_suffix(".svg")
    if not _pdf_to_svg(pdf, svg):
        return None
    _normalise_svg_size(svg)
    warn_if_rasterized(pdf, svg)
    return svg


def build_figures(project, force=False, extra_preamble=""):
    """Build every out-of-date figure to PDF + SVG. Returns (built, skipped)."""
    extra_preamble = extra_preamble or book_preamble(project)
    sources = figure_sources(project)
    if any(s.suffix == ".tex" for s in sources) and not have_tool("lualatex"):
        print("⚠️  lualatex not found — standalone figures not rebuilt")
        return [], []
    style = SHARED_PROFILE_DIR / "parody-standalone.sty"
    built, skipped, failed = [], [], []
    for source in sources:
        out_dir = output_dir_for(project, source)
        pdf = out_dir / (source.stem + ".pdf")
        svg = out_dir / (source.stem + ".svg")
        deps = (style,) if source.suffix == ".tex" else ()
        if not force and not _needs_build(source, pdf, deps) and svg.is_file():
            skipped.append(source)
            continue
        if source.suffix == ".tex":
            made = build_figure(source, extra_preamble=extra_preamble,
                                out_dir=out_dir)
        else:
            made = place_artwork(source, out_dir)
        if made:
            build_svg(made, svg)
            built.append(source)
        else:
            failed.append(source)
    if failed:
        # "0 built" alone reads like "nothing to do"; say which ones broke.
        print(f"⚠️  {len(failed)} figure(s) failed to build: "
              + ", ".join(f.name for f in failed[:5])
              + ("…" if len(failed) > 5 else ""))
    return built, skipped
