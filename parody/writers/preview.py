"""Standalone static-HTML preview writer.

The artifact's html fields are Django-template-flavored (the schema-v1
quirk): they embed ``{% media %}``, ``{% cite %}`` and friends, which
ricopic.one re-renders through its template engine at view time. The
preview writer resolves those tags itself so a collaborator can review
content with nothing but a browser:

- ``{% media 'p' %}``       → relative ``media/p`` path
- ``{% static 'p' %}``      → relative ``static/p`` path
- ``{% cite 'k' %}`` / ``{% cite_many "a" "b" %}``
                            → citeproc-rendered citation when a .bib is
                              available, ``[k]`` otherwise
- ``{% url ... %}``         → ``#`` (server-side routes don't exist here)
- ``{% auth_button ... %}`` → plain download link (no auth in preview)
- ``{% get_cell ... %}``    → placeholder (per-user table cells are a
                              site-only interactive feature)
- ``{% csrf_token %}``      → removed
"""

import html as html_mod
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

STYLE = """\
body { max-width: 46rem; margin: 2rem auto; padding: 0 1rem;
       font: 1.05rem/1.6 Georgia, 'Times New Roman', serif; color: #1a1a1a; }
nav.crumbs { font-family: system-ui, sans-serif; font-size: .85rem; margin-bottom: 2rem; }
nav.pager { display: flex; justify-content: space-between;
            font-family: system-ui, sans-serif; font-size: .9rem; margin-top: 3rem; }
h1, h2, h3 { font-family: system-ui, sans-serif; line-height: 1.25; }
img.figure-img, img { max-width: 100%; }
pre { background: #f6f6f4; padding: .8rem 1rem; overflow-x: auto;
      font-size: .85rem; line-height: 1.45; }
code { font-size: .9em; }
table { border-collapse: collapse; }
th, td { border: 1px solid #ccc; padding: .3rem .6rem; }
div.exercise { border-left: 3px solid #7a6ff0; padding: .2rem 1rem; margin: 1.5rem 0;
               background: #f8f7ff; }
details.solution { border: 1px solid #d8d4f8; padding: .5rem 1rem; margin: 1rem 0; }
details.solution > summary { cursor: pointer; font-family: system-ui, sans-serif;
                             font-weight: 600; }
span.get-cell-placeholder { color: #999; }
a.download-button { display: inline-block; font-family: system-ui, sans-serif;
                    font-size: .9rem; border: 1px solid #7a6ff0; border-radius: 4px;
                    padding: .25rem .7rem; text-decoration: none; }
div#refs p { margin: .4rem 0; }
"""

MATHJAX = (
    '<script src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-chtml.js" async>'
    "</script>"
)

