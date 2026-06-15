"""Book-metadata plugin: surface editions/bibliographic data into the artifact.

In meta (System B), ``common/book-defs.json`` is the per-book registry: full
title, short name, companion URL, and an ``editions`` map (each with edition
number, year, publisher, ISBN, publisher URL, series, and the version-track
bindings v-ts/v-ds). The website and build tooling read it; for parody it is
exactly the bibliographic metadata a homepage book page wants.

Unlike apocrypha's large machine-generated sidecar, this is small curated
data, so it lives **inline** in parody.yaml under a ``book:`` key (the
config value *is* the metadata). Enabling the plugin (i.e. having a ``book:``
block) injects a normalized ``book`` object into the build artifact via the
``make_artifact_hook`` post-processor; print builds never call it.

``normalize_book`` accepts both the meta shape (``book-name``,
``url-companion``, ``editions: {id: {...}}`` with hyphenated keys) and the
parody shape (``name``, ``companion_url``, ``editions: [...]`` snake_case),
so a round-tripped block re-normalizes to itself (idempotent). Meta-internal
keys (``json-file-*``, the apocrypha pointer) and obvious placeholders
(``TBD``, all-zero ISBNs, empty strings) are dropped.
"""

import re


def _placeholder(key, value):
    if value in (None, ""):
        return True
    text = str(value).strip()
    if text.upper() == "TBD":
        return True
    if key == "isbn":
        digits = re.sub(r"\D", "", text)
        if digits and set(digits) == {"0"}:
            return True
    return False


# source key -> normalized key, in emit order; ``edition``/``v`` handled apart
_EDITION_KEYS = (
    ("description", "description"),
    ("year", "year"),
    ("publisher", "publisher"),
    ("isbn", "isbn"),
    ("series", "series"),
    ("series-name", "series_name"), ("series_name", "series_name"),
    ("url-companion", "url_companion"), ("url_companion", "url_companion"),
    ("url-publisher", "url_publisher"), ("url_publisher", "url_publisher"),
    ("v-ts", "v_ts"), ("v_ts", "v_ts"),
    ("v-ds", "v_ds"), ("v_ds", "v_ds"),
)


def _edition(eid, fields):
    out = {"id": str(eid)}
    # meta stores the edition number under "edition"; engineering-computing
    # used "v". Prefer the explicit one.
    number = fields.get("edition") or fields.get("v")
    if number not in (None, ""):
        out["edition"] = str(number)
    for src_key, dst_key in _EDITION_KEYS:
        if dst_key in out:
            continue
        val = fields.get(src_key)
        if not _placeholder(dst_key, val):
            out[dst_key] = val
    return out


def normalize_book(raw):
    """Normalize either shape into the parody ``book`` object. Returns {} if
    there's nothing usable."""
    if not isinstance(raw, dict):
        return {}

    editions = []
    eds = raw.get("editions")
    if isinstance(eds, dict):
        for eid, fields in eds.items():
            if isinstance(fields, dict):
                editions.append(_edition(eid, fields))
    elif isinstance(eds, list):
        for fields in eds:
            if isinstance(fields, dict):
                editions.append(_edition(fields.get("id", ""), fields))

    book = {}
    name = raw.get("name") or raw.get("book-name") or raw.get("book_name")
    short = (raw.get("short_name") or raw.get("book-short-name")
             or raw.get("book_short_name"))
    companion = (raw.get("companion_url") or raw.get("url-companion")
                 or raw.get("url_companion"))
    if name:
        book["name"] = name
    if short:
        book["short_name"] = short
    if companion:
        book["companion_url"] = companion
    if editions:
        book["editions"] = editions
    return book


def make_artifact_hook(config, project_dir):
    """Return a hook ``(artifact) -> artifact`` that adds the ``book`` object.
    No-op when the config normalizes to nothing."""
    book = normalize_book(config if isinstance(config, dict) else {})

    def hook(artifact):
        if book:
            artifact["book"] = book
        return artifact

    return hook
