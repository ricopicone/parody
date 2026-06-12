# Parody — Unified Book/Notebook Toolchain (Seed Plan)

**Status:** Approved 2026-06-10; in execution.
**Name:** `parody` — a play on *parity* (keeping the print and web versions in parity). Confirmed available on PyPI 2026-06-10.

---

## 1. Mission

One authoring toolchain, distributed as an installable Python package with a CLI, that unifies two existing systems by the same author:

- **System A — homepage notebooks pipeline** (private Django monolith `homepage-django`): pandoc-markdown + executed jupytext sources → JSON → imported into Django models, served dynamically at ricopic.one with course-integrated solution gating, exam printing, and per-user annotations.
- **System B — meta-based book system** (rtc-book et al.): pandoc-markdown + LaTeX → print-quality PDF (MIT Press production) *and* a Jekyll website, machinery shared across books via `meta-*` git submodules synchronized by hard links.

Parody replaces System A's embedded converter scripts and System B's `meta-book`/`meta-common` (and most of `meta-site`). It does **not** replace System A's Django serving layer—that stays in homepage-django and consumes Parody's JSON artifact.

**Ancestor repos (private; reference implementations):**
- https://github.com/rtc-book/real-time-computing (book), https://github.com/rtc-book/common, https://github.com/rtc-book/site-source
- https://github.com/ricopicone/meta-book, https://github.com/ricopicone/meta-common, https://github.com/ricopicone/meta-site
- homepage-django (local): toolchain code listed in §6 inventory.

## 2. Principles (lessons paid for in both ancestors)

1. **Shared machinery is a versioned dependency, never synchronized files.** The meta-* hard-link scheme (`links.json`, `link-here.py`, manual `meta-*-adoption-notes.txt` merges) is the single biggest maintenance failure in System B. Parody is `pip install parody==X.Y.Z`; a book upgrades by bumping a pin.
2. **The artifact is the contract.** Builds emit machine-readable, schema-versioned JSON (System B already proved this: its LaTeX build emits `book-json/` that generates the website). Consumers (Django importer, static preview, future tools) depend on the schema, not on Parody internals.
3. **One source, many targets.** Pandoc markdown (with executed-code blocks via jupytext) is the canonical source; targets are JSON artifact, print PDF, standalone HTML preview, (later) slides.
4. **Content repos are plain.** One repo per book/notebook, no submodules by default. Collaborators clone one repo, run one containerized command, open a PR. Private content (solutions) lives in the private content repo, extracted into the artifact at build, access-controlled at serve time.
5. **CI exists.** System B has none; every contribution burdens the author's laptop. Content repos build on PR and release artifacts on tag.
6. **Port incrementally, gated by golden tests.** Never rewrite both pipelines at once. Parity with System A first (it has a live production consumer), System B's print machinery second.

## 3. Architecture

```
parody (this repo, pip package + CLI)
├── parody/readers/        markdown + YAML frontmatter; jupytext execution (cached)
├── parody/filters/        pandoc lua/panflute filters (ported from both ancestors)
├── parody/writers/
│   ├── artifact.py       → <slug>.json  (schema below; primary target)
│   ├── latex.py          → print PDF via latexmk/lualatex profiles   (Phase 3)
│   └── preview.py        → standalone static HTML for local review   (Phase 2)
├── parody/cli.py          parody init | build | watch | preview | check
├── profiles/             LaTeX classes/styles (from rtc styles-tex), HTML templates
└── tests/golden/         golden artifacts from both ancestors

content repo (one per book/notebook, from `parody init`)
├── parody.yaml            title, slug, authors, targets, parody version pin
├── chapters/<ch>/<sec>.md   (+ optional <sec>.py jupytext sources)
├── assets/               figures etc. (manifest-listed in the artifact)
├── solutions visibility  via the same .exercise/.exercise-solution divs as System A
└── .github/workflows/    build on PR; artifact + PDF on tag
```

### The artifact contract (schema v1)

Superset of homepage-django's current `notebooks_data/*.json` (so the existing Django importer keeps working with minimal change):

```jsonc
{
  "schema_version": 1,
  "generator": "parody X.Y.Z",
  "source_repo": "github.com/…", "source_commit": "…", "built_at": "…",
  "title": "…", "slug": "…", "description": "…", "acronym": "…",
  "author": ["Full Name", "…"],
  "cover_image": "…", "pdf_file": "…",
  "assets": [{"path": "assets/fig1.png", "sha256": "…"}],
  "chapters": [{
    "slug": "…", "title": "…",
    "sections": [{
      "slug": "…", "title": "…",
      "html": "<rendered html>",
      "anchors": [{"id": "fig:…", "type": "figure", "title": "…"}],
      "has_solutions": true,
      "solutions": {"exe:id": {"content": "<html>", "title": "…"}},
      "problems":  {"exe:id": "<html>"}
    }]
  }]
}
```