PAGE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<link rel="stylesheet" href="{prefix}style.css">
{mathjax}
</head>
<body>
{body}
</body>
</html>
"""


def _load_artifact(artifact):
    if isinstance(artifact, dict):
        return artifact
    with open(artifact, encoding="utf-8") as f:
        return json.load(f)


def _collect_cite_keys(artifact):
    keys = []
    seen = set()
    pattern = re.compile(r"\{%\s*cite\s+['\"]([^'\"]+)['\"]\s*%\}|\{%\s*cite_many\s+([^%]+?)\s*%\}")
    for chapter in artifact.get("chapters", []):
        for section in chapter.get("sections", []):
            blobs = [section.get("html", "")]
            blobs += [s.get("content", "") for s in (section.get("solutions") or {}).values()]
            blobs += [
                p.get("content", "") if isinstance(p, dict) else p
                for p in (section.get("problems") or {}).values()
            ]
            for blob in blobs:
                for m in pattern.finditer(blob):
                    if m.group(1):
                        found = [m.group(1)]
                    else:
                        found = re.findall(r"['\"]([^'\"]+)['\"]", m.group(2))
                    for k in found:
                        if k not in seen:
                            seen.add(k)
                            keys.append(k)
    return keys


def _render_citations(keys, bib_path):
    """Map cite key → inline citation HTML via pandoc citeproc; also return
    the rendered bibliography div for the cited keys."""
    if not keys or not bib_path:
        return {}, ""
    import pypandoc

    md = "\n\n".join(f"[@{k}]" for k in keys)
    out = pypandoc.convert_text(
        md, "html", format="markdown",
        extra_args=["--citeproc", f"--bibliography={bib_path}", "--wrap=none"],
    )
    refs_html = ""
    refs_at = out.find('<div id="refs"')
    if refs_at != -1:
        refs_html = out[refs_at:]
        out = out[:refs_at]
    paras = re.findall(r"<p>(.*?)</p>", out, flags=re.DOTALL)
    rendered = dict(zip(keys, paras))
    return rendered, refs_html


def _media_refs(artifact):
    """Every path referenced by a ``{% media %}`` tag anywhere in the artifact."""
    text = json.dumps(artifact)
    return sorted(set(re.findall(r"\{%\s*media\s+['\"]([^'\"]+)['\"]\s*%\}", text)))


_SEARCH_SKIP_DIRS = {"build", "node_modules", "__pycache__"}


def _index_tree(root, exclude):
    """Map basename -> path for every file under root, pruning build trees
    and the preview output itself. Content repos co-locate section assets in
    chapters/<ch>/ rather than a media/ tree, so refs are looked up by name."""
    index = {}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [
            d for d in dirnames
            if d not in _SEARCH_SKIP_DIRS and not d.startswith(".")
            and (Path(dirpath) / d).resolve() != exclude
        ]
        for name in filenames:
            index.setdefault(name, Path(dirpath) / name)
    return index


def _latex_env():
    from .latex import _tool_env
    return _tool_env()


def _pdf_to_svg(pdf_path, svg_path):
    if shutil.which("pdftocairo") is None:
        return False
    res = subprocess.run(
        ["pdftocairo", "-svg", str(pdf_path), str(svg_path)],
        capture_output=True,
    )
    return res.returncode == 0 and svg_path.is_file()


def _pgf_to_svg(pgf_src, svg_path):
    """Compile a (matplotlib-style) .pgf to .svg via standalone lualatex +
    pdftocairo. Raster companions referenced by \\pgfimage are pulled from
    the .pgf's directory."""
    env = _latex_env()
    if shutil.which("lualatex", path=env["PATH"]) is None:
        return False
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        shutil.copy2(pgf_src, td / pgf_src.name)
        pgf_text = pgf_src.read_text(errors="ignore")
        for raster in set(re.findall(r"\\pgfimage(?:\[[^]]*\])?\{([^}]+)\}", pgf_text)):
            for cand in (pgf_src.parent / raster,
                         (pgf_src.parent / raster).with_suffix(".png")):
                if cand.is_file():
                    shutil.copy2(cand, td / cand.name)
                    break
        (td / "wrap.tex").write_text(
            "\\documentclass{standalone}\n"
            "\\usepackage{pgf}\n"
            "\\usepackage{amsmath,amssymb}\n"
            "\\providecommand{\\mathdefault}[1]{#1}\n"
            "\\begin{document}\n"
            "\\input{" + pgf_src.name + "}\n"
            "\\end{document}\n",
            encoding="utf-8",
        )
        subprocess.run(
            ["lualatex", "-interaction=nonstopmode", "wrap.tex"],
            cwd=td, env=env, capture_output=True,
        )
        pdf = td / "wrap.pdf"
        # nonstopmode can exit nonzero yet still emit a usable pdf
        if not pdf.is_file():
            return False
        return _pdf_to_svg(pdf, svg_path)


def _assemble_media(artifact, media_src, output_dir):
    """Copy every referenced media file into output_dir/media and make it
    browser-renderable. Returns {original ref: replacement ref} for refs
    whose target changed (.pgf/.pdf converted or swapped for an .svg
    sibling)."""
    media_dir = output_dir / "media"
    media_map = {}
    missing = []
    index = None
    for ref in _media_refs(artifact):
        target = ref
        dest = media_dir / ref
        src = None
        if not dest.is_file():
            if index is None:
                index = _index_tree(media_src, output_dir.resolve()) \
                    if media_src else {}
            src = index.get(Path(ref).name)
            if src is None and not Path(ref).suffix:
                # extensionless refs (standalone-TikZ style) rely on TeX
                # extension resolution; try the usual suspects
                for ext in (".svg", ".png", ".jpg", ".jpeg", ".pdf"):
                    src = index.get(Path(ref).name + ext)
                    if src is not None:
                        target = ref + ext
                        dest = media_dir / target
                        break
            if src is None:
                missing.append(ref)
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
        if target != ref:
            media_map[ref] = target
        if dest.suffix.lower() not in (".pgf", ".pdf"):
            continue
        svg_ref = str(Path(target).with_suffix(".svg"))
        svg_dest = media_dir / svg_ref
        if not svg_dest.is_file():
            sibling = (src or dest).with_suffix(".svg")
            if src is not None and sibling.is_file():
                shutil.copy2(sibling, svg_dest)
            elif dest.suffix.lower() == ".pgf":
                if not _pgf_to_svg(src or dest, svg_dest):
                    continue
            else:
                if not _pdf_to_svg(src or dest, svg_dest):
                    continue
        media_map[ref] = svg_ref
    if missing:
        print(f"warning: {len(missing)} media refs not found "
              f"(first: {missing[0]!r})")
    return media_map


