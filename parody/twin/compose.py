"""What each twin page says, in Markdown, before LaTeX (task #825).

For each page's pieces the translation is cut to the English page's extent:
- a whole chunk, or the run of sentences the page holds (``slices``);
- a chunk with no translation yet sets its English, marked "not yet
  translated";
- one whose English changed since it was translated sets the older
  translation, marked "may lag the English".

Footnote definitions always come along with their section, since pandoc only
sets the ones a page refers to. A box reopened on the page after a break
steps its counter back first, so it keeps its number.
"""

from dataclasses import dataclass
from pathlib import Path

from ..translate.chunks import align_chunks, chunk_hash, split_chunks, split_frontmatter
from .slices import footnote_definitions, slice_chunk, without_footnote_definitions

# Counters a box steps when it opens (parody-environments.sty).
BOX_COUNTERS = ("thmctr", "examplectr", "infoboxctr", "listingctr", "algorithmctr",
                # xsim's: an exercise, its running total, and its solution
                "exercise", "numberofexercises", "solution",
                "labexercise", "numberoflabexercises", "labsolution")


@dataclass
class SectionSource:
    index: int
    key: str  # "chapter/section"
    chapter: object
    slug: str
    source: Path
    meta: dict
    chunks: list
    title: str | None


@dataclass
class AlignedTranslation:
    texts: list  # per English chunk: the translation to set, or None
    states: list  # per English chunk: current | stale | missing
    title: str | None


def english_sections(project, section_index):
    """``{index: SectionSource}`` for every section of the book."""
    out = {}
    for chapter in project.chapters:
        for slug in chapter.section_slugs:
            key = f"{chapter.slug}/{slug}"
            source = chapter.directory / f"{slug}.md"
            if key not in section_index or not source.is_file():
                continue
            meta, body = split_frontmatter(source.read_text(encoding="utf-8"))
            title = meta.get("title")
            out[section_index[key]] = SectionSource(
                section_index[key], key, chapter, slug, source, meta, split_chunks(body),
                str(title).strip() if title not in (None, "") else None)
    return out


def align_translation(section, translation):
    """The translation of each English chunk, lined up by hash (``align_chunks``)."""
    n = len(section.chunks)
    if translation is None:
        return AlignedTranslation([None] * n, ["missing"] * n, None)
    hashes = [chunk_hash(c) for c in section.chunks]
    stored = [h for h, _ in translation.chunks]
    texts, states = [None] * n, ["missing"] * n
    for k, j, state in align_chunks(hashes, stored):
        if j is not None:
            texts[k], states[k] = translation.chunks[j][1], state
    return AlignedTranslation(texts, states, translation.title)


def _value(section, chunk, sentence):
    return section * 1_000_000 + (chunk + 1) * 1000 + sentence


def _box_step_back(section, chunk, counters, start=1):
    """Raw LaTeX undoing the steps the reopened openers take again, from the
    English counters: before the box (its head) against where the cut falls,
    which counts every opener above the cut (a solution inside an exercise)."""
    head = counters.get(_value(section, chunk, 0)) or {}
    inside = (counters.get(_value(section, chunk, max(start, 1)))
              or counters.get(_value(section, chunk, 1)) or {})
    lines = [f"\\addtocounter{{{name}}}{{-{inside[name] - head[name]}}}"
             for name in BOX_COUNTERS
             if name in head and name in inside and inside[name] > head[name]]
    return "\n".join(lines)


def _is_footnote_definition(chunk):
    return chunk.startswith("[^")


def page_markdown(page, english, translated, language, counters):
    """``([(section index, markdown)], notes)`` for one twin page."""
    groups, notes = [], []
    run = None  # the marker the previous piece opened: one per run of chunks, not per chunk
    for piece in page.pieces:
        en = english[piece.section]
        en_text = en.chunks[piece.chunk]
        if _is_footnote_definition(en_text):
            continue  # every page gets the section's definitions below
        tr = translated[piece.section]
        text, state = tr.texts[piece.chunk], tr.states[piece.chunk]
        lang, blocks, marker = language, [], None
        if text is None:
            text, lang, marker = en_text, "en", "\\parodyuntranslated"
            notes.append(f"untranslated: {en.key} chunk {piece.chunk}")
        elif state == "stale":
            marker = "\\parodystale"
            notes.append(f"stale: {en.key} chunk {piece.chunk}")
        if marker and marker != run:
            blocks.append(marker)
        run = marker
        if piece.start == 0 and piece.end is None:
            # its nested footnote definitions come below, with the section's
            body = without_footnote_definitions(text)
        else:
            cut = slice_chunk(text, lang, piece.start, piece.end, en_text)
            body = cut.text
            if cut.approximate:
                notes.append(f"approximate: {en.key} chunk {piece.chunk} "
                             f"sentences {piece.start}–{piece.end or 'end'}")
            if cut.reopened:
                step_back = _box_step_back(piece.section, piece.chunk, counters, piece.start)
                if step_back:
                    blocks.append(step_back)
        blocks.append(body)
        markdown = "\n\n".join(blocks)
        if groups and groups[-1][0] == piece.section:
            groups[-1] = (piece.section, groups[-1][1] + "\n\n" + markdown)
        else:
            groups.append((piece.section, markdown))
    # Footnote definitions, for whatever references the page holds.
    for i, (section, markdown) in enumerate(groups):
        en, tr = english[section], translated[section]
        definitions = [tr.texts[k] or en.chunks[k] for k, c in enumerate(en.chunks)
                       if _is_footnote_definition(c)]
        # and those inside a chunk (an exercise, an example, a list item),
        # which no slice carries: the reference may be on this page and the
        # definition's sentences on another
        for k, c in enumerate(en.chunks):
            if not _is_footnote_definition(c):
                definitions += footnote_definitions(tr.texts[k] or c)
        if definitions:
            groups[i] = (section, markdown + "\n\n" + "\n\n".join(definitions))
    return groups, notes
