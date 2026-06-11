"""Layout-aware build orchestration.

Legacy (System A) projects delegate to the verbatim-ported
writers.artifact.convert_notebook so golden parity is untouched. Parody
content repos run the same section pipeline driven by parody.yaml, with
slug context passed to the lua filter and figure mover via env vars
(their legacy path-pattern matching can't see the new layout).
"""

import contextlib
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from . import __version__
from .config import load_project
from .writers.artifact import (
    SCHEMA_VERSION,
    convert_jupytext_files_in_directory,
    convert_notebook,
    copy_selected_code_files_to_media,
    get_section_download_paths,
    get_source_commit,
    load_section,
)


def get_source_repo(path):
    """Origin remote URL of the repo containing the sources, if any."""
    try:
        url = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            cwd=path, capture_output=True, text=True, timeout=10,
        ).stdout.strip()
        return url or None
    except Exception:
        return None


class DuplicateHashError(RuntimeError):
    """Short hashes are permalink/cross-ref/QR keys; per the seed plan a
    duplicate is a build error, never a warning (the ancestor's advisory
    find_duplicate_hashes.py let collisions ship)."""


def _check_duplicate_hashes(artifact):
    """One flat namespace per book, matching the ancestor's checker. A
    section's own hash and its heading anchor's hash are one identity."""
    locations = {}
    for chapter in artifact["chapters"]:
        for section in chapter["sections"]:
            where = f"{chapter['slug']}/{section['slug']}"
            anchor_hashes = set()
            for anchor in section.get("anchors", []):
                h = anchor.get("hash") if isinstance(anchor, dict) else None
                if h:
                    anchor_hashes.add(h)
                    locations.setdefault(h, []).append(
                        f"{where}#{anchor['id']}")
            h = section.get("hash")
            if h and h not in anchor_hashes:
                locations.setdefault(h, []).append(where)
    duplicates = {h: locs for h, locs in locations.items() if len(locs) > 1}
    if duplicates:
        lines = [f"  {h}: {', '.join(locs)}" for h, locs in
                 sorted(duplicates.items())]
        raise DuplicateHashError(
            "duplicate short hashes (must be unique per book):\n"
            + "\n".join(lines))


@contextlib.contextmanager
def _slug_env(notebook_slug=None, chapter_slug=None, media_root=None):
    """Set PARODY_* context env vars, restoring previous values on exit."""
    updates = {
        "PARODY_NOTEBOOK_SLUG": notebook_slug,
        "PARODY_CHAPTER_SLUG": chapter_slug,
        "PARODY_MEDIA_ROOT": str(media_root) if media_root else None,
    }
    saved = {k: os.environ.get(k) for k in updates}
    try:
        for k, v in updates.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        yield
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def build_project(project_dir, output_path, convert_jupytext=True, media_root=None):
    """Build the JSON artifact for either layout. Returns the artifact dict."""
    project = load_project(project_dir)

    if project.layout == "legacy":
        convert_notebook(
            project.directory, output_path,
            convert_jupytext=convert_jupytext, media_root=media_root,
        )
        with open(output_path, encoding="utf-8") as f:
            return json.load(f)

    # Parody content-repo layout. Figures and code-file copies default to a
    # media/ tree inside the project (gitignored by the init scaffold).
    if media_root is None:
        media_root = project.directory

    # Schema v2 (parody.yaml `schema: 2`) adds short-hash stable IDs; v1
    # stays the default because its output is pinned by golden parity.
    schema_version = int(project.meta.get("schema", SCHEMA_VERSION))
    with_hashes = schema_version >= 2

    output = {
        "schema_version": schema_version,
        "generator": f"parody {__version__}",
        "source_repo": get_source_repo(project.directory),
        "source_commit": get_source_commit(project.directory),
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "title": project.meta.get("title", ""),
        "slug": project.slug,
        "author": project.meta.get("author", []),
        "description": project.meta.get("description", ""),
        "acronym": project.meta.get("acronym", ""),
        "cover_image": project.meta.get("cover_image", ""),
        "pdf_file": project.meta.get("pdf_file", ""),
        "chapters": [],
    }

    requested_code_files = set()

    for chapter in project.chapters:
        with _slug_env(project.slug, chapter.slug, media_root):
            if convert_jupytext:
                converted = convert_jupytext_files_in_directory(chapter.directory)
                if converted:
                    print(f"✓ Converted {len(converted)} jupytext files in chapter {chapter.slug}")

            chapter_data = {"title": chapter.title, "slug": chapter.slug, "sections": []}
            for section_slug in chapter.section_slugs:
                for path in get_section_download_paths(chapter.directory, section_slug):
                    requested_code_files.add((chapter.directory.name, path))
                chapter_data["sections"].append(load_section(
                    chapter.directory, section_slug, with_hashes=with_hashes))

        output["chapters"].append(chapter_data)

    if with_hashes:
        _check_duplicate_hashes(output)

    if requested_code_files:
        files_copied = copy_selected_code_files_to_media(
            project.directory / "chapters", project.slug, requested_code_files,
            media_root=media_root,
        )
        if files_copied:
            print(f"✓ Copied {files_copied} code files to media/notebooks/{project.slug}/")

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2)

    print(f"Artifact written to {output_path}")
    return output
