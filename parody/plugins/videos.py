"""Videos plugin: surface lecture-video playlist links into the artifact.

In meta (System B), ``common/book-json/videos.json`` maps section hashes to
positions in a YouTube playlist, per edition:

    {"0": {"playlist": "<id>", "indices": {"61": 1, "ha": [3, 4], ...}}}

The website renders a "Watch Lecture Video" button on each section whose hash
is in the map (a list of indices = a section spanning several videos). Port it
as the fourth opt-in plugin (artifact-hook kind), so a consumer can attach the
same links.

Like apocrypha, this is machine-generated hash-keyed data, so it lives in a
``videos.yaml`` sidecar (``videos: true`` in parody.yaml). The hook emits only
the entries whose hash identifies a real section of this book — in-book or
apocrypha (online-only) — dropping dangling links (e.g. a stale copied
videos.json pointing at another book's hashes).
"""

from pathlib import Path

import yaml

from .apocrypha import _in_book_hashes


def _indices(value):
    """A single position or a list of them -> a list of ints."""
    if isinstance(value, list):
        return [int(x) for x in value]
    return [int(value)]


def normalize_videos(raw):
    """Flatten either shape into a list of edition objects, preserving the
    source (playlist) order of sections.

    - meta shape: ``{edition: {playlist, indices: {hash: idx|[idx]}}}``
    - parody shape: ``[{edition, playlist, sections: [{hash, indices}]}]``
    """
    editions = []
    if isinstance(raw, dict):
        for eid, ed in raw.items():
            if not isinstance(ed, dict):
                continue
            sections = []
            indices = ed.get("indices", {})
            if isinstance(indices, dict):
                for h, v in indices.items():
                    if h:
                        sections.append({"hash": h, "indices": _indices(v)})
            editions.append({"edition": str(eid),
                             "playlist": ed.get("playlist", ""),
                             "sections": sections})
    elif isinstance(raw, list):
        for ed in raw:
            if not isinstance(ed, dict):
                continue
            sections = []
            for s in ed.get("sections", []):
                if isinstance(s, dict) and s.get("hash"):
                    sections.append({"hash": s["hash"],
                                     "indices": _indices(s.get("indices", []))})
            editions.append({"edition": str(ed.get("edition", "")),
                             "playlist": ed.get("playlist", ""),
                             "sections": sections})
    return editions


def video_hashes(editions):
    """Every section hash referenced across editions (for staleness checks)."""
    return {s["hash"] for ed in editions for s in ed["sections"]}


def _known_hashes(artifact):
    """Hashes of real sections in this build: in-book plus apocrypha
    (online-only). A video for anything else is a dead link."""
    known = _in_book_hashes(artifact)
    for entry in artifact.get("apocrypha", []):
        if isinstance(entry, dict) and entry.get("hash"):
            known.add(entry["hash"])
    return known


def _resolve_source(config, project_dir):
    name = "videos.yaml"
    if isinstance(config, dict):
        name = config.get("source", name)
    return Path(project_dir) / name


def make_artifact_hook(config, project_dir):
    """Return a hook ``(artifact) -> artifact`` that adds video links for
    sections present in this build. No-op when the source is absent or every
    link is dangling."""
    source = _resolve_source(config, project_dir)

    def hook(artifact):
        if not source.is_file():
            return artifact
        with open(source, encoding="utf-8") as f:
            raw = yaml.safe_load(f)  # parses videos.json too (JSON ⊂ YAML)
        known = _known_hashes(artifact)
        out = []
        for ed in normalize_videos(raw):
            sections = [s for s in ed["sections"] if s["hash"] in known]
            if sections:
                out.append({**ed, "sections": sections})
        if out:
            artifact["videos"] = out
        return artifact

    return hook
