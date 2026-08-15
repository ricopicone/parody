"""Print-PDF writer (Phase 3).

Pipeline, ported from rtc-book's common.mk + meta-book Makefile:

    section .md --pandoc(-t latex, print.lua, pandoc-crossref, --biblatex)--> .tex
    main.tex template (\\input per section) --latexmk(lualatex, -shell-escape,
    biber)--> PDF

Targets mirror meta-book: full book, solutions manual (\\issolution),
single section. The generic profile (parody/profiles/print/) supplies the
environments; book-private classes/fonts (MIT Press) come from the content
repo via profile_dir override.
"""

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from string import Template

from ..config import load_project
from .pagemap import (build_ranges, insert_section_mark, read_pagemap,
                      write_sidecar)

# tex_math_single_backslash: parse \(...\)/\[...\] as math too (some raw-HTML
# tables write math that way, e.g. \(r(t)\) in cells — without it pandoc escapes
# the backslashes to \textbackslash( and the math leaks as literal text).
PANDOC_FROM = ("markdown-markdown_in_html_blocks+raw_tex+tex_math_dollars"
               "+tex_math_single_backslash")
TEXBIN_FALLBACKS = ["/Library/TeX/texbin", "/usr/local/texlive/bin"]


def _tool_env():
    env = os.environ.copy()
    # minted shells out to pygmentize; when parody runs from an unactivated
    # venv the venv bin (where pygmentize lives) isn't on PATH, so prepend it.
    env["PATH"] = str(Path(sys.executable).parent) + os.pathsep + env["PATH"]
    extra = [p for p in TEXBIN_FALLBACKS if Path(p).is_dir()]
    local_bin = Path.home() / ".local" / "bin"
    if local_bin.is_dir():
        extra.append(str(local_bin))
    if extra:
        env["PATH"] = env["PATH"] + os.pathsep + os.pathsep.join(extra)
    # xsim writes whole exercise/solution bodies as single .xsim lines;
    # big solutions overflow TeX's default input buffer (200k). Web2c
    # texmf.cnf values are overridable via same-name env vars.
    env.setdefault("buf_size", "2000000")
    return env


def have_tool(name):
    return shutil.which(name, path=_tool_env()["PATH"]) is not None


def section_to_latex(section_md, output_tex, resource_dir=None, crossref=True):
    """Convert one section .md to a .tex fragment via pandoc + print.lua."""
    import pypandoc

    filter_path = Path(__file__).parent.parent / "filters" / "print.lua"
    args = [
        f"--lua-filter={filter_path}",
        "--biblatex",
        "-M", "cref=True",
        "--wrap=none",
    ]
    if crossref and have_tool("pandoc-crossref"):
        args += ["-F", shutil.which("pandoc-crossref", path=_tool_env()["PATH"])]
    if resource_dir:
        args += [f"--resource-path={resource_dir}"]
    output_tex = Path(output_tex)
    output_tex.parent.mkdir(parents=True, exist_ok=True)
    # pypandoc needs cwd at the section dir so includes resolve relative paths
    tex = pypandoc.convert_file(
        str(section_md), "latex", format=PANDOC_FROM, extra_args=args,
        cworkdir=str(Path(section_md).parent),
    )
    tex = _externalize_exercise_verbatim(tex, output_tex)
    tex = _detoxify_exercise_longtables(tex)
    output_tex.write_text(tex, encoding="utf-8")
    return output_tex


_EXERCISE_ENV_RE = re.compile(
    r"\\begin\{(exercise|labexercise|solution|labsolution)\}"
    r".*?\\end\{\1\}", re.S)
_MINTED_RE = re.compile(
    r"\\begin\{(minted|listingsbox|listingsboxfloat)\}.*?\\end\{\1\}", re.S)


def _externalize_exercise_verbatim(tex, output_tex):
    """Move minted blocks inside xsim environments to \\input'd side files.

    xsim collects exercise/solution bodies by re-tokenizing them, which
    destroys the line structure verbatim scanning needs — minted inside an
    exercise dies with 'Paragraph ended before \\FV@BeginScanning'. The
    ancestor meta-book avoided this by \\input-ing code from side files;
    do the same mechanically. \\input paths are relative to the latexmk
    cwd (the build dir), two levels up from sections/<ch>/<sec>.tex.
    """
    output_tex = Path(output_tex)
    counter = 0

    def externalize(env_match):
        def to_input(minted_match):
            nonlocal counter
            counter += 1
            side = output_tex.with_name(f"{output_tex.stem}-verb{counter}.tex")
            side.write_text(minted_match.group(0) + "\n", encoding="utf-8")
            rel = f"sections/{output_tex.parent.name}/{side.name}"
            return f"\\input{{{rel}}}"
        return _MINTED_RE.sub(to_input, env_match.group(0))

    return _EXERCISE_ENV_RE.sub(externalize, tex)


