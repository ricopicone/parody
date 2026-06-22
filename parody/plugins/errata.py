"""Errata plugin: render an errata markdown file into the artifact as ``errata``
(html). Enabled by an ``errata:`` key in parody.yaml — a path to the markdown
(default ``errata.md``).

The artifact consumer (parody-web) serves it at /errata. Image references are
rewritten to ``/media/<basename>``; place those figures in the project's
``assets/`` so the build stages them into media. Math uses MathJax (\\(…\\)).
"""
import re
from pathlib import Path

import pypandoc

_IMG_SRC_RE = re.compile(r'(<img\b[^>]*\bsrc=")([^"]+)(")')


def render_errata(path):
    md = Path(path).read_text(encoding="utf-8")
    md = re.sub(r"^---\n.*?\n---\n", "", md, count=1, flags=re.S)  # drop frontmatter
    html = pypandoc.convert_text(
        md, "html", format="markdown+tex_math_dollars", extra_args=["--mathjax"])
    # point figure refs at staged media by basename
    return _IMG_SRC_RE.sub(
        lambda m: m.group(1) + "/media/" + m.group(2).rsplit("/", 1)[-1] + m.group(3),
        html)


def make_artifact_hook(config, project_dir):
    rel = config if isinstance(config, str) else (
        (config or {}).get("source", "errata.md") if isinstance(config, dict) else "errata.md")
    src = Path(project_dir) / rel

    def hook(artifact):
        if src.exists():
            artifact["errata"] = render_errata(src)
        return artifact
    return hook
