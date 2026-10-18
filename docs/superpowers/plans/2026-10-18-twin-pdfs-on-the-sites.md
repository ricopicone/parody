# Twin PDFs on the Book Sites Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A reader of a book site (electronics.ricopic.one and the others) can download each section, or the whole book, as its translated twin PDF and as the English + twin side-by-side sheets, gated exactly like the English PDF. The twins are built in the book's release CI.

**Architecture:** This is subsystem 3 of 5. It spans four repos.

- **parody** (branch `mellow-harbor`): `parody twin` writes a sidecar, `<twin>.twin.json`. It holds:
  - the twin's sha256 and the sha256 of the English PDF it twins;
  - the side-by-side file name;
  - each section's twin page range.

  The twin starts at the first selected section, not at English page 1, so the English `print_pages` cannot slice it. The sidecar ranges can.
- **parody-web** (worktree `/Users/picone/parody-web-worktrees/twins`, branch `twins`, from origin/main 0.99.0). It adds:
  - a `TwinPdf` model;
  - `import_artifact --twin <sidecar>`;
  - slicing keyed by the twin's sha;
  - four gated URLs;
  - a "Translations" entry in the section rail and the PDF viewer's bar.
- A twin is served only when its `english_sha256` equals the book's current `print_sha256`. A twin of an older English PDF would pair the wrong pages, so it is absent.
- **homepage-django** (worktree from origin/main). The fetcher unpacks `twins.zip` when the manifest's features list `translations`. `import_books` passes `--twin` for each sidecar.
- **The book repo** (electronics): its CI print job builds twins after `parody publish`. The step is `continue-on-error`, so a twin failure never blocks the English release.

**Tech Stack:** Python, Django (parody-web, homepage-django), pypdf, GitHub Actions, TeX Live with Noto CJK fonts in CI.

**Spec:** `docs/superpowers/specs/2026-10-17-translations-design.md`: "Side-by-side PDF", "When translations lag the English", D4, D15, D16.

## Global Constraints

- A twin is gated exactly like the English: same draft check, `can_download_section_pdf` / `can_download_book_pdf`, and 404 for every refusal or absence (D16).
- A twin whose `english_sha256` ≠ `Book.print_sha256` is never served (spec, "When translations lag the English": no twin from another English build).
- The language code is one of parody's `LANGUAGES` keys (zh, ko, de, fr, es). The URL segment is that code, lowercase.
- parody-web: every new template is a new partial; no shadowed template is edited. New migrations are additive.
- parody-web versions bump with `uv.lock` in the same commit.
- Nothing is merged, pushed or released by this plan. It ends with branches ready and a written release chain.

## Review Focus

1. **A twin built from an older English PDF** (the English rebuilt, twins not). No translation links are offered, and every twin URL 404s. *Task 3.*
2. **A section the twin does not cover** (a chapter not built, or a draft). No link, and a 404. *Task 3.*
3. **A reader without access to the section.** A 404, the same as an absent section, and no link in the chrome. *Task 4.*
4. **A sidecar whose PDF is missing, or whose sha does not match the file on disk.** `import_artifact` warns, imports nothing for that twin, and still imports the English. *Task 2.*
5. **A malicious or odd language segment** (`../`, `xx`, uppercase). A 404; no path is ever built from it. *Task 4.*

---

### Task 1: parody — the twin sidecar

**Files:** Modify `parody/twin/build.py` and `parody/cli.py`. Test in `tests/test_twin_build.py` and `tests/test_twin_cli.py`.

**Interfaces:**
- `TwinReport.sections: dict[str, list[int]]`. It maps `"chapter/section"` to `[first, last]`, 1-based pages of the twin PDF, filled by `build_twin` from the pages' pieces.
- `write_twin_sidecar(pdf: Path, report: TwinReport, side_by_side: Path | None = None) -> Path`. It writes `pdf.with_suffix(".twin.json")` containing:

```json
{"schema": 1, "language": "de", "pdf": "electronics-de.pdf", "sha256": "…",
 "english_sha256": "…", "side_by_side": "electronics-de-sbs.pdf" | null,
 "sections": {"fundamentals/lead-in": [1, 1], …}, "abspages": [5, …],
 "base_scale": 0.87, "squeezed": [[22, 0.85]], "approximate": [4, 5],
 "untranslated": 0, "stale": 0}
```

  - `sha256` is the twin file's sha256, computed as `parody publish` computes the English one (sha256 of the bytes).
  - `english_sha256` is the sha256 of `report.english_pdf`.
- `cmd_twin` writes the sidecar after the optional side-by-side, but only when the build passed (exit 0).

- [ ] **Step 1: Failing tests:**
  - `test_sections_ranges_from_pages`, a pure function `section_ranges(pages, section_keys)`.
  - `test_sidecar_round_trip` (tmp files; sha256 of the bytes).
  - `test_cli_writes_sidecar_only_on_success`.
