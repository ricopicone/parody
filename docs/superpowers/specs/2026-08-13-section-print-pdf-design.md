# Bundling a print PDF on each section page

Task #583. Cross-repo: `parody` (build) and `parody-web` (render/serve).

## Summary

Every section page on a parody-web book site offers the print PDF of that
section — not a separately typeset copy, but the exact pages cut out of the
full-book PDF, with the book's own pagination intact. A student who prints one
section at a time ends up holding the whole book.

The build side (`parody`) learns where each section starts and ends in the
print PDF and records it. The render side (`parody-web`) slices those pages
out on demand, behind the access policy, and offers them through a sticky
utility rail that is built to take video embeds later without rework.

## Goals

- A per-section PDF on every section page, extracted from the full book PDF
  with correct (book) pagination.
- The chapter title + lead-in prose is one such unit, available on the chapter
  page.
- A subtle, non-intrusive download affordance.
- One command that publishes the latest to print and to web.
- A full-book PDF on the book's home page.
- A full-window "PDF view" that a future annotation layer can adopt.

## Non-goals

- PDF annotation itself. This spec leaves the seam; it does not build it.
- Video embeds. The utility rail is built to accept them; no video work here.
- Per-reader PDF variants (an instructor's solutions copy, alternate cloze
  modes). One bundled variant per edition — the same student build the print
  release is.

## Decisions

| # | Decision | Rationale |
|---|---|---|
| D1 | Print builds locally via a new `parody publish`, with an **opt-in** CI job scaffolded for content repos | Content-repo CI has no TeX; the pinned TeX Live image is ~5 GB. The local command is needed either way. |
| D2 | Per-section PDFs are served **through a gated parody-web view**, not as static files | Some books (rtcbook) gate sections; `media/` is served by nginx with no auth. The viewer and future annotation need a view regardless. |
| D3 | Ship the **full PDF + a page map**; slice **on demand** and cache | Smallest release; the whole book is never served whole unless permitted; the viewer wants a page range, not a pile of files. |
| D4 | Build the **sticky utility rail now**, PDF as its first tenant | It is the design the task describes; adding it later means moving the PDF UI twice. |
| D5 | The full-book PDF is **public by default**; rtcbook turns it off | Owner's call. See "Risk: permissive default" below. |
| D6 | Per-section PDFs are **extracted**, never separately compiled | See below — this is load-bearing. |

### D6: extraction, not per-section compilation

`parody pdf --section CH/SEC` already exists and is the trap here. A section
compiled on its own starts at page 1, places its floats differently, resets
equation and figure counters, and dangles every `\cref` to another chapter.
That destroys the property the task is built on: *print one section at a time
and it becomes the entire book*.

Extraction preserves it by construction. The bytes on the page are the book's
bytes. There is no second rendering path that can disagree with the first, so
a restyle — new class, new trim size, a font swap that reflows everything — is
correct in the section PDFs the moment the full PDF rebuilds. Per-section
compilation would require every style change to be applied twice, and any
divergence between "how the section renders alone" and "how it renders in the
book" would be a silent defect: the page a student prints would not match the
page the book has.

**Do not "optimize" this into per-section compilation later.**

## Build side (`parody`)

### Page marks

New `parody/profiles/shared/parody-pagemap.sty`, copied into every build dir
alongside the selected profile's files:

```latex
\ProvidesPackage{parody-pagemap}
\RequirePackage[user]{zref}
\RequirePackage{zref-abspage}
\newcommand{\parodypagemark}[1]{\zlabel{parodypage@#1}}
```

`zref-abspage` gives *absolute* page numbers. This matters: front matter is
roman-numbered, so the printed page number is not the physical page index, and
extraction needs the physical one.

`build_pdf` pulls the package in through the existing `$flags` substitution,
which both bundled profiles place immediately after `\documentclass`. **No
profile is edited**, so book-private profiles (MIT Press) are covered too. If a
profile's template lacks `$flags`, `build_pdf` warns and skips the page map
rather than producing a wrong one.

The mark is a *query*, not a layout decision: it asks LaTeX, after all styling
and page-breaking, which absolute page the point landed on. A style change that
reflows the book moves the marks with the content automatically.

Rejected alternative: deriving boundaries from hyperref's PDF bookmarks (zero
LaTeX change). It is *more* coupled to styling, not less — bookmark structure
varies by document class, and the headless sections from #576 emit no bookmark.

### `parody/writers/pagemap.py` (new)

Three pure functions, each unit-testable without LaTeX:

- `insert_section_mark(tex, key)` — brace-aware scan for the fragment's first
  sectioning command; insert `\parodypagemark{key}` *after* it. Falls back to
  prepending when the fragment opens with no heading (the #576 case, where the
  title comes from `parody.yaml`).
- `read_pagemap(aux_path)` — parse `\zref@newlabel{parodypage@KEY}{…\abspage{N}…}`
  out of `main.aux` into `{key: abspage}`.
- `build_ranges(order, pages, end_page)` — `end(i) = max(own_end(i), start(i+1) - 1)`, **inclusive**.

