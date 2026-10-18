"""Translate a book, or report how far its translations lag (task #825).

Per section and language:

1. Split the English into chunks and line them up against the stored
   translation by hash.
2. Send only the chunks that are missing or stale, with the whole section and
   the existing translation as context.
3. Check every returned chunk, and retry the failures with the problems
   spelled out.
4. Write what passed.

A chunk whose English is unchanged keeps its translation byte for byte. A
chunk that never passes is not written. Its earlier translation, if it had
one, stays as it was. Each section is written as soon as it is done, so an
interrupted run resumes where it stopped.
"""

import datetime
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from ..writers.artifact import resolve_section_draft
from .check import chunk_facts, compare_chunks
from .chunks import align_chunks, chunk_hash, split_chunks, split_frontmatter
from .engines import EngineError
from .prompt import ResponseError, parse_response, request, system_prompt
from .store import (
    TranslationFile,
    glossary_path,
    load_glossary,
    save_glossary,
    translation_path,
)


@dataclass
class SectionStatus:
    chapter: str
    section: str
    language: str
    state: str  # current|stale|missing|draft|translated|partial|failed|no-source
    todo: int = 0
    total: int = 0
    problems: list = field(default_factory=list)


@dataclass
class _Section:
    """One section's English and its stored translation, lined up."""
    chapter: object
    slug: str
    language: str
    source: object
    title: str | None
    body: list
    body_hashes: list
    existing: TranslationFile | None
    alignment: list  # align_chunks(body_hashes, stored hashes)
    title_state: str | None  # current|stale|missing, None when no title

    @property
    def offset(self):
        return 1 if self.title is not None else 0

    @property
    def english(self):
        return ([self.title] if self.title is not None else []) + self.body

    def todo(self):
        """English indices (title = 0 when present) that need translating."""
        out = [0] if self.title_state not in (None, "current") else []
        out += [k + self.offset for k, _, state in self.alignment if state != "current"]
        return out

    def previous(self):
        """English index → the stored translation lined up with it."""
        prev = {}
        if self.existing and self.title is not None and self.existing.title:
            prev[0] = self.existing.title
        for k, j, _ in self.alignment:
            if j is not None:
                prev[k + self.offset] = self.existing.chunks[j][1]
        return prev


def _load(project, chapter, slug, language):
    source = chapter.directory / f"{slug}.md"
    if not source.is_file():
        return None, None
    meta, body_text = split_frontmatter(source.read_text(encoding="utf-8"))
    if resolve_section_draft(meta.get("draft"), chapter.draft):
        return meta, "draft"
    title = meta.get("title")
    title = str(title).strip() if title not in (None, "") else None
    body = split_chunks(body_text)
    hashes = [chunk_hash(c) for c in body]
    path = translation_path(project.directory, language, chapter.slug, slug)
    existing = TranslationFile.read(path) if path.is_file() else None
    stored = [h for h, _ in existing.chunks] if existing else []
    title_state = None
    if title is not None:
        if existing and existing.title and existing.title_hash == chunk_hash(title):
            title_state = "current"
        elif existing and existing.title:
            title_state = "stale"
        else:
            title_state = "missing"
    return meta, _Section(chapter, slug, language, source, title, body, hashes,
                          existing, align_chunks(hashes, stored), title_state)


def _status_of(project, chapter, slug, language):
    meta, sec = _load(project, chapter, slug, language)
    if sec is None:
        return SectionStatus(chapter.slug, slug, language, "no-source"), None
    if sec == "draft":
        return SectionStatus(chapter.slug, slug, language, "draft"), None
    todo = sec.todo()
    total = len(sec.english)
    if sec.existing is None:
        state = "missing"
    elif todo:
        state = "stale"
    else:
        state = "current"
    return SectionStatus(chapter.slug, slug, language, state, len(todo), total), sec


def _relevant(glossary, texts):
    haystack = "\n".join(texts).lower()
    return {en: tr for en, tr in glossary.items() if en.lower() in haystack}