class TagResolver:
    def __init__(self, citations=None, refs_page=False, media_map=None):
        self.citations = citations or {}
        self.refs_page = refs_page
        self.media_map = media_map or {}

    def _cite_one(self, key, prefix):
        rendered = self.citations.get(key)
        if rendered is None:
            return f'<span class="citation">[{html_mod.escape(key)}]</span>'
        if self.refs_page:
            return f'<a href="{prefix}references.html">{rendered}</a>'
        return rendered

    def resolve(self, content, prefix=""):
        def media(m):
            ref = self.media_map.get(m.group(1), m.group(1))
            return f"{prefix}media/{ref}"

        def static(m):
            return f"{prefix}static/{m.group(1)}"

        def cite(m):
            return self._cite_one(m.group(1), prefix)

        def cite_many(m):
            keys = re.findall(r"['\"]([^'\"]+)['\"]", m.group(1))
            return "; ".join(self._cite_one(k, prefix) for k in keys)

        def auth_button(m):
            attrs = dict(re.findall(r"(\w+)\s*=\s*['\"]([^'\"]*)['\"]", m.group(1)))
            href = attrs.get("href", "")
            label = attrs.get("label", "Download")
            return (
                f'<a class="download-button" href="{prefix}media/{html_mod.escape(href)}">'
                f"{html_mod.escape(label)}</a>"
            )

        content = re.sub(r"\{%\s*media\s+['\"]([^'\"]+)['\"]\s*%\}", media, content)
        content = re.sub(r"\{%\s*static\s+['\"]([^'\"]+)['\"]\s*%\}", static, content)
        content = re.sub(r"\{%\s*cite\s+['\"]([^'\"]+)['\"]\s*%\}", cite, content)
        content = re.sub(r"\{%\s*cite_many\s+([^%]+?)\s*%\}", cite_many, content)
        content = re.sub(r"\{%\s*auth_button\s+([^%]+?)\s*%\}", auth_button, content)
        content = re.sub(
            r"\{%\s*get_cell\s+[^%]*%\}",
            '<span class="get-cell-placeholder" '
            'title="interactive table cell (available on the site only)">—</span>',
            content,
        )
        content = re.sub(r"\{%\s*url\s+[^%]*%\}", "#", content)
        content = re.sub(r"\{%\s*csrf_token\s*%\}", "", content)
        # Any remaining server-side tag: drop it, leave a breadcrumb comment.
        content = re.sub(
            r"\{%\s*(\w+)[^%]*%\}", r"<!-- unresolved site tag: \1 -->", content
        )
        return content


def _section_filename(section):
    return f"{section.get('slug')}.html"


def _page(title, body, prefix=""):
    return PAGE.format(title=html_mod.escape(title), body=body, prefix=prefix,
                       mathjax=MATHJAX)


def _solutions_block(section, resolver, prefix):
    solutions = section.get("solutions") or {}
    if not solutions:
        return ""
    parts = ["<h2>Solutions</h2>"]
    for exe_id, sol in solutions.items():
        title = sol.get("title") or exe_id
        body = resolver.resolve(sol.get("content", ""), prefix)
        parts.append(
            f'<details class="solution" id="solution-{html_mod.escape(exe_id)}">'
            f"<summary>Solution: {html_mod.escape(title)} "
            f'(<a href="#{html_mod.escape(exe_id)}">exercise</a>)</summary>'
            f"{body}</details>"
        )
    return "\n".join(parts)