- [ ] **Step 2–4:** RED, implement, GREEN.
- [ ] **Step 5: Commit** `feat(twin): sidecar with the twin's page ranges and the English it twins`.

### Task 2: parody-web — the TwinPdf model and the import

**Files:**
- Modify `parody_web/models.py` and add a migration.
- Modify `parody_web/management/commands/import_artifact.py`.
- Create `parody_web/twins.py` for the sidecar validation.
- Test in `tests/test_twins.py`. Follow the existing tests' style; look at `tests/` for the settings and helpers.

**Interfaces:**
- `class TwinPdf(models.Model)`:
  - `book = ForeignKey(Book, CASCADE, related_name="twins")`
  - `language = CharField(max_length=8)`
  - `pdf = CharField(max_length=200)` (a basename)
  - `sha256 = CharField(max_length=64)`
  - `english_sha256 = CharField(max_length=64)`
  - `side_by_side_pdf = CharField(max_length=200, blank=True)`
  - `sections = JSONField(default=dict)`
  - `approximate = JSONField(default=list)`
  - `imported_at = DateTimeField(auto_now=True)`
  - `Meta.unique_together = ("book", "language")`
- `twins.load_sidecar(path: Path) -> dict`. It raises `ValueError` with a reason for:
  - a wrong schema;
  - an unknown language;
  - a PDF missing under `printing.print_root()`;
  - a sha mismatch with the file.
- `import_artifact --twin PATH` (`action="append"`). After the Book is imported, it loads each sidecar. A good one is `update_or_create`d. A bad one is reported through `self.stderr` and that twin is skipped; the English import still succeeds. Twins of this book whose language was not given this time are deleted, so twins never outlive their release.

- [ ] **Step 1: Failing tests:**
  - `test_import_twin_records_it`
  - `test_bad_twin_is_skipped_english_imported`: missing PDF, sha mismatch, bad language.
  - `test_reimport_without_twin_removes_it`
  - `test_twin_needs_pypdf_free_validation`: sha only, no PDF parsing.
- [ ] **Step 2–4:** RED, implement (`makemigrations parody_web`), GREEN. Run `uv run python runtests.py`; the whole suite must pass.
- [ ] **Step 5: Commit** `feat: import translated twin PDFs (TwinPdf, import_artifact --twin)`.

### Task 3: parody-web — slicing and validity

**Files:** Modify `parody_web/printing.py`. Test in `tests/test_twins.py`.

**Interfaces:**
- `twin_for(book, language) -> TwinPdf | None`. It returns None unless:
  - the twin exists;
  - `twin.english_sha256 == book.print_sha256`;
  - `print_root()/twin.pdf` is a file;
  - pypdf is available.
- `twin_pdf_path(twin, side_by_side=False) -> Path | None`. A basename under `print_root`.
- `twin_section_pdf_path(book, section, twin, side_by_side=False) -> Path | None`.
  - The range comes from `twin.sections.get(section.key_path)`, where `key_path` is `f"{section.chapter.slug}/{section.slug}"`; add that property to `Section` if it does not exist.
  - The cache path is `cache/<slug>/<edition or _>/twin-<lang>-<sha[:12]>[-sbs]/<chapter>-<section>.pdf`.
  - Slicing uses `slice_pdf`. None if any piece is missing.
- `translations_available(book) -> list[TwinPdf]`, the valid twins, ordered by language.

- [ ] **Step 1: Failing tests:**
  - `test_twin_for_requires_matching_english_sha`
  - `test_twin_section_slice_uses_sidecar_range`: build a 3-page PDF with pypdf, and give the sidecar a range for the section.
  - `test_section_outside_twin_has_no_slice`
  - `test_side_by_side_slice`
- [ ] **Step 2–4:** RED, implement, GREEN.
- [ ] **Step 5: Commit** `feat: slice twin PDFs by their own page ranges`.

### Task 4: parody-web — URLs, views and the reader-facing links

**Files:**
- Modify `parody_web/urls.py` and `parody_web/views.py`.
- Create `parody_web/templates/parody_web/_translations_download.html`, and include it in `_section_rail.html` (inside the card, after the book download) and in `pdf_view.html`'s exits.
- Add CSS beside `.util-rail-card` and `.pdf-exit`.
- Test in `tests/test_twins.py`.

**Interfaces:**
- URLs, all before the bare section pattern:
  - `pdf/<str:language>/` → `views.book_twin_pdf`, named `book_twin_pdf`;
  - `pdf/<str:language>/side-by-side/` → `book_twin_sbs`;
  - `<ch>/<sec>/pdf/<str:language>/` → `section_twin_pdf`;
  - `<ch>/<sec>/pdf/<str:language>/side-by-side/` → `section_twin_sbs`.