**Important quirk (verified in System A, Phase 0 of its split plan):** the `html` field is *Django-template-flavored*—System A's `filter.lua` emits `{% media 'path' %}`, `{% static 'path' %}`, and `{% cite 'key' %}` tags that homepage-django re-renders through its template engine at view time (resolving to local `/media/` or S3 URLs, and to its zotero-backed bibliography). Schema v1 keeps this verbatim for parity; Parody's standalone `preview` writer must implement its own resolution of these tags (media → relative asset paths from the manifest; cite → citeproc). Schema v2 should consider neutral asset URLs + manifest instead of embedded tags.

v2 (post-migration, not now): rtc-style stable short-hash IDs per section/anchor (System B uses 2–4-char hashes as directory names, permalinks, cross-ref keys, and print QR targets—its best idea), print page-number map (from the LaTeX build, System B's `book-0-raw.json` trick), neutral asset references replacing embedded Django tags.

## 4. Phases

### Phase 0 — Bootstrap & decisions
- [x] Confirm name; reserve PyPI; repo + `pyproject.toml` (Python ≥3.11), `uv`/venv, ruff, pytest. *(2026-06-10: name `parody` confirmed available; PyPI reservation pending first publish)*
- [x] Pin toolchain versions explicitly: pandoc (both ancestors have been bitten by pandoc API churn—System B's adoption notes literally say "might break our build system because the figure environment changed"), pandoc-crossref, jupytext, nbconvert. Provide a Dockerfile/devcontainer from day one (System B's `camerondevine/rtc_docker` proved this is the collaboration enabler). *(pandoc pinned via `pypandoc-binary==1.15` → bundled pandoc 3.6.1, the version the goldens were built with; `parody check --toolchain` verifies; pandoc-crossref deferred to Phase 3 where it first appears)*
- [x] Decide filter strategy (recommendation: **keep lua filters initially**—System A's `filter.lua` and System B's 2,803-line `filter.lua` are both pandoc-lua; port them as-is per environment, refactor to shared code later. A panflute rewrite is a separate, optional project; do not block migration on it). *(decided: lua kept as-is)*

### Phase 1 — Parity with System A (gates homepage migration)
- [x] Port verbatim from homepage-django: `convert_notebook_md_to_json.py` (614 LOC), `jupytext_converter_api.py` (1,034), `jupytext_converter_with_execution.py` (471), `filter.lua`, `notebook_helpers.py`/`notebook_utils.py`. Strip Django imports (there are none of substance—these are scripts). *(2026-06-10: only changes—package imports, `media_root` parameterized away from Django root, generator string)*
- [x] Golden tests: build homepage's 5 notebooks (engineering-artificial-intelligence, general-topics, heat-transfer-lab-manual, mechatronics-lab-manual, sample-notebook) and diff against their committed `notebooks_data/*.json` (normalize: key order, whitespace). Target: semantic identity. *(all 5 pass; normalization = provenance keys only—generator, built_at, source_commit, schema_version—since older goldens predate them)*
- [x] Add schema_version/provenance keys; `parody check` validates an artifact against the schema. *(schema at `parody/schemas/artifact-v1.json`)*
- [ ] Release v0.1.0 → homepage-django Phase 2 (see its `NOTEBOOKS_SPLIT_PLAN.md`) swaps its management commands to thin wrappers over this CLI.

### Phase 2 — Content-repo ergonomics
- [x] `parody init` scaffold (layout above), `parody build` (JSON + preview), `parody watch` (replaces homepage's `watch_notebooks.py`/livereload), `parody preview` (static HTML so a collaborator never needs Django to see their work). *(2026-06-10: preview resolves {% media %}/{% cite %}/{% cite_many %} (citeproc when a .bib exists) and degrades {% url %}/{% get_cell %}/{% auth_button %}/{% csrf_token %} — the real tag surface turned out larger than the §3 quirk note. New layout passes slug context to filter.lua/figure_mover via PARODY_* env vars, fallback-only so legacy stays golden.)*
- [x] CI workflow template: build on PR (the missing System B affordance), artifact + checksums on tag. *(ships in `parody init` → .github/workflows/build.yml)*
- [ ] Migrate homepage notebooks into content repos one at a time, smallest first (sequencing and delivery mechanics are owned by homepage's plan, not this repo).

### Phase 3 — Print target (System B's machinery, ported properly)
- [x] Inventory `rtc-book/common/filter.lua` capabilities → port per-environment with golden LaTeX-snippet tests: numbered divs (`.exercise` w/ XSIM, `.example`, `.theorem`/`.lemma`/`.corollary`, `.definition`, `.infobox`, `.listing`, `.algorithm`), semantic spans (`.keyword`, `.index`, `.path`, `.keys`, `.menu`, `.plaincite`), `pandoc-crossref` integration, hashref cross-links. *(2026-06-10: `parody/filters/print.lua`; golden snippet `tests/print_fixtures/environments.golden.tex` + 36 per-environment assertions. NOT ported, per plan: book-defs/book-json lookups, ts/ds versioning, apocrypha/videos (Phase 4 plugin), meta-site HTML branches, MIT \lab/\resource section commands. pandoc-crossref pinned 0.3.18.1 (built against pandoc 3.6) in toolchain.py + Dockerfile.)*
- [x] latexmk profiles from `meta-book` (`latexmkrc_main`, `latexmkrc_solutions`; lualatex, `-shell-escape`/minted; conditional flags `\issolution`, `\ispartial`, `\nocropmarks`); styles from `common/styles-tex` (note: MIT Press class + licensed fonts are **book-private**—they belong in the book's content repo or a private profile package, not in Parody). *(generic profile at `parody/profiles/print/` — parody-print.sty implements every emitted environment with stock packages; `parody pdf --profile` plugs in book-private profiles; lualatex -shell-escape + biber via latexmkrc; `\issolution` honored via xsim solution/print)*
- [x] Bibliography: single `book.bib` per content repo; citeproc for HTML, biblatex for print (both ancestors already agree on this split). *(preview uses citeproc; `parody pdf` emits \autocite/\textcite + biblatex/biber with auto-detected *.bib)*
- [x] Targets: full PDF, per-section PDF (System B's `make section h=…`), solutions manual. Sample/marketing pipeline (pdftk watermark, bookmark splitting) ports only if still wanted. *(`parody pdf`, `--section ch/sec`, `--solutions`; full + solutions compile under lualatex in tests. Sample/marketing pipeline deliberately not ported.)*

### Phase 4 — Migrate a System B book
- [ ] Pilot with the smallest/least in-flight meta-based project; `real-time-computing` (MIT Press production constraints, hardware versioning) goes **last**.
- [ ] Mapping: `meta-book` → Parody latex profiles + CLI; `meta-common` → Parody filters/styles/figure templates; `common/` content → the book's content repo (versioned prose merges in; the separate `common` repo dissolves unless two books truly share prose); `meta-site` + `site-source` → **retire per book** in favor of either (a) the Parody artifact imported into homepage-django (books become first-class citizens of the notebooks UI—likely the point of this whole effort) or (b) `parody preview` static output where a standalone book site must persist (rtcbook.org).
- [x] Hardware versioning (`versions.json` → inheritance flattening → conditional prose + parts lists): port **only when the migrating book needs it**, as a Parody plugin/filter, not core. *(2026-06-11: `parody/plugins/versioning.py` — first plugin; named tracks (rtc ts/ds two-track and single-track books are both just config; 2nd-ed = `tracks: {ts: T2, ds: D2}`), variant-inheritance flattening, `[]{.ts}`/`[]{.tsicon}`/`[]{.T1-…}` span substitution in both pipelines, unresolved params warn (surfaced 4 stale rtc refs meta hid). Parts lists (versions-lister) deferred to the rtc lab appendices.)*
- [x] Adopt short-hash stable IDs into schema v2 here, where the rtc content already carries them. *(2026-06-10: opt-in `schema: 2` in parody.yaml; duplicate hashes are a build error; math pilot migrated, 10 inherited collisions re-keyed.)*
- [x] **Migration toolkit consolidated** *(2026-06-11: the three diverged per-book migrate_from_meta.py copies (math < ec < systems, each strictly more capable) now live in `parody/migrate/` — `parody migrate SRC` + `parody rehash` (data-driven duplicate-hash loser lists in scripts/rehash_losers.yaml, per-book salt). Book repos keep thin wrappers. Parity: ec and systems re-migrations reproduce their committed trees byte-for-byte; math re-runs documented as title/figure-hash-churning (exercises-tex gotcha).*
- [x] **Unified latex→md converter before rtc.** *(2026-06-11: `parody/migrate/latex_to_md.py` + `filters/latex-to-md.lua` — luafilesystem dropped (vestigial; pinned pandoc now runs it), deterministic short-strings, `\myindex`→`.index` spans, sectioning pre-pass (`\section`/`\subsection`/`\subsubsection`/`\resource` 3-arg forms → attributed ATX headers; 2-arg versioned pulls → include fences), clean_math in postprocess. Validated on all 12 rtc latex-only prose sections: 0 failures, correct titles/slugs/hashes, deterministic.)* `latex-to-md-filter.lua` has diverged per book (rtc 761 lines, math 1,109) and is unreliable (live rtc test: section titles mangled into `bkMemory and its contents`, `\myindex` left as raw latex, math defects need post-patching). Exposure survey (2026-06-11): engineering-computing **0** latex-only sections, systems **1** (one exercises.tex), math **8** (done), rtc **~16 prose sections + 12 exercises files**. So: migrate engineering-computing and systems with current tooling; before rtc, absorb the converter into Parody migration tooling seeded from math's copy — golden tests from rtc's real latex-only sections, fix in-filter (per-book section-command parsing, the migrator's clean_math post-patches, `\myindex` → `.index` spans, deterministic figure-dir hashes, drop the luafilesystem dependency so the pinned pypandoc pandoc runs it).

### Phase 5 — Collaboration hardening
- [ ] Devcontainer + one-command build documented for outside collaborators; CONTRIBUTING template in `parody init`.
- [ ] Private-solutions pattern documented: private content repo → artifact carries solutions → serve-time gating (homepage) or excluded preview builds (`parody build --no-solutions`) for public artifacts.
- [ ] Artifact signing/checksums in the release workflow (homepage's deploy verifies before import).

## 5. Decisions to make early (with recommendations)

| Decision | Recommendation |
|---|---|
| Name | **decided:** `parody` (play on parity); PyPI availability confirmed 2026-06-10 |
| Lua filters vs panflute rewrite | keep lua now; converge later |
| One Parody repo vs core+profiles split | one repo until a second book needs a private profile (MIT Press styles force a private `parody-profiles-rtc` eventually) |
| Where does `common`'s shared-prose idea go | dissolve into per-book repos; resurrect as a shared content repo only if two books actually share sections again |
| Jekyll site replacement | don't rebuild it; homepage Django serves artifacts, `parody preview` covers standalone needs |
| Execution backend for code cells | keep System A's cached jupytext/nbconvert approach (it works and is already API-cached) |

## 6. Inventory of source material

**From homepage-django** (`teaching/scripts/`, `teaching/utils/`, `scripts/`): converter trio + filter.lua + helpers + watchers (≈2,800 LOC Python, 1 lua filter). Golden outputs: `teaching/notebooks_data/*.json` (5 files). Source corpora to migrate: `teaching/notebooks-source/*` (54 MB, 4 real notebooks + sample).

**From rtc-book/meta**: `common/filter.lua` (2,803 lines), `common/common.mk` (pandoc invocations: `include-files.lua`, `include-code-files.lua`, `section-divs.lua`, `pandoc-crossref`, citeproc/biblatex split), `common/styles-tex/` (`NewMath_MIT.cls`, `environments.sty`—note `environments.sty` also emits the build JSON), `meta-book` (Makefile, latexmkrc profiles, `scripts/`: `build-alone.py`, `split_pdf_at_bookmarks.sh`, hash tooling `new-version*-text.py`, `find_duplicate_hashes.py`), `meta-site` (generate-pages/faux-sources/menus scripts—reference only), `common/versions.json` + `versions-inheriter.py`/`versions-lister.py` (Phase 4, plugin), Docker image recipe.

**Known gotchas inherited:** pandoc version sensitivity; LaTeX-emitted JSON is malformed by construction (System B's `json-clean.py`)—Parody's artifact must come from the pandoc/Python side, never from LaTeX, with the LaTeX build contributing only optional enrichment (page numbers) post-cleaned; duplicate-hash detection must be a build **error**, not a warning; don't commit build artifacts to content repos (System B carries 153 MB of versioned PDFs in git)—releases/object storage instead.

## 7. Definition of done

Parody v1.0 = homepage-django builds nothing locally (all notebook content arrives as pinned artifacts from content repos), at least one former meta-based book builds print PDF + artifact from a plain content repo with CI, and `meta-book`/`meta-common` are archived.
