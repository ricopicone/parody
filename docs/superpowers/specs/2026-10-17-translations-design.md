# Parallel translations

Task #825. Cross-repo:

- `parody`: the translate step, build and print.
- `parody-web`: web pages, read-along and PDF serving.
- `homepage-django`: hosts the ricopic.one book subdomains with parody-web
  installed. Its deploy and artifact import are where new per-language
  outputs land.
- The book repos: they hold the translations.

## Summary

International students in Rico's courses struggle with the advanced material,
and they struggle with English too. The combination is harder than either one
alone. This feature gives every published section a machine translation in
**Chinese (Simplified), Korean, German, French and Spanish**. The translation
is built to sit *beside* the English, never to replace it.

The central moment: a student is in the PDF read-along, listening to the
English voice with the karaoke mark moving across the page. A passage loses
them. They glance across at the same page in their own language, get unstuck,
and carry on in English. Nothing is voiced in the other languages. The English
voice is the only voice.

Each surface gets the translation in its own form:

- **Print.** Every English page has a *twin* page in each language. The twin
  holds exactly the content of the English page, laid out the same way, with
  only the words translated. A side-by-side PDF puts each English page and its
  twin on one landscape sheet.
- **Read-along.** The twin PDF sits beside the English PDF, and the two scroll
  together in both directions.
- **Web pages.** The page stays in English. Any paragraph can open its
  translation beneath it on demand, and a switch turns the whole page into the
  reader's language.

Translations are made on Rico's laptop by a new `parody translate` step, using
Claude through his Claude Code subscription. They are committed into the book
repo next to the English and rebuilt only for sections that changed. Draft
sections are never translated.

## Why this shape

- **Glance, don't switch.** The student's anchor is the English: the voice,
  the page, the markup they've written on it. The translation is consulted, so
  it has to be *already at the right spot* the moment they look.
- **The English pages never change.** The read-along's word geometry and
  students' annotations are keyed to the English PDF pages. Translation must
  add a parallel object and leave the English pages untouched.
- **Printable side by side.** Students want this on paper. Twin pages make
  "page 37 next to page 37" trivially printable. Earlier in the design Rico
  chose a free-flowing translation that scrolls to follow the voice. He
  reversed that to twin pages once printing was considered, because padded or
  re-flowed English pages would break the stable page sizes the markup feature
  depends on.

## Goals

- A translation of every published section in five languages: `zh`
  (Simplified Chinese, my guess at the variety, see below), `ko`, `de`, `fr`,
  `es`.
- Twin print pages per language, plus a landscape side-by-side PDF, for each
  section and the whole book.
- A read-along view with the twin PDF beside the English and two-way synced
  scrolling.
- Web section pages with per-paragraph on-demand translation and a whole-page
  language switch.
- Translations kept current. An edited published section is retranslated
  where it changed, a section leaving draft gets translated, and drafts are
  never translated.
- Quality: faithful sentence by sentence, natural textbook register in each
  language, standard technical vocabulary, the author's informal tone kept,
  and nothing lost.
- Key terms glossed with the English term, since students must learn the
  English vocabulary too.

## Non-goals

- Audio in any language other than English.
- Reader feedback or correction in the app at launch. Rico decided this. A
  per-paragraph "flag this translation" whose notes feed the next translate
  run is the natural later step; leave room for it, but don't build it.
- Translating figure artwork. Labels inside figures stay English; captions are
  translated.
- Annotating translated pages. Ink stays on the English pages.
- Running translation in CI or on the server. Rico chose the laptop for now,
  with CI possibly later, so the engine must be swappable (see D7).
- Translating while a section is still draft.
- rtcbook.org / the Real-Time Computing book (my call: it is a published book
  with co-authors and a publisher, so translation rights are not Rico's alone
  to decide). Scope is the ricopic.one notes.

## Decisions

"Rico" means Rico decided it in the brainstorm. "Mine" means I made the call
and Rico can overturn it.

