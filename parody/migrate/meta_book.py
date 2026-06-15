"""Meta-book -> parody content-repo migrator.

Reads a meta-based book (chapter order from <book>-0.tex, section order from
chx-*/chx-*.tex wrappers, prose from common/versioned/HASH/source.md with
```include blocks inlined) and writes the parody layout (chapters/<ch>/<sec>.md
+ parody.yaml chapter list) into the destination repo. Rerunnable: wipes
chapters/ first. After any re-run, re-apply the book's re-hash loser list
(parody.migrate.rehash): meta tolerated duplicate short hashes and synthesizes
problems-section hashes from version hashes, both of which collide with
content hashes; schema v2 makes duplicates a build error.

Deliberately not migrated (per the seed plan): front matter, prefaces,
appendices, exams, solutions manuals, book-json/apocrypha versioning (plugin
territory), index see-entries.
"""

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

# Some main-file inputs carry no `% Title` comment; titles come from each
# chapter's header file instead. Two chapter-dir conventions: chx-<slug>
# (math/ec/systems) and chNN (rtc).
CHAPTER_RE = re.compile(
    r"^\\input\{((?:chx-[\w-]+|ch\d+))/\1\}\s*(?:%\s*(.+))?$")
# \chapter[toc][wherein...]{slug}{hash}{Title}: optional args may nest
# brackets ([Notebooks [Outlined]]); anchor on the last three brace groups
CHAPTER_HEADER_RE = re.compile(
    r"\\chapter.*\{([\w-]+)\}\{([\w-]+)\}\{(.+)\}\s*$", re.M)
# bare appendix input (after \appendix): \input{chx-foo} with \chapter inline
APPENDIX_CHAPTER_RE = re.compile(r"^\\input\{(chx-[\w-]+)\}\s*$")
# auto-generated appendix skipped (just \listoffigures/\listoftables)
_SKIP_APPENDIX = {"chx-lists-of-figures-tables"}
INCLUDESECTION_RE = re.compile(r"^\s*\\includesection\{([\w-]+)\}")
EXERCISES_BEGIN_RE = re.compile(r"^\s*\\begin\{exercises\}\{([\w-]+)\}")
EXERCISES_END_RE = re.compile(r"^\s*\\end\{exercises\}")
INPUT_RE = re.compile(r"^\s*\\input\{([\w/-]+)\}")
# some versioned sections open at H2/H3 (e.g. rtc's .ds subsections)
HEADER_RE = re.compile(r"^#{1,3}\s+(.+?)\s*\{([^}]*)\}\s*$")
# both spellings appear: ```include (math/ec) and ```{.include} (rtc)
INCLUDE_BLOCK_RE = re.compile(r"^```\s*(?:include|\{\.include\})\s*$")
# pandoc image/link targets: ](path) or ](path){attrs}
IMAGE_REF_RE = re.compile(r"\]\(([^)\s]+\.(?:pgf|pdf|png|jpg|jpeg|svg|gif))\)")
# extensionless standalone-TikZ refs: ](figures/x/main){... .standalone ...}
STANDALONE_REF_RE = re.compile(r"\]\(([^)\s]+)\)(\{[^}]*\.standalone[^}]*\})")
# algorithm figures: ](figures/x/main){... .algorithm ...} — print splices
# the .tex body; preview displays the .svg sibling
ALGORITHM_REF_RE = re.compile(r"\]\(([^)\s]+)\)(\{[^}]*\.algorithm[^}]*\})")
# raw-LaTeX figure includes surviving in the prose
RAW_GRAPHICS_RE = re.compile(r"(\\includegraphics(?:\[[^]]*\])?)\{([^}]+)\}")
# extensionless image refs relying on TeX extension resolution; restrict to
# paths with a directory component so hash-only anchors are not touched
BARE_REF_RE = re.compile(r"\]\(([\w./-]*/[\w-]+)\)(\{)")
BARE_EXTS = (".pdf", ".png", ".jpg", ".jpeg", ".svg")

FRAGBUILD = Path("/tmp/figbuild/fragments")
FIGBUILD = Path("/tmp/figbuild/common/figures")


def _latex_env():
    from ..writers.latex import _tool_env
    return _tool_env()


def slugify(text):
    text = re.sub(r"\\[a-zA-Z]+", "", text)  # strip latex commands in titles
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text.lower()).strip("-")
    return text or "section"


def first_header_line(text):
    """First live ATX header line (sections may open with raw-latex lines
    like \\clearpage before their header; HTML-commented headings are
    dead and must not define the section identity)."""
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    for line in text.splitlines():
        if HEADER_RE.match(line):
            return line
    return ""