# longtable is a page-breaking float-like environment. xsim re-tokenizes an
# exercise body to collect it, and longtable's counter machinery does not
# survive that: the build dies with "No counter 'none' defined" and produces
# no PDF at all. A table inside an exercise should not be page-breaking
# anyway — it is already inside a box that cannot break sensibly.
_LONGTABLE_RE = re.compile(r"\\begin\{longtable\}(\[[^\]]*\])?", re.S)


def _detoxify_exercise_longtables(tex):
    """Turn longtables inside xsim environments into plain tabulars.

    Same failure family as the minted problem above: xsim collects an exercise
    body by re-tokenizing it, which some environments cannot survive. Here the
    build does not just lose the content — it produces no PDF.
    """
    def fix(env_match):
        body = env_match.group(0)
        if "\\begin{longtable}" not in body:
            return body
        body = _LONGTABLE_RE.sub(r"\\begin{tabular}", body)
        body = body.replace("\\end{longtable}", "\\end{tabular}")
        # longtable-only row commands mean nothing to tabular
        for macro in ("\\endfirsthead", "\\endhead", "\\endfoot",
                      "\\endlastfoot"):
            body = body.replace(macro, "")
        return body

    return _EXERCISE_ENV_RE.sub(fix, tex)


def section_frontmatter(md_path):
    """The section's YAML front matter as a dict ({} when it has none)."""
    import yaml

    raw = Path(md_path).read_text(encoding="utf-8")
    if not raw.startswith("---"):
        return {}
    parts = raw.split("---", 2)
    if len(parts) != 3:
        return {}
    try:
        return yaml.safe_load(parts[1]) or {}
    except yaml.YAMLError:
        return {}


# \section / \section* / \lab — the commands print.lua emits for a section's
# OWN heading. \subsection and below are headings WITHIN a section and must not
# be mistaken for one (a book whose sections open with ## would otherwise keep
# losing its titles).
_OWN_HEADING = re.compile(r"\\(?:section\*?|lab)\s*[\[{]")


def synthesize_section_heading(tex, meta, slug):
    """Prepend ``\\section{title}`` when the section carries no heading itself.

    Across parody books a section's title lives in front matter and the
    CONSUMER renders it — parody-web's template does (``title_in_html``). Print
    had no such step, so a book following the convention lost every section
    heading: no title, no TOC entry, subsections dropping to 1.0.x, and no
    \\label, so cross-references to the section dangled.

    Returns ``tex`` unchanged when the section already owns a heading, or when
    it is a chapter lead-in (whose heading is the ``\\chapter`` itself, exactly
    as parody-web renders it).
    """
    if slug == "lead-in" or _OWN_HEADING.search(tex):
        return tex
    title = str(meta.get("title") or "").strip()
    if not title:
        return tex
    heading = "\\section{%s}" % title
    # The same labels headerer_latex hangs off a real heading, so \cref to the
    # section's id or short hash resolves.
    for key in ("id", "hash"):
        value = str(meta.get(key) or "").strip()
        if value and value != slug:
            heading += "\n\\label{%s}" % value
    return heading + "\n\n" + tex


def strip_frontmatter(md_path, dest_path, transform=None):
    """Write a copy of the section with YAML frontmatter removed (pandoc
    would otherwise interpret stray frontmatter keys), applying any
    plugin content transforms."""
    raw = Path(md_path).read_text(encoding="utf-8")
    if raw.startswith("---"):
        parts = raw.split("---", 2)
        if len(parts) == 3:
            raw = parts[2]
    if transform is not None:
        raw = transform(raw)
    Path(dest_path).write_text(raw.strip() + "\n", encoding="utf-8")
    return dest_path


