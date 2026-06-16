"""Parts-list plugin: generate the general hardware catalog for the web.

Meta's ``versions-lister.py`` reads the (flattened) versions DB and emits the
general target/development-system catalog two ways: LaTeX (print) and HTML
``<details>`` markdown (web). The rtc migration captured the *print* tex (a
print-only ``{=latex}\\input{...}`` blob — works, the components table's
``\\Cref{a6}`` etc. resolve) but NOT the web markdown, so the general catalog
is missing from the artifact/website.

This plugin closes that gap: it ports the *markdown* branch of versions-lister
and injects the generated ``<details>`` general catalog into the artifact
pipeline only (print keeps its migration-generated tex). It is a
**pipeline-aware** ``make_transform`` — it replaces a ``[]{.parts-list ...}``
marker with the generated catalog when ``target == 'artifact'`` and removes it
for print. The catalog is built from ``versions.yaml`` for the active ts/ds
versions (the versioning plugin's tracks), so it is dynamic per edition.

Faithful to versions-lister's HTML structure: ``<details><summary>…</summary>``
per component with ``<div class="version-list-item">key: value</div>`` rows and
a nested suppliers ``<details>``.
"""

import re

from .versioning import flatten_versions, load_versions

# subsystem headings, mirroring versions-lister.py's `headings` (slug -> web
# heading name + hashref). These are the general-catalog section anchors the
# components table cross-references.
HEADINGS = (
    ("target-computer", "target computer", "a6"),
    ("ui", "user interface subsystem", "y6"),
    ("electromechanical-subsystem", "electromechanical subsystem", "lf"),
    ("prototyping", "prototyping and testing hardware", "wi"),
)

# keys that never render as their own version-list-item row
_SKIP_ALWAYS = {"hash", "emulation", "general", "name", "kind", "description",
                "variants", "url"}


def capfirst(s):
    return s[:1].upper() + s[1:]


def _emulation(v):
    if isinstance(v, dict) and v.get("emulation") == "yes":
        return ('<div class="tooltip"><div data-md-tooltip="has software '
                'emulation support"><span class="fa-solid fa-laptop-code">'
                '</span></div></div>')
    return ""


def _enumerate_general(node, out, skip, ts_version=""):
    """Port of versions-lister.py enumerater_general_md: walk a subsystem dict
    emitting <details>/<div class="version-list-item"> rows."""
    keys = list(node.keys())
    for i, k in enumerate(keys):
        v = node[k]
        if k in skip:
            pass
        elif isinstance(v, str):
            if k == "quantity":
                out.append(f"#. Total quantity: {v}\n")
            elif k in ("hash", "emulation", "general"):
                pass
            elif k not in ("name", "kind", "description", "variants", "url"):
                out.append(f'<div class="version-list-item">{capfirst(k)}')
                out.append(f": {capfirst(v)}</div>\n")
        elif isinstance(v, list) and v:
            if k == "variables":
                anchor = (f"specific-target-systems-{ts_version}" if ts_version
                          else "specific-target-systems")
                label = (f"different for each "
                         f"[specific {ts_version} system](#{anchor})")
                summary = f"Variables ({label})"
            else:
                summary = k
            out.append(f"<details open><summary>{capfirst(summary)}</summary>")
            for li in v:
                out.append(f'\n<div class="version-list-item">{capfirst(li)}</div>')
            out.append("\n</details>\n")
        elif isinstance(v, dict) and k != "variants":
            em = _emulation(v)
            if k == "specific":
                out.append("#. Devices to choose from that satisfy the "
                           "general requirements:")
            else:
                sub = set(v) - {"hash", "emulation", "name", "kind",
                                "unspecific", "specific", "quantity", "general"}
                cls = "" if sub else ' class="empty"'
                if "name" in v:
                    if "kind" in v:
                        head = f'{capfirst(v["kind"])}: {capfirst(v["name"])} {em}'
                    else:
                        head = f'{capfirst(v["name"])} {em}'
                    desc = f' {v["description"]}' if "description" in v else ""
                    out.append(f"<details{cls}><summary>{head}</summary>{desc}")
                elif "url" in v:
                    out.append(f'<details{cls}><summary><a href="{v["url"]}" '
                               f'target="_blank">{capfirst(k)}</a> {em}</summary>')
                else:
                    out.append(f"<details{cls}><summary>{capfirst(k)} {em}</summary>")
                if sub:
                    _enumerate_general(v, out, skip, ts_version)
                else:
                    out.append("</details>")
        if i == len(keys) - 1:
            out.append("</details>\n")


