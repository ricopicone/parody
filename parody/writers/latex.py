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
        if candidate.is_dir():
            return candidate
    return Path(profile)


def build_pdf(project_dir, output_pdf=None, solutions=False, section=None,
              profile_dir=None, keep_build=False, build_dir=None):
    """Build the print PDF. Returns the path to the produced PDF.

    section: "chapter-slug/section-slug" builds just that section
    (meta-book's `make section h=...` equivalent).
    """
    # Resolve before anything derives paths: section_to_latex runs pandoc
    # with cwd at the section dir, where relative paths no longer resolve.
    project_dir = Path(project_dir).resolve()
    project = load_project(project_dir)

    from ..plugins import apply_transforms, content_transforms
    transforms = content_transforms(project.meta, project.directory, target="print")
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

    # Convert sections. The filter resolves notebook includes and figure
    # paths against the SOURCE tree (pandoc itself runs in the build dir),
    # so hand it the project/chapter context and an svg-conversion cache.
    # Save/restore so the context never leaks past this build.
    _ctx_keys = ("PARODY_PROJECT_DIR", "PARODY_NOTEBOOK_SLUG",
                 "PARODY_SVG_CACHE", "PARODY_CHAPTER_DIR")
    _saved_env = {k: os.environ.get(k) for k in _ctx_keys}
    os.environ["PARODY_PROJECT_DIR"] = str(project_dir)
    os.environ["PARODY_NOTEBOOK_SLUG"] = project.slug
    os.environ["PARODY_SVG_CACHE"] = str(build_dir / "svg-cache")
    chapters_tex = []
    # chapter_start: the number of the first (non-appendix) chapter (default 1).
    # \chapter increments the counter before printing, so seed it one below the
    # wanted start. \appendix later resets to letter numbering, so this only
    # shifts the main-matter arabic chapters. Skipped for single-section builds
    # (section=...), which emit no \chapter at all.
    chapter_start = int(project.meta.get("chapter_start", 1))
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
                chapters_tex.append(chapter_tex)
            os.environ["PARODY_CHAPTER_DIR"] = str(Path(chapter.directory).resolve())
            for sec_slug in sections:
                src = chapter.directory / f"{sec_slug}.md"
                stripped = build_dir / "sections" / chapter.slug / f"{sec_slug}.md"
                stripped.parent.mkdir(parents=True, exist_ok=True)
                strip_frontmatter(src, stripped, transform=transform)
                tex_path = build_dir / "sections" / chapter.slug / f"{sec_slug}.tex"
                print(f"  pandoc: {chapter.slug}/{sec_slug}.md → .tex")
                section_to_latex(stripped, tex_path, resource_dir=chapter.directory)
                chapters_tex.append(f"\\input{{sections/{chapter.slug}/{sec_slug}.tex}}")
    finally:
        for k, v in _saved_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

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
    if solutions:
        flags.append("\\def\\issolution{1}")

    # Front matter (title/copyright/dedication pages): on by default when the
    # profile ships a front-matter.tex; opt out with `front_matter: false` in
    # parody.yaml. It ends with \tableofcontents; without it we still emit the
    # TOC so the document is never left without one.
    frontmatter = "\\tableofcontents"
    if project.meta.get("front_matter") is not False:
        fm_src = profile_dir / "front-matter.tex"
        if fm_src.exists():
            shutil.copy2(fm_src, build_dir / fm_src.name)
            frontmatter = "\\input{front-matter}"

    template = Template((profile_dir / "main.tex.template").read_text(encoding="utf-8"))
    main_tex = template.safe_substitute(
        flags="\n".join(flags),
        title=project.meta.get("title", project.slug),
        author=" \\and ".join(project.meta.get("author", [])),
        frontmatter=frontmatter,
        chapters="\n".join(chapters_tex),
        bibresource=bibresource,
        bibliography=bibliography,
    )
    (build_dir / "main.tex").write_text(main_tex, encoding="utf-8")

    # latexmk
    env = _tool_env()
    # Section figures (\includegraphics, \inputpgf) stay in the content
    # repo's chapter/assets dirs; let kpathsea find them from the build dir.
    resource_dirs = [str(ch.directory) for ch in project.chapters]
    assets = project_dir / "assets"
    if assets.is_dir():
        resource_dirs.append(str(assets))
    env["TEXINPUTS"] = "." + os.pathsep + os.pathsep.join(resource_dirs) \
        + os.pathsep + env.get("TEXINPUTS", "")
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
    if not keep_build:
        pass  # build dir kept for incremental latexmk runs; it is gitignored
    print(f"PDF written to {output_pdf}")
    return output_pdf