def translate_section(project, chapter, slug, language, engine, glossary,
                      retries=2, today=None):
    status, sec = _status_of(project, chapter, slug, language)
    if sec is None or status.state == "current":
        return status

    english, offset = sec.english, sec.offset
    en_facts = chunk_facts(sec.body)
    previous = sec.previous()
    pending = sec.todo()
    system = system_prompt(language, _relevant(glossary, [english[i] for i in pending]))
    accepted = {}  # English index → checked translation
    problems = {}

    for _ in range(retries + 1):
        if not pending:
            break
        try:
            got = parse_response(
                engine.complete(system, request(english, pending, previous,
                                                problems=problems or None)),
                pending)
        except (EngineError, ResponseError) as e:
            problems = {i: [f"the answer could not be used: {e}"] for i in pending}
            continue
        # Check the new chunks in place, with the English standing in for any
        # chunk that has no translation yet: it trivially passes, and keeps
        # every other chunk's facts where the build would find them.
        candidate = list(sec.body)
        for k in range(len(sec.body)):
            i = k + offset
            if i in got:
                got[i] = _gloss(got[i], en_facts[k].keywords)
                candidate[k] = got[i]
            elif i in accepted:
                candidate[k] = accepted[i]
        failures = {k + offset: p for k, p in compare_chunks(sec.body, candidate).items()
                    if k + offset in got}
        if 0 in got and offset:
            title = got[0].strip()
            if not title or "\n" in title:
                failures[0] = ["the title must be one non-empty line"]
            else:
                got[0] = title
        for i, text in got.items():
            if i not in failures:
                accepted[i] = text
        pending = sorted(failures)
        problems = failures

    if accepted:
        _write(project, sec, accepted, engine, today)
        _update_glossary(glossary, sec, accepted, en_facts)
    state = "translated" if not pending else ("partial" if accepted else "failed")
    return SectionStatus(chapter.slug, slug, language, state, len(accepted),
                         len(english), [f"chunk {i}: {p}" for i in pending
                                        for p in problems.get(i, [])])


def _gloss(text, en_keywords):
    from .check import add_keyword_glosses
    return add_keyword_glosses(text, en_keywords)


def _write(project, sec, accepted, engine, today):
    offset = sec.offset
    chunks = []
    for k, j, _ in sec.alignment:
        if k + offset in accepted:
            chunks.append((sec.body_hashes[k], accepted[k + offset]))
        elif j is not None:
            # Current, or stale and not fixed this run: keep what was there.
            chunks.append(sec.existing.chunks[j])
    title = title_hash = None
    if sec.title is not None:
        if 0 in accepted:
            title, title_hash = accepted[0], chunk_hash(sec.title)
        elif sec.existing and sec.existing.title:
            title, title_hash = sec.existing.title, sec.existing.title_hash
    TranslationFile(
        language=sec.language,
        source=sec.source.relative_to(project.directory).as_posix(),
        title=title, title_hash=title_hash, chunks=chunks,
        engine=engine.name, model=engine.model,
        updated=today or datetime.date.today().isoformat(),
    ).write(translation_path(project.directory, sec.language, sec.chapter.slug, sec.slug))


def _update_glossary(glossary, sec, accepted, en_facts):
    ks = [k for k in range(len(sec.body)) if k + sec.offset in accepted
          and en_facts[k].keywords]
    if not ks:
        return
    tr_facts = chunk_facts([accepted[k + sec.offset] for k in ks], isolated=True)
    for k, facts in zip(ks, tr_facts):
        for en, tr in zip(en_facts[k].keywords, facts.keywords):
            if en and tr:
                glossary.setdefault(en, tr)


def _sections(project, sections):
    wanted = set(sections or [])
    for chapter in project.chapters:
        for slug in chapter.section_slugs:
            if not wanted or f"{chapter.slug}/{slug}" in wanted:
                yield chapter, slug


def _require_translations(project):
    from ..config import ProjectLayoutError

    if project.translations is None:
        raise ProjectLayoutError("parody.yaml has no translations: key")
    if project.editions:
        raise ProjectLayoutError(
            "translations do not support edition-aware books (editions:) yet")


def project_status(project, languages=None, sections=None):
    """Where every section's translation stands, without translating anything."""
    _require_translations(project)
    return [_status_of(project, chapter, slug, lang)[0]
            for lang in (languages or project.translations.languages)
            for chapter, slug in _sections(project, sections)]


def translate_project(project, engine, languages=None, sections=None, jobs=1,
                      retries=2, today=None, log=print):
    """Translate every eligible section that needs it; one status per section."""
    _require_translations(project)
    languages = list(languages or project.translations.languages)
    work = list(_sections(project, sections))

    def one_language(lang):
        gpath = glossary_path(project.directory, lang)
        glossary = load_glossary(gpath)
        results = []
        for chapter, slug in work:
            before = dict(glossary)
            st = translate_section(project, chapter, slug, lang, engine, glossary,
                                   retries=retries, today=today)
            if glossary != before:
                save_glossary(gpath, glossary)
            results.append(st)
            log(_line(st))
        return results

    if jobs <= 1 or len(languages) == 1:
        return [st for lang in languages for st in one_language(lang)]
    with ThreadPoolExecutor(max_workers=jobs) as pool:
        return [st for chunk in pool.map(one_language, languages) for st in chunk]


def _line(st):
    where = f"{st.language} {st.chapter}/{st.section}"
    if st.state == "translated":
        return f"✓ {where} ({st.todo} chunks)"
    if st.state in ("partial", "failed"):
        return f"✗ {where} {st.state}: " + "; ".join(st.problems[:3])
    return f"· {where} {st.state}"