def header_attrs(text):
    """(id, hash) from the body's first attributed H1."""
    m = HEADER_RE.match(first_header_line(text))
    if not m:
        return None, None
    attrs = m.group(2)
    id_m = re.search(r"#([^\s}]+)", attrs)
    h_m = re.search(r'h="?([\w-]+)"?', attrs)
    return (id_m.group(1) if id_m else None), (h_m.group(1) if h_m else None)


def section_slug_and_title(text, h, kind, existing, ch_title):
    if kind == "chapter-tex":
        # whole-chapter appendix body renders under the chapter heading
        return "lead-in", ch_title
    if kind in ("exercises", "exercises-tex"):
        return "problems", "Problems"
    if h.endswith("-lead-in"):
        # lead-in prose renders directly under the chapter heading (no \section)
        return "lead-in", ch_title
    m = HEADER_RE.match(first_header_line(text))
    if m:
        slug, title = slugify(m.group(1)), m.group(1)
    else:
        slug, title = h, h  # headerless non-lead-in section: fall back to hash
    base, n = slug, 2
    while slug in existing:
        slug, n = f"{base}-{n}", n + 1
    return slug, title


def frontmatter(title, slug, sec_id, h):
    meta = {"title": title, "slug": slug, "id": sec_id}
    if h:
        meta["hash"] = h  # meta-book stable short hash (schema v2)
    return "---\n" + yaml.dump(meta, sort_keys=False, allow_unicode=True) + "---\n\n"


def clean_math(text):
    """Fix the math defects the latex-to-md conversion leaves inside
    $$...$$ spans: blank lines (pandoc math cannot span them), nested
    align environments, \\tag misuse, and fused display blocks."""
    def fix(m):
        inner = re.sub(r"\n[ \t]*\n+", "\n", m.group(1))
        inner = re.sub(r"\\(begin|end)\{align\*?\}", r"\\\1{aligned}", inner)
        # \tag is align-only; after the aligned demotion render tags as
        # inline right-side annotations
        inner = re.sub(r"\\tag\{(.+?)\}(?=\s*(?:\\\\|\n|$))",
                       r"\\qquad\\text{(\1)}", inner)
        # the conversion sometimes fuses two display blocks and the prose
        # between them into one span; split at aligned-prose-aligned seams
        inner = re.sub(
            r"(\\end\{aligned\})\n(\s*\S[^\n]*(?:\n(?!\s*\\begin\{aligned\})[^\n]*)*?)\n(\s*\\begin\{aligned\})",
            r"\1$$\n\2\n$$\3", inner)
        return "$$" + inner + "$$"
    return re.sub(r"\$\$(.+?)\$\$", fix, text, flags=re.S)


