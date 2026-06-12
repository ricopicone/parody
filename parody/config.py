"""Project configuration: detect and load content layouts.

Two layouts are supported:

- **parody** (Phase 2 content repos, from `parody init`)::

    parody.yaml            title, slug, authors, chapters list
    chapters/<ch>/<sec>.md (+ optional <sec>_code.py jupytext sources)
    assets/

- **legacy** (System A, homepage-django notebooks-source)::

    __meta.yaml
    _chapter_<slug>.yaml
    chapter_<slug>/<sec>.md

The legacy layout is handled byte-for-byte by the verbatim-ported
writers.artifact.convert_notebook; this module only identifies it.
"""

from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class Chapter:
    slug: str
    title: str
    directory: Path
    section_slugs: list = field(default_factory=list)
    hash: str = ""  # stable short hash (schema v2 / hashref target)


@dataclass
class Project:
    directory: Path
    layout: str  # "parody" | "legacy"
    slug: str
    meta: dict
    chapters: list = field(default_factory=list)
    bibliography: Path | None = None


class ProjectLayoutError(Exception):
    pass


def detect_layout(project_dir):
    project_dir = Path(project_dir)
    if (project_dir / "parody.yaml").is_file():
        return "parody"
    if (project_dir / "__meta.yaml").is_file():
        return "legacy"
    raise ProjectLayoutError(
        f"{project_dir} is not a parody project: no parody.yaml (content repo) "
        "or __meta.yaml (legacy notebook) found"
    )


def _find_bibliography(project_dir):
    book_bib = project_dir / "book.bib"
    if book_bib.is_file():
        return book_bib
    bibs = sorted(project_dir.glob("*.bib"))
    return bibs[0] if bibs else None


def load_project(project_dir):
    project_dir = Path(project_dir)
    layout = detect_layout(project_dir)

    if layout == "legacy":
        with open(project_dir / "__meta.yaml", encoding="utf-8") as f:
            meta = yaml.safe_load(f) or {}
        chapters = []
        for ch_slug in meta.get("chapter_slugs", []):
            ch_yaml = project_dir / f"_chapter_{ch_slug}.yaml"
            with open(ch_yaml, encoding="utf-8") as f:
                ch_meta = yaml.safe_load(f) or {}
            chapters.append(Chapter(
                slug=ch_slug,
                title=ch_meta.get("title", ""),
                directory=project_dir / f"chapter_{ch_slug}",
                section_slugs=ch_meta.get("section_slugs", []),
            ))
        return Project(
            directory=project_dir, layout="legacy",
            slug=project_dir.name, meta=meta, chapters=chapters,
            bibliography=_find_bibliography(project_dir),
        )

    with open(project_dir / "parody.yaml", encoding="utf-8") as f:
        meta = yaml.safe_load(f) or {}

    slug = meta.get("slug") or project_dir.name
    authors = meta.get("authors", meta.get("author", []))
    if isinstance(authors, str):
        authors = [authors]
    meta["author"] = authors

    chapters = []
    for ch in meta.get("chapters", []):
        ch_slug = ch["slug"]
        sections = ch.get("sections", [])
        chapters.append(Chapter(
            slug=ch_slug,
            title=ch.get("title", ""),
            directory=project_dir / "chapters" / ch_slug,
            section_slugs=sections,
            hash=str(ch.get("hash", "") or ""),
        ))

    return Project(
        directory=project_dir, layout="parody",
        slug=slug, meta=meta, chapters=chapters,
        bibliography=_find_bibliography(project_dir),
    )
