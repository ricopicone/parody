"""Bibliography plugin: parse the book's BibTeX into a key->citation map and
emit it into the artifact as ``references``.

Enabled by a ``references:`` key in parody.yaml — a path to the .bib (default
``book.bib``). The artifact consumer (parody-web) resolves ``[@key]`` citation
spans to "Author (Year)" links and per-section reference lists from this map,
so the bibliography travels with the artifact rather than being shipped beside
the renderer. Print builds use biblatex directly and never call this.
"""
import re
from pathlib import Path


def _find_entries(text):
    """Yield (type, key, body) for each @type{key, ...} with brace matching."""
    i = 0
    while True:
        at = text.find("@", i)
        if at < 0:
            break
        m = re.match(r"@(\w+)\s*\{\s*([^,\s]+)\s*,", text[at:])
        if not m:
            i = at + 1
            continue
        ob = text.find("{", at)
        depth = 0
        k = ob
        while k < len(text):
            if text[k] == "{":
                depth += 1
            elif text[k] == "}":
                depth -= 1
                if depth == 0:
                    break
            k += 1
        yield m.group(1).lower(), m.group(2).strip(), text[ob + 1:k]
        i = k + 1


def _fields(body):
    out = {}
    for fm in re.finditer(r"(\w+)\s*=\s*", body):
        name = fm.group(1).lower()
        p = fm.end()
        if p >= len(body):
            break
        if body[p] == "{":
            depth, q = 0, p
            while q < len(body):
                if body[q] == "{":
                    depth += 1
                elif body[q] == "}":
                    depth -= 1
                    if depth == 0:
                        break
                q += 1
            out[name] = body[p + 1:q]
        elif body[p] == '"':
            q = body.find('"', p + 1)
            out[name] = body[p + 1:q if q > 0 else len(body)]
        else:
            mm = re.search(r"[,\n]", body[p:])
            out[name] = (body[p:p + mm.start()] if mm else body[p:]).strip()
    return out


def _clean(s):
    s = s or ""
    s = re.sub(r"\\(?:emph|textbf|textit|texttt|mkbibquote|enquote)\{(.*?)\}", r"\1", s)
    s = s.replace("~", " ").replace(r"\&", "&").replace("---", "—").replace("--", "–")
    s = re.sub(r"\\['`^\"=.~]\{?([a-zA-Z])\}?", r"\1", s)  # accents \'{e} -> e
    s = re.sub(r"\\[a-zA-Z]+", "", s)
    s = re.sub(r"[{}]", "", s)
    return " ".join(s.split())


def _lastnames(author):
    names = []
    for a in re.split(r"\s+and\s+", author or ""):
        a = _clean(a)
        if not a:
            continue
        names.append(a.split(",")[0].strip() if "," in a else a.split()[-1])
    return names


def _label(author, year, key):
    ln, y = _lastnames(author), _clean(year)
    if not ln:
        who = _clean(key)
    elif len(ln) == 1:
        who = ln[0]
    elif len(ln) == 2:
        who = f"{ln[0]} and {ln[1]}"
    else:
        who = f"{ln[0]} et al."
    return f"{who} ({y})" if y else who


def parse_bib(path):
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    refs = {}
    for _typ, key, body in _find_entries(text):
        f = _fields(body)
        author = f.get("author") or f.get("editor") or ""
        year = f.get("year") or f.get("date") or ""
        bits = [b for b in (_clean(author), _clean(f.get("title")),
                            _clean(f.get("journal") or f.get("booktitle")
                                   or f.get("publisher") or f.get("howpublished")),
                            _clean(year)) if b]
        refs[key] = {"label": _label(author, year, key), "full": ". ".join(bits) + "."}
    return refs


def make_artifact_hook(config, project_dir):
    rel = config if isinstance(config, str) else (
        (config or {}).get("source", "book.bib") if isinstance(config, dict) else "book.bib")
    bib = Path(project_dir) / rel

    def hook(artifact):
        if bib.exists():
            artifact["references"] = parse_bib(bib)
        return artifact
    return hook