BUNDLED_PROFILES = Path(__file__).parent.parent / "profiles"
# memoir is the foundational house style; `print` remains as the portable
# stock-book fallback, selectable via --profile print.
DEFAULT_PROFILE = "memoir"
# Support files copied into every build dir regardless of profile (the page-map
# package). Leading underscore: not a selectable profile.
SHARED_PROFILE_DIR = BUNDLED_PROFILES / "_shared"


# QR hash sources: external-URL \myurl/\myurlbottom, and \parodyqr{hash} that
# print.lua/build_pdf drop at each chapter/section heading (companion QR).
_QR_HASH = re.compile(
    r"\\myurl(?:bottom)?\*?(?:\[[^\]]*\])*\{[^}]*\}\{([A-Za-z0-9]+)\}"
    r"|\\parodyqr(?:ch|url)?\{([A-Za-z0-9]+)\}")


def _render_qr_codes(build_dir, companion_url):
    """Pre-render a QR image per companion hash used in the build.

    Covers external-URL \\myurl/\\myurlbottom and the per-chapter/section
    \\parodyqr{hash} headings. The qrcode LaTeX package conflicts with hyperref,
    so instead of drawing the QR in TeX we generate a PNG per hash (encoding the
    companion short link ``companion_url/<hash>``) into the build dir; a profile
    places them with ``\\includegraphics{qr-<hash>}``. No-op (with a warning) if
    segno is absent, so print builds never hard-fail on a missing optional dep.
    """
    hashes = set()
    for tex in build_dir.rglob("*.tex"):
        for m in _QR_HASH.finditer(
                tex.read_text(encoding="utf-8", errors="replace")):
            hashes.add(m.group(1) or m.group(2))
    if not hashes:
        return
    try:
        import segno
    except ImportError:
        print("⚠️  segno not installed — printed QR codes omitted "
              "(pip install segno)")
        return
    base = companion_url.rstrip("/")
    for h in sorted(hashes):
        segno.make(f"{base}/{h}", error="m").save(
            str(build_dir / f"qr-{h}.png"), scale=8, border=2)
    print(f"  qr: rendered {len(hashes)} QR code(s)")


def resolve_profile(profile):
    """Resolve a profile selector to a directory.

    None -> the bundled default profile. A bare name (e.g. "memoir") that
    matches a bundled profile dir under parody/profiles/ resolves to it; any
    value containing a path separator (or not matching a bundled name) is
    treated as a filesystem path so book-private profiles still work.
    """
    if profile is None:
        return BUNDLED_PROFILES / DEFAULT_PROFILE
    name = str(profile)
    if os.sep not in name and (os.altsep or os.sep) not in name:
        candidate = BUNDLED_PROFILES / name
        # names starting with "_" are support dirs (e.g. _shared), not profiles
        if candidate.is_dir() and not name.startswith("_"):
            return candidate
    return Path(profile)


_UNDEFINED_REF = re.compile(r"Reference `([^']*)' on page")
_MISSING_CITE = re.compile(r"Citation `([^']*)' on page")


def _report_log_problems(log_path):
    """Say what the finished build still gets wrong.

    latexmk runs in force_mode so the pass sequence completes even when the
    document has non-fatal problems (see the profiles' latexmkrc) — which means
    nothing else would ever mention them. An undefined cross-reference prints
    as ?? in the PDF and is invisible unless someone reads that page.
    """
    log_path = Path(log_path)
    if not log_path.is_file():
        return
    text = log_path.read_text(encoding="utf-8", errors="replace")
    for label, pattern in (("undefined cross-reference", _UNDEFINED_REF),
                           ("missing citation", _MISSING_CITE)):
        names = sorted(set(pattern.findall(text)))
        if names:
            shown = ", ".join(names[:5])
            more = f" …and {len(names) - 5} more" if len(names) > 5 else ""
            print(f"⚠️  {len(names)} {label}(s): {shown}{more}")