Each section carries two marks: one at its heading and one (`<key>@end`) after
its last content. The rule threads between two failure modes:

- Taking `start(i+1)` outright is wrong at a **chapter break**. `\chapter`
  forces a page break, so the next section's first page can belong wholly to
  it — the last section of every chapter would end with the *next* chapter's
  title page. (This was the original rule; a real build caught it.)
- Taking `own_end(i)` outright drops the **blank verso** pages between a
  section's last page and the next chapter's opening, so printing every section
  would no longer reassemble the book.

When a section genuinely shares its last sheet with the next, `own_end ==
start(i+1)` and both PDFs carry that sheet — the duplication the task accepts.
The end-to-end invariant to assert is therefore *coverage with no gaps*, not
strict tiling.

### Boundary rules

- The mark for a chapter's **first** section is emitted in `main.tex`
  immediately after `\chapter{…}\label{…}`, not inside the section fragment.
  So that section's PDF opens on the chapter title page. With a `lead-in.md`
  that is the lead-in — satisfying "we treat the chapter title and lead-in text
  as a section". Without one, the first real section absorbs the chapter
  opening, which is also what you want.
- `build_pdf` appends `\parodypagemark{@end}` after the last chapter and before
  `\backmatter`, so the final section's range stops at the bibliography rather
  than running to the last page of the index.

### Editions

`build_pdf` currently has **no edition support**; `build_project` does, via
three contained helpers: `_meta_for_edition` (version-track substitution),
`_resolve_section_file` (the single-source-until-fork overlay), and dropping
chapters left empty. rtcbook is the flagship and has ed1/ed2, so without this
its per-section PDFs would be wrong.

`build_pdf` gains `edition=` and reuses those same helpers — no second
implementation of the overlay rules. Scoped as its own phase so it can be
deferred for single-edition books.

### Outputs

`build_pdf` writes a sidecar next to the PDF, `<output>.pages.json`:

```json
{
  "schema": 1,
  "pdf": "real-time-computing-parody.ed1.pdf",
  "pages": 512,
  "sha256": "…",
  "cloze_mode": "blank",
  "solutions": false,
  "sections": {
    "introduction/lead-in": [1, 4],
    "introduction/voltage-dividers": [4, 9]
  }
}
```

Keys are `<chapter-slug>/<section-slug>` — exactly the always-present fallback
form of `parody_web.Section.key`, so the join needs no new identity concept.

### Artifact

`parody build --print-pages <sidecar>` folds it in. Per section:

```json
"print": { "pages": [4, 9] }
```

and top level:

```json
"print": { "pdf": "…", "pages": 512, "sha256": "…" }
```

Declared explicitly in `artifact-v2.json` so `parody check` validates them. The
v2 schema sets no `additionalProperties: false`, so this is purely additive and
older artifacts keep validating. The vestigial top-level `pdf_file` string
(passed through from `parody.yaml`, read by nothing) is left alone.

### `parody publish` (new command)

Runs pdf → build in order, wiring the sidecar through automatically and looping
editions when the project declares them. `--skip-pdf` and `--pdf-only` as
escapes. This is the "publish the latest to print and to web" command.

`parody init` scaffolds an opt-in CI job that runs the print step in the pinned
TeX Live image, commented out by default.

## Web side (`parody-web`)

### Data

One migration:

- `Book.print_pdf` (filename within the print root), `Book.print_pages`,
  `Book.print_sha256`
- `Section.print_pages` — JSON `[start, end]`, nullable

The importer reads the artifact's `print` keys. Absent → null, and the whole
feature disappears silently, matching the existing posture for artifacts that
carry no solutions.

### Storage

Three settings, validated at boot exactly as `PARODY_WEB_THEME` and
`PARODY_WEB_ACCESS_POLICY` already are:

- `PARODY_WEB_PRINT_ROOT` — where the PDFs live. Deliberately **not** under
  `MEDIA_ROOT`, so nginx cannot serve them by accident.
- `PARODY_WEB_PRINT_CACHE` — writable dir for slices (default
  `<PRINT_ROOT>/.cache`).
- `PARODY_WEB_PRINT_XACCEL` — optional internal location prefix. Set, responses
  use `X-Accel-Redirect` and nginx streams the bytes; unset, `FileResponse`.

### Slicing — `parody_web/printing.py` (new)

Cache path: `<slug>/<ed>/<sha256[:12]>/<ch>-<sec>.pdf`.

Folding the source PDF's hash into the *path* is what makes restyling safe:
repaginate the book and every slice lands in a new directory, so a stale slice
can never be served and there is no cache to bust by hand.

Writes are tmp-file + `os.replace`, so a concurrent request cannot read a
half-written PDF. `pypdf` is imported lazily behind a flag; absent, the feature
is simply off.

### Access

Two new hooks on `DefaultPolicy`, overridable like the solution hooks:

- `can_download_section_pdf(request, section)` — defaults to whatever the page
  itself shows: a preview section's PDF is owner-only, because the page is.
