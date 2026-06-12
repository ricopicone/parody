"""LaTeX -> markdown conversion for meta-book latex-only sections.

Drives parody's own copy of the meta latex-to-md filter
(filters/latex-to-md.lua — seeded from the math book's most-evolved copy,
with the vestigial luafilesystem require dropped so the pinned pypandoc
binary can run it, deterministic short-hash generation, and \\myindex ->
.index spans). The per-book filter copies this replaces had diverged just
like the migrators had.

Adds a pre-pass for the meta classes' custom sectioning commands, which
plain pandoc mangles (the slug parses as the title and the hash+title fuse
into body text):

- \\section[opts...]{slug}{hash}{Title}   -> ATX header {#slug h="hash"}
  (and the 3-arg \\subsection/\\subsubsection forms, one level down)
- \\subsection{slug}{hash}                -> a ```include fence pulling
  common/versioned/<hash>/source.md: the 2-arg form doesn't carry prose,
  it splices the versioned (markdown-backed) source at build time, so the
  migrator should inline the markdown, not convert generated latex.
"""

import re
from pathlib import Path

FILTER = Path(__file__).parent / "filters" / "latex-to-md.lua"

_SEC_MARK = "PARODYSECATTR"
_INC_MARK = "PARODYVERSIONED"
_PCT_MARK = "PARODYPCT"

# \section / \subsection / \subsubsection / \resource (MIT lab apparatus
# pages, same shape) with 0-4 optional args and the 3-arg
# {slug}{hash}{Title} mandatory tail. Title may span lines and nest one
# brace level.
_SECTION3_RE = re.compile(
    r"\\(section|subsection|subsubsection|resource)"
    r"((?:\[[^][]*(?:\[[^]]*\][^][]*)*\]){0,4})"
    r"\{([\w-]+)\}\{([\w-]+)\}\{((?:[^{}]|\{[^{}]*\})*)\}")
# the 2-arg versioned-pull form: \subsection{slug}{hash} with NO third group
_SECTION2_RE = re.compile(
    r"\\(subsection|subsubsection)\{([\w-]+)\}\{([\w-]+)\}(?!\{)")

# The filter promotes headers by one level (its original exercises.tex
# diet parsed one level deep); emit one level deeper to compensate.
# \section -> H1 is exempt from the promotion.
_LEVEL_CMD = {"section": "section", "subsection": "subsubsection",
              "subsubsection": "paragraph", "resource": "section"}


def _commented(text, pos):
    """True when pos sits on a %-commented line."""
    line_start = text.rfind("\n", 0, pos) + 1
    return text[line_start:pos].lstrip().startswith("%")


def preprocess(tex_text):
    """Normalize meta sectioning commands (markers resolved in
    postprocess) and apply the brace fixes pandoc's latex reader needs
    (\\frac{a}{b} -> \\frac{a} {b}; tabular preamble detached)."""
    def sec3(m):
        if _commented(m.string, m.start()):
            return m.group(0)  # stay commented: markers insert newlines
        cmd, _opts, slug, h, title = m.groups()
        title = " ".join(title.split())
        cls = " resource" if cmd == "resource" else ""
        return (f"\\{_LEVEL_CMD[cmd]}{{{title}}}\n\n"
                f"{_SEC_MARK} {slug} {h}{cls}\n")

    def sec2(m):
        if _commented(m.string, m.start()):
            return m.group(0)
        _cmd, slug, h = m.groups()
        return f"\n{_INC_MARK} {h} {slug}\n"

    tex_text = _SECTION3_RE.sub(sec3, tex_text)
    tex_text = _SECTION2_RE.sub(sec2, tex_text)
    tex_text = re.sub(r"\\(d?frac)\{([^}]+)\}\{([^}]+)\}",
                      r"\\\1{\2} {\3}", tex_text)
    tex_text = tex_text.replace(r"\begin{tabular}{", r"\begin{tabular} {")
    # % inside \mintinline survives pandoc standalone, but inside an
    # unknown raw env (exercise/solution) the reader's comment stripping
    # eats it and mangles the env body; sentinel through the pipeline
    tex_text = re.sub(
        r"(\\mintinline\{\w+\})\{([^}]*)\}",
        lambda m: m.group(1) + "{" + m.group(2).replace("%", _PCT_MARK) + "}",
        tex_text)
    return tex_text


def postprocess(md_text):
    """Resolve the pre-pass markers in the converted markdown and clean up
    the math defects the conversion leaves behind."""
    from .meta_book import clean_math

    lines = md_text.splitlines()
    out = []
    for line in lines:
        # tolerate trailing debris merged into the marker paragraph
        # (e.g. a \label that followed the sectioning command)
        m = re.match(rf"^{_SEC_MARK} (\S+) (\S+)( resource)?\b",
                     line.strip())
        if m:
            slug, h, res = m.groups()
            cls = " .resource" if res else ""
            # attach to the nearest preceding ATX header (skipping blanks)
            for j in range(len(out) - 1, -1, -1):
                if out[j].strip() == "":
                    continue
                if out[j].startswith("#"):
                    out[j] = re.sub(r"\s*\{[^}]*\}\s*$", "", out[j])
                    out[j] += f' {{#{slug}{cls} h="{h}"}}'
                break
            continue
        m = re.match(rf"^{_INC_MARK} (\S+) (\S+)\b", line.strip())
        if m:
            h = m.group(1)
            out.append("```include")
            out.append(f"common/versioned/{h}/source.md")
            out.append("```")
            continue
        out.append(line)
    return clean_math("\n".join(out)).replace(_PCT_MARK, "%")


def convert_latex_file(tex_path, src_root):
    """Convert a meta-book latex-only file to markdown.

    Runs in src_root so the filter can resolve common/figures templates and
    write extracted figure sources to figures_converted/ (deterministic dir
    names; rerunnable)."""
    import pypandoc

    tex_path = Path(tex_path)
    src_root = Path(src_root)
    # the tmp name seeds the filter's deterministic hash generator: it must
    # vary per source file or every conversion shares one hash sequence
    tmp = src_root / f".parody-migrate-{tex_path.stem}.tex"
    tmp.write_text(preprocess(tex_path.read_text()))
    try:
        out = pypandoc.convert_file(
            str(tmp), "markdown", format="latex+raw_tex",
            extra_args=["-s", f"--lua-filter={FILTER}"],
            cworkdir=str(src_root),
        )
    finally:
        tmp.unlink(missing_ok=True)
    return postprocess(out)