def write_preview(artifact, output_dir, media_src=None, bib_path=None,
                  include_solutions=True):
    """Render a static HTML preview site from an artifact.

    media_src: directory that contains the build's ``media/`` tree (i.e. the
    build's media_root); copied alongside the pages so relative links work.
    """
    artifact = _load_artifact(artifact)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    citations, refs_html = _render_citations(
        _collect_cite_keys(artifact), bib_path
    )

    (output_dir / "style.css").write_text(STYLE, encoding="utf-8")

    if media_src:
        media_tree = Path(media_src) / "media"
        if media_tree.is_dir():
            shutil.copytree(media_tree, output_dir / "media", dirs_exist_ok=True)
    media_map = _assemble_media(
        artifact, Path(media_src) if media_src else None, output_dir
    )
    resolver = TagResolver(citations, refs_page=bool(refs_html),
                           media_map=media_map)

    # Flattened section list for prev/next navigation
    flat = []
    for chapter in artifact.get("chapters", []):
        for section in chapter.get("sections", []):
            flat.append((chapter, section))

    title = artifact.get("title", "Untitled")

    for i, (chapter, section) in enumerate(flat):
        prefix = "../"
        ch_dir = output_dir / chapter["slug"]
        ch_dir.mkdir(exist_ok=True)

        crumbs = (
            f'<nav class="crumbs"><a href="{prefix}index.html">{html_mod.escape(title)}</a>'
            f" › {html_mod.escape(chapter.get('title') or chapter['slug'])}</nav>"
        )
        body = [crumbs]
        body.append(f"<h1>{html_mod.escape(section.get('title', ''))}</h1>")
        body.append(resolver.resolve(section.get("html", ""), prefix))
        if include_solutions:
            body.append(_solutions_block(section, resolver, prefix))

        pager = ["<nav class='pager'>"]
        if i > 0:
            pch, psec = flat[i - 1]
            pager.append(
                f'<a href="{prefix}{pch["slug"]}/{_section_filename(psec)}">'
                f"← {html_mod.escape(psec.get('title', ''))}</a>"
            )
        else:
            pager.append("<span></span>")
        if i < len(flat) - 1:
            nch, nsec = flat[i + 1]
            pager.append(
                f'<a href="{prefix}{nch["slug"]}/{_section_filename(nsec)}">'
                f"{html_mod.escape(nsec.get('title', ''))} →</a>"
            )
        else:
            pager.append("<span></span>")
        pager.append("</nav>")
        body.append("".join(pager))

        page_html = _page(
            f"{section.get('title', '')} — {title}", "\n".join(body), prefix
        )
        (ch_dir / _section_filename(section)).write_text(page_html, encoding="utf-8")

    # Index / table of contents
    toc = [f"<h1>{html_mod.escape(title)}</h1>"]
    authors = artifact.get("author") or []
    if authors:
        toc.append(f"<p><em>{html_mod.escape(', '.join(authors))}</em></p>")
    if artifact.get("description"):
        toc.append(f"<p>{html_mod.escape(artifact['description'])}</p>")
    for chapter in artifact.get("chapters", []):
        toc.append(f"<h2>{html_mod.escape(chapter.get('title') or chapter['slug'])}</h2>")
        toc.append("<ul>")
        for section in chapter.get("sections", []):
            toc.append(
                f'<li><a href="{chapter["slug"]}/{_section_filename(section)}">'
                f"{html_mod.escape(section.get('title', ''))}</a></li>"
            )
        toc.append("</ul>")
    if refs_html:
        toc.append('<p><a href="references.html">References</a></p>')
    gen = artifact.get("generator", "parody")
    toc.append(
        f'<p style="color:#999;font-size:.8rem">Preview built by {html_mod.escape(gen)};'
        " interactive site features (annotations, solution gating, table cells)"
        " are placeholders here.</p>"
    )
    (output_dir / "index.html").write_text(_page(title, "\n".join(toc)), encoding="utf-8")

    if refs_html:
        refs_body = (
            f'<nav class="crumbs"><a href="index.html">{html_mod.escape(title)}</a>'
            " › References</nav><h1>References</h1>" + refs_html
        )
        (output_dir / "references.html").write_text(
            _page(f"References — {title}", refs_body), encoding="utf-8"
        )

    print(f"Preview written to {output_dir} ({len(flat)} sections)")
    return output_dir