- `can_download_book_pdf(request, book)` — defaults to **True**, gated by the
  `PARODY_WEB_PUBLIC_BOOK_PDF` setting (default `True`).

### Routes

Following the existing reserved-first-segment pattern (`errata`, `go`,
`systems`, `index`, `search`), all edition-aware via `_resolve_book`:

| Route | Purpose |
|---|---|
| `<ch>/<sec>/pdf/` | download this section (`RTC-3.2-Voltage-dividers.pdf`) |
| `<ch>/<sec>/pdf/view/` | full-window viewer |
| `pdf/` | full book |

### The viewer

A bare template — no masthead, sidebar, or rail. A slim bar (book title,
section label, back, download) and the PDF filling the viewport.

Built as a positioned container with an empty sibling overlay div carrying
`data-section-key` — the same `Section.key` a host already keys its own records
to. That is the annotation seam, left open the way `_section_overlay.html` is.

### The sticky utility rail

New host-shadowable `_section_rail.html`: a `<ul class="util-rail">` of
`<li data-util="pdf">` in the upper right. The video icon later is one more
`<li>` and nothing else moves — that is the reason to build it now.

The button expands a small card: *Read as PDF* / *Download this section* (with
its page count) / *Download full book* when permitted.

- With JS off the button is a plain link to the viewer page. The PDF never
  depends on scripting.
- Real `<button aria-expanded>`, Escape closes, focus returns to the trigger.
- Rules go in the existing `book.css` using existing tokens, SVG inlined in the
  template — **no new static files**, sidestepping the `package-data` trap that
  has silently shipped a CSS-less site before.

### Elsewhere

- A quiet full-PDF line on the book home page (`index.html`), not a hero button.
- `deploy.sh` gains an optional print asset downloaded into the print root;
  nginx gains an `internal` location for X-Accel. `site.env.example` and
  `AWS.md` updated. A site with no print assets behaves exactly as today.

## Testing

**Build side.** Unit tests for `insert_section_mark` against brace-heavy and
math-bearing headings and the headless-section case; `read_pagemap` against
real `.aux` fixtures; `build_ranges` for the coverage invariant and the
chapter-break case. One end-to-end test, skipped when `latexmk` is absent, that
builds a small fixture book and asserts the derived ranges cover the real PDF's
body with no gaps, no page beyond its length, and no section swallowing the
page a later section opens on. Per the `latex-newcommand-clashes-hide-in-nonstopmode` gotcha, that
test gates on `LaTeX Error` — not merely `Undefined control sequence` — so a
`\parodypagemark` name collision cannot pass silently.

**Web side.** The gating matrix matters most: anonymous vs owner × full vs
preview section × section vs book PDF, with an explicit test that a preview
section's PDF is refused to the public. Preventing that leak is the entire
reason serving goes through a view (D2).

Also: slice page count equals `end - start + 1`; a second request does not
re-slice; a changed `print_sha256` yields a different cache path; and the
degradation cases (no `pypdf`, no `print_pages`, file missing from disk) render
no affordance rather than a 500.

## Risks

1. **Permissive full-book default (D5).** The default is public, so a gated
   book that does not set `PARODY_WEB_PUBLIC_BOOK_PDF = False` serves its whole
   text. rtcbook must set it. Mitigation, which informs rather than overrides
   the decision: a startup check warns when a book has gated (preview or
   online-only) sections while the setting is `True`. Setting it for rtcbook is
   a required step in that book's release chain.
2. **Layout collision.** The utility rail and the existing "On this page" rail
   both want the upper right. The fiddliest visual work here, especially at
   narrow widths.
3. **A second dependency.** parody-web currently depends on Django alone.
   `pypdf` ships as an optional extra, `parody-web[print]`, so existing
   deployments are untouched until they opt in.
4. **Cold-cache memory.** pypdf holds the whole document; a 500-page
   illustrated book is tens of MB per slice. The parsed reader is cached per
   `(book, sha)` so a cold-cache crawl parses once rather than per section.
5. **Mark insertion operates on pandoc's generated LaTeX.** Insulated from the
   profiles; only a change to `print.lua`'s `Header` output can disturb it, and
   that is covered by the fixture tests above.

## Phasing

1. **Page map** — `parody-pagemap.sty`, `pagemap.py`, `build_pdf` marks +
   sidecar. Verifiable alone: build a book, assert the ranges cover its body.
2. **Editions in `build_pdf`** — reuse `build_project`'s three helpers.
   Deferrable for single-edition books.
3. **Artifact + `parody publish`** — schema, `--print-pages`, the combined
   command, the opt-in CI scaffold.
4. **Web data + slicing** — models, migration, importer, `printing.py`,
   settings, policy hooks.
5. **Web routes + viewer** — the three routes and the bare viewer template.
6. **Chrome** — the utility rail, the home-page line, CSS.
7. **Deploy** — `deploy.sh`, nginx, docs, and rtcbook's
   `PARODY_WEB_PUBLIC_BOOK_PDF = False`.
