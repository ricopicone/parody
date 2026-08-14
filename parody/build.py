"""Layout-aware build orchestration.

Legacy (System A) projects delegate to the verbatim-ported
writers.artifact.convert_notebook so golden parity is untouched. Parody
content repos run the same section pipeline driven by parody.yaml, with
slug context passed to the lua filter and figure mover via env vars
(their legacy path-pattern matching can't see the new layout).
"""

import contextlib
import copy
import json
import os
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import yaml

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

_MEDIA_REF_RE = re.compile(r"\{%\s*media\s+'([^']+)'\s*%\}")
_STAGE_SKIP_DIRS = {"build", "node_modules", "__pycache__", ".git", "media"}
_IMG_EXTS = (".svg", ".png", ".jpg", ".jpeg", ".pdf")


def _apply_media_rewrites(output, rewrites):
    """Rewrite ``{% media 'old' %}`` -> ``{% media 'new' %}`` across the
    artifact (section html, solutions, problems, online_resources)."""
    def fix(blob):
        for old, new in rewrites.items():
            blob = blob.replace("{%% media '%s' %%}" % old,
                                "{%% media '%s' %%}" % new)
        return blob
    for chapter in output.get("chapters", []):
        for section in chapter.get("sections", []):
            if section.get("html"):
                section["html"] = fix(section["html"])
            if section.get("online_resources"):
                section["online_resources"] = fix(section["online_resources"])
            for bucket in ("solutions", "problems"):
                for entry in (section.get(bucket) or {}).values():
                    if isinstance(entry, dict) and entry.get("content"):
                        entry["content"] = fix(entry["content"])


_RIGHTS_FIG_RE = re.compile(r'<figure\b[^>]*\bdata-permission="permission"')
_FIG_DELIM_RE = re.compile(r'<figure\b|</figure>')
_RIGHTS_IMG_RE = re.compile(r'<img\b[^>]*\bdata-permission="permission"[^>]*>')


def _rights_withheld_refs(output):
    """Media refs of permission=permission figures in non-preview (public)
    sections — to be excluded from the public media tree. Covers single figures
    (<img data-permission>) and subfigure floats (outer <figure data-permission>,
    every panel <img>, via a balanced scan)."""
    withheld = set()
    for chapter in output.get("chapters", []):
        for section in chapter.get("sections", []):
            if section.get("preview"):
                continue  # gated: owner sees the real figure
            html = section.get("html") or ""
            for m in _RIGHTS_FIG_RE.finditer(html):
                depth, end = 0, len(html)
                for d in _FIG_DELIM_RE.finditer(html, m.start()):
                    depth += 1 if d.group(0) == "<figure" else -1
                    if depth == 0:
                        end = d.end()
                        break
                withheld.update(_MEDIA_REF_RE.findall(html[m.start():end]))
            for im in _RIGHTS_IMG_RE.finditer(html):
                withheld.update(_MEDIA_REF_RE.findall(im.group(0)))
    return withheld


