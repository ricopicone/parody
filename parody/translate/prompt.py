"""What the engine is asked, and how its answer is read back (task #825).

The section goes over whole, cut into numbered chunks, so the translator has
the context. Only the chunks named on the last line are translated, and they
come back under the same markers. Anything else in the answer, a chunk
missing, extra or doubled, is a ``ResponseError`` and gets retried.
"""

import re

from .languages import LANGUAGES

BRIEF = """\
You are translating one section of an undergraduate engineering textbook from English into {LANGUAGE}.

Who reads this: international students whose English is still developing. They read your translation side by side with the English original while listening to an English audio narration, and glance at the translation when a passage in English is hard to follow. So the translation must be faithful to the English sentence by sentence (no summarising, no added explanation, nothing omitted), keep the same sentences in the same order, and read naturally and clearly, in the register of a good university textbook written in {LANGUAGE}. Keep the author's informal, encouraging tone. Use the standard technical terminology that {LANGUAGE}-language engineering courses actually use.

The section arrives split into numbered chunks, each starting with a line `<<<chunk N>>>`. Chunk 0, when present, is the section title as plain text. You may also get the existing translation of some chunks for context; keep your terminology consistent with it. Translate only the chunks you are asked for, and return each one starting with its own `<<<chunk N>>>` line, in order, with nothing before, between or after them.

The chunks are Pandoc Markdown with extensions. Translate the prose; preserve every piece of markup exactly:

- Math: everything between `$…$` and `$$…$$` stays byte-for-byte identical, including `\\text{…}`, `\\cloze{…}` and environment names. Do not translate inside math.
- Attributes and ids: keep `{#…}`, `{.…}`, `h="…"`, `width="…"` and the like exactly.
- `[xx]{.hashref}` spans: keep them exactly; do not translate their contents.
- Cross-references such as `[@fig:voltage_divider_demo]`: keep exactly, positioned where the grammar of {LANGUAGE} needs them.
- Images `![caption](path){…}`: translate the caption, keep the path and attributes.
- Code (inline `code` and fenced code blocks): keep exactly.
- Raw LaTeX commands outside math: keep exactly.
- Fenced divs (`::: name` … `:::`), block quotes (`>`), lists, tables, footnote markers (`[^3]`) and footnote definitions: keep the structure; translate the text.
- `[text]{.keyword}`: translate the term, keep the span wrapper and its attributes.
- `[text]{.cloze}`: these are fill-in-the-blank answers. Translate the text inside, keep the span wrapper, and keep exactly one cloze span for each one in the original. If the cloze holds only math, leave it unchanged. Rearrange the surrounding sentence as {LANGUAGE} grammar requires, but the blank must still stand for the same idea.
- References to equations such as `($*$)` and `($*$b)`: keep them.
- Keep the same paragraphs, list items and blocks, in the same order: one translated block for each English block.
"""

_MARKER = re.compile(r"^<<<chunk (\d+)>>>[ \t]*$", re.M)
_WRAPPER = re.compile(r"\A```[^\n]*\n(.*)\n```\s*\Z", re.S)


class ResponseError(Exception):
    pass


def system_prompt(language, glossary):
    text = BRIEF.replace("{LANGUAGE}", LANGUAGES[language])
    if glossary:
        lines = "\n".join(f"- {en} → {tr}" for en, tr in sorted(glossary.items()))
        text += (f"\nUse these established {LANGUAGES[language]} translations "
                 f"for these terms:\n\n{lines}\n")
    return text


def _chunked(chunks):
    return "\n".join(f"<<<chunk {i}>>>\n{text}" for i, text in chunks)


def request(english, todo, previous, problems=None):
    parts = ["<english-section>", _chunked(enumerate(english)), "</english-section>"]
    if previous:
        parts += ["", "<existing-translation>", _chunked(sorted(previous.items())),
                  "</existing-translation>"]
    if problems:
        parts += ["", "Problems with your previous attempt:"]
        parts += [f"- chunk {i}: {p}" for i in sorted(problems) for p in problems[i]]
    parts += ["", "Translate these chunks: " + ", ".join(map(str, todo))]
    return "\n".join(parts) + "\n"


def parse_response(text, todo):
    """``{chunk index: translated text}`` for exactly the chunks in ``todo``."""
    text = text.strip()
    wrapped = _WRAPPER.match(text)
    if wrapped and _MARKER.search(wrapped.group(1)):
        text = wrapped.group(1)
    pieces = _MARKER.split(text)
    if pieces[0].strip():
        raise ResponseError("text before the first <<<chunk N>>> marker")
    got = {}
    for k in range(1, len(pieces), 2):
        index = int(pieces[k])
        if index in got:
            raise ResponseError(f"chunk {index} returned twice")
        got[index] = pieces[k + 1].strip("\n").rstrip()
    missing = sorted(set(todo) - set(got))
    extra = sorted(set(got) - set(todo))
    if missing or extra:
        raise ResponseError(
            "chunks " + (f"missing: {missing} " if missing else "")
            + (f"not asked for: {extra}" if extra else ""))
    return got
