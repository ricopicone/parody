"""What a translated chunk must keep exactly as the English had it (task #825).

The translator may rewrite every word of prose, so this compares only what
has to survive translation untouched or uncounted:

- maths, byte for byte;
- the number of blanks, key terms, footnotes, tables and blocks;
- section links, cross-references, code, images and links;
- ids, classes, attributes and raw LaTeX.

It catches loss, not misplacement, and not wrong meaning. In the trial a
service passed all of it while dropping maths into the middle of words. A
failed chunk is never written.
"""

import json
import re
from collections import Counter
from dataclasses import dataclass, field

import pypandoc

# The web path's reader (writers/artifact.py), so a chunk is parsed here the
# way the build will parse it, less auto_identifiers: pandoc would otherwise
# invent a heading's id from its text, and every translated heading without an
# explicit {#id} would "lose" its id (## Problems → problems, ## Aufgaben →
# aufgaben). Explicit ids are still read and compared.
CHECK_FROM = ("markdown-smart-markdown_in_html_blocks+raw_tex+tex_math_dollars"
              "+grid_tables-auto_identifiers")
_SPLIT = "<!-- parody:split -->"

_HTML_TAG = re.compile(r"<[^>]+>")
_HTML_MATH = re.compile(r"\$\$.+?\$\$|\$[^$]+\$", re.S)

# Where each node type keeps its [id, classes, key-values] triple.
_ATTR_AT = {"Span": 0, "Div": 0, "Image": 0, "Link": 0, "Code": 0,
            "CodeBlock": 0, "Table": 0, "Figure": 0, "Header": 1}


@dataclass
class Facts:
    blocks: int = 0
    math: Counter = field(default_factory=Counter)
    cloze: int = 0
    keywords: list = field(default_factory=list)
    keyword_en: list = field(default_factory=list)  # each key term's en="…", in order
    hashrefs: Counter = field(default_factory=Counter)
    cites: Counter = field(default_factory=Counter)
    notes: int = 0
    code: Counter = field(default_factory=Counter)
    images: Counter = field(default_factory=Counter)
    links: Counter = field(default_factory=Counter)
    tables: int = 0
    ids: Counter = field(default_factory=Counter)
    classes: Counter = field(default_factory=Counter)
    attrs: Counter = field(default_factory=Counter)
    raw: Counter = field(default_factory=Counter)


def _stringify(node):
    if isinstance(node, list):
        return "".join(_stringify(n) for n in node)
    if not isinstance(node, dict):
        return ""
    t, c = node.get("t"), node.get("c")
    if t == "Str":
        return c
    if t in ("Space", "SoftBreak", "LineBreak"):
        return " "
    if t == "Math":
        return f"${c[1]}$"
    if t == "Code":
        return c[1]
    if t == "Span":
        return _stringify(c[1])
    if t in ("Link", "Image"):
        return _stringify(c[1])
    if t == "Quoted":
        return _stringify(c[1])
    if t == "Cite":
        return _stringify(c[1])
    return _stringify(c) if isinstance(c, list) else ""


def _walk(node, facts):
    if isinstance(node, list):
        for n in node:
            _walk(n, facts)
        return
    if not isinstance(node, dict) or "t" not in node:
        return
    t, c = node["t"], node.get("c")
    if t in _ATTR_AT:
        ident, classes, kvs = c[_ATTR_AT[t]]
        if ident:
            facts.ids[ident] += 1
        facts.classes.update(classes)
        # caption_plain is a leftover of the LaTeX migration that nothing reads;
        # its prose may be translated or not.
        facts.attrs.update((k, v) for k, v in kvs if k != "caption_plain")
        if "cloze" in classes:
            facts.cloze += 1
        if t == "Span" and "keyword" in classes:
            facts.keywords.append(_stringify(c[1]).strip())
            facts.keyword_en.append(dict(kvs).get("en"))
        if t == "Span" and "hashref" in classes:
            facts.hashrefs[_stringify(c[1])] += 1
    if t == "Math":
        facts.math[c[1]] += 1
    elif t in ("Code", "CodeBlock"):
        facts.code[c[1]] += 1
    elif t == "Image":
        facts.images[c[2][0]] += 1
    elif t == "Link":
        facts.links[c[2][0]] += 1
    elif t == "Cite":
        facts.cites.update(cit["citationId"] for cit in c[0])
    elif t == "Note":
        facts.notes += 1
    elif t == "Table":
        facts.tables += 1
    elif t in ("RawInline", "RawBlock"):
        if c[1].strip() == _SPLIT:
            pass
        elif c[0] == "html":
            # Raw HTML (the summary tables) carries prose in its cells: its
            # tags and maths must survive, the text between them is translated.
            facts.raw.update(_HTML_TAG.findall(c[1]))
            facts.raw.update(_HTML_MATH.findall(c[1]))
        else:
            facts.raw[c[1]] += 1
    if isinstance(c, list):
        _walk(c, facts)


def _parse(text):
    return json.loads(pypandoc.convert_text(text, "json", format=CHECK_FROM))


def _facts_of_blocks(blocks):
    facts = Facts(blocks=len(blocks))
    _walk(blocks, facts)
    return facts