class MetaBookMigrator:
    def __init__(self, src, dst, salt=None):
        self.src = Path(src)
        self.dst = Path(dst)
        self.salt = salt  # kept for symmetry with rehash; unused here

    # Chapter/section discovery ------------------------------------------

    def find_main_tex(self):
        mains = sorted(self.src.glob("*-0.tex"))
        if len(mains) != 1:
            sys.exit(f"expected exactly one *-0.tex in {self.src}, "
                     f"found {len(mains)}")
        return mains[0]

    def parse_chapters(self):
        """[(chapter_slug, chapter_title, hash, is_appendix, entries)] in
        book order; entry kind is 'section' (payload None), 'exercises'
        (versioned md, None), 'exercises-tex' / 'section-tex' (Path to a
        latex source)."""
        chapters = []
        in_appendix = False
        for line in self.find_main_tex().read_text().splitlines():
            s = line.strip()
            if s == r"\appendix":
                in_appendix = True
                continue
            if s.startswith(r"\backmatter"):
                break
            m = CHAPTER_RE.match(s)
            bm = APPENDIX_CHAPTER_RE.match(s) if in_appendix else None
            if m:
                # dir form: \input{chx-foo/chx-foo} [% Title]; \chapter
                # lives in chx-foo/chx-foo-header.tex
                chx, title = m.group(1), (m.group(2) or "").strip()
                wrapper = self.src / chx / f"{chx}.tex"
                hdr = self.src / chx / f"{chx}-header.tex"
                header_text = hdr.read_text() if hdr.is_file() else ""
            elif bm:
                # bare appendix form: \input{chx-foo}; \chapter is inline in
                # chx-foo.tex (auto-generated lists/glossary skipped)
                chx = bm.group(1)
                if chx in _SKIP_APPENDIX:
                    continue
                wrapper = self.src / f"{chx}.tex"
                if not wrapper.is_file():
                    continue
                header_text = wrapper.read_text()
                title = ""
            else:
                continue
            ch_slug = chx.removeprefix("chx-")
            ch_hash = None
            hm = CHAPTER_HEADER_RE.search(header_text)
            if hm:
                title = hm.group(3)
                ch_hash = hm.group(2)
                if not chx.startswith("chx-"):
                    # numbered chapter dirs (rtc ch01): the real slug
                    # lives in the header's first mandatory arg
                    ch_slug = hm.group(1)
            if not title:
                sys.exit(f"no title found for chapter {chx}")
            entries = []
            lines = wrapper.read_text().splitlines()
            i = 0
            while i < len(lines):
                em = EXERCISES_BEGIN_RE.match(lines[i])
                if em:
                    env_hash = em.group(1)
                    while not EXERCISES_END_RE.match(lines[i]):
                        sm = INCLUDESECTION_RE.match(lines[i])
                        im = INPUT_RE.match(lines[i])
                        if sm:
                            entries.append((sm.group(1), "exercises", None))
                        elif im:
                            tex = self.src / f"{im.group(1)}.tex"
                            has_real = any(
                                re.match(r"^\s*\\begin\{exercise\}", t)
                                for t in tex.read_text().splitlines()
                            )
                            if has_real:
                                entries.append((env_hash, "exercises-tex", tex))
                            else:
                                print(f"  note: {tex.relative_to(self.src)} "
                                      "has no uncommented exercises; skipping")
                        i += 1
                else:
                    sm = INCLUDESECTION_RE.match(lines[i])
                    im = INPUT_RE.match(lines[i])
                    if sm:
                        h = sm.group(1)
                        if not any(h == e[0] for e in entries):
                            entries.append((h, "section", None))
                    elif im and im.group(1).startswith(chx + "/") \
                            and not im.group(1).endswith("-header") \
                            and "exercises" not in im.group(1):
                        # latex-only prose section (rtc):
                        # \input{ch01/memory/memory} -> converter
                        tex = self.src / f"{im.group(1)}.tex"
                        if tex.is_file():
                            entries.append((tex.stem, "section-tex", tex))
                        else:
                            print(f"  warning: section input not found: "
                                  f"{im.group(1)}")
                    i += 1
            # latex-only appendix chapter (no \includesection): convert the
            # whole chapter body as a single lead-in section
            if in_appendix and not entries and bm:
                body = re.sub(r"<!--.*?-->", "", wrapper.read_text(), flags=re.S)
                body = re.sub(r"^\\chapter\b[^\n]*$", "", body, flags=re.M)
                if body.strip():
                    entries.append((ch_hash or ch_slug, "chapter-tex", wrapper))
            chapters.append((ch_slug, title, ch_hash, in_appendix, entries))
        return chapters

    # Figure compilation ---------------------------------------------------

    def compile_tikz_fragment(self, tex_path):
        """Wrap a preamble-less tikz/pgfplots fragment (matlab2tikz output)
        in \\documentclass{standalone} and compile to pdf. Returns the pdf
        Path or None. Cached by source name in FRAGBUILD."""
        workdir = FRAGBUILD / tex_path.stem
        pdf = workdir / "wrap.pdf"
        if pdf.is_file() and pdf.stat().st_mtime >= tex_path.stat().st_mtime:
            return pdf
        workdir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(tex_path, workdir / tex_path.name)
        (workdir / "wrap.tex").write_text(
            "\\documentclass{standalone}\n"
            "\\usepackage{tikz,pgfplots,amsmath}\n"
            "\\pgfplotsset{compat=1.12}\n"
            "\\usetikzlibrary{plotmarks,arrows.meta,positioning}\n"
            "\\begin{document}\n"
            "\\input{" + tex_path.name + "}\n"
            "\\end{document}\n")
        res = subprocess.run(
            ["lualatex", "-interaction=nonstopmode", "wrap.tex"],
            cwd=workdir, env=_latex_env(), capture_output=True, timeout=180,
        )
        if pdf.is_file():
            return pdf
        print(f"  warning: fragment compile failed: {tex_path.name} "
              f"(rc {res.returncode})")
        return None

    def compile_standalone_fig(self, fig_dir):
        """Compile a standalone-TikZ figure dir (main.tex) to main.pdf.

        The latex-to-md filter *generates* these dirs (fresh hash names every
        run) when it extracts figure environments from exercises.tex, so they
        can never be pre-compiled. The templates expect to live under
        common/figures (their relative \\usepackage paths), so build in a
        replicated layout under /tmp/figbuild."""
        target = FIGBUILD / fig_dir.name
        if (fig_dir / "main.pdf").is_file():
            return fig_dir / "main.pdf"
        FIGBUILD.mkdir(parents=True, exist_ok=True)
        if not (FIGBUILD.parent / "styles-tex").is_dir():
            shutil.copytree(self.src / "common" / "styles-tex",
                            FIGBUILD.parent / "styles-tex")
            for sty in (self.src / "common" / "figures").glob("0-standalone-*"):
                dest = FIGBUILD / sty.name
                (shutil.copytree if sty.is_dir() else shutil.copy2)(sty, dest)
        shutil.rmtree(target, ignore_errors=True)
        shutil.copytree(fig_dir, target)
        subprocess.run(
            ["latexmk", "-lualatex", "-shell-escape",
             "-interaction=nonstopmode", "main.tex"],
            cwd=target, env=_latex_env(), capture_output=True,
        )
        built = target / "main.pdf"
        if built.is_file():
            shutil.copy2(built, fig_dir / "main.pdf")
            return fig_dir / "main.pdf"
        return None

    # LaTeX-only exercises --------------------------------------------------

    def convert_exercises_tex(self, tex_path):
        """LaTeX xsim exercises -> markdown .exercise/.solution divs via
        parody's own latex-to-md converter (filters/latex-to-md.lua +
        sectioning pre-pass + math cleanup)."""
        from .latex_to_md import convert_latex_file

        return convert_latex_file(tex_path, self.src)

    # Includes ---------------------------------------------------------------

    def inline_includes(self, md_text, base_dir):
        """Expand ```include blocks (paths relative to the source root,
        fallback to the including file's dir). Returns
        (text, [resolved include dirs])."""
        out, include_dirs = [], []
        lines = md_text.splitlines()
        i = 0
        while i < len(lines):
            if INCLUDE_BLOCK_RE.match(lines[i]):
                i += 1
                while i < len(lines) and lines[i].strip() != "```":
                    rel = lines[i].strip()
                    if rel:
                        path = (self.src / rel) if (self.src / rel).is_file() \
                            else (base_dir / rel)
                        if not path.is_file():
                            # versioned pulls may live in the versionless tree
                            m_v = re.match(
                                r"common/versioned/([\w-]+)/source\.md$", rel)
                            if m_v:
                                alt = (self.src / "versionless" / m_v.group(1)
                                       / "source.md")
                                if alt.is_file():
                                    path = alt
                        if not path.is_file():
                            # dangling in meta too (e.g. source/j3/main.md):
                            # keep going, leave a marker for content triage
                            print(f"  warning: unresolvable include {rel!r} "
                                  f"(from {base_dir}); leaving TODO marker")
                            out.append("<!-- TODO(migration): missing "
                                       f"include {rel} -->")
                        else:
                            inner, dirs = self.inline_includes(
                                path.read_text(), path.parent)
                            out.append(inner)
                            include_dirs.extend([path.parent] + dirs)
                    i += 1
                i += 1  # closing fence
            else:
                out.append(lines[i])
                i += 1
        return "\n".join(out), include_dirs

    # Figures ------------------------------------------------------------------

    def copy_figures(self, text, search_dirs, ch_dir, sec_slug):
        """Copy referenced figure files next to the section md, prefixing with
        the section slug to avoid cross-section collisions; rewrite refs."""
        def repl(m):
            ref = m.group(1)
            for d in search_dirs:
                cand = (d / ref).resolve()
                if cand.is_file():
                    new_name = f"{sec_slug}-{cand.name}"
                    shutil.copy2(cand, ch_dir / new_name)
                    # meta keeps browser-renderable .svg siblings beside .pgf
                    # sources; ship them so preview/site needn't recompile
                    sib = cand.with_suffix(".svg")
                    if cand.suffix == ".pgf" and sib.is_file():
                        shutil.copy2(sib, ch_dir / f"{sec_slug}-{sib.name}")
                    return f"]({new_name})"
            print(f"  warning: figure not found, ref left as-is: {ref}")
            return m.group(0)

        def repl_algorithm(m):
            ref, attrs = m.group(1), m.group(2)
            base = re.sub(r"\.(tex|svg)$", "", ref)
            for d in search_dirs:
                cand = (d / (base + ".tex")).resolve()
                if cand.is_file():
                    new_name = f"{sec_slug}-{cand.parent.name}-{cand.stem}"
                    shutil.copy2(cand, ch_dir / f"{new_name}.tex")
                    svg = cand.with_suffix(".svg")
                    if svg.is_file():
                        shutil.copy2(svg, ch_dir / f"{new_name}.svg")
                    return f"]({new_name}){attrs}"
            print(f"  warning: algorithm source not found: {ref}")
            return m.group(0)

        def repl_standalone(m):
            # The ancestor compiles standalone TikZ sources separately; ship
            # the committed .pdf and keep the ref extensionless so the
            # profile's \includestandalone fallback resolves it.
            ref, attrs = m.group(1), m.group(2)
            for d in search_dirs:
                cand = (d / (ref + ".pdf")).resolve()
                if cand.is_file():
                    new_name = f"{sec_slug}-{cand.parent.name}-{cand.stem}"
                    shutil.copy2(cand, ch_dir / f"{new_name}.pdf")
                    return f"]({new_name}){attrs}"
            # the latex-to-md filter extracts figure envs into
            # figures_converted/<hash>/main.tex (complete standalone docs);
            # refs keep the figures/ prefix. Compile the dir in place.
            if ref.startswith("figures/"):
                conv = (self.src / "figures_converted"
                        / ref[len("figures/"):]).resolve()
                if conv.name == "main" and (conv.parent / "main.tex").is_file():
                    pdf = self.compile_standalone_fig(conv.parent)
                    if pdf:
                        new_name = f"{sec_slug}-{conv.parent.name}-main"
                        shutil.copy2(pdf, ch_dir / f"{new_name}.pdf")
                        return f"]({new_name}){attrs}"
            # no committed pdf: some are flat matlab2tikz fragments (no
            # preamble); wrap and compile one-off
            for d in search_dirs:
                cand = (d / (ref + ".tex")).resolve()
                if cand.is_file():
                    pdf = self.compile_tikz_fragment(cand)
                    if pdf:
                        new_name = f"{sec_slug}-{cand.parent.name}-{cand.stem}"
                        shutil.copy2(pdf, ch_dir / f"{new_name}.pdf")
                        return f"]({new_name}){attrs}"
            print(f"  warning: standalone figure pdf not found: {ref}")
            return m.group(0)

        def repl_raw_standalone(m):
            # raw \includestandalone in prose: ship the committed pdf, emit
            # plain \includegraphics (the profile shim takes no standalone
            # keys)
            ref = m.group(2)
            for d in search_dirs:
                cand = (d / (ref + ".pdf")).resolve()
                if cand.is_file():
                    new_name = f"{sec_slug}-{cand.parent.name}-{cand.stem}"
                    shutil.copy2(cand, ch_dir / f"{new_name}.pdf")
                    svg = cand.with_suffix(".svg")
                    if svg.is_file():
                        shutil.copy2(svg, ch_dir / f"{new_name}.svg")
                    return f"\\includegraphics{{{new_name}}}"
            for d in search_dirs:
                cand = (d / (ref + ".tex")).resolve()
                if cand.is_file():
                    pdf = self.compile_tikz_fragment(cand)
                    if pdf:
                        new_name = f"{sec_slug}-{cand.parent.name}-{cand.stem}"
                        shutil.copy2(pdf, ch_dir / f"{new_name}.pdf")
                        return f"\\includegraphics{{{new_name}}}"
            print(f"  warning: raw includestandalone not found: {ref}; "
                  "TODO marker")
            return f"\\textbf{{[TODO(migration): missing figure {ref}]}}"

        def repl_raw(m):
            cmd, ref = m.group(1), m.group(2)
            if ref.startswith(sec_slug + "-"):
                return m.group(0)  # already localized by an earlier pass
            # extensionless raw includes rely on TeX extension resolution
            exts = ("",) if "." in ref.rsplit("/", 1)[-1] else ("",) + BARE_EXTS
            for d in search_dirs:
                for ext in exts:
                    cand = (d / (ref + ext)).resolve()
                    if cand.is_file():
                        new_name = f"{sec_slug}-{cand.name}"
                        shutil.copy2(cand, ch_dir / new_name)
                        sib = cand.with_suffix(".svg")
                        if cand.suffix in (".pdf", ".pgf") and sib.is_file():
                            shutil.copy2(sib, ch_dir / f"{sec_slug}-{sib.name}")
                        return f"{cmd}{{{new_name}}}"
            # some assets ship only as <name>_source.pdf (the publishable
            # export); fall back to it (rtc Lab5_Drwg_1a)
            stem = re.sub(r"\.pdf$", "", ref)
            for d in search_dirs:
                cand = (d / (stem + "_source.pdf")).resolve()
                if cand.is_file():
                    new_name = f"{sec_slug}-{Path(stem).name}.pdf"
                    shutil.copy2(cand, ch_dir / new_name)
                    return f"{cmd}{{{new_name[:-4]}}}"
            print(f"  warning: raw graphics not found: {ref}; TODO marker")
            return f"\\textbf{{[TODO(migration): missing figure {ref}]}}"

        def repl_bare(m):
            ref, brace = m.group(1), m.group(2)
            if "." in ref.rsplit("/", 1)[-1]:
                return m.group(0)  # extensioned: handled by the other passes
            if ref.rsplit("/", 1)[-1].startswith(sec_slug + "-"):
                return m.group(0)  # already localized
            for d in search_dirs:
                for ext in BARE_EXTS:
                    cand = (d / (ref + ext)).resolve()
                    if cand.is_file():
                        new_name = f"{sec_slug}-{cand.name}"
                        shutil.copy2(cand, ch_dir / new_name)
                        return f"]({new_name}){brace}"
            print(f"  warning: extensionless figure not found: {ref}")
            return m.group(0)

        def localize_tex_asset(cand, new_name):
            """Copy a .tex asset, rewriting its internal \\input refs to
            co-located slug-prefixed copies (ancestor-layout paths don't
            exist in the build tree). Recurses one asset at a time."""
            text2 = cand.read_text()

            def inner(m2):
                iref = m2.group(1)
                if iref.startswith(sec_slug + "-"):
                    return m2.group(0)
                for d2 in [cand.parent] + search_dirs:
                    for suf in ("", ".tex"):
                        c2 = (d2 / (iref + suf)).resolve()
                        if c2.is_file() and c2 != cand:
                            # parent-dir prefix: inner figures often share
                            # the outer asset's basename (self-\input loop
                            # otherwise)
                            n2 = f"{sec_slug}-{c2.parent.name}-{c2.name}"
                            if c2.suffix == ".tex":
                                localize_tex_asset(c2, n2)
                            else:
                                shutil.copy2(c2, ch_dir / n2)
                            return f"\\input{{{n2}}}"
                print(f"  warning: nested \\input not found: {iref} "
                      f"(in {cand.name})")
                return m2.group(0)

            text2 = re.sub(r"\\input\{([^}\\]+)\}", inner, text2)
            # meta sectioning commands (\subsection[opts]{slug}{hash}{title})
            # in localized raw-latex assets (e.g. the versions-list parts
            # lists) would mis-render under standard LaTeX and emit no label;
            # rewrite to \<cmd>{title}\label{hash}\label{slug} so hashrefs
            # like [a6] resolve
            def sec_in_asset(sm):
                cmd, slug, h, title = sm.group(1), sm.group(2), sm.group(3), sm.group(4)
                title = " ".join(title.split())
                return (f"\\{cmd}{{{title}}}\\label{{{h}}}"
                        + (f"\\label{{{slug}}}" if slug != h else ""))
            text2 = re.sub(
                r"\\(section|subsection|subsubsection)"
                r"(?:\[[^][]*\]){0,4}"
                r"\{([\w-]+)\}\{([\w-]+)\}\{((?:[^{}]|\{[^{}]*\})*)\}",
                sec_in_asset, text2)
            # resolve figure includes inside the asset too (the ancestor
            # layout's figures/ paths don't exist in the build tree)
            text2 = re.sub(r"\\includestandalone(\[[^]]*\])?\{([^}]+)\}",
                           repl_raw_standalone, text2)
            text2 = RAW_GRAPHICS_RE.sub(repl_raw, text2)
            # these assets are spliced inside exercise/example boxes where
            # floats are illegal ("not in outer par mode"); de-float them
            text2 = re.sub(r"\\begin\{figure\}(\[[^]]*\])?",
                           r"\\begin{center}", text2)
            text2 = text2.replace("\\end{figure}", "\\end{center}")
            text2 = text2.replace("\\caption{", "\\captionof{figure}{")
            (ch_dir / new_name).write_text(text2)

        def repl_input(m):
            ref = m.group(1)
            if ref.startswith(sec_slug + "-"):
                return m.group(0)  # already localized
            for d in search_dirs:
                for suffix in ("", ".tex"):
                    cand = (d / (ref + suffix)).resolve()
                    if cand.is_file():
                        new_name = f"{sec_slug}-{cand.name}"
                        if cand.suffix == ".tex":
                            localize_tex_asset(cand, new_name)
                        else:
                            shutil.copy2(cand, ch_dir / new_name)
                        local = new_name[:-4] if new_name.endswith(".tex") \
                            else new_name
                        return f"\\input{{{local}}}"
            print(f"  warning: raw \\input target not found: {ref}")
            return m.group(0)

        def candidate_refs(ref):
            yield ref
            # some figure sources moved to figures_converted/ during the
            # ancestor's own markdown conversion; the refs kept figures/
            if ref.startswith("figures/"):
                yield "figures_converted/" + ref[len("figures/"):]

        def repl_html_img(m):
            # exercise conversion sometimes emits figures as raw HTML <img>;
            # same standalone resolution (the committed sibling .pdf), with
            # on-the-fly compilation for filter-generated figure dirs
            for r in candidate_refs(m.group(1)):
                for d in search_dirs:
                    for suffix in ("", ".pdf"):
                        cand = (d / (r + suffix)).resolve()
                        if cand.is_file() and cand.suffix == ".pdf":
                            new_name = (f"{sec_slug}-{cand.parent.name}-"
                                        f"{cand.stem}")
                            shutil.copy2(cand, ch_dir / f"{new_name}.pdf")
                            return f'<img src="{new_name}"'
                    tex_cand = (d / (r + ".tex")).resolve()
                    if tex_cand.is_file():
                        pdf = self.compile_standalone_fig(tex_cand.parent)
                        if pdf:
                            new_name = f"{sec_slug}-{pdf.parent.name}-main"
                            shutil.copy2(pdf, ch_dir / f"{new_name}.pdf")
                            return f'<img src="{new_name}"'
            print(f"  warning: html img not found: {m.group(1)}")
            return m.group(0)

        text = re.sub(r'<img src="([^"]+)"', repl_html_img, text)
        text = ALGORITHM_REF_RE.sub(repl_algorithm, text)
        text = STANDALONE_REF_RE.sub(repl_standalone, text)
        text = re.sub(r"\\includestandalone(\[[^]]*\])?\{([^}]+)\}",
                      repl_raw_standalone, text)
        text = RAW_GRAPHICS_RE.sub(repl_raw, text)
        text = re.sub(r"\\input\{([^}]+)\}", repl_input, text)
        text = IMAGE_REF_RE.sub(repl, text)
        text = BARE_REF_RE.sub(repl_bare, text)

        # Anything still pointing into the meta figure tree was unresolvable
        # (source never committed); neutralize so LaTeX doesn't die on it.
        def neutralize(m):
            ref = m.group(1)
            print(f"  warning: missing figure replaced with TODO marker: {ref}")
            return f"**[TODO(migration): missing figure {ref}]**"

        return re.sub(
            r"!\[(?:[^][]|\[[^]]*\])*\]\(((?:common/)?figures/[^)]+)\)(\{[^}]*\})?",
            neutralize, text)

    # Top level -------------------------------------------------------------

    def run(self):
        chapters_dir = self.dst / "chapters"
        if chapters_dir.exists():
            shutil.rmtree(chapters_dir)

        yaml_chapters = []
        n_sections = 0
        for ch_slug, ch_title, ch_hash, is_appendix, entries in \
                self.parse_chapters():
            if not entries:
                # latex-only appendices (whole-chapter prose, no
                # \includesection) aren't migrated yet — skip rather than
                # emit an empty chapter
                print(f"  note: chapter {ch_slug} has no includesection "
                      "entries (latex-only); skipping")
                continue
            ch_dir = chapters_dir / ch_slug
            ch_dir.mkdir(parents=True)
            slugs = []
            for h, kind, payload in entries:
                if kind in ("exercises-tex", "section-tex", "chapter-tex"):
                    text = self.convert_exercises_tex(payload)
                    # the converter emits ```include fences for versioned
                    # pulls; inline them like any other include
                    text, extra_dirs = self.inline_includes(
                        text, payload.parent)
                    include_dirs = [payload.parent] + extra_dirs
                else:
                    # rtc keeps hardware-version-independent sections in a
                    # separate versionless/ tree
                    candidates = [
                        self.src / "common" / "versioned" / h / "source.md",
                        self.src / "versionless" / h / "source.md",
                    ]
                    src_md = next((c for c in candidates if c.is_file()), None)
                    if src_md is None:
                        sys.exit(f"missing versioned section {h} "
                                 f"(chapter {ch_slug})")
                    text, include_dirs = self.inline_includes(
                        src_md.read_text(), src_md.parent)
                    include_dirs = [src_md.parent] + include_dirs
                from .latex_to_md import normalize_lexers
                text = normalize_lexers(text)
                slug, title = section_slug_and_title(
                    text, h, kind, slugs, ch_title)
                if kind in ("exercises", "exercises-tex") \
                        and not first_header_line(text):
                    text = (f'# Problems {{#{ch_slug}-problems h="{h}"}}'
                            f'\n\n{text}')
                # the meta build resolved figure refs against several roots;
                # try them in the same precedence (common/ holds the book
                # figures)
                search_dirs = include_dirs + [
                    self.src / "common", self.src, self.src / "source",
                    self.src / "common" / "figures",
                    self.src / "common" / "versioned",  # ../../common/... refs
                ]
                text = self.copy_figures(text, search_dirs, ch_dir, slug)
                sec_id, h_attr = header_attrs(text)
                # chapter-tex lead-ins render under the chapter heading; the
                # chapter owns the hash, so don't duplicate it on the section
                sec_hash = None if kind == "chapter-tex" else (h_attr or h)
                fm = frontmatter(
                    title, slug, sec_id or f"sec-{ch_slug}-{slug}", sec_hash
                )
                (ch_dir / f"{slug}.md").write_text(fm + text.rstrip() + "\n")
                slugs.append(slug)
                n_sections += 1
            entry = {"slug": ch_slug, "title": ch_title, "sections": slugs}
            if ch_hash:
                entry["hash"] = ch_hash  # chapter-level hashref target
            if is_appendix:
                entry["appendix"] = True
            yaml_chapters.append(entry)

        self.assign_generated_hashes()
        has_apocrypha = self.copy_apocrypha()

        cfg_path = self.dst / "parody.yaml"
        cfg = yaml.safe_load(cfg_path.read_text())
        cfg["chapters"] = yaml_chapters
        if has_apocrypha:
            cfg["apocrypha"] = True  # enable the apocrypha plugin
        cfg_path.write_text(yaml.dump(cfg, sort_keys=False, allow_unicode=True))

        bib = self.src / "common" / "book.bib"
        if bib.is_file():
            shutil.copy2(bib, self.dst / "book.bib")

        # hardware-versioning DB for the versioning plugin (.yaml: the
        # ancestor's json is hand-edited with trailing commas, YAML-only)
        versions = self.src / "common" / "versions.json"
        if versions.is_file():
            shutil.copy2(versions, self.dst / "versions.yaml")

        print(f"migrated {len(yaml_chapters)} chapters, {n_sections} sections")
        return len(yaml_chapters), n_sections

    def copy_apocrypha(self):
        """Convert meta's common/book-json/apocrypha.json (online-only section
        metadata for website TOCs) into a normalized apocrypha.yaml the
        apocrypha plugin surfaces into the artifact. Returns True if written."""
        from ..plugins.apocrypha import normalize_entries

        src = self.src / "common" / "book-json" / "apocrypha.json"
        if not src.is_file():
            return False
        try:
            raw = json.loads(src.read_text())
        except (OSError, ValueError):
            return False
        entries = normalize_entries(raw)
        if not entries:
            return False
        (self.dst / "apocrypha.yaml").write_text(
            yaml.dump(entries, sort_keys=False, allow_unicode=True))
        print(f"copied {len(entries)} apocrypha entries")
        return True

    def assign_generated_hashes(self):
        """Replace the converter's __pg<token> placeholders (headings the
        author didn't hash) with real 2-char hashes, globally collision-free
        against authored hashes and each other. Authored hashes are never
        touched. Deterministic: the same token -> the same hash across
        re-migrations (derived from the token, dedup in stable file order)."""
        from .rehash import fresh_hash, used_hashes

        md_files = sorted((self.dst / "chapters").rglob("*.md"))
        # authored hashes = every h="..."/front-matter hash that ISN'T a
        # placeholder; these are sacrosanct (published permalinks)
        used = {h for h in used_hashes(self.dst) if not h.startswith("__pg")}
        # also avoid authored hashes anywhere in the SOURCE — including
        # commented-out / online-only sections — so generated hashes never
        # collide with a website permalink in the shared QR namespace
        for sf in list(self.src.rglob("source.md")) + list(self.src.rglob("*.tex")):
            try:
                used |= set(re.findall(r'h="([a-z0-9]{2})"', sf.read_text()))
                used |= set(re.findall(r'\}\{([a-z0-9]{2})\}\{', sf.read_text()))
            except (OSError, UnicodeDecodeError):
                pass
        salt = self.dst.name
        n = 0
        for md in md_files:
            text = md.read_text()
            tokens = []
            for t in re.findall(r'h="(__pg[\w]+)"', text):
                if t not in tokens:
                    tokens.append(t)
            if not tokens:
                continue
            for tok in tokens:
                h = fresh_hash(tok, used, salt)  # adds h to `used`
                text = text.replace(f'h="{tok}"', f'h="{h}"')
            md.write_text(text)
            n += len(tokens)
        if n:
            print(f"assigned {n} generated heading hashes (2-char, dedup)")


def migrate_meta_book(src, dst):
    """Convenience wrapper: migrate the meta book at src into the parody
    content repo at dst (must contain parody.yaml)."""
    return MetaBookMigrator(src, dst).run()