| # | Decision | Who | Rationale |
|---|---|---|---|
| D1 | Languages: zh, ko, de, fr, es | Rico | Korean was added mid-brainstorm. Chinese is Simplified (mine; unconfirmed). |
| D2 | Print translation is **twin pages**: page N in each language holds exactly what English page N holds | Rico | Glance-across lands on the same content, and printing side by side stays trivial. |
| D3 | Twins use the **same 6×9 page and margins** as the English. Longer languages get **smaller type**, one size per language, and the odd page that still overflows gets a **per-page squeeze, with no hard lower limit**. Every squeezed page is reported | Rico (chose this over a wider German page or narrower margins, and smaller type over condensing the translation) | A wider page shrinks the whole printed spread, English included, to 80%. Same-size twins print at 92% on landscape letter. The translation always stays faithful; legibility gives on rare pages, and the report shows how rare. |
| D4 | Side-by-side print: English page left, twin right, on one landscape letter sheet (≈92% scale for 6×9) | Rico | Two 6×9 pages are 12×9 in; letter landscape is 11×8.5. |
| D5 | Read-along: twin PDF beside the English, **two-way synced scroll** (scroll either pane and the other follows to the same page and position). No "follow" button | Rico | Rico preferred automatic sync both ways. Twin pages make it a page-and-fraction mapping. |
| D6 | Web: **English page with per-paragraph translation on demand** (a 文-style button opens it beneath the paragraph), plus a **whole-page switch** to the reader's language | Rico | Matches the glance pattern, and keeps reading the whole thing in their language available. |
| D7 | Engine: **Claude**, called through **Claude Code headless on Rico's subscription** (`claude -p`) from a local `parody translate` step. The engine is a pluggable backend, so an Anthropic API key (CI later) is a configuration change | Rico (Claude, laptop); mine (pluggable) | Trial results below. On the subscription it's a local, personal build step, not a hosted service, which is the use the docs support. |
| D8 | Translations are **files committed in the book repo**, one per section per language, each recording a hash of the English it was made from | Mine | Reviewable diffs, no server state, and staleness is mechanical. |
| D9 | Retranslation is **per block**. Blocks whose English is unchanged keep their translation verbatim, and only changed blocks are sent, with the whole section and the previous translation as context | Mine | A small edit must not churn the rest of the section, and it's cheaper. "Unchanged stays unchanged" is guaranteed mechanically, not by asking the model. |
| D10 | Every translation must pass a **preservation check** before it is written: every math string byte-identical, the same count of blanks, key terms, cross-refs, hashrefs and footnotes, and the same number of blocks. A failure retries, and is never written | Mine | Measured in the trial. The checker was proven able to fail; see below. |
| D11 | **No second-opinion review pass.** Each translation is made once and checked mechanically (D10), with no second Claude call to check meaning | Rico | A review pass would double token use against the subscription limits. Meaning errors are left to readers until in-app flags exist (see Non-goals). |
| D12 | **Key terms glossed**: where the English marks a term (`[…]{.keyword}`), the translation shows the English after it, e.g. 分压器 (voltage divider). Other occurrences are not glossed | Rico (gloss); mine (only marked occurrences) | Students are learning the subject *in English*. |
| D13 | A **per-language glossary** file in the book repo, built up as sections are translated, used by every translation, and editable by hand | Mine | Consistent terms across chapters, and one place to fix a term. |
| D14 | Blanks stay blank in translations wherever the English is blank. The staff answer toggle fills them in both languages | Mine (Rico didn't object) | A translation must never give an answer away. |
| D15 | Readers choose a language once, and it's remembered across web pages and the read-along. A reader who never chooses sees no translation affordances at all | Mine | English-only readers see no change. |
| D16 | Translations are gated exactly like the English: same access policy, same drafts, same online-only rules | Mine | A translation is the same content. |
| D17 | In the read-along, the twin pane **mirrors blank reveals**. When the voice reaches a blank and its answer appears on the English page, the translated answer appears at the matching blank on the twin page | Rico (I recommended deferring it; he chose to include it) | The student glancing across should see the answer in their language, not an empty blank beside a revealed English answer. |

## Evidence from the trial

The trial ran on 2026-10-17 on Electronics Primer §1.3 *Voltage dividers*
(`chapters/fundamentals/voltage-dividers.md`, 3.4 KB). It has 34 math spans,
3 prose blanks plus blanks inside display math, 1 keyword, 1 figure
reference, 1 hashref, 1 footnote and 12 top-level blocks. Throwaway scripts
are in the session scratchpad and weren't kept.

- **Claude** (Opus 5.5, prompt below): all five languages passed every
  preservation check. Spot-read zh and de: fluent and textbook-like, with the
  tone kept ("limp along unsystematically" became 凑合着; the German is a
  little literal there).
- **Amazon Translate** (`TranslateDocument`, html, with maths, refs and
  hashrefs marked `translate="no"`): it kept every protected item but **put
  them in the wrong places**. Maths landed mid-word (电[M]阻器), refs moved past
  sentence ends, and English words were left in the Chinese ("for", "or", a
  stray "f"). That is fatal for maths-dense text. Rejected.
- **GPT**: not run (the OpenAI account has no credits). Rico may add credits
  and rerun; the result would not change the design.
- **DeepL**: rejected on cost by Rico.
- The checker counts preservation, **not placement**. It passed Amazon
  Translate. So it guards against loss, not misplacement. For Claude,
  placement was right in every spot read. Nothing automated guards meaning
  (D11).

The trial's prompt was the starting point for the production prompt. It
covered the audience and purpose (glance-across, faithful sentence by
sentence, textbook register, keep tone, standard terminology) and preserving
markup exactly: front matter (translate `title` only), math, attributes and
ids, `.hashref` untouched, `[@…]` refs placed by target grammar, image paths,
fenced divs, quotes, footnotes, `.keyword` translated with its wrapper kept,
and `.cloze` contents translated with its wrapper kept, exactly one blank per
English blank.

## Cost

These are estimates from source size, at Anthropic API list prices. Opus 5.5
costs $4 per M input tokens and $20 per M output tokens; Sonnet 5.5 costs $2
and $10. Batch is half price. Bedrock's per-token price wasn't confirmed.

- A full first pass, all five languages: Electronics Primer (323 KB of
  Markdown) ≈ $20 with Opus 5.5. All four ricopic.one books (2.9 MB) ≈ $150.
- A typical edit (one section, five languages): well under $1.
- On the subscription these draw on Rico's shared 5-hour and weekly limits
  instead of money. A first full pass of a large book may take a noticeable
  share of a week, so it should be resumable (see "The translate step").

## How it fits the existing system

What the recon found, and what the builder must work with.

### The translate step (parody)

- A new `parody translate` subcommand in `parody/cli.py`, following the
  `cmd_figures` pattern. It reads a new `translations:` key in `parody.yaml`:
  the languages, the engine, and per-language print settings. Validate it the
  way `normalize_editions` / `resolve_cloze_mode` do (`config.py`); other keys
  are read ad hoc.
- Section eligibility reuses `resolve_section_draft` (`writers/artifact.py`)
  unchanged. It is the same resolver print and artifact use. A section with
  no `draft:` of its own inherits its chapter's status, and an explicit value
  overrides the chapter in either direction. A released section in a draft
  chapter is therefore eligible, and a draft section in a released chapter is
  not.
- For each eligible section and language it compares the English blocks with
  the translation's recorded source hashes. It translates new or changed
  blocks (D9), runs the preservation check (D10), retries on failure, and
  writes the file.
- Output is written to the working tree and reported. Rico reviews and
  commits, like the other content commands. Nothing is committed
  automatically.
- It is resumable and idempotent. Run it twice and the second run does
  nothing. Interrupt it, and a rerun picks up where it left off. A first full
  pass can span days of subscription limits.
- It prints a clear summary: what was translated, what failed the check after
  retries, and what is stale.
- Engine backends:
  - `claude-code`: headless `claude -p`. **`ANTHROPIC_API_KEY` must be unset,
    or Claude Code bills the API instead of the subscription**; do not use
    `--bare`, which ignores subscription login.
  - `anthropic-api`: the Anthropic SDK, model `claude-opus-5-5`.
  The prompt and the checks are shared, and only transport differs.

### Translation files (book repo)

Suggested layout, which the builder may refine:

```
translations/
  zh/
    glossary.yaml
    fundamentals/voltage-dividers.md
  ko/ …
```

Each file is the section's Markdown in that language. It has the same block
structure as the English, and its front matter records the engine, model,
date, and a hash per source block (or an equivalent that makes D9 and
staleness mechanical). The glossary maps English key terms to that language.
It is seeded from translations as they happen, it is hand-editable, and it is
fed to every translation call.

### Paragraph identity

**Paragraphs carry no ids today.** `filter.lua` and `print.lua` have no
`Para` handler; only headings (`data-h`), environments, `eq:`/`fig:`/`tbl:`
and anchors have stable ids. Three consumers need a key per top-level block
that is shared between the English and each translation:

- web per-paragraph toggles,
- twin-page placement,
- the read-along's "paragraph the voice is on" tint.

The ordinal within the section works, because the preservation check enforces
equal block counts. A block hash serves D9. The builder decides how blocks
are keyed and how nested blocks (lists, definition boxes, quotes) are treated
for the web toggle.

### Twin pages (print), the hardest part

The requirement:

- **Content.** Twin page N contains exactly the content of English page N.
  That covers the same blocks, the same figures and tables (floats included,
  wherever LaTeX floated them in the English), the same equations with the
  same numbers, and the same footnotes, all translated.
- **Same page number.** The twin has the same page number as the English
  page.
- **Same numbering.** Cross-ref numbers match the English: Figure 1.4 is
  图 1.4.
- **Running heads.** These are translated.
- **Page breaks inside paragraphs.** When an English page break falls inside a
  paragraph, the translation splits at the **sentence boundary nearest the
  English break**. Each sentence goes on the page holding most of its English.
  This needs sentence correspondence between English and translation. The
  translation is faithful sentence by sentence, but the builder must make the
  correspondence explicit, for example with sentence markers through the
  translate step. It must not be guessed at typesetting time.
- **Type size and fit.** Each language gets one type size chosen so nearly
  every page fits. Expect roughly 9.5 pt for de, fr and es against 11 pt
  English, and probably 11 pt for zh and ko. Treat these as guesses to
  measure, not specs. A page that still overflows is squeezed on that page
  alone (smaller type, tighter leading) as far as it takes. Rico chose **no
  hard lower limit**: a faithful translation in small type beats a condensed
  one. Every squeezed page is listed in the build report with its effective
  type size, so a page that gets uncomfortably small is visible. **Text is
  never dropped or truncated to make a page fit.** Silent content loss is a
  known failure family in this codebase (see `silent-content-loss-guards` and
  `print-builds-fail-quietly` in project memory). The twin build must verify
  that every block of the section appears on exactly one twin page.
- **Short pages.** Shorter translations (often zh and ko) leave white space at
  the bottom of the page. That's fine.
- **Blanks.** Twins are built in the same cloze mode as the English PDF they
  twin. The read-along and the student PDF use `blank`.

What exists to build on:

- The page map is per section only. `parody-pagemap.sty` puts
  `\zlabel{parodypage@key}` marks at section starts and ends, read back from
  `main.aux` by `pagemap.py`. **Nothing records where paragraphs or sentences
  fall on pages.**
- `latexmk` already runs with `-synctex=1`, but synctex maps to generated
  `.tex` lines, not to source blocks.
- parody-web's read-along already extracts per-word page boxes with PyMuPDF
  (`parody_web_readaloud/geometry.py`). It aligns them to html tokens
  (`align.py`), so a word-level English-page inventory is a known-feasible
  technique.

The builder picks the method: zref marks per block or sentence, or geometry
extraction, or something else. Same-page-number twins also mean the existing
per-section page ranges (`<pdf>.pages.json`) apply unchanged to every
language's twin PDF.

Typesetting non-Latin and non-English text: the profiles have **no
babel/polyglossia, and fonts are newpx/Pagella (Latin only)**. The build runs
LuaLaTeX. Twins need:

- CJK and Korean fonts and line breaking (e.g. Noto Serif CJK SC/KR with
  LuaLaTeX-compatible CJK and Korean support),
- hyphenation patterns for de, fr and es,
- language-appropriate punctuation spacing (French in particular),
- every machine that builds twins carrying all of these, or CI print jobs
  will fail where local builds pass. Two traps the review found:
  - **Noto CJK fonts are not part of TeX Live.** They must be installed
    separately, locally and in CI.
  - **The book repos' CI does not use parody's `Dockerfile.print`.**
    Electronics' `build.yml` runs in an unpinned `texlive/texlive:latest-full`
    container, so the fonts and packages have to be added there too, or the
    image pinned.

Maths stays in the book's maths fonts.

**Strongly suggested:** prove twin-page typesetting on one real chapter (for
example Electronics Primer chapter 1) in German, the longest language, and
Chinese, the most different script, before building the rest. It is the part
most likely to need a design adjustment.

### When translations lag the English

Translation runs only on Rico's laptop, while English releases run in CI on a
tag. So the English will regularly be ahead of its translations: a typo fix, a
newly published section, or a block that failed the preservation check after
retries. Rico approved this behaviour in the brainstorm: the build warns, and
readers see the older translation with a note. The details below are my
calls.

- **Translation never blocks an English release.** Twins and side-by-side
  PDFs are built in their own job (or step) that can fail without failing the
  English print, the page map or the artifact.
- **A stale block** (its English changed since it was translated) still uses
  its previous translation. It is placed according to the *current* English
  layout, so twin pages stay page-for-page. On the web and on the twin, it
  carries a small "translation may lag the English" marker.
- **A block with no translation yet** (a new block, or a section just out of
  draft): the twin page sets the **English text** for that block, marked
  "not yet translated", so page N still holds page N's content. The web
  per-paragraph button is absent for that block.
- **A language whose twin build fails** for a release (e.g. a LaTeX error, or
  a missing font) publishes no twin for the affected sections in that release.
  The twin pane shows "translation unavailable for this version". It never
  serves a twin from an earlier release, because that would no longer match
  the English pages. Web translations for those sections still work.
- The build's summary says what is stale, what's missing and what failed, per
  language. A typo fix therefore does not *require* a translate run; Rico runs
  one when he chooses.

### Side-by-side PDF

Landscape letter. English page N on the left, twin page N on the right, both
scaled to fit (≈92% for 6×9). It covers the whole book and each section, per
language, using the English and twin PDFs as built (composited, not
re-typeset). The PDF-composition gotchas in project memory apply:
`pdf-composition-gotchas`.

### Read-along (parody-web)

- The PDF view stage (`_pdf_view_stage.html`, overridden by
  `parody_web_annotate`) renders pages through `PageView`
  (`assets/annotate/pages.js`). It creates one `.ink-spread` row per page,
  with a scratch-pad margin and canvases kept only in a ±1-page window.
- The twin pane is a second page view of the same section's twin PDF in the
  reader's language. It sits beside the English. Scroll sync works by page
  index and fractional position, both directions, without feedback loops.
- When the voice moves the English (`assets/readaloud/follow.js`), the twin
  follows through the same sync.
- The paragraph the voice is on is tinted on the twin. That needs the twin
  page boxes of each block, which the twin build knows because it placed them,
  or which can be extracted afterwards.
- **Blank reveals mirror onto the twin (D17).** When the English reveal fires
  for a blank, the twin shows that blank's translated answer at the matching
  blank on the twin page. This needs:
  - blank geometry from every twin PDF, including blanks inside display maths
    (the English side already does this; see `readalong-architecture-and-alignment`
    and `in-equation-cloze-reveals-the-whole-equation` in project memory);
  - a blank-by-blank mapping between English and each translation. The
    preservation check (D10) guarantees the same prose blanks in the same
    order, and identical maths strings, so order is a sound key. The builder
    should verify it, not assume it;
  - the translated answers, from a key-mode build of the translation, as the
    English reveal uses the key artifact;
  - the reveal rendering in the second pane, inside the same ±1-page memory
    window.
- Narrow screens: two 6×9 pages plus the scratch-pad margin don't fit side by
  side on a phone or a small laptop. The builder decides the fallback, for
  example the twin replacing the scratch margin, or a toggle. The
  glance-across moment must still work on a typical laptop.
- Memory: the read-along and annotator have had measured canvas and memory
  regressions (`konva-stage-cost-and-host-ownership`,
  `readalong-blank-marks-are-elements-not-canvas`). A second pane must keep
  the ±1-page windowing.
- Serving: `Book.print_pdf` and `Section.print_pages` are one PDF per book
  today (`models.py`). Twins need a per-language PDF per book/edition, served
  through the same gated view and sliced by the same page ranges.
  Downloadables per section: the twin PDF and the side-by-side PDF.

### Web pages (parody-web)

- Section html renders through `section.html` → `render_book`. Section-page
  JS is inline in `base.html` with no bundle.
- Each top-level block needs the shared key (see "Paragraph identity"). The
  translated block html for the reader's language must be available to the
  page. Whether it is embedded, lazy-fetched or stored per section is up to
  the builder.
- Translated html must render maths, blanks and refs exactly as the English
  does. The same filter pipeline should run on the translation, with
  `PARODY_CLOZE_MODE` and the staff `?answers=on` toggle behaving the same.
- `<html lang="en">` is hardcoded (`base.html`). Translated blocks need
  correct `lang` attributes and CJK/Korean font stacks in the theme tokens.
- Language choice is remembered per reader (D15), so readers who never choose
  see nothing new.

## What's left to the builder

- Paragraph and sentence keying; the translation file format details; how
  staleness is recorded.
- The twin-page typesetting method, the type size per language (measured),
  and how the per-page squeeze is applied.
- How twin PDFs and side-by-side PDFs are stored, published and served
  (parody-web models and the release chain). The release chains for the
  ricopic.one books are in project memory (`electronics-ricopic-one-release-chain`,
  `systems-ricopic-one-release-chain`, `robotics-ricopic-one-release-chain`).
- Read-along twin pane layout on narrow screens.
- Web toggle UI details, within D6.
- The order of work. A suggested order, riskiest first: the translate step,
  files and checks → a twin-page proof on one chapter (de + zh) → the full
  twin and side-by-side PDFs → the read-along twin pane → web toggles.
- Chunking long sections for the engine, retry policy, and rate-limit
  handling on the subscription.

## Release chain for twins

How twin PDFs reach a book site (built in subsystem 3; the ricopic.one chains
in project memory apply: `electronics-ricopic-one-release-chain`,
`pypi-propagation-lag-is-measured-from-the-box`). In order:

1. **parody.** Merge `mellow-harbor` (0.61.0 translate step, 0.62.x twin pages
   and the twin sidecar) to main and publish to PyPI.
2. **The book.** Translate and commit: `parody translate --lang de,zh`, then
   commit `translations/`. Re-pin the print job's parody to `parody[twin]` at
   that release. For electronics this is a jump from 0.54.2, so it is a
   migration: rebuild and read the English PDF before tagging. The `Translated
   twins` step (`scripts/build-twins.sh`) only builds when the pinned parody
   has `parody twin`. Merge the book's `twins` branch.
3. **Tag the book.** The print job publishes the English, then builds one twin
   per language with `continue-on-error`, and attaches `twins.zip` beside
   `print.zip`. A language that failed its checks is left out of the zip and
   marks the step failed; the reason is in its log.
4. **parody-web.** Merge `twins` and publish 0.100.0 (TwinPdf, migration 0016,
   `import_artifact --twin`, twin URLs and links).
5. **homepage-django.** Merge its `twins` branch, bump the pin to
   `parody-web[print,readalong]==0.100.0`, and add
   `"translations": ["de", "zh"]` to the book's `features` in
   `teaching/content-manifest.json`, all in one commit on main. With the
   branch merged but the pin still 0.99.0, `import_books` passes `--twin` to
   a parody-web that does not know it and the deploy fails; and a concurrent
   deploy ships whatever is on main (`homepage-deploy-ships-origin-main-not-your-commit`).
6. **Fetch, check, commit, deploy.** Run `scripts/fetch_notebook_artifacts.py
   --update -n electronics --tag <tag>`. It unpacks each language's twin into
   `teaching/notebooks_data/`. Then run `check_book_features --book
   electronics`, which fails on a missing twin, a twin of another English
   build, or a declared language with no twin. Commit, and deploy once
   `pip download` of the new pin works on the box.
7. **Verify live.** Count the book's `TwinPdf` rows over SSM and fetch one
   section's `pdf/de/` signed in. A curl of a gated page proves nothing:
   see `rtcbook-verify-live-via-psql`.

What the twins cost in the repo: each language adds the twin (about 0.6 MB
for one chapter of electronics) and its side-by-side sheets (about 1.7 MB) to
`teaching/notebooks_data/`, committed with every repin, as the English PDF
already is.

## Open questions for Rico

None. The builder check raised three questions. Rico answered the overflow
policy (D3: smaller type, no hard limit) and twin blank reveals (D17: yes).
The third, what ships when translations lag the English, is settled in "When
translations lag the English", following the behaviour he approved in the
brainstorm.

## Housekeeping from the trial

For the trial, an IAM managed policy `parody-translate`
(`translate:TranslateText`, `TranslateDocument`, `ListLanguages`) was created
and attached to IAM user `rico` in account 226466052849. With Amazon
Translate rejected, it can be detached and deleted.