def build_pdf(project_dir, output_pdf=None, solutions=False, section=None,
              profile_dir=None, keep_build=False, build_dir=None,
              cloze_mode=None, pagemap=True, edition=None):
    """Build the print PDF. Returns the path to the produced PDF.

    section: "chapter-slug/section-slug" builds just that section
    (meta-book's `make section h=...` equivalent).
    """
    # Resolve before anything derives paths: section_to_latex runs pandoc
    # with cwd at the section dir, where relative paths no longer resolve.
    project_dir = Path(project_dir).resolve()
    project = load_project(project_dir)

    # Editions: reuse build_project's overlay helpers rather than restating the
    # rules, so print and web can never disagree about what an edition contains.
    from ..build import _meta_for_edition, _resolve_section_file
    active_meta = _meta_for_edition(project.meta, edition) if edition \
        else project.meta

    from ..config import resolve_cloze_mode
    cloze_mode = resolve_cloze_mode(active_meta, cloze_mode)

    from ..plugins import apply_transforms, content_transforms
    transforms = content_transforms(active_meta, project.directory, target="print")
    transform = (lambda text: apply_transforms(text, transforms)) \
        if transforms else None

    profile_dir = resolve_profile(profile_dir)

    if build_dir is None:
        build_dir = project_dir / "build" / ("solutions" if solutions else "print")
    build_dir = Path(build_dir)
    build_dir.mkdir(parents=True, exist_ok=True)

    # Profile files into the build dir
    for f in profile_dir.iterdir():
        if f.name != "main.tex.template":
            shutil.copy2(f, build_dir / f.name)

    # Page-map support package, copied in beside the profile's own files. A
    # single-section build has no book to index into, so it never gets one.
    template_text = (profile_dir / "main.tex.template").read_text(encoding="utf-8")
    if pagemap and section:
        pagemap = False
    if pagemap and "$flags" not in template_text:
        print(f"⚠️  profile {profile_dir.name} has no $flags slot — "
              "per-section page map disabled for this build")
        pagemap = False
    if pagemap:
        shutil.copy2(SHARED_PROFILE_DIR / "parody-pagemap.sty",
                     build_dir / "parody-pagemap.sty")

    # Convert sections. The filter resolves notebook includes and figure
    # paths against the SOURCE tree (pandoc itself runs in the build dir),
    # so hand it the project/chapter context and an svg-conversion cache.
    # Save/restore so the context never leaks past this build.
    _ctx_keys = ("PARODY_PROJECT_DIR", "PARODY_NOTEBOOK_SLUG",
                 "PARODY_SVG_CACHE", "PARODY_CHAPTER_DIR",
                 "PARODY_CLOZE_MODE", "PARODY_FIGURES_BUILD")
    _saved_env = {k: os.environ.get(k) for k in _ctx_keys}
    os.environ["PARODY_PROJECT_DIR"] = str(project_dir)
    os.environ["PARODY_NOTEBOOK_SLUG"] = project.slug
    os.environ["PARODY_SVG_CACHE"] = str(build_dir / "svg-cache")
    # print.lua needs the mode only for figure variants; TeX branches on
    # \clozemode for everything else.
    os.environ["PARODY_CLOZE_MODE"] = cloze_mode
    # Where `parody figures` puts what it built. Figures live there for books
    # using the figures/ layout; books whose art still sits beside its section
    # resolve from the chapter dir as before.
    from .figures import figures_build_dir
    _fig_build = figures_build_dir(project)
    os.environ["PARODY_FIGURES_BUILD"] = str(_fig_build) if _fig_build.is_dir() else ""
    chapters_tex = []
    pagemap_order = []  # section keys in book order, for build_ranges
    # chapter_start: the number of the first (non-appendix) chapter (default 1).
    # \chapter increments the counter before printing, so seed it one below the
    # wanted start. \appendix later resets to letter numbering, so this only
    # shifts the main-matter arabic chapters. Skipped for single-section builds
    # (section=...), which emit no \chapter at all.
    chapter_start = int(active_meta.get("chapter_start", 1))
    if chapter_start != 1 and not section:
        chapters_tex.append(f"\\setcounter{{chapter}}{{{chapter_start - 1}}}")
    appendix_started = False
    try:
        for chapter in project.chapters:
            sections = chapter.section_slugs
            if section:
                want_ch, _, want_sec = section.partition("/")
                if chapter.slug != want_ch:
                    continue
                sections = [s for s in sections if s == want_sec]
            if edition:
                # Drop sections this edition does not carry, BEFORE the chapter
                # heading is emitted — a chapter left empty must emit no
                # \chapter at all (build_project drops it the same way).
                sections = [
                    s for s in sections
                    if _resolve_section_file(chapter.directory, s,
                                             edition["id"]) is not None]
            if sections and not section:
                if chapter.appendix and not appendix_started:
                    # switch to A.1/B.1 numbering for the appendix chapters
                    chapters_tex.append("\\appendix")
                    appendix_started = True
                chapter_tex = f"\\chapter{{{chapter.title or chapter.slug}}}"
                chapter_tex += f"\\label{{{chapter.slug}}}"
                if chapter.hash and chapter.hash != chapter.slug:
                    # chapter-level hashref target
                    chapter_tex += f"\\label{{{chapter.hash}}}"
                if chapter.hash:
                    # companion QR at the chapter opening (profile renders it;
                    # \parodyqrch aligns to the tall chapter title, vs sections)
                    chapter_tex += ("\\ifcsname parodyqrch\\endcsname"
                                    f"\\parodyqrch{{{chapter.hash}}}\\fi")
                chapters_tex.append(chapter_tex)
            os.environ["PARODY_CHAPTER_DIR"] = str(Path(chapter.directory).resolve())
            first_in_chapter = bool(sections) and not section
            for sec_slug in sections:
                key = f"{chapter.slug}/{sec_slug}"
                pagemap_order.append(key)
                if edition:
                    # The single-source-until-fork overlay: a per-edition
                    # <slug>.<edition>.md shadows the shared <slug>.md.
                    src = chapter.directory / _resolve_section_file(
                        chapter.directory, sec_slug, edition["id"])
                else:
                    src = chapter.directory / f"{sec_slug}.md"
                stripped = build_dir / "sections" / chapter.slug / f"{sec_slug}.md"
                stripped.parent.mkdir(parents=True, exist_ok=True)
                strip_frontmatter(src, stripped, transform=transform)
                tex_path = build_dir / "sections" / chapter.slug / f"{sec_slug}.tex"
                print(f"  pandoc: {chapter.slug}/{sec_slug}.md → .tex")
                section_to_latex(stripped, tex_path, resource_dir=chapter.directory)
                # The title lives in front matter for books that keep their
                # sections heading-free; print has to render it, or the section
                # arrives with no title, no TOC entry and no cross-ref target.
                tex_path.write_text(
                    synthesize_section_heading(
                        tex_path.read_text(encoding="utf-8"),
                        section_frontmatter(src), sec_slug),
                    encoding="utf-8")
                if pagemap:
                    if first_in_chapter:
                        # Marked at the chapter opening instead, so the range
                        # covers the chapter title page + lead-in prose.
                        chapters_tex.append(f"\\parodypagemark{{{key}}}")
                    else:
                        tex_path.write_text(
                            insert_section_mark(
                                tex_path.read_text(encoding="utf-8"), key),
                            encoding="utf-8")
                first_in_chapter = False
                chapters_tex.append(f"\\input{{sections/{chapter.slug}/{sec_slug}.tex}}")
                if pagemap:
                    # End mark, so a section that does NOT share its last sheet
                    # with the next one (a chapter break forces a new page)
                    # does not swallow the next chapter's opening page.
                    chapters_tex.append(f"\\parodypagemark{{{key}@end}}")
    finally:
        for k, v in _saved_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    if pagemap and chapters_tex:
        # Closes the last section's range at the end of the body, so it stops
        # at the bibliography rather than running through the back matter.
        chapters_tex.append("\\parodypagemark{@end}")

    if not chapters_tex:
        raise SystemExit(f"no sections matched (section={section!r})")

    # Bibliography
    bibresource = ""
    bibliography = ""
    if project.bibliography:
        shutil.copy2(project.bibliography, build_dir / project.bibliography.name)
        bibresource = f"\\addbibresource{{{project.bibliography.name}}}"
        bibliography = "\\printbibliography"

    flags = []
    if pagemap:
        flags.append("\\usepackage{parody-pagemap}")
    if solutions:
        flags.append("\\def\\issolution{1}")
    # Cloze mode is a separate axis from --solutions: a published student book
    # wants clozes filled and exercise solutions hidden.
    flags.append("\\def\\clozemode{%s}" % cloze_mode)

    # Companion-site base URL (book.companion_url in parody.yaml). A profile
    # can use it to build printed QR codes / short links (\companionurl/<hash>).
    book = active_meta.get("book") or {}
    companion_url = book.get("companion_url")
    if companion_url:
        flags.append("\\def\\companionurl{%s}" % companion_url)

    # Front matter (title/copyright/dedication pages): on by default when the
    # profile ships a front-matter.tex; opt out with `front_matter: false` in
    # parody.yaml. It ends with \tableofcontents; without it we still emit the
    # TOC so the document is never left without one.
    frontmatter = "\\tableofcontents"
    if active_meta.get("front_matter") is not False:
        fm_src = profile_dir / "front-matter.tex"
        if fm_src.exists():
            shutil.copy2(fm_src, build_dir / fm_src.name)
            frontmatter = "\\input{front-matter}"

    template = Template((profile_dir / "main.tex.template").read_text(encoding="utf-8"))
    main_tex = template.safe_substitute(
        flags="\n".join(flags),
        title=active_meta.get("title", project.slug),
        author=" \\and ".join(active_meta.get("author", [])),
        frontmatter=frontmatter,
        chapters="\n".join(chapters_tex),
        bibresource=bibresource,
        bibliography=bibliography,
    )
    (build_dir / "main.tex").write_text(main_tex, encoding="utf-8")

    # Pre-render companion QR images now that every .tex (sections + main.tex
    # chapter openings) exists to scan for \myurl / \parodyqr hashes.
    if companion_url:
        _render_qr_codes(build_dir, companion_url)

    # latexmk
    env = _tool_env()
    # Section figures (\includegraphics, \inputpgf) stay in the content
    # repo's chapter/assets dirs; let kpathsea find them from the build dir.
    resource_dirs = [str(ch.directory) for ch in project.chapters]
    if _fig_build.is_dir():
        resource_dirs.insert(0, str(_fig_build))
    assets = project_dir / "assets"
    if assets.is_dir():
        resource_dirs.append(str(assets))
    env["TEXINPUTS"] = "." + os.pathsep + os.pathsep.join(resource_dirs) \
        + os.pathsep + env.get("TEXINPUTS", "")
    # luaotfload resolves \setmainfont{Family} against OSFONTDIR (plus the OS
    # font dirs). Point it at the build dir so fonts a profile bundles there
    # (e.g. a licensed Palatino.ttc copied in with the profile) resolve by
    # family name in ANY environment — notably the Linux print container, where
    # the font is not installed system-wide. Prepend so the bundled font is
    # authoritative, giving identical host/container output.
    env["OSFONTDIR"] = str(build_dir) + os.pathsep + env.get("OSFONTDIR", "")
    if not shutil.which("latexmk", path=env["PATH"]):
        print("⚠️  latexmk not found — wrote LaTeX sources to "
              f"{build_dir}, skipping PDF compilation")
        return None
    result = subprocess.run(
        ["latexmk", "-r", "latexmkrc", "main.tex"],
        cwd=build_dir, env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    produced = build_dir / "main.pdf"
    if result.returncode != 0:
        tail = "\n".join(result.stdout.splitlines()[-30:])
        # A profile may run latexmk in force_mode to push past benign non-fatal
        # errors a custom class emits (e.g. MIT Press's NewMath_MIT), so latexmk
        # can exit nonzero yet still produce a complete PDF. Treat that as a
        # warning; only a missing PDF is fatal.
        if not produced.exists():
            raise RuntimeError(
                f"latexmk failed (exit {result.returncode}):\n{tail}")
        print(f"⚠️  latexmk exited {result.returncode} but produced a PDF; "
              f"continuing. Last output:\n{tail}")
    if output_pdf is None:
        suffix = "-solutions" if solutions else ""
        output_pdf = project_dir / f"{project.slug}{suffix}.pdf"
    output_pdf = Path(output_pdf)
    output_pdf.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(produced, output_pdf)
    _report_log_problems(build_dir / "main.log")

    if pagemap:
        starts = read_pagemap(build_dir / "main.aux")
        end_page = starts.get("@end")
        if end_page is None:
            print("⚠️  no page marks in main.aux — per-section page map "
                  "omitted (rerun the build if this persists)")
        else:
            ranges = build_ranges(pagemap_order, starts, end_page)
            missing = [k for k in pagemap_order if k not in ranges]
            if missing:
                print(f"⚠️  page map: no mark for {len(missing)} section(s): "
                      f"{', '.join(missing[:5])}"
                      f"{'…' if len(missing) > 5 else ''}")
            side = write_sidecar(output_pdf, ranges, cloze_mode=cloze_mode,
                                 solutions=solutions)
            print(f"  pagemap: {len(ranges)} section ranges → {side.name}")
    if not keep_build:
        pass  # build dir kept for incremental latexmk runs; it is gitignored
    print(f"PDF written to {output_pdf}")
    return output_pdf