def _stage_referenced_media(output, source_root, media_dir):
    """Stage every ``{% media 'ref' %}`` file into the media tree so a consumer
    serving ``MEDIA_URL/<ref>`` finds it, converting print figures to web form.

    Meta-migrated figures are bare/extensionless refs resolving to ``<ref>.<ext>``
    on disk, and most are ``.pdf`` (print) which browsers can't show in
    ``<img>``. Such refs are converted to ``.svg`` (reusing the preview writer's
    pdftocairo/lualatex converters) and the artifact ref is rewritten to the
    served ``.svg``. Non-print images are copied. Returns (staged, missing)."""
    from .writers.preview import _pdf_to_svg, _pgf_to_svg

    refs = set(_MEDIA_REF_RE.findall(json.dumps(output)))
    # Licensed third-party figures (permission=permission) are replaced by a
    # print-only placeholder on public pages, so their image must not ship in the
    # public media tree (it'd be reachable by URL). Drop those refs unless the
    # section is gated (preview), where the figure shows normally to the owner.
    refs -= _rights_withheld_refs(output)
    index = {}  # basename -> source path
    for root, dirs, files in os.walk(source_root):
        dirs[:] = [d for d in dirs
                   if d not in _STAGE_SKIP_DIRS and not d.startswith(".")]
        for f in files:
            index.setdefault(f, Path(root) / f)

    staged, missing, rewrites = 0, [], {}
    for ref in refs:
        base = os.path.basename(ref)
        src = index.get(base)
        if src is None and not os.path.splitext(ref)[1]:
            for ext in _IMG_EXTS:
                src = index.get(base + ext)
                if src is not None:
                    break
        if src is None:
            missing.append(ref)
            continue
        stem = os.path.splitext(ref)[0]
        if src.suffix.lower() in (".pdf", ".pgf"):
            target = stem + ".svg"
            dest = Path(media_dir) / target
            if not dest.exists():
                dest.parent.mkdir(parents=True, exist_ok=True)
                ok = (_pgf_to_svg(src, dest) if src.suffix.lower() == ".pgf"
                      else _pdf_to_svg(src, dest))
                if not ok:  # converter unavailable -> keep the source as-is
                    target = ref if os.path.splitext(ref)[1] else ref + src.suffix
                    dest = Path(media_dir) / target
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src, dest)
        else:
            target = ref if os.path.splitext(ref)[1] else ref + src.suffix
            dest = Path(media_dir) / target
            if not dest.exists():
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dest)
        staged += 1
        if target != ref:
            rewrites[ref] = target

    if rewrites:
        _apply_media_rewrites(output, rewrites)
    return staged, missing


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
def _slug_env(notebook_slug=None, chapter_slug=None, media_root=None,
              chapter_dir=None, cloze_mode=None):
    """Set PARODY_* context env vars, restoring previous values on exit."""
    updates = {
        "PARODY_NOTEBOOK_SLUG": notebook_slug,
        "PARODY_CHAPTER_SLUG": chapter_slug,
        "PARODY_MEDIA_ROOT": str(media_root) if media_root else None,
        # chapter_dir lets the web filter stat sibling files (e.g. a figure's
        # <stem>-cloze.<ext> variant) the way print.lua already can.
        "PARODY_CHAPTER_DIR": str(chapter_dir) if chapter_dir else None,
        "PARODY_CLOZE_MODE": cloze_mode,
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


def _filter_online_only(output):
    """Reduce an artifact to the public web subset (e.g. rtcbook.org): keep
    online-only section content in full, keep online-resources from any section
    as a resource-only page (copyrighted body stripped — MIT-safe), drop the
    rest and any now-empty chapters. Top-level book/videos/apocrypha stay."""
    chapters = []
    for ch in output.get("chapters", []):
        kept = []
        for s in ch.get("sections", []):
            if s.get("online_only"):
                kept.append(s)
            elif s.get("online_resources"):
                # resource page only — never publish the licensed body/anchors
                kept.append({k: s[k] for k in
                             ("title", "slug", "hash", "online_resources")
                             if k in s})
        if kept:
            chapters.append({**{k: v for k, v in ch.items() if k != "sections"},
                             "sections": kept})
    return {**output, "chapters": chapters}


def _section_editions(path):
    """A section's ``editions:`` frontmatter membership as a list of edition
    ids, or None when unset (the single-source default: belongs to *every*
    edition until it forks). Honors single string or list forms."""
    try:
        raw = Path(path).read_text(encoding="utf-8")
    except OSError:
        return None
    if not raw.startswith("---"):
        return None
    try:
        _, frontmatter, _ = raw.split("---", 2)
        meta = yaml.safe_load(frontmatter.strip()) or {}
    except ValueError:
        return None
    eds = meta.get("editions")
    if eds is None:
        return None
    if isinstance(eds, str):
        eds = [eds]
    return [str(e) for e in eds]


def _resolve_section_file(chapter_dir, section_slug, edition_id):
    """Which file an edition reads for a section — the single-source-until-fork
    overlay (decision 1a). A per-edition fork ``<slug>.<edition>.md`` shadows
    the shared ``<slug>.md`` for that edition only; the shared source serves
    every edition in its membership (default: all). Returns the filename to
    read, or None when the section is absent from this edition."""
    fork = chapter_dir / f"{section_slug}.{edition_id}.md"
    if fork.is_file():
        return fork.name
    shared = chapter_dir / f"{section_slug}.md"
    if shared.is_file():
        members = _section_editions(shared)
        if members is None or edition_id in members:
            return shared.name
    return None


def _meta_for_edition(meta, edition):
    """A copy of the project meta with the edition's active version tracks
    injected into the version-aware plugins (versioning, parts_list), so each
    edition's artifact substitutes its own (TX, DY)."""
    m = copy.deepcopy(meta)
    tracks = edition.get("tracks") or {}
    if tracks:
        for key in ("versioning", "parts_list"):
            cfg = m.get(key)
            if isinstance(cfg, dict):
                cfg["tracks"] = dict(tracks)
    return m


def build_editions(project_dir, output_dir, **kwargs):
    """Build one artifact per configured edition into ``output_dir``, named
    ``<slug>.<edition>.json``. Returns the list of written paths. Raises if the
    project declares no editions (use build_project for single-artifact books).
    """
    project = load_project(project_dir)
    if not project.editions:
        raise ValueError(
            f"{project_dir} declares no editions: in parody.yaml; "
            "use build_project for a single-artifact build")
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for edition in project.editions:
        out = output_dir / f"{project.slug}.{edition['id']}.json"
        build_project(project_dir, out, edition=edition, **kwargs)
        paths.append(out)
    return paths


def build_project(project_dir, output_path, convert_jupytext=True,
                  media_root=None, online_only=False, edition=None,
                  cloze_mode=None, print_pages=None):
    """Build the JSON artifact for either layout. Returns the artifact dict.

    online_only: emit only the public web subset (online-only sections +
    per-section online-resources) — the partial artifact a standalone book
    host (rtcbook.org) imports; the full licensed book never leaves the build.

    edition: a normalized edition dict (see config.normalize_editions). When
    given, build that edition's artifact — substitute its active version
    tracks and include only the sections that belong to it (single-source
    overlay, decision 1a). None builds the unfiltered single artifact (also
    the back-compat path for books without editions). Usually called via
    build_editions, which loops over every configured edition.

    cloze_mode: "blank" | "key" | "full" (see config.resolve_cloze_mode).
    None takes parody.yaml's `cloze.default`, itself defaulting to "blank".

    print_pages: path to the page-map sidecar `parody pdf` writes beside the
    PDF (see writers/pagemap.py). Folds each section's print page range into
    the artifact so a book site can offer per-section PDFs. Absent → the
    artifact carries no print keys and the web side renders no PDF affordance.
    """
    project = load_project(project_dir)

    print_map, print_meta = {}, None
    if print_pages:
        data = json.loads(Path(print_pages).read_text(encoding="utf-8"))
        print_map = data.get("sections") or {}
        print_meta = {"pdf": data.get("pdf", ""), "pages": data.get("pages"),
                      "sha256": data.get("sha256", "")}

    from .config import resolve_cloze_mode
    cloze_mode = resolve_cloze_mode(project.meta, cloze_mode)

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

    active_meta = _meta_for_edition(project.meta, edition) if edition \
        else project.meta

    from .plugins import apply_transforms, content_transforms
    transforms = content_transforms(active_meta, project.directory)
    transform = (lambda text: apply_transforms(text, transforms)) \
        if transforms else None

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

    # The print PDF this artifact's page ranges index into. Emitted only when a
    # sidecar was supplied, so web-only builds stay byte-identical.
    if print_meta:
        output["print"] = print_meta

    # chapter_start: the number of the first (non-appendix) chapter. Default 1;
    # emit only when overridden (e.g. RTC's `chapter_start: 0`) so artifacts of
    # books that don't care stay byte-identical and the renderer's own default
    # of 1 covers them. Section/figure/equation numbers inherit it downstream.
    chapter_start = int(project.meta.get("chapter_start", 1))
    if chapter_start != 1:
        output["chapter_start"] = chapter_start

    # Cloze rendering mode. Emitted only when it isn't the default, so
    # artifacts of books without fill-in-the-blank content stay byte-identical
    # (same convention as chapter_start). Absence means "blank".
    if cloze_mode != "blank":
        output["cloze_mode"] = cloze_mode

    # Edition metadata: this artifact's edition plus the full roster, so a
    # renderer can build the edition switcher (default = latest) from any one
    # edition's artifact.
    if edition:
        output["edition"] = {k: edition[k]
                             for k in ("id", "title", "tracks", "default",
                                       "draft")}
        output["editions"] = [
            {"id": e["id"], "title": e["title"], "default": e["default"],
             "draft": e["draft"]}
            for e in project.editions]

    requested_code_files = set()

    for chapter in project.chapters:
        with _slug_env(project.slug, chapter.slug, media_root,
                       chapter_dir=chapter.directory, cloze_mode=cloze_mode):
            if convert_jupytext:
                converted = convert_jupytext_files_in_directory(chapter.directory)
                if converted:
                    print(f"✓ Converted {len(converted)} jupytext files in chapter {chapter.slug}")

            chapter_data = {"title": chapter.title, "slug": chapter.slug, "sections": []}
            if with_hashes and chapter.hash:
                chapter_data["hash"] = chapter.hash
            if with_hashes and chapter.appendix:
                chapter_data["appendix"] = True
            for section_slug in chapter.section_slugs:
                section_file = None
                if edition:
                    section_file = _resolve_section_file(
                        chapter.directory, section_slug, edition["id"])
                    if section_file is None:
                        continue  # section absent from this edition
                for path in get_section_download_paths(
                        chapter.directory, section_slug, section_file=section_file):
                    requested_code_files.add((chapter.directory.name, path))
                section_data = load_section(
                    chapter.directory, section_slug,
                    with_hashes=with_hashes, transform=transform,
                    section_file=section_file)
                # Print page range from `parody pdf`'s sidecar, when one was
                # supplied. Sections the sidecar does not mention simply carry
                # no print key, and the web side offers them no PDF.
                pages = print_map.get(f"{chapter.slug}/{section_slug}")
                if pages:
                    section_data["print"] = {"pages": pages}
                chapter_data["sections"].append(section_data)

        # Drop a chapter that has no sections in this edition.
        if edition and not chapter_data["sections"]:
            continue
        output["chapters"].append(chapter_data)

    if with_hashes:
        _check_duplicate_hashes(output)

    # Plugin artifact hooks augment the finished dict (e.g. apocrypha adds
    # online-only TOC metadata; parts-list adds the per-edition systems
    # catalog). Run after dedup so they see the full build. Use active_meta so
    # per-edition version tracks reach version-aware hooks.
    from .plugins import apply_artifact_hooks, artifact_hooks
    hooks = artifact_hooks(active_meta, project.directory)
    output = apply_artifact_hooks(output, hooks)

    if requested_code_files:
        files_copied = copy_selected_code_files_to_media(
            project.directory / "chapters", project.slug, requested_code_files,
            media_root=media_root,
        )
        if files_copied:
            print(f"✓ Copied {files_copied} code files to media/notebooks/{project.slug}/")

    # Stage committed figure assets (chapters/<ch>/<stem>_files/) into the
    # media tree. Captures save straight into the source-tree _files dirs;
    # this staging step is how they (and any hand-placed assets) reach the
    # served-media layout.
    staged = 0
    for chapter in project.chapters:
        for files_dir in sorted(chapter.directory.glob("*_files")):
            if not files_dir.is_dir():
                continue
            dest = (Path(media_root) / "media" / "notebooks" / project.slug
                    / chapter.slug / files_dir.name)
            dest.mkdir(parents=True, exist_ok=True)
            for asset in sorted(files_dir.iterdir()):
                if asset.is_file() and not asset.name.startswith("."):
                    shutil.copy2(asset, dest / asset.name)
                    staged += 1
    if staged:
        print(f"✓ Staged {staged} figure assets into media/notebooks/{project.slug}/")

    # Stage hand-placed static media (cover, errata figures, …) from the
    # project's assets/ dir into the served media root, flat by basename.
    assets_dir = project.directory / "assets"
    asset_staged = 0
    if assets_dir.is_dir():
        media_dir = Path(media_root) / "media"
        media_dir.mkdir(parents=True, exist_ok=True)
        for asset in sorted(assets_dir.rglob("*")):
            if asset.is_file() and not asset.name.startswith("."):
                shutil.copy2(asset, media_dir / asset.name)
                asset_staged += 1
    if asset_staged:
        print(f"✓ Staged {asset_staged} static assets into media/")

    # General pass: stage every {% media %}-referenced file (covers meta-migrated
    # books whose figure refs are bare/extensionless flat names, which the
    # *_files staging above doesn't reach).
    ref_staged, ref_missing = _stage_referenced_media(
        output, project.directory, Path(media_root) / "media")
    if ref_staged:
        print(f"✓ Staged {ref_staged} referenced media files into media/")
    if ref_missing:
        print(f"warning: {len(ref_missing)} media refs not found "
              f"(first: {sorted(ref_missing)[0]!r})")

    if online_only:
        output = _filter_online_only(output)

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2)

    print(f"Artifact written to {output_path}")
    return output
