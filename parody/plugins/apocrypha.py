"""Apocrypha plugin: surface online-only section metadata into the artifact.

In meta (System B), ``common/book-json/apocrypha.json`` records the hash,
id, title, type and version-specificity of sections that **don't appear in
the printed book but still need TOC/versioning info for the website** — the
``%\\includesection``-commented sections and the per-section
``-online-resources`` pages. The meta filter both reads and writes that file
during website builds; it is the authoritative, author-maintained metadata.

Parody keeps the same idea as opt-in plugin data. The book carries a
normalized ``apocrypha.yaml`` (a flat list of entries); enabling the plugin
in parody.yaml (``apocrypha: true``) injects an ``apocrypha`` array into the
build artifact so a consumer (homepage importer) can render a complete table
of contents spanning in-book and online-only content.

The emitted set is the *online-only* subset: an entry whose hash already
identifies an in-book section/anchor is dropped (it is in this build, so it
is not apocryphal), matching meta's definition — "sections that don't appear
in a book". Versioned variants (entries carrying a ``subhash``) are kept even
when the base hash is in-book, because they represent a different edition.

Unlike ``make_transform`` plugins (per-section markdown rewrites that run
before pandoc), this plugin exposes ``make_artifact_hook`` — a post-processor
that augments the finished artifact dict.
"""

from pathlib import Path

import yaml


def _truthy(value):
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("yes", "true", "1")


def _entry(h, subhash, fields):
    """Normalize one (hash, subhash, fields) triple to a parody entry.

    Accepts both meta's keys (``v-specific``, ``v-ts``, ``v-ds``) and the
    snake_case parody keys, so a round-tripped apocrypha.yaml re-normalizes
    to itself (idempotent)."""
    entry = {
        "hash": fields.get("hash", h) or h,
        "id": fields.get("id", "") or "",
        "title": fields.get("title", "") or "",
        "type": fields.get("type", "") or "",
    }
    vspec = fields.get("v-specific", fields.get("v_specific"))
    if vspec is not None:
        entry["v_specific"] = _truthy(vspec)
    for src_key, dst_key in (("v-ts", "v_ts"), ("v-ds", "v_ds")):
        val = fields.get(src_key, fields.get(dst_key))
        if val not in (None, ""):
            entry[dst_key] = val
    if subhash and subhash != "unversioned":
        entry["subhash"] = subhash
    return entry


def normalize_entries(raw):
    """Flatten either shape into a sorted list of parody apocrypha entries.

    - meta shape: ``{hash: {subhash: {fields...}}}`` (apocrypha.json)
    - parody shape: ``[{hash, id, title, type, ...}, ...]`` (apocrypha.yaml)
    """
    triples = []
    if isinstance(raw, dict):
        for h, subs in raw.items():
            if not isinstance(subs, dict):
                continue
            for subhash, fields in subs.items():
                if isinstance(fields, dict):
                    triples.append((h, subhash, fields))
    elif isinstance(raw, list):
        for item in raw:
            if isinstance(item, dict):
                triples.append(
                    (item.get("hash", ""),
                     item.get("subhash", "unversioned"),
                     item))
    else:
        return []
    # Drop the occasional malformed source entry with no usable hash (the
    # hash is the permalink/cross-ref key — an empty one is meaningless).
    entries = [_entry(h, sub, f) for h, sub, f in triples]
    entries = [e for e in entries if e["hash"]]
    entries.sort(key=lambda e: (e["hash"], e.get("subhash", "")))
    return entries


def _in_book_hashes(artifact):
    """Every hash that identifies a section/anchor/chapter in this build."""
    found = set()
    for chapter in artifact.get("chapters", []):
        if chapter.get("hash"):
            found.add(chapter["hash"])
        for section in chapter.get("sections", []):
            if section.get("hash"):
                found.add(section["hash"])
            for anchor in section.get("anchors", []):
                if isinstance(anchor, dict) and anchor.get("hash"):
                    found.add(anchor["hash"])
    return found


def _resolve_source(config, project_dir):
    name = "apocrypha.yaml"
    if isinstance(config, dict):
        name = config.get("source", name)
    return Path(project_dir) / name


def make_artifact_hook(config, project_dir):
    """Return a hook ``(artifact) -> artifact`` that adds the online-only
    apocrypha entries. No-op when the source file is absent or yields nothing."""
    source = _resolve_source(config, project_dir)

    def hook(artifact):
        if not source.is_file():
            return artifact
        with open(source, encoding="utf-8") as f:
            raw = yaml.safe_load(f)  # also parses apocrypha.json (JSON ⊂ YAML)
        entries = normalize_entries(raw)
        in_book = _in_book_hashes(artifact)
        online = [e for e in entries
                  if "subhash" in e or e["hash"] not in in_book]
        if online:
            artifact["apocrypha"] = online
        return artifact

    return hook