def _ts_general(flat, ts_version):
    """General target-system section for the active ts version."""
    node = flat.get(ts_version)
    if not isinstance(node, dict):
        return ""
    k1 = ts_version
    out = [
        f"\n## General {k1} target system "
        f'{{#general-target-system-{k1} .ts .{k1} h="wp"}}\n\n'
        f"This section includes a definition of the general {k1} target "
        f"system. For specific hardware instances, see "
        f"[Specific {k1} target systems](#specific-target-systems-{k1}). "
        f"We define the general {k1} target system as follows.\n",
    ]
    for slug, name, h in HEADINGS:
        hv = node.get(slug)
        if hv is None:
            continue
        if isinstance(hv, str):
            out.append(f'\n### {name} {{#{slug} .ts .{k1} h="{h}"}}\n\n{hv}.\n\n')
            continue
        deets = "<details><summary>Details</summary>" if slug == "target-computer" else ""
        if "name" in hv:
            if "description" in hv and "kind" in hv:
                title = f'{name}: {hv["kind"]}, {hv["name"]}'
            else:
                title = f'{name}: {hv["name"]}'
            desc = f'\n<p>{hv.get("description", "")}</p>' if "description" in hv else ""
            out.append(f'\n### {title} {{#{slug} .ts .{k1} h="{h}"}}{desc}\n{deets}\n\n')
        else:
            out.append(f'\n### {name} {{#{slug} .ts .{k1} h="{h}"}}\n\n{deets}\n\n')
        rows = []
        _enumerate_general(hv, rows, skip={"specific", "suppliers", "quantity",
                                           "unspecific"}, ts_version=k1)
        out.extend(rows)
        if slug == "target-computer":
            out.append("\n</details>")
    return "".join(out)


def _ds_general(flat, ds_version):
    """General development-system section (a blurb; no component enumeration,
    matching versions-lister.py's DS-general markdown branch)."""
    node = flat.get(ds_version)
    if not isinstance(node, dict):
        return ""
    k1 = ds_version
    ide = node.get("ide", "the IDE")
    return (
        f"\n## General {k1} development system "
        f'{{#general-development-system-{k1} .ds .{k1} h="2b"}}\n\n'
        f"This section includes a definition of the general {k1} development "
        f"system. For specific hardware instances, see "
        f"[Specific {k1} development systems](#specific-development-systems-{k1}). "
        f"We define the general {k1} development system as follows. It consists "
        f"of a development computer, a virtual machine (VM), and {ide}.\n")


def generate_general_catalog(flat, ts_version=None, ds_version=None):
    """Markdown for the general TS + DS catalog, for the active versions."""
    parts = []
    if ts_version:
        parts.append(_ts_general(flat, ts_version))
    if ds_version:
        parts.append(_ds_general(flat, ds_version))
    return "\n".join(p for p in parts if p)


# marker the migrator drops where the catalog belongs, e.g.
# []{.parts-list ts=T1 ds=D1} or just []{.parts-list-ts} / []{.parts-list-ds}
_MARKER_RE = re.compile(
    r'\[\]\{\.parts-list(?P<attrs>[^}]*)\}')


def _marker_versions(attrs, default_ts, default_ds):
    ts = default_ts if ".ts" in attrs or "parts-list-ts" in attrs else None
    ds = default_ds if ".ds" in attrs or "parts-list-ds" in attrs else None
    if ts is None and ds is None:  # bare []{.parts-list}: both
        ts, ds = default_ts, default_ds
    m = re.search(r"ts=([\w.]+)", attrs)
    if m:
        ts = m.group(1)
    m = re.search(r"ds=([\w.]+)", attrs)
    if m:
        ds = m.group(1)
    return ts, ds


def make_transform(config, project_dir, target="artifact"):
    """Pipeline-aware transform. In the artifact pipeline it expands a
    ``[]{.parts-list …}`` marker into the generated web catalog; in print it
    drops the marker (print uses its migration-generated tex)."""
    cfg = config if isinstance(config, dict) else {}
    source = cfg.get("source", "versions.yaml")
    tracks = cfg.get("tracks") or {}
    default_ts = tracks.get("ts")
    default_ds = tracks.get("ds")
    from pathlib import Path
    src = Path(project_dir) / source
    flat = flatten_versions(load_versions(src)) if src.is_file() else {}

    def transform(text):
        def repl(m):
            if target != "artifact":
                return ""  # print keeps its tex include elsewhere
            ts, ds = _marker_versions(m.group("attrs"), default_ts, default_ds)
            return generate_general_catalog(flat, ts, ds)
        return _MARKER_RE.sub(repl, text)

    return transform