def chunk_facts(chunks, isolated=False):
    """One ``Facts`` per chunk.

    By default the chunks are parsed as one document, joined by split markers,
    so a footnote's text is counted where it is referenced, as in the build.
    ``isolated`` parses each chunk on its own, for chunks whose markup is broken
    badly enough to swallow a marker. It raises ``ValueError`` in joined mode
    when that has happened.
    """
    if isolated:
        return [_facts_of_blocks(_parse(c)["blocks"]) for c in chunks]
    doc = _parse(f"\n\n{_SPLIT}\n\n".join(chunks))
    segments, current = [], []
    for block in doc["blocks"]:
        if block.get("t") == "RawBlock" and block["c"][1].strip() == _SPLIT:
            segments.append(current)
            current = []
        else:
            current.append(block)
    segments.append(current)
    if len(segments) != len(chunks):
        raise ValueError("a chunk's markup swallowed a split marker")
    return [_facts_of_blocks(s) for s in segments]


def _counter_diff(en, tr):
    missing = sorted((en - tr).elements())
    extra = sorted((tr - en).elements())
    parts = []
    if missing:
        parts.append("missing " + ", ".join(map(str, missing[:5])))
    if extra:
        parts.append("unexpected " + ", ".join(map(str, extra[:5])))
    return "; ".join(parts)


def compare_facts(en, tr):
    """Problems with a translated chunk, as readable strings; empty if none."""
    problems = []
    for name, label in (("blocks", "block count"), ("cloze", "blanks"),
                        ("notes", "footnotes"), ("tables", "tables")):
        a, b = getattr(en, name), getattr(tr, name)
        if a != b:
            problems.append(f"{label}: {b} of {a}")
    if len(en.keywords) != len(tr.keywords):
        problems.append(f"key terms: {len(tr.keywords)} of {len(en.keywords)}")
    for name, label in (("math", "maths changed"), ("hashrefs", "section links changed"),
                        ("cites", "cross-references changed"), ("code", "code changed"),
                        ("images", "images changed"), ("links", "links changed"),
                        ("ids", "ids changed"), ("classes", "classes changed"),
                        ("attrs", "attributes changed"), ("raw", "raw LaTeX changed")):
        a, b = getattr(en, name), getattr(tr, name)
        if a != b:
            problems.append(f"{label}: {_counter_diff(a, b)}")
    return problems


def _div_fences(chunk):
    """(opening, closing) ``:::`` fence lines in a chunk, outside code."""
    from .chunks import _DIV_CLOSE, _DIV_OPEN, _FENCE_OPEN

    opens = closes = 0
    fence = None
    for line in chunk.split("\n"):
        m = _FENCE_OPEN.match(line)
        if fence:
            if m and m.group(1)[0] == fence and not line.strip().strip(fence):
                fence = None
            continue
        if m:
            fence = m.group(1)[0]
        elif _DIV_OPEN.match(line):
            opens += 1
        elif _DIV_CLOSE.match(line):
            closes += 1
    return opens, closes


_FOOTNOTE_REF = re.compile(r"\[\^([^\]\s]+)\](?!:)")
_FOOTNOTE_DEF = re.compile(r"^\[\^([^\]\s]+)\]:", re.M)


def _footnote_labels(chunk):
    """The chunk's footnote references and definitions, by label.

    Checked per chunk at the source because pandoc resolves a footnote
    across chunks: a definition that was relabelled shows up as a missing
    note on the chunk that *refers* to it, not on the chunk that broke it.
    """
    return (sorted(_FOOTNOTE_REF.findall(chunk)), sorted(_FOOTNOTE_DEF.findall(chunk)))


def compare_chunks(en_chunks, tr_chunks):
    """``{chunk index: [problems]}`` for every chunk that fails; ``{}`` if all pass."""
    try:
        en, tr = chunk_facts(en_chunks), chunk_facts(tr_chunks)
    except ValueError:
        # Broken markup in a translation (an unclosed div, say) can swallow the
        # markers. Compare chunk by chunk so the fault lands on its own chunk.
        en, tr = chunk_facts(en_chunks, isolated=True), chunk_facts(tr_chunks, isolated=True)
    result = {}
    for i, (a, b) in enumerate(zip(en, tr)):
        problems = compare_facts(a, b)
        # Pandoc closes an unclosed div silently, so on its own a chunk that
        # lost its closing ::: parses the same as one that kept it.
        if _div_fences(tr_chunks[i]) != _div_fences(en_chunks[i]):
            problems.append("fenced divs: opening/closing ::: lines changed")
        if _footnote_labels(tr_chunks[i]) != _footnote_labels(en_chunks[i]):
            problems.append("footnote labels changed: keep [^label] exactly")
        if problems:
            result[i] = problems
    return result


_ATTR_BLOCK = re.compile(r"\]\{([^{}]*)\}")
_KEYWORD_CLASS = re.compile(r"(?:^|\s)\.keyword(?:\s|$)")


def add_keyword_glosses(tr_chunk, en_keywords):
    """Give the i-th key term in a chunk the i-th term of ``en_keywords`` as ``en="…"``.

    Applied to the *English*, before it is sent: positional matching is only
    right in the chunk the terms were read from. The translator then carries
    each ``en`` along with its term, wherever grammar moves it, and the check
    verifies that it did. The renderer shows it after the translated term
    (spec D12). Unchanged when a term already has one, or when the counts
    differ.
    """
    blocks = [m for m in _ATTR_BLOCK.finditer(tr_chunk)
              if _KEYWORD_CLASS.search(m.group(1))]
    if len(blocks) != len(en_keywords) or any("en=" in m.group(1) for m in blocks):
        return tr_chunk
    out, last = [], 0
    for m, english in zip(blocks, en_keywords):
        value = english.replace('"', "”")
        out.append(tr_chunk[last:m.end(1)])
        out.append(f' en="{value}"')
        last = m.end(1)
    out.append(tr_chunk[last:])
    return "".join(out)
