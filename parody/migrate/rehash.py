"""Re-key duplicate short hashes after a meta-book migration.

Meta tolerated duplicate short hashes (its checker was advisory) and the
migrator synthesizes problems-section hashes from meta *version* hashes —
both collide with content hashes, and parody schema v2 makes duplicates a
build error. Each book keeps a loser list (who gives up the contested hash);
selection precedence, applied when the list is authored:

1. problems sections whose hash was synthesized from a version hash lose to
   real content hashes;
2. where a hashref reference disambiguates the intended target, the other
   side loses;
3. interior headings lose to section headings;
4. otherwise the later-in-book occurrence loses.

New hashes are deterministic (md5 of salt:chapter/section#anchor, base36,
2 chars like meta's), skipping every hash already used in the book.
Idempotent: rerunning after the fix changes nothing. Rerun after any
re-migration (the migrator resurrects the duplicates).
"""

import hashlib
import re
from pathlib import Path

ALPHABET = "0123456789abcdefghijklmnopqrstuvwxyz"


def used_hashes(dst):
    used = set()
    for md in (Path(dst) / "chapters").rglob("*.md"):
        text = md.read_text()
        fm = re.match(r"---\n(.*?)\n---", text, re.S)
        if fm:
            m = re.search(r"^hash:\s*['\"]?([^'\"\n]+?)['\"]?\s*$",
                          fm.group(1), re.M)
            if m:
                used.add(m.group(1))
        used.update(re.findall(r"""\bh=["']?([A-Za-z0-9_:-]+)["']?""", text))
    return used


def fresh_hash(key, used, salt):
    digest = int(hashlib.md5(f"{salt}:{key}".encode()).hexdigest(), 16)
    while True:
        h = ALPHABET[digest % 36] + ALPHABET[(digest // 36) % 36]
        if h not in used:
            used.add(h)
            return h
        digest //= 36


def _rekey_line(line, old, new):
    return re.sub(
        rf"""(\bh=)(["']?){re.escape(old)}\2""", rf"\g<1>\g<2>{new}\g<2>", line)


def rehash_duplicates(dst, losers, salt):
    """Apply a loser list to the content repo at dst.

    losers: iterable of (relative md path, anchor id or None for the
    section level, duplicated hash). salt: stable per-book string (the
    historical scripts used the source repo's short name).
    Returns the number of entries re-keyed.
    """
    dst = Path(dst)
    used = used_hashes(dst)
    changed = 0
    for rel, anchor, old in losers:
        path = dst / rel
        key = (f"{rel.removeprefix('chapters/').removesuffix('.md')}"
               f"#{anchor or ''}")
        new = fresh_hash(key, used, salt)
        lines = path.read_text().splitlines(keepends=True)
        hit = False
        for i, line in enumerate(lines):
            if anchor is None:
                # front matter hash: line and the section heading's h= attr
                if re.match(rf"hash:\s*['\"]?{re.escape(old)}['\"]?\s*$", line):
                    lines[i] = re.sub(re.escape(old), new, line)
                    hit = True
                elif line.startswith("#") and (f'h="{old}"' in line
                                               or f"h={old}" in line):
                    lines[i] = _rekey_line(line, old, new)
                    hit = True
            elif f"{{#{anchor}" in line or f"#{anchor} " in line:
                if _rekey_line(line, old, new) != line:
                    lines[i] = _rekey_line(line, old, new)
                    hit = True
        if hit:
            path.write_text("".join(lines))
            print(f"  {rel}#{anchor or '<section>'}: {old} -> {new}")
            changed += 1
        else:
            print(f"  {rel}#{anchor or '<section>'}: {old} already re-keyed, "
                  "skipping")
    print(f"{changed} re-keyed")
    return changed


def load_losers(path):
    """Loser list from YAML: a list of {file, anchor, hash} mappings
    (anchor may be null for section-level hashes)."""
    import yaml

    entries = yaml.safe_load(Path(path).read_text()) or []
    return [(e["file"], e.get("anchor"), e["hash"]) for e in entries]
