"""Parts-list plugin: generate the general hardware catalog for the web.

Meta's ``versions-lister.py`` reads the (flattened) versions DB and emits the
general target/development-system catalog two ways: LaTeX (print) and HTML
``<details>`` markdown (web). The rtc migration captured the *print* tex (a
print-only ``{=latex}\\input{...}`` blob — works, the components table's
``\\Cref{a6}`` etc. resolve) but NOT the web markdown, so the general catalog
is missing from the artifact/website.

This plugin ports BOTH branches of versions-lister. It is a **pipeline-aware**
``make_transform``:

- artifact (web): replaces a ``[]{.parts-list ...}`` marker with the generated
  ``<details>`` markdown catalog;
- print: drops that marker and expands the migration's print-only
  ``\\input{…-versions-list-<edition>-<version>-general}`` into the generated
  LaTeX catalog. (The migration kept the ``\\input`` but versions-lister's LaTeX
  branch was never ported, so the .tex never existed; this generates it inline.)

The catalog is built from ``versions.yaml`` for the active ts/ds versions (the
versioning plugin's tracks), so it is dynamic per edition.

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


# ---------------------------------------------------------------------------
# LaTeX (print) general catalog — the other half of versions-lister.py that the
# rtc migration never captured. The source markdown carries a print-only
# `{=latex}\input{<sec>-versions-list-<edition>-<version>-general}` blob whose
# .tex was generated by versions-lister's LaTeX branch; that branch was never
# ported, so the file did not exist. This generates the same content inline
# (the print transform substitutes it for the \input), built from versions.yaml.
#
# Adapted to parody's print contract: standard \section/\subsection (the MIT
# class disables versions-lister's custom 3-arg sectioning) with hashref \labels
# for cross-refs, and parody-print.sty's \myindex/\mintinline/\myurlinline. The
# system-diagram \includestandalone figure of the meta original is dropped (no
# such asset in the parody source).
# ---------------------------------------------------------------------------

_TEX_GENERAL_SKIP = {"specific", "suppliers", "quantity", "unspecific",
                     "variables-descriptions", "variables-names"}


def _enumerate_general_tex(node, out, skip, depth=0, old_depth=0, ts_version=""):
    """Port of versions-lister.py enumerater_general_tex: walk a subsystem dict
    emitting ``\\item`` rows, opening/closing nested ``enumerate`` per depth."""
    dd = depth - old_depth
    for _ in range(abs(dd)):
        out.append("\n\\begin{enumerate}\n" if dd > 0 else "\n\\end{enumerate}\n")
    keys = list(node.keys())
    for i, k in enumerate(keys):
        v = node[k]
        if k in skip or k in ("hash", "emulation", "general"):
            pass
        elif isinstance(v, str):
            if k == "quantity":
                out.append(f"\\item Total quantity: {v}\n")
            elif k not in ("name", "kind", "description", "variants", "url"):
                if v.startswith("`"):
                    code = v.replace("`", "")
                    out.append(f"\\item {capfirst(k)}: "
                               f"\\mintinline{{matlab}}{{{code}}}\n")
                else:
                    out.append(f"\\item {capfirst(k)}: {capfirst(v)}\n")
        elif isinstance(v, list) and v:
            if k == "variables" and ts_version:
                summary = (f"Variables (different for each specific "
                           f"{ts_version} system---see \\cref{{ef}})")
            elif k == "variables":
                summary = ("Variables (different for each specific "
                           "system---see \\cref{ef})")
            else:
                summary = k
            out.append(f"\\item {capfirst(summary)}\\begin{{enumerate}}\n")
            descriptions = node.get(f"{k}-descriptions", {})
            names = node.get(f"{k}-names", {})
            for li in v:
                if f"{k}-descriptions" in node:
                    out.append(f"\n\\item {capfirst(li).replace('-', ' ')}: "
                               f"{descriptions[li]}")
                    if li in names:
                        out.append(f", given the code variable name "
                                   f"\\mintinline{{matlab}}"
                                   f"{{{names[li].replace('`', '')}}}")
                else:
                    out.append(f"\n\\item {capfirst(li)}")
            out.append("\\end{enumerate}\n")
        elif isinstance(v, dict) and k != "variants":
            label = f"\\label{{component-{v['hash']}}}" if "hash" in v else ""
            em = " (software emulation support)" if v.get("emulation") == "yes" else ""
            if k == "specific":
                out.append("\\item Devices to choose from that satisfy the "
                           "general requirements:")
            else:
                sub = set(v) - {"hash", "emulation", "name", "kind", "unspecific",
                                "specific", "quantity", "general"}
                if "name" in v:
                    if "kind" in v and "description" in v:
                        out.append(f'\n\\item {capfirst(v["kind"])}: '
                                   f'{capfirst(v["name"])}{em}. {label} '
                                   f'{v["description"]}')
                    elif "kind" in v:
                        out.append(f'\n\\item {capfirst(v["kind"])}: '
                                   f'{capfirst(v["name"])}{em} {label}')
                    else:
                        out.append(f'\n\\item {capfirst(v["name"])} {label} {em}')
                elif "url" in v:
                    out.append(f'\n{capfirst(k)}\\myurlinline{{{v["url"]}}}'
                               f'{{{v.get("hash", "")}}}{em} {label}')
                else:
                    out.append(f"\n{capfirst(k)} ({em})")
                if sub:
                    _enumerate_general_tex(v, out, skip, depth + 1, depth,
                                           ts_version)
        if i == len(keys) - 1:
            out.append("\\end{enumerate}\n")


def _ts_general_tex(flat, version):
    """General target-system LaTeX section for the active ts version."""
    node = flat.get(version)
    if not isinstance(node, dict):
        return ""
    v = version
    out = [
        f"\\section{{General {v} target system}}"
        f"\\label{{general-target-system-{v}}}\\label{{wp}}\n",
        "\\myindex[start]{Target system!general}\n",
        f"This section includes a definition of the general {v} target system. "
        f"For specific hardware instances, see \\cref{{ef}}. "
        f"We define the general {v} target system as follows.\n",
    ]
    for slug, name, h in HEADINGS:
        hv = node.get(slug)
        if hv is None:
            continue
        if isinstance(hv, str):
            out.append(f"\n\\subsection{{{name}}}\\label{{{slug}}}"
                       f"\\label{{{h}}}\n\n{hv}.\n")
            continue
        if "name" in hv:
            if "description" in hv and "kind" in hv:
                title = f'{name}: {hv["kind"]}, {hv["name"]}'
            else:
                title = f'{name}: {hv["name"]}'
            desc = f'\n\n{hv["description"]}' if "description" in hv else ""
            includes = f'The {hv["name"]} includes the following components:'
        else:
            title, desc = name, ""
            includes = f"The {name} includes the following components:"
        out.append(f"\n\\subsection{{{title}}}\\label{{{slug}}}\\label{{{h}}}"
                   f"{desc}\n\n{includes}\n\\begin{{enumerate}}\n")
        _enumerate_general_tex(hv, out, _TEX_GENERAL_SKIP, ts_version=v)
    out.append("\n\\myindex[stop]{Target system!general}\n")
    return "".join(out)


def _ds_general_tex(flat, version):
    """General development-system LaTeX section (a blurb; no enumeration,
    matching versions-lister.py's DS-general LaTeX branch)."""
    node = flat.get(version)
    if not isinstance(node, dict):
        return ""
    v = version
    ide = node.get("ide", "the IDE")
    return (
        f"\\section{{General {v} development system}}"
        f"\\label{{general-development-system-{v}}}\\label{{dm}}\n"
        "\\myindex[start]{Development system!general}\n"
        f"This section includes a definition of the general {v} development "
        f"system. For specific hardware instances, see \\cref{{uh}}. "
        f"We define the general {v} development system as follows. It consists "
        f"of a development computer, a virtual machine hypervisor, and {ide}.\n"
        "\\myindex[stop]{Development system!general}\n")


def generate_general_catalog_tex(flat, version):
    """LaTeX for one general catalog (TS or DS), dispatched by version prefix."""
    if version.startswith("T"):
        return _ts_general_tex(flat, version)
    if version.startswith("D"):
        return _ds_general_tex(flat, version)
    return ""


# marker the migrator drops where the catalog belongs, e.g.
# []{.parts-list ts=T1 ds=D1} or just []{.parts-list-ts} / []{.parts-list-ds}
_MARKER_RE = re.compile(
    r'\[\]\{\.parts-list(?P<attrs>[^}]*)\}')

# the migration's print-only include, e.g.
# \input{specific-t1-target-systems-versions-list-hp1-T1-general}
_VERSIONS_LIST_INPUT_RE = re.compile(
    r"\\input\{[\w-]*versions-list-(?P<edition>\w+)-(?P<version>\w+)-general\}")


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


# ---------------------------------------------------------------------------
# Structured specific-variant catalog (P3): the parts DATA the web /systems
# pages render — every component of the active ts/ds system with its scalar
# specs and the specific/unspecific device choices (make/model + suppliers)
# from versions.yaml. Distinct from the general <details> markdown above:
# this is structured JSON on the artifact, one "system" per active version.
# ---------------------------------------------------------------------------

# keys that are structure/metadata, never rendered as a plain spec row
_META_KEYS = {"hash", "emulation", "general", "name", "kind", "description",
              "variants", "url", "parent", "children", "suppliers",
              "specific", "unspecific", "variables", "variables-names",
              "variables-descriptions"}


def _suppliers(node):
    out = []
    for name, sup in (node.get("suppliers") or {}).items():
        if isinstance(sup, dict) and sup.get("url"):
            out.append({"name": name, "url": sup["url"]})
    return out


def _spec_rows(node):
    """Scalar (label, value) rows for a node, excluding structural keys."""
    rows = []
    for k, v in node.items():
        if k in _META_KEYS or k == "quantity":
            continue
        if isinstance(v, (str, int, float)):
            rows.append([capfirst(str(k)), capfirst(str(v))])
    return rows


def _choices(node):
    """The device options that satisfy a component: ``specific`` (fully
    specified, owner-recommended) and ``unspecific`` (acceptable alternatives),
    each with its own fields + suppliers."""
    out = []
    for bucket in ("specific", "unspecific"):
        group = node.get(bucket)
        if not isinstance(group, dict):
            continue
        for key, choice in group.items():
            if not isinstance(choice, dict):
                continue
            out.append({
                "kind": bucket,
                "name": choice.get("name", str(key)),
                "description": choice.get("description", ""),
                "hash": choice.get("hash", ""),
                "fields": _spec_rows(choice),
                "suppliers": _suppliers(choice),
            })
    return out


def _component(subsystem, subsystem_title, node):
    return {
        "subsystem": subsystem,
        "subsystem_title": subsystem_title,
        "name": node.get("name", ""),
        "kind": node.get("kind", ""),
        "description": node.get("description", ""),
        "hash": node.get("hash", ""),
        "quantity": str(node.get("quantity", "")),
        "specs": _spec_rows(node),
        "suppliers": _suppliers(node),
        "choices": _choices(node),
    }


def _system_components(version_node):
    """Flatten a version's subsystems into a component list. A subsystem that
    carries its own ``name`` (target-computer) is one component; otherwise its
    children (ui→keypad/display, prototyping→nand…) are the components."""
    components = []
    for slug, title, _h in HEADINGS:
        sub = version_node.get(slug)
        if not isinstance(sub, dict):
            continue
        if "name" in sub:
            components.append(_component(slug, title, sub))
        else:
            for cslug, cnode in sub.items():
                if isinstance(cnode, dict):
                    components.append(
                        _component(f"{slug}-{cslug}", title, cnode))
    return components


def generate_parts_data(flat, ts_version=None, ds_version=None):
    """Structured systems catalog for the active versions: a list of systems
    (the active ts target system, the active ds development system), each with
    its components and their device choices + suppliers."""
    systems = []
    for track, version, kind in (("ts", ts_version, "target"),
                                 ("ds", ds_version, "development")):
        if not version:
            continue
        node = flat.get(version)
        if not isinstance(node, dict):
            continue
        systems.append({
            "track": track,
            "version": version,
            "title": f"{version} {kind} system",
            "description": node.get("description", ""),
            "components": _system_components(node),
        })
    return systems


def make_artifact_hook(config, project_dir):
    """Attach the structured per-edition systems catalog to the artifact as a
    top-level ``parts`` key (the data parody-web's /systems pages render)."""
    from pathlib import Path
    cfg = config if isinstance(config, dict) else {}
    tracks = cfg.get("tracks") or {}
    src = Path(project_dir) / cfg.get("source", "versions.yaml")
    flat = flatten_versions(load_versions(src)) if src.is_file() else {}
    systems = generate_parts_data(flat, tracks.get("ts"), tracks.get("ds"))

    def hook(artifact):
        if systems:
            artifact["parts"] = systems
        return artifact

    return hook


def make_transform(config, project_dir, target="artifact"):
    """Pipeline-aware transform. In the artifact pipeline it expands a
    ``[]{.parts-list …}`` marker into the generated web catalog; in print it
    drops the marker and instead expands the migration's print-only
    ``\\input{…-versions-list-…-general}`` into the generated LaTeX catalog
    (its .tex was never produced — see generate_general_catalog_tex)."""
    cfg = config if isinstance(config, dict) else {}
    source = cfg.get("source", "versions.yaml")
    tracks = cfg.get("tracks") or {}
    default_ts = tracks.get("ts")
    default_ds = tracks.get("ds")
    from pathlib import Path
    src = Path(project_dir) / source
    flat = flatten_versions(load_versions(src)) if src.is_file() else {}

    def transform(text):
        def repl_marker(m):
            if target != "artifact":
                return ""  # print's catalog comes from the \input below
            ts, ds = _marker_versions(m.group("attrs"), default_ts, default_ds)
            return generate_general_catalog(flat, ts, ds)
        text = _MARKER_RE.sub(repl_marker, text)
        if target == "print":
            text = _VERSIONS_LIST_INPUT_RE.sub(
                lambda m: generate_general_catalog_tex(flat, m.group("version")),
                text)
        return text

    return transform
