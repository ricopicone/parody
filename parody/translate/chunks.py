"""A section's source, cut into the units it is translated in (task #825).

A chunk is a top-level run of lines between blank lines. A blank line is not
a boundary inside a code fence, a fenced div, or display maths, nor when the
next line is indented (a footnote or list item continuing). So a chunk is
always one or more whole Markdown blocks. It may be coarser than pandoc's
blocks, never finer.

Chunk identity is a hash of its English text. A translation stores each chunk
under the hash of the English it was made from, and ``align_chunks`` lines the
stored hashes up against the current English, so an edit re-translates only
what it touched.
"""

import difflib
import hashlib
import re

import yaml

_FRONTMATTER = re.compile(r"\A---[ \t]*\n(.*?)\n---[ \t]*(?:\n|\Z)", re.S)
_FENCE_OPEN = re.compile(r"^\s*(`{3,}|~{3,})")
_FENCE_CLOSE = re.compile(r"^\s*(`{3,}|~{3,})\s*$")
# Not ^:{3,}\s*\S, which backtracks and reads the fourth colon of a ::::
# closer as a div name, so every exercise swallowed the one after it.
_DIV_OPEN = re.compile(r"^:{3,}\s*[^\s:]")
_DIV_CLOSE = re.compile(r"^:{3,}\s*$")
# A line that continues the block above it across a blank line: a definition
# (":   text" / "~   text") or a table caption ("Table: …" / ": …"). Split
# there, and pandoc reads the definition's indented paragraphs as code.
_CONTINUES = re.compile(r"^(?:Table:|[:~][ \t])")


def split_frontmatter(raw):
    """``(front matter dict, body)``; ``({}, raw)`` when there is none."""
    m = _FRONTMATTER.match(raw)
    if not m:
        return {}, raw
    meta = yaml.safe_load(m.group(1)) or {}
    return (meta if isinstance(meta, dict) else {}), raw[m.end():]


def _trim_blank_lines(lines):
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    return "\n".join(lines)


def split_chunks(body):
    """The section body as a list of chunks, in order, none empty."""
    lines = body.split("\n")
    chunks, current = [], []
    fence = None  # (fence char, run length) while inside a code fence
    depth = 0  # fenced-div nesting
    in_math = False  # inside $$ … $$

    def flush():
        text = _trim_blank_lines(current[:])
        if text:
            chunks.append(text)
        current.clear()

    for i, line in enumerate(lines):
        if fence is None and not line.strip():
            if depth == 0 and not in_math:
                following = next((nxt for nxt in lines[i + 1:] if nxt.strip()), None)
                # An indented next line continues the block above it, as does
                # a definition or a table caption.
                if following is None or not (following[:1].isspace()
                                             or _CONTINUES.match(following)):
                    flush()
                    continue
            current.append(line)
            continue

        current.append(line)
        if fence is not None:
            m = _FENCE_CLOSE.match(line)
            if m and m.group(1)[0] == fence[0] and len(m.group(1)) >= fence[1]:
                fence = None
            continue
        m = _FENCE_OPEN.match(line)
        if m:
            fence = (m.group(1)[0], len(m.group(1)))
            continue
        if _DIV_OPEN.match(line):
            depth += 1
        elif _DIV_CLOSE.match(line):
            depth = max(0, depth - 1)
        if line.count("$$") % 2:
            in_math = not in_math

    flush()
    return chunks


def chunk_hash(text):
    """Twelve hex digits of the chunk's SHA-256, ignoring surrounding whitespace."""
    return hashlib.sha256(text.strip().encode("utf-8")).hexdigest()[:12]


def align_chunks(english, stored):
    """Line stored translation hashes up against the current English hashes.

    Returns one ``(english index, stored index or None, status)`` per English
    chunk. ``current`` means the translation was made from exactly this
    English. ``stale`` means it was made from an earlier version of this
    chunk. ``missing`` means there is no translation to show. Stored chunks
    whose English was deleted are left out.
    """
    result = []
    matcher = difflib.SequenceMatcher(a=stored, b=english, autojunk=False)
    for op, a0, a1, b0, b1 in matcher.get_opcodes():
        if op == "equal":
            result.extend((b0 + k, a0 + k, "current") for k in range(b1 - b0))
        elif op == "replace":
            paired = min(a1 - a0, b1 - b0)
            result.extend((b0 + k, a0 + k, "stale") for k in range(paired))
            result.extend((b, None, "missing") for b in range(b0 + paired, b1))
        elif op == "insert":
            result.extend((b, None, "missing") for b in range(b0, b1))
    return result
