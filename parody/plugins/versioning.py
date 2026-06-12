"""Hardware/platform versioning plugin (ancestor: rtc's ts/ds machinery).

A book declares named version *tracks* and the active version per track in
parody.yaml; the version database describes each version's parameters with
variant inheritance (minor versions inherit the fields they don't
override), the ancestor's versions.json + versions-inheriter.py model:

    versioning:
      source: versions.yaml      # default; the ancestor's versions.json
                                 # loads too (YAML tolerates its trailing
                                 # commas)
      tracks:
        ts: T1                   # rtc: target system + development system
        ds: D1                   # (second edition: T2 / D2 — config only)

Most books need a single track — ``tracks: {v: "1.0"}`` — the track names
are arbitrary.

Content syntax (the ancestor's, unchanged):

- ``[]{.ts}``                       -> the track's active version name
- ``[]{.tsicon}``                   -> ``[T1]{.version-icon .ts}`` (the
                                       profile/site styles margin icons)
- ``[]{.T1-target-computer-name}``  -> flattened parameter value: version
  name + dash-joined key path. Display keys ending in an abbreviation,
  e.g. "System on a chip (SoC)", flatten to the abbreviation (-> soc).
  A dict-valued reference resolves to its "name" field.

Unresolved spans that name a known version are warnings (the ancestor's
filter dropped them silently). Parts-list generation (versions-lister.py)
is deliberately not ported yet — port when the rtc migration reaches the
lab-manual appendices.
"""

import re
from pathlib import Path

import yaml

_EMPTY_SPAN_RE = re.compile(r"\[\]\{\.([A-Za-z0-9._-]+)\}")


def _slug_key(key):
    """Flatten a parameter key: a trailing parenthesized abbreviation wins
    ("System on a chip (SoC)" -> "soc"), else slugify the whole key."""
    m = re.search(r"\(([^()]+)\)\s*$", key)
    if m:
        key = m.group(1)
    return re.sub(r"[^a-z0-9]+", "-", key.lower()).strip("-")


def load_versions(path):
    """The version database. YAML loader by design: the ancestor's
    versions.json is hand-edited with trailing commas, which YAML's flow
    mappings accept."""
    return yaml.safe_load(Path(path).read_text()) or {}


def flatten_versions(db):
    """{version name: params} with variant inheritance applied — the
    versions-inheriter.py model: minor versions inherit every field of
    their parent that they don't override; parent/children links kept."""
    flat = {}

    def visit(name, node, parent):
        node = dict(node)
        variants = node.pop("variants", None) or {}
        node["parent"] = parent
        node["children"] = list(variants.keys())
        flat[name] = node
        for child_name, child in variants.items():
            merged = dict(child)
            for k, v in node.items():
                if k not in merged and k not in ("parent", "children"):
                    merged[k] = v
            visit(child_name, merged, name)

    for _track, versions in (db or {}).items():
        for name, node in (versions or {}).items():
            visit(name, node, None)
    return flat


def _params_table(flat):
    """{f"{version}-{slug-path}": value} for every version and parameter.
    Dict nodes are addressable too and resolve to their "name" field."""
    table = {}

    def walk(prefix, node):
        for key, value in node.items():
            if key in ("parent", "children", "suppliers"):
                continue
            slug = _slug_key(str(key))
            path = f"{prefix}-{slug}" if slug else prefix
            if isinstance(value, dict):
                if "name" in value:
                    table.setdefault(path, str(value["name"]))
                walk(path, value)
            elif isinstance(value, (str, int, float)):
                table[path] = str(value)

    for version, params in flat.items():
        walk(version, params)
    return table


def make_transform(config, project_dir):
    tracks = config.get("tracks") or {}
    if not tracks:
        raise ValueError("versioning: config needs a 'tracks' mapping "
                         "(e.g. tracks: {v: '1.0'})")
    source = Path(project_dir) / config.get("source", "versions.yaml")
    flat = flatten_versions(load_versions(source)) if source.is_file() else {}
    for track, active in tracks.items():
        if flat and active not in flat:
            raise ValueError(
                f"versioning: active {track} version {active!r} not in "
                f"{source.name} (known: {', '.join(sorted(flat))})")
    params = _params_table(flat)
    version_names = set(flat)
    warned = set()

    def resolve(m):
        key = m.group(1)
        if key in tracks:
            return tracks[key]
        for track, active in tracks.items():
            if key == f"{track}icon":
                return f"[{active}]{{.version-icon .{track}}}"
        if key in params:
            return params[key]
        # content keys sometimes carry the display-key casing
        # (T1-target-computer-Microprocessor); table keys are slugged
        prefix, _, rest = key.partition("-")
        if rest and f"{prefix}-{rest.lower()}" in params:
            return params[f"{prefix}-{rest.lower()}"]
        prefix = key.split("-", 1)[0]
        if prefix in version_names and key not in warned:
            warned.add(key)
            print(f"  warning: versioning: unresolved parameter "
                  f"[]{{.{key}}} left as-is")
        return m.group(0)

    def transform(text):
        return _EMPTY_SPAN_RE.sub(resolve, text)

    return transform