- Each view:
  - validates `language in LANGUAGE_NAMES` (a `twins.LANGUAGE_NAMES` map: code → native name, e.g. de → Deutsch, zh → 中文);
  - applies the same draft check and policy call as `section_pdf` / `book_pdf`;
  - finds `twin_for`, then the path, and returns `_pdf_response(path, name)`, where name is `_pdf_filename(...)` with `-<lang>` or `-<lang>-side-by-side` before `.pdf`;
  - otherwise raises `Http404`.
- `_print_context` adds `"translations": [{"language", "name", "pdf_url", "sbs_url"}]`: the valid twins that cover this section (section page) or the book (home page). It is empty when the reader may not download the English.
- `_translations_download.html` renders nothing when `translations` is empty. Otherwise it renders one line per language: `<native name>: <a>PDF</a> · <a>side by side</a>`.

- [ ] **Step 1: Failing tests:**
  - `test_section_twin_served_inline_and_download`
  - `test_draft_or_policy_refusal_404s`
  - `test_stale_twin_404s_and_no_link`
  - `test_bad_language_404s`, covering `xx`, `DE` and `..`
  - `test_rail_lists_translations_only_when_available`
  - `test_pdf_view_bar_lists_translations`
- [ ] **Step 2–4:** RED, implement, GREEN. Run the full `runtests.py`.
- [ ] **Step 5: Commit** `feat: serve translated twins and side-by-side sheets, gated like the English`.
- [ ] **Step 6: Bump the version** to `0.100.0` with `uv.lock`. Commit `0.100.0: translated twin PDFs`.

### Task 5: homepage-django — fetch and import twins

**Files:** In a worktree from origin/main (`/Users/picone/homepage-django-worktrees/twins`, branch `twins`):
- `scripts/fetch_notebook_artifacts.py` (`_companions`)
- `teaching/book_features.py` (`KNOWN`)
- `teaching/management/commands/import_books.py`
- their tests

Read `homepage-django-local-main-may-be-ahead-unpushed` and `homepage-deploy-ships-origin-main-not-your-commit` in project memory first.

**Interfaces:**
- **Manifest feature.** `features: {translations: [de, zh]}`. `book_features.KNOWN` accepts it, validated as a list of known codes.
- **Fetcher.** When the feature is present, it downloads the release asset `twins.zip` and unpacks `<slug>-<lang>.pdf`, `<slug>-<lang>-sbs.pdf` and `<slug>-<lang>.twin.json` into `teaching/notebooks_data/`. A missing asset is a warning, not a failure: the English still ships.
- **Importer.** `import_books` passes `--twin teaching/notebooks_data/<slug>-<lang>.twin.json` for each present sidecar of each language in the feature.

- [ ] **Step 1: Failing tests,** in the style of the existing tests for these modules (find them first):
  - fetch unpacks the twin files;
  - the manifest validates `translations`;
  - `import_books` passes `--twin`.
- [ ] **Step 2–4:** RED, implement, GREEN (homepage's own test command; find it).
- [ ] **Step 5: Commit** on the branch. Do not push.

### Task 6: the book repo — build twins in the release CI

**Files:** In the electronics book repo, in a worktree from origin/main, `.github/workflows/build.yml`, the print job.

**What the job does:**
- After `parody publish` succeeds, run a step `Twins` with `continue-on-error: true` that:
  - installs `fonts-noto-cjk` (apt) and `parody[twin]` at the pinned version (≥0.62);
  - for each language in `parody.yaml`'s `translations.languages`, runs `parody twin . --lang $L --english electronics.pdf -o twins/electronics-$L.pdf --side-by-side twins/electronics-$L-sbs.pdf`;
  - zips `twins/*` into `twins.zip` and uploads it as a release asset beside `print.zip`.
- With no `translations:` key the step does nothing.
- Document the step in the book's README "Releasing" section, if one exists.

- [ ] **Step 1:** Write a small shell script `scripts/build-twins.sh` that the workflow calls, so it can be run locally. Test it locally on the scratch copy that has translations, and check that `twins.zip` holds the expected files.
- [ ] **Step 2:** Wire it into the workflow. Validate the YAML with `python -c "import yaml; yaml.safe_load(open('.github/workflows/build.yml'))"`.
- [ ] **Step 3: Commit** on a branch. Do not push.

### Task 7: The written release chain

Append to the spec, under a new "Release chain for twins" section, the exact ordered steps (cross-repo) to ship this:
1. Publish parody 0.62.x and 0.63.0 to PyPI.
2. Bump parody in the book CI; translate and commit `translations/`.
3. Tag the book.
4. Publish parody-web 0.100.0.
5. Bump homepage's pin; set the manifest feature.
6. Fetch, commit, deploy.
7. Verify live.

The memory references for each step are `electronics-ricopic-one-release-chain` and `pypi-propagation-lag-is-measured-from-the-box`. Commit it.
