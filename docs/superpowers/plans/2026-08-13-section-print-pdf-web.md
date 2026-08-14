# Section Print PDF — Web Side (`parody-web`) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Serve each section's print PDF from the book site — sliced on demand out of the full-book PDF, behind the access policy — and offer it through a sticky utility rail built to take video embeds later.

**Architecture:** The artifact carries each section's absolute page range. A gated Django view slices those pages out of the full PDF with `pypdf`, caches the result under a path keyed by the source PDF's hash, and streams it. A full-window viewer route renders the PDF alone in a container whose empty overlay sibling is the seam a future annotation layer plugs into.

**Tech Stack:** Django 5.x, `pypdf` (optional extra), the existing tokenised CSS in `parody_web/static/parody_web/css/book.css`.

**Spec:** `docs/superpowers/specs/2026-08-13-section-print-pdf-design.md` (in the **parody** repo, alongside the build-side plan).

**Prerequisite:** `docs/superpowers/plans/2026-08-13-section-print-pdf-build.md` must be complete — it defines the artifact `print` fields this plan consumes.

**Repo:** This plan executes in `~/parody-web`, not the parody repo the spec lives in.

## Global Constraints

- **Never serve print PDFs from `MEDIA_ROOT`.** nginx serves that tree with no auth; the whole point of routing through a view is that gated books stay gated (spec D2).
- **Absolute page ranges are inclusive at both ends.** A slice is `end - start + 1` pages, and consecutive sections deliberately share their boundary page.
- **The feature must vanish silently when unavailable** — no `pypdf`, no `PARODY_WEB_PRINT_ROOT`, no `Section.print_pages`, or a missing file on disk must render *no affordance*, never a 500.
- **`pypdf` is an optional extra** (`parody-web[print]`). parody-web currently depends on Django alone; existing deployments must be unaffected until they opt in.
- **New static files must be listed in `[tool.setuptools.package-data]`** or they are silently dropped from the wheel and the deploy ships a site missing them. This plan adds **no** new static files (SVG inlined, CSS appended to `book.css`) precisely to avoid that trap — keep it that way.
- **The full-book PDF is public by default** (`PARODY_WEB_PUBLIC_BOOK_PDF = True`), per the owner's decision. rtcbook sets it `False` (Task 8).
- Working trees are shared with concurrent agent sessions. **Never `git add -A`.** Add only the exact paths each task names.
- Version bumps commit `pyproject.toml` **and** `uv.lock` together, and the number is **re-derived against `main` at merge time** — parallel sessions move it, and an identical version on both sides merges without conflict and ships a duplicate release.
- Run the suite with `python runtests.py`; a single module with
  `DJANGO_SETTINGS_MODULE=tests.settings python -m django test parody_web.tests_printing -v 2`.

---

### Task 1: Model fields and importer

**Files:**
- Modify: `parody_web/models.py`, `parody_web/management/commands/import_artifact.py`
- Create: `parody_web/migrations/0010_print_pdf.py`
- Create: `parody_web/tests_printing.py`

**Interfaces:**
- Produces: `Book.print_pdf` (str), `Book.print_pages` (int|None), `Book.print_sha256` (str), `Section.print_pages` (list|None), and `Section.print_page_count` (property).

- [ ] **Step 1: Write the failing test**

```python
"""Per-section print PDFs: import, slicing, gating, and chrome."""
import json
import tempfile
from pathlib import Path

from django.core.management import call_command
from django.test import TestCase

from parody_web.models import Book, Section

ARTIFACT = {
    "schema_version": 2,
    "slug": "print-book",
    "title": "Print Book",
    "author": ["A. Author"],
    "print": {"pdf": "print-book.pdf", "pages": 20, "sha256": "c" * 64},
    "chapters": [{
        "title": "One", "slug": "one", "hash": "c1",
        "sections": [
            {"title": "One", "slug": "lead-in", "hash": "li",
             "html": "<p>Intro.</p>", "print": {"pages": [3, 5]}},
            {"title": "Alpha", "slug": "alpha", "hash": "al",
             "html": "<p>Alpha.</p>", "print": {"pages": [5, 9]}},
            {"title": "Beta", "slug": "beta", "hash": "be",
             "html": "<p>Beta.</p>"},
        ],
    }],
}


def import_artifact(data=None, **opts):
    payload = json.loads(json.dumps(data or ARTIFACT))
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump(payload, f)
        path = f.name
    call_command("import_artifact", path, **opts)
    Path(path).unlink()
    return Book.objects.get(slug=payload["slug"])


class ImportPrintFieldsTests(TestCase):
    def test_book_carries_the_print_metadata(self):
        book = import_artifact()
        self.assertEqual(book.print_pdf, "print-book.pdf")
        self.assertEqual(book.print_pages, 20)
        self.assertEqual(book.print_sha256, "c" * 64)

    def test_sections_carry_their_page_range(self):
        book = import_artifact()
        alpha = book.sections.get(slug="alpha")
        self.assertEqual(alpha.print_pages, [5, 9])

    def test_a_section_without_a_range_is_null(self):
        book = import_artifact()
        self.assertIsNone(book.sections.get(slug="beta").print_pages)

    def test_page_count_is_inclusive_of_both_ends(self):
        book = import_artifact()
        # [5, 9] shares page 5 with the lead-in and page 9 with what follows
        self.assertEqual(book.sections.get(slug="alpha").print_page_count, 5)
        self.assertIsNone(book.sections.get(slug="beta").print_page_count)

    def test_an_artifact_with_no_print_block_imports_cleanly(self):
        data = json.loads(json.dumps(ARTIFACT))
        del data["print"]
        for sec in data["chapters"][0]["sections"]:
            sec.pop("print", None)
        book = import_artifact(data)
        self.assertEqual(book.print_pdf, "")
        self.assertIsNone(book.print_pages)
        self.assertTrue(all(s.print_pages is None for s in book.sections.all()))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `DJANGO_SETTINGS_MODULE=tests.settings python -m django test parody_web.tests_printing -v 2`
Expected: FAIL — `AttributeError: 'Book' object has no attribute 'print_pdf'`

- [ ] **Step 3a: Add the fields**

In `parody_web/models.py`, add to `Book` (after `parts`):

```python
    # Print PDF this edition's page ranges index into. Empty when the artifact
    # carried no print block — the whole PDF feature then simply does not exist
    # for this book, which is the correct behaviour for a web-only build.
    print_pdf = models.CharField(max_length=200, blank=True, default="")
    print_pages = models.PositiveIntegerField(null=True, blank=True)
    # sha256 of the source PDF: folded into the slice cache path so a rebuilt
    # (repaginated) book can never be served a stale slice.
    print_sha256 = models.CharField(max_length=64, blank=True, default="")
```

and to `Section` (after `problems`):

```python
    # Inclusive [start, end] absolute page range in the print PDF. The end page
    # is shared with the next section when both fall on one sheet — intended,
    # so a student printing section by section loses nothing at the seams.
    print_pages = models.JSONField(null=True, blank=True)
```

plus the property, next to `key`:

```python
    @property
    def print_page_count(self):
        """Sheets in this section's PDF, or None when it has no page range."""
        if not self.print_pages or len(self.print_pages) != 2:
            return None
        start, end = self.print_pages
        return end - start + 1
```

- [ ] **Step 3b: Generate the migration**

```bash
DJANGO_SETTINGS_MODULE=tests.settings python -m django makemigrations parody_web -n print_pdf
```

Confirm it created `parody_web/migrations/0010_print_pdf.py` and adds exactly the four fields.

- [ ] **Step 3c: Import them**

In `import_artifact.py`, inside `_import`, add to the `Book.objects.update_or_create` defaults:

```python
                "print_pdf": (data.get("print") or {}).get("pdf", ""),
                "print_pages": (data.get("print") or {}).get("pages"),
                "print_sha256": (data.get("print") or {}).get("sha256", ""),
```

and to the `Section.objects.update_or_create` defaults:

```python
                        "print_pages": (sec.get("print") or {}).get("pages"),
```

- [ ] **Step 4: Run test to verify it passes**

Run: `DJANGO_SETTINGS_MODULE=tests.settings python -m django test parody_web.tests_printing -v 2`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add parody_web/models.py parody_web/migrations/0010_print_pdf.py parody_web/management/commands/import_artifact.py parody_web/tests_printing.py
git commit -m "print: carry the print PDF page ranges through the importer (task #583)"
```

---

### Task 2: Settings, validation, and the `pypdf` extra

**Files:**
- Create: `parody_web/printing.py` (settings surface only; slicing lands in Task 3)
- Modify: `parody_web/apps.py`, `pyproject.toml`
- Test: `parody_web/tests_printing.py`

**Interfaces:**
- Produces:
  - `print_root() -> Path | None`, `print_cache_root() -> Path | None`
  - `has_pypdf() -> bool`
  - `validate_print_settings(root, cache, xaccel)` — raises `ImproperlyConfigured`
  - Settings: `PARODY_WEB_PRINT_ROOT`, `PARODY_WEB_PRINT_CACHE`, `PARODY_WEB_PRINT_XACCEL`, `PARODY_WEB_PUBLIC_BOOK_PDF`

- [ ] **Step 1: Write the failing test**

```python
# append to parody_web/tests_printing.py

from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase, override_settings

from parody_web import printing


class PrintSettingsTests(SimpleTestCase):
    def test_no_root_configured_means_the_feature_is_off(self):
        with override_settings(PARODY_WEB_PRINT_ROOT=""):
            self.assertIsNone(printing.print_root())

    def test_cache_defaults_inside_the_print_root(self):
        with tempfile.TemporaryDirectory() as td:
            with override_settings(PARODY_WEB_PRINT_ROOT=td,
                                   PARODY_WEB_PRINT_CACHE=""):
                self.assertEqual(printing.print_cache_root(),
                                 Path(td) / ".cache")

    def test_cache_can_be_pointed_elsewhere(self):
        with tempfile.TemporaryDirectory() as td, \
                tempfile.TemporaryDirectory() as cache:
            with override_settings(PARODY_WEB_PRINT_ROOT=td,
                                   PARODY_WEB_PRINT_CACHE=cache):
                self.assertEqual(printing.print_cache_root(), Path(cache))

    def test_a_non_directory_root_is_rejected_at_startup(self):
        with self.assertRaises(ImproperlyConfigured):
            printing.validate_print_settings("/definitely/not/here", "", "")

    def test_xaccel_requires_the_cache_to_live_under_the_root(self):
        # nginx maps ONE internal location at the print root, so a cache
        # outside it could never be streamed.
        with tempfile.TemporaryDirectory() as td, \
                tempfile.TemporaryDirectory() as outside:
            with self.assertRaises(ImproperlyConfigured):
                printing.validate_print_settings(td, outside, "/print-internal/")
            printing.validate_print_settings(td, "", "/print-internal/")

    def test_valid_settings_pass(self):
        with tempfile.TemporaryDirectory() as td:
            printing.validate_print_settings(td, "", "")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `DJANGO_SETTINGS_MODULE=tests.settings python -m django test parody_web.tests_printing.PrintSettingsTests -v 2`
Expected: FAIL — `ModuleNotFoundError: No module named 'parody_web.printing'`

- [ ] **Step 3a: Write the settings surface**

Create `parody_web/printing.py`:

```python
"""Per-section print PDFs, sliced on demand from the full-book PDF.

The print PDF is NOT part of the media tree: nginx serves that with no auth,
and some books gate sections behind preview/owner rules. It lives in its own
root and reaches readers only through a view that has asked the access policy
first.

Slices are cut on demand and cached. The cache path carries the source PDF's
sha256, so a rebuilt (repaginated) book writes to a fresh directory and a stale
slice can never be served — there is no cache to bust by hand.

`pypdf` is an optional extra (`parody-web[print]`). Without it every entry
point here reports "unavailable" and the site renders no PDF affordance at all,
rather than erroring.
"""

from pathlib import Path

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


def has_pypdf():
    try:
        import pypdf  # noqa: F401
    except ImportError:
        return False
    return True


def print_root():
    """Directory holding the full-book PDFs, or None when unconfigured."""
    root = getattr(settings, "PARODY_WEB_PRINT_ROOT", "")
    return Path(root) if root else None


def print_cache_root():
    """Where slices are cached; defaults to ``.cache`` inside the print root."""
    cache = getattr(settings, "PARODY_WEB_PRINT_CACHE", "")
    if cache:
        return Path(cache)
    root = print_root()
    return (root / ".cache") if root else None


def xaccel_prefix():
    """nginx internal location that maps to the print root, or ""."""
    return getattr(settings, "PARODY_WEB_PRINT_XACCEL", "") or ""


def validate_print_settings(root, cache, xaccel):
    """Raise ImproperlyConfigured on a print configuration that cannot work.

    Called at startup (apps.ready) so a typo fails on boot rather than at the
    first reader's download — the same posture as PARODY_WEB_THEME.
    """
    if not root:
        return
    root_path = Path(root)
    if not root_path.is_dir():
        raise ImproperlyConfigured(
            f"PARODY_WEB_PRINT_ROOT: {root!r} is not a directory")
    if xaccel:
        # X-Accel-Redirect maps one internal location at the print root, so
        # anything served through it must live beneath that root.
        cache_path = Path(cache) if cache else root_path / ".cache"
        try:
            cache_path.resolve().relative_to(root_path.resolve())
        except ValueError:
            raise ImproperlyConfigured(
                "PARODY_WEB_PRINT_CACHE must live under "
                "PARODY_WEB_PRINT_ROOT when PARODY_WEB_PRINT_XACCEL is set "
                f"({cache_path} is outside {root_path})")
```

- [ ] **Step 3b: Validate at startup**

In `parody_web/apps.py`, inside `ready()`, add:

```python
        from .printing import validate_print_settings
        validate_print_settings(
            getattr(settings, "PARODY_WEB_PRINT_ROOT", ""),
            getattr(settings, "PARODY_WEB_PRINT_CACHE", ""),
            getattr(settings, "PARODY_WEB_PRINT_XACCEL", ""))
```

- [ ] **Step 3c: Declare the extra**

In `pyproject.toml`, after `dependencies`:

```toml
[project.optional-dependencies]
# Per-section print PDFs are sliced out of the full book PDF at request time.
# Optional so a deployment that serves no print PDFs keeps parody-web's
# single-dependency footprint.
print = ["pypdf>=4.0"]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python runtests.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add parody_web/printing.py parody_web/apps.py pyproject.toml parody_web/tests_printing.py
git commit -m "print: settings surface for the print root, cache, and X-Accel (task #583)"
```

---

### Task 3: Slicing and the hash-keyed cache

**Files:**
- Modify: `parody_web/printing.py`
- Test: `parody_web/tests_printing.py`

**Interfaces:**
- Consumes: Task 1's model fields, Task 2's settings helpers.
- Produces:
  - `book_pdf_path(book) -> Path | None` — the full PDF if it exists on disk
  - `section_pdf_path(book, section) -> Path | None` — cached slice, cut on miss
  - `slice_pdf(src, dest, start, end) -> None`

- [ ] **Step 1: Write the failing test**

```python
# append to parody_web/tests_printing.py

def make_pdf(path, pages):
    """A real multi-page PDF, each page stamped with its number."""
    from pypdf import PdfWriter
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=200, height=200)
    with open(path, "wb") as f:
        writer.write(f)
    return path


class SlicingTests(TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        make_pdf(self.root / "print-book.pdf", 20)

    def _book(self):
        return import_artifact()

    def test_book_pdf_path_finds_the_file(self):
        with override_settings(PARODY_WEB_PRINT_ROOT=str(self.root)):
            self.assertEqual(printing.book_pdf_path(self._book()),
                             self.root / "print-book.pdf")

    def test_book_pdf_path_is_none_when_the_file_is_absent(self):
        (self.root / "print-book.pdf").unlink()
        with override_settings(PARODY_WEB_PRINT_ROOT=str(self.root)):
            self.assertIsNone(printing.book_pdf_path(self._book()))

    def test_slice_has_exactly_the_inclusive_page_count(self):
        from pypdf import PdfReader
        book = self._book()
        with override_settings(PARODY_WEB_PRINT_ROOT=str(self.root)):
            out = printing.section_pdf_path(book, book.sections.get(slug="alpha"))
        # [5, 9] inclusive = 5 pages
        self.assertEqual(len(PdfReader(str(out)).pages), 5)

    def test_the_cache_path_carries_the_source_hash(self):
        book = self._book()
        with override_settings(PARODY_WEB_PRINT_ROOT=str(self.root)):
            out = printing.section_pdf_path(book, book.sections.get(slug="alpha"))
        self.assertIn(book.print_sha256[:12], str(out))

    def test_a_repaginated_book_gets_a_fresh_cache_path(self):
        book = self._book()
        with override_settings(PARODY_WEB_PRINT_ROOT=str(self.root)):
            first = printing.section_pdf_path(
                book, book.sections.get(slug="alpha"))
            Book.objects.filter(pk=book.pk).update(print_sha256="d" * 64)
            book.refresh_from_db()
            second = printing.section_pdf_path(
                book, book.sections.get(slug="alpha"))
        self.assertNotEqual(first, second)

    def test_a_second_request_reuses_the_cached_slice(self):
        book = self._book()
        section = book.sections.get(slug="alpha")
        with override_settings(PARODY_WEB_PRINT_ROOT=str(self.root)):
            first = printing.section_pdf_path(book, section)
            stamp = first.stat().st_mtime_ns
            second = printing.section_pdf_path(book, section)
        self.assertEqual(first, second)
        self.assertEqual(stamp, second.stat().st_mtime_ns)

    def test_a_section_with_no_range_has_no_slice(self):
        book = self._book()
        with override_settings(PARODY_WEB_PRINT_ROOT=str(self.root)):
            self.assertIsNone(printing.section_pdf_path(
                book, book.sections.get(slug="beta")))

    def test_a_range_past_the_end_of_the_pdf_is_clamped(self):
        from pypdf import PdfReader
        book = self._book()
        section = book.sections.get(slug="alpha")
        Section.objects.filter(pk=section.pk).update(print_pages=[19, 40])
        section.refresh_from_db()
        with override_settings(PARODY_WEB_PRINT_ROOT=str(self.root)):
            out = printing.section_pdf_path(book, section)
        self.assertEqual(len(PdfReader(str(out)).pages), 2)  # pages 19-20

    def test_no_print_root_means_no_slice(self):
        book = self._book()
        with override_settings(PARODY_WEB_PRINT_ROOT=""):
            self.assertIsNone(printing.section_pdf_path(
                book, book.sections.get(slug="alpha")))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `DJANGO_SETTINGS_MODULE=tests.settings python -m django test parody_web.tests_printing.SlicingTests -v 2`
Expected: FAIL — `AttributeError: module 'parody_web.printing' has no attribute 'book_pdf_path'`

- [ ] **Step 3: Write minimal implementation**

Append to `parody_web/printing.py` (add `import os` and
`from functools import lru_cache` at the top):

```python
@lru_cache(maxsize=4)
def _reader(path_str, token):
    """Parsed PdfReader, cached per (file, token).

    pypdf holds the whole document, so a cold-cache crawl over a 500-page
    illustrated book would otherwise re-parse tens of MB per section. `token`
    is the file's mtime, so a rebuilt book invalidates the entry rather than
    being served from a reader for the previous PDF.
    """
    from pypdf import PdfReader

    return PdfReader(path_str)


def book_pdf_path(book):
    """The full-book PDF on disk, or None when unavailable."""
    root = print_root()
    if not root or not book.print_pdf or not has_pypdf():
        return None
    # basename only: the artifact must never be able to escape the print root
    path = root / Path(book.print_pdf).name
    return path if path.is_file() else None


def slice_pdf(src, dest, start, end):
    """Write pages [start, end] (1-based, inclusive) of `src` to `dest`.

    Written to a temp file and renamed, so a concurrent request can never read
    a half-written PDF.
    """
    from pypdf import PdfWriter

    reader = _reader(str(src), src.stat().st_mtime_ns)  # mtime = cache token
    total = len(reader.pages)
    first = max(1, start)
    last = min(end, total)
    writer = PdfWriter()
    for i in range(first - 1, last):
        writer.add_page(reader.pages[i])
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(f"{dest.name}.{os.getpid()}.tmp")
    with open(tmp, "wb") as f:
        writer.write(f)
    os.replace(tmp, dest)


def section_pdf_path(book, section):
    """Path to this section's PDF, slicing and caching it on first request.

    None when anything the slice needs is missing — no pypdf, no print root, no
    PDF on disk, no page range. Callers render no affordance in that case.
    """
    if not section.print_pages or len(section.print_pages) != 2:
        return None
    src = book_pdf_path(book)
    if src is None:
        return None
    cache = print_cache_root()
    if cache is None:
        return None
    start, end = section.print_pages
    dest = (cache / book.slug / (book.edition_id or "_")
            / (book.print_sha256[:12] or "nohash")
            / f"{section.chapter.slug}-{section.slug}.pdf")
    if not dest.is_file():
        slice_pdf(src, dest, start, end)
    return dest
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pip install "pypdf>=4.0" && python runtests.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add parody_web/printing.py parody_web/tests_printing.py
git commit -m "print: slice section PDFs on demand into a hash-keyed cache (task #583)"
```

---

### Task 4: Access-policy hooks

**Files:**
- Modify: `parody_web/access.py`
- Test: `parody_web/tests_printing.py`

**Interfaces:**
- Produces on `DefaultPolicy`:
  - `can_download_section_pdf(request, section) -> bool`
  - `can_download_book_pdf(request, book) -> bool`

- [ ] **Step 1: Write the failing test**

```python
# append to parody_web/tests_printing.py

from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory

from parody_web.access import DefaultPolicy


class PdfPolicyTests(TestCase):
    def setUp(self):
        self.rf = RequestFactory()
        self.policy = DefaultPolicy()
        self.book = import_artifact()

    def _anon(self):
        req = self.rf.get("/")
        req.user = AnonymousUser()
        return req

    def _owner(self):
        from django.contrib.auth import get_user_model
        req = self.rf.get("/")
        req.user = get_user_model()(username="owner")
        req.user.is_authenticated = True
        return req

    def test_a_full_sections_pdf_is_public(self):
        section = self.book.sections.get(slug="alpha")
        self.assertTrue(
            self.policy.can_download_section_pdf(self._anon(), section))

    def test_a_preview_sections_pdf_is_owner_only(self):
        section = self.book.sections.get(slug="alpha")
        Section.objects.filter(pk=section.pk).update(preview=True)
        section.refresh_from_db()
        self.assertFalse(
            self.policy.can_download_section_pdf(self._anon(), section))
        self.assertTrue(
            self.policy.can_download_section_pdf(self._owner(), section))

    def test_the_full_book_pdf_is_public_by_default(self):
        self.assertTrue(
            self.policy.can_download_book_pdf(self._anon(), self.book))

    def test_the_full_book_pdf_can_be_turned_off_for_a_site(self):
        with override_settings(PARODY_WEB_PUBLIC_BOOK_PDF=False):
            self.assertFalse(
                self.policy.can_download_book_pdf(self._anon(), self.book))
            # the owner always keeps it
            self.assertTrue(
                self.policy.can_download_book_pdf(self._owner(), self.book))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `DJANGO_SETTINGS_MODULE=tests.settings python -m django test parody_web.tests_printing.PdfPolicyTests -v 2`
Expected: FAIL — `AttributeError: 'DefaultPolicy' object has no attribute 'can_download_section_pdf'`

- [ ] **Step 3: Write minimal implementation**

Add to `DefaultPolicy` in `parody_web/access.py`:

```python
    def can_download_section_pdf(self, request, section):
        """May this reader download this section's print PDF?

        Defaults to exactly what the page itself shows: a preview section's PDF
        is owner-only, because the page is. A course host that gates sections
        differently overrides this alongside can_view_section.
        """
        if not self.can_view_section(request, section):
            return False
        return not self.section_is_preview(request, section)

    def can_download_book_pdf(self, request, book):
        """May this reader download the whole book as one PDF?

        Public by default. A site whose book is not wholly public sets
        PARODY_WEB_PUBLIC_BOOK_PDF = False, which leaves it to the owner. Note
        the direction of the default: a gated book that forgets the setting
        serves its full text, so apps.py warns about exactly that at startup.
        """
        from django.conf import settings

        if self.is_owner(request):
            return True
        return bool(getattr(settings, "PARODY_WEB_PUBLIC_BOOK_PDF", True))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python runtests.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add parody_web/access.py parody_web/tests_printing.py
git commit -m "print: access-policy hooks for section and full-book PDFs (task #583)"
```

---

### Task 5: Download routes

**Files:**
- Modify: `parody_web/views.py`, `parody_web/urls.py`
- Test: `parody_web/tests_printing.py`

**Interfaces:**
- Consumes: Tasks 3 and 4.
- Produces: named routes `parody_web:section_pdf` (`<ch>/<sec>/pdf/`) and `parody_web:book_pdf` (`pdf/`); helper `_pdf_response(path, download_name)`.

`pdf/` is a reserved first segment and must be registered **before** the bare
`<slug:chapter_slug>/` pattern, exactly as `systems/`, `index/`, and `search/`
already are. `<ch>/<sec>/pdf/` must precede the bare section pattern.

- [ ] **Step 1: Write the failing test**

```python
# append to parody_web/tests_printing.py

from django.test import Client


class PdfViewTests(TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        make_pdf(self.root / "print-book.pdf", 20)
        self.book = import_artifact()
        self.client = Client()

    def _login(self):
        from django.contrib.auth import get_user_model
        get_user_model().objects.create_user("owner", password="pw")
        self.client.login(username="owner", password="pw")

    def test_section_pdf_downloads_with_the_right_page_count(self):
        from pypdf import PdfReader
        import io
        with override_settings(PARODY_WEB_PRINT_ROOT=str(self.root)):
            resp = self.client.get("/one/alpha/pdf/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "application/pdf")
        body = b"".join(resp.streaming_content) if resp.streaming \
            else resp.content
        self.assertEqual(len(PdfReader(io.BytesIO(body)).pages), 5)

    def test_the_filename_names_the_section(self):
        with override_settings(PARODY_WEB_PRINT_ROOT=str(self.root)):
            resp = self.client.get("/one/alpha/pdf/")
        self.assertIn("alpha", resp["Content-Disposition"].lower())
        self.assertIn(".pdf", resp["Content-Disposition"])

    def test_a_preview_sections_pdf_is_refused_to_the_public(self):
        # THE leak this whole design exists to prevent: the print PDF holds the
        # full text of a section the online artifact deliberately withholds.
        Section.objects.filter(book=self.book, slug="alpha").update(preview=True)
        with override_settings(PARODY_WEB_PRINT_ROOT=str(self.root)):
            resp = self.client.get("/one/alpha/pdf/")
        self.assertEqual(resp.status_code, 404)

    def test_the_owner_still_gets_a_preview_sections_pdf(self):
        Section.objects.filter(book=self.book, slug="alpha").update(preview=True)
        self._login()
        with override_settings(PARODY_WEB_PRINT_ROOT=str(self.root)):
            resp = self.client.get("/one/alpha/pdf/")
        self.assertEqual(resp.status_code, 200)

    def test_a_section_with_no_range_has_no_pdf(self):
        with override_settings(PARODY_WEB_PRINT_ROOT=str(self.root)):
            self.assertEqual(self.client.get("/one/beta/pdf/").status_code, 404)

    def test_full_book_pdf_is_served_by_default(self):
        with override_settings(PARODY_WEB_PRINT_ROOT=str(self.root)):
            resp = self.client.get("/pdf/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "application/pdf")

    def test_full_book_pdf_can_be_withheld_from_the_public(self):
        with override_settings(PARODY_WEB_PRINT_ROOT=str(self.root),
                               PARODY_WEB_PUBLIC_BOOK_PDF=False):
            self.assertEqual(self.client.get("/pdf/").status_code, 404)
            self._login()
            self.assertEqual(self.client.get("/pdf/").status_code, 200)

    def test_a_missing_file_on_disk_is_a_404_not_a_500(self):
        (self.root / "print-book.pdf").unlink()
        with override_settings(PARODY_WEB_PRINT_ROOT=str(self.root)):
            self.assertEqual(self.client.get("/one/alpha/pdf/").status_code, 404)
            self.assertEqual(self.client.get("/pdf/").status_code, 404)

    def test_no_print_root_is_a_404_not_a_500(self):
        with override_settings(PARODY_WEB_PRINT_ROOT=""):
            self.assertEqual(self.client.get("/one/alpha/pdf/").status_code, 404)

    def test_xaccel_delegates_streaming_to_nginx(self):
        with override_settings(PARODY_WEB_PRINT_ROOT=str(self.root),
                               PARODY_WEB_PRINT_XACCEL="/print-internal/"):
            resp = self.client.get("/one/alpha/pdf/")
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp["X-Accel-Redirect"].startswith("/print-internal/"))
        self.assertEqual(resp.content, b"")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `DJANGO_SETTINGS_MODULE=tests.settings python -m django test parody_web.tests_printing.PdfViewTests -v 2`
Expected: FAIL — 404 on every route (the URLs do not exist yet)

- [ ] **Step 3a: Add the views**

In `parody_web/views.py`, add (near `solution_detail`):

```python
def _pdf_response(path, download_name):
    """Stream a PDF, delegating to nginx when X-Accel is configured.

    With PARODY_WEB_PRINT_XACCEL set, nginx serves the bytes from its internal
    location and Django's worker is free immediately; without it, FileResponse
    streams from the process, which is fine for dev and small deployments.
    """
    from django.conf import settings
    from django.http import FileResponse, HttpResponse

    from .printing import print_root, xaccel_prefix

    prefix = xaccel_prefix()
    if prefix:
        rel = Path(path).resolve().relative_to(Path(print_root()).resolve())
        resp = HttpResponse(content_type="application/pdf")
        resp["X-Accel-Redirect"] = f"{prefix.rstrip('/')}/{rel}"
    else:
        resp = FileResponse(open(path, "rb"), content_type="application/pdf")
    resp["Content-Disposition"] = f'attachment; filename="{download_name}"'
    return resp


def _pdf_filename(book, section=None):
    from django.utils.text import slugify

    stem = slugify(book.title) or book.slug
    if section is None:
        return f"{stem}.pdf"
    parts = [stem]
    if section.number:
        parts.append(slugify(section.number))
    parts.append(slugify(section.title) or section.slug)
    return "-".join(p for p in parts if p) + ".pdf"


def section_pdf(request, chapter_slug, section_slug):
    """This section's pages, cut out of the full print PDF.

    404 covers every unavailable case — no page range, no PDF on disk, no
    pypdf, or refused by the policy. A refusal must not distinguish itself from
    an absence, or it would confirm that gated content exists.
    """
    from .printing import section_pdf_path

    book, _ = _resolve_book(request)
    section = get_object_or_404(
        Section, book=book, chapter__slug=chapter_slug, slug=section_slug)
    if not get_policy().can_download_section_pdf(request, section):
        raise Http404("no pdf for this section")
    path = section_pdf_path(book, section)
    if path is None:
        raise Http404("no pdf for this section")
    return _pdf_response(path, _pdf_filename(book, section))


def book_pdf(request):
    """The whole book as one PDF."""
    from .printing import book_pdf_path

    book, _ = _resolve_book(request)
    if not get_policy().can_download_book_pdf(request, book):
        raise Http404("no pdf for this book")
    path = book_pdf_path(book)
    if path is None:
        raise Http404("no pdf for this book")
    return _pdf_response(path, _pdf_filename(book))
```

Add `from pathlib import Path` to the module imports if absent.

- [ ] **Step 3b: Register the routes**

In `parody_web/urls.py`, add `pdf/` beside the other reserved segments (after
the `search/` line):

```python
    # /pdf/ — the whole book as one PDF (reserved segment, like "search").
    path("pdf/", views.book_pdf, name="book_pdf"),
```

and the per-section route **before** the bare section pattern, beside the
`solutions/` route:

```python
    path("<slug:chapter_slug>/<slug:section_slug>/pdf/", views.section_pdf,
         name="section_pdf"),
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python runtests.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add parody_web/views.py parody_web/urls.py parody_web/tests_printing.py
git commit -m "print: gated download routes for section and full-book PDFs (task #583)"
```

---

### Task 6: The full-window PDF view

**Files:**
- Create: `parody_web/templates/parody_web/pdf_view.html`
- Modify: `parody_web/views.py`, `parody_web/urls.py`, `pyproject.toml`
- Test: `parody_web/tests_printing.py`

**Interfaces:**
- Produces: route `parody_web:section_pdf_view` (`<ch>/<sec>/pdf/view/`).

The overlay div is deliberately empty. It is the seam a future annotation layer
adopts, mirroring how `_section_overlay.html` already works — do not build
annotation here.

- [ ] **Step 1: Write the failing test**

```python
# append to parody_web/tests_printing.py

class PdfViewerTests(TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        make_pdf(self.root / "print-book.pdf", 20)
        self.book = import_artifact()
        self.client = Client()

    def test_the_viewer_renders_and_points_at_the_section_pdf(self):
        with override_settings(PARODY_WEB_PRINT_ROOT=str(self.root)):
            resp = self.client.get("/one/alpha/pdf/view/")
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode()
        self.assertIn("/one/alpha/pdf/", html)
        self.assertIn("Alpha", html)

    def test_the_viewer_exposes_the_annotation_seam(self):
        with override_settings(PARODY_WEB_PRINT_ROOT=str(self.root)):
            html = self.client.get("/one/alpha/pdf/view/").content.decode()
        # the empty overlay a future annotation layer adopts, keyed the way
        # hosts already key their per-section records
        self.assertIn('class="pdf-annotation-layer"', html)
        self.assertIn('data-section-key="one/alpha"', html)

    def test_the_viewer_offers_a_way_back_to_the_section(self):
        with override_settings(PARODY_WEB_PRINT_ROOT=str(self.root)):
            html = self.client.get("/one/alpha/pdf/view/").content.decode()
        self.assertIn('href="/one/alpha/"', html)

    def test_a_refused_section_has_no_viewer(self):
        Section.objects.filter(book=self.book, slug="alpha").update(preview=True)
        with override_settings(PARODY_WEB_PRINT_ROOT=str(self.root)):
            resp = self.client.get("/one/alpha/pdf/view/")
        self.assertEqual(resp.status_code, 404)

    def test_a_section_with_no_pdf_has_no_viewer(self):
        with override_settings(PARODY_WEB_PRINT_ROOT=str(self.root)):
            self.assertEqual(
                self.client.get("/one/beta/pdf/view/").status_code, 404)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `DJANGO_SETTINGS_MODULE=tests.settings python -m django test parody_web.tests_printing.PdfViewerTests -v 2`
Expected: FAIL — 404 (route missing)

- [ ] **Step 3a: Add the view and route**

In `parody_web/views.py`:

```python
def section_pdf_view(request, chapter_slug, section_slug):
    """Full-window PDF reader for one section.

    Deliberately chrome-free: no masthead, sidebar, or rail. The PDF sits in a
    positioned container with an empty overlay sibling — the seam a future
    annotation layer adopts (see _section_overlay.html for the same pattern).
    """
    from .printing import section_pdf_path

    book, editions = _resolve_book(request)
    section = get_object_or_404(
        Section, book=book, chapter__slug=chapter_slug, slug=section_slug)
    if not get_policy().can_download_section_pdf(request, section):
        raise Http404("no pdf for this section")
    if section_pdf_path(book, section) is None:
        raise Http404("no pdf for this section")
    return render(request, "parody_web/pdf_view.html", {
        "book": book, "editions": editions,
        "section": section, "chapter": section.chapter,
        "canonical_url": request.build_absolute_uri(request.path),
    })
```

In `parody_web/urls.py`, **before** the section-pdf route (longer path first):

```python
    path("<slug:chapter_slug>/<slug:section_slug>/pdf/view/",
         views.section_pdf_view, name="section_pdf_view"),
```

- [ ] **Step 3b: Add the template**

Create `parody_web/templates/parody_web/pdf_view.html`:

```html
{% load parody_web %}<title>{{ section.title|cut:"`" }} (PDF) — {{ book.title }}</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex">
<style>
  .pdf-shell { position: fixed; inset: 0; display: flex; flex-direction: column;
               background: var(--surface, #fff); color: var(--ink, #111); }
  .pdf-bar { display: flex; align-items: center; gap: 1rem; flex: none;
             padding: .5rem .9rem; border-bottom: 1px solid var(--rule, #ddd);
             font: 500 .9rem/1.2 var(--ui-font, system-ui, sans-serif); }
  .pdf-bar .pdf-title { font-weight: 600; }
  .pdf-bar .pdf-spacer { margin-left: auto; }
  .pdf-bar a { color: inherit; text-decoration: none; opacity: .8; }
  .pdf-bar a:hover, .pdf-bar a:focus-visible { opacity: 1; text-decoration: underline; }
  /* The PDF and its (currently empty) annotation layer share this stacking
     context, so a future layer can sit exactly over the page. */
  .pdf-stage { position: relative; flex: 1 1 auto; min-height: 0; }
  .pdf-stage > iframe { position: absolute; inset: 0; width: 100%; height: 100%; border: 0; }
  .pdf-annotation-layer { position: absolute; inset: 0; pointer-events: none; }
</style>
<div class="pdf-shell">
  <nav class="pdf-bar">
    <span class="pdf-title">{% if section.number %}{{ section.number }} {% endif %}{{ section.title|cut:"`" }}</span>
    <span>{{ book.title }}</span>
    <span class="pdf-spacer"></span>
    <a href="{% section_url book chapter.slug section.slug %}">← Back to the section</a>
    <a href="{% url 'parody_web:section_pdf' chapter.slug section.slug %}">Download</a>
  </nav>
  <div class="pdf-stage">
    <iframe title="{{ section.title|cut:'`' }} (PDF)"
            src="{% url 'parody_web:section_pdf' chapter.slug section.slug %}#view=FitH"></iframe>
    {% comment %}
    Annotation seam. Ships empty and inert; a host project that adds drawing
    keys its records to this data-section-key (the same Section.key hosts
    already use). See docs/host-integration.md.
    {% endcomment %}
    <div class="pdf-annotation-layer" data-section-key="{{ section.key }}"></div>
  </div>
</div>
```

- [ ] **Step 3c: Ship the template in the wheel**

`pyproject.toml`'s `package-data` already globs
`templates/parody_web/*.html`, so this template is covered. **Confirm** it —
a template outside that glob would be silently omitted from the wheel:

```bash
grep -n 'templates/parody_web/\*.html' pyproject.toml
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python runtests.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add parody_web/views.py parody_web/urls.py parody_web/templates/parody_web/pdf_view.html parody_web/tests_printing.py
git commit -m "print: full-window PDF view with an empty annotation seam (task #583)"
```

---

### Task 7: The sticky utility rail and the home-page link

**Files:**
- Create: `parody_web/templates/parody_web/_section_rail.html`
- Modify: `parody_web/templates/parody_web/section.html`, `parody_web/templates/parody_web/chapter.html`, `parody_web/templates/parody_web/index.html`, `parody_web/views.py`, `parody_web/static/parody_web/css/book.css`
- Test: `parody_web/tests_printing.py`

**Interfaces:**
- Consumes: Tasks 3–6.
- Produces: `section_detail` and `chapter_detail` context keys `section_pdf_url`, `section_pdf_view_url`, `section_pdf_pages`, `book_pdf_url`; `index` context key `book_pdf_url`.

The rail is a generic list so the coming video embed is one more `<li>` and
nothing else moves. Ship it with a single tenant.

**The chapter page matters here.** The chapter title + lead-in prose is one of
the PDF units (the build side marks it at the chapter opening), but the lead-in
is *not* browsed at `/<ch>/lead-in/` — `chapter_detail` renders it on the
chapter landing page and drops it from the contents list. So the chapter page
needs the rail too, pointed at the lead-in section, or that unit's PDF has no
affordance anywhere on the site.

- [ ] **Step 1: Write the failing test**

```python
# append to parody_web/tests_printing.py

class SectionRailTests(TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        make_pdf(self.root / "print-book.pdf", 20)
        self.book = import_artifact()
        self.client = Client()

    def test_the_rail_offers_the_section_pdf(self):
        with override_settings(PARODY_WEB_PRINT_ROOT=str(self.root)):
            html = self.client.get("/one/alpha/").content.decode()
        self.assertIn('class="util-rail"', html)
        self.assertIn('data-util="pdf"', html)
        self.assertIn("/one/alpha/pdf/", html)
        self.assertIn("/one/alpha/pdf/view/", html)

    def test_the_rail_states_the_page_count(self):
        with override_settings(PARODY_WEB_PRINT_ROOT=str(self.root)):
            html = self.client.get("/one/alpha/").content.decode()
        self.assertIn("5 pages", html)

    def test_the_rail_is_absent_when_the_section_has_no_pdf(self):
        with override_settings(PARODY_WEB_PRINT_ROOT=str(self.root)):
            html = self.client.get("/one/beta/").content.decode()
        self.assertNotIn('class="util-rail"', html)

    def test_the_rail_is_absent_without_a_print_root(self):
        with override_settings(PARODY_WEB_PRINT_ROOT=""):
            html = self.client.get("/one/alpha/").content.decode()
        self.assertNotIn('class="util-rail"', html)

    def test_a_preview_section_offers_the_public_no_pdf(self):
        Section.objects.filter(book=self.book, slug="alpha").update(preview=True)
        with override_settings(PARODY_WEB_PRINT_ROOT=str(self.root)):
            html = self.client.get("/one/alpha/").content.decode()
        self.assertNotIn("/one/alpha/pdf/", html)

    def test_the_rail_works_without_javascript(self):
        # the trigger is a real link to the viewer, progressively enhanced
        with override_settings(PARODY_WEB_PRINT_ROOT=str(self.root)):
            html = self.client.get("/one/alpha/").content.decode()
        self.assertIn('<a class="util-rail-trigger"', html)

    def test_the_chapter_page_offers_the_lead_in_pdf(self):
        # The lead-in is the chapter title + intro prose unit. It is rendered
        # on the chapter landing page, not at /one/lead-in/, so this is the
        # only place its PDF can be offered.
        with override_settings(PARODY_WEB_PRINT_ROOT=str(self.root)):
            html = self.client.get("/one/").content.decode()
        self.assertIn('class="util-rail"', html)
        self.assertIn("/one/lead-in/pdf/", html)
        self.assertIn("3 pages", html)  # [3, 5] inclusive

    def test_a_chapter_with_no_lead_in_has_no_rail(self):
        Section.objects.filter(book=self.book, slug="lead-in").delete()
        with override_settings(PARODY_WEB_PRINT_ROOT=str(self.root)):
            html = self.client.get("/one/").content.decode()
        self.assertNotIn('class="util-rail"', html)

    def test_the_home_page_offers_the_full_book(self):
        with override_settings(PARODY_WEB_PRINT_ROOT=str(self.root)):
            html = self.client.get("/").content.decode()
        self.assertIn('href="/pdf/"', html)

    def test_the_home_page_hides_a_withheld_full_book(self):
        with override_settings(PARODY_WEB_PRINT_ROOT=str(self.root),
                               PARODY_WEB_PUBLIC_BOOK_PDF=False):
            html = self.client.get("/").content.decode()
        self.assertNotIn('href="/pdf/"', html)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `DJANGO_SETTINGS_MODULE=tests.settings python -m django test parody_web.tests_printing.SectionRailTests -v 2`
Expected: FAIL — `util-rail` not in the response

- [ ] **Step 3a: Supply the context**

In `parody_web/views.py`, add a helper near `_pdf_filename`:

```python
def _print_context(request, book, section=None):
    """PDF links for the chrome, empty when there is nothing to offer.

    Everything here is computed from what the reader may actually have, so a
    template can render the affordance unconditionally on truthiness.
    """
    from .printing import book_pdf_path, section_pdf_path

    policy = get_policy()
    ctx = {"section_pdf_url": "", "section_pdf_view_url": "",
           "section_pdf_pages": None, "book_pdf_url": ""}
    if book_pdf_path(book) and policy.can_download_book_pdf(request, book):
        ctx["book_pdf_url"] = reverse("parody_web:book_pdf")
    if section is not None and policy.can_download_section_pdf(request, section) \
            and section_pdf_path(book, section) is not None:
        ctx["section_pdf_url"] = reverse(
            "parody_web:section_pdf", args=[section.chapter.slug, section.slug])
        ctx["section_pdf_view_url"] = reverse(
            "parody_web:section_pdf_view",
            args=[section.chapter.slug, section.slug])
        ctx["section_pdf_pages"] = section.print_page_count
    return ctx
```

Add `from django.urls import reverse` to the imports if absent.

In `section_detail`, merge it into the render context:

```python
    context = {
        ... existing keys ...
    }
    context.update(_print_context(request, book, section))
    return render(request, "parody_web/section.html", context)
```

In `chapter_detail`, merge `_print_context(request, book, leadin)` in the same
way — `leadin` is already computed there. The helper tolerates `leadin` being
`None` (a chapter with no lead-in), returning empty URLs so the rail does not
render.

In `index`, merge `_print_context(request, book)` into its context the same way.

- [ ] **Step 3b: Add the rail template**

Create `parody_web/templates/parody_web/_section_rail.html`:

```html
{% comment %}
Sticky utility rail: one entry per per-section utility, upper right.

Ships with a single tenant (the print PDF). A coming video embed is one more
<li data-util="video"> and nothing else moves — that is the point of the
structure. Host-shadowable like _section_toolbar.html / _section_overlay.html.

Progressive enhancement: the trigger is a real link to the full-window viewer,
so the PDF is reachable with JavaScript off. Script (if any) upgrades it to a
popover.
{% endcomment %}
{% if section_pdf_url %}
<ul class="util-rail" aria-label="Section tools">
  <li class="util-rail-item" data-util="pdf">
    <a class="util-rail-trigger" href="{{ section_pdf_view_url }}"
       aria-label="Read this section as a PDF">
      <svg viewBox="0 0 16 16" width="18" height="18" aria-hidden="true" focusable="false">
        <path fill="currentColor" d="M4 1h5l3 3v11H4V1zm5 1v2h2L9 2z"/>
        <path fill="currentColor" d="M5.6 12.6V9h1.6a1.2 1.2 0 0 1 0 2.4h-.7v1.2h-.9zm.9-1.9h.6a.45.45 0 0 0 0-.9h-.6v.9z"/>
      </svg>
    </a>
    <div class="util-rail-card">
      <p class="util-rail-cap">Print version</p>
      <a href="{{ section_pdf_view_url }}">Read as PDF</a>
      <a href="{{ section_pdf_url }}">Download this section{% if section_pdf_pages %}
        <span class="util-rail-note">{{ section_pdf_pages }} page{{ section_pdf_pages|pluralize }}</span>{% endif %}</a>
      {% if book_pdf_url %}<a href="{{ book_pdf_url }}">Download the full book</a>{% endif %}
    </div>
  </li>
</ul>
{% endif %}
```

- [ ] **Step 3c: Render it, and link the full book from the home page**

In `section.html`, immediately after the `_section_toolbar.html` include:

```html
{% include "parody_web/_section_rail.html" %}
```

In `chapter.html`, add the same include just before the lead-in prose is
rendered, so the chapter title + lead-in unit's PDF is reachable:

```html
{% include "parody_web/_section_rail.html" %}
```

In `index.html`, add near the book title/cover block:

```html
{% if book_pdf_url %}<p class="book-pdf-link"><a href="{{ book_pdf_url }}">Download the full book as a PDF</a></p>{% endif %}
```

- [ ] **Step 3d: Style it**

Append to `parody_web/static/parody_web/css/book.css` (tokens only — no
hardcoded colours, so dark mode follows for free):

```css
/* Sticky utility rail -------------------------------------------------- */
/* One entry per per-section utility, upper right. Sits above the "On this
   page" rail in the same column; on narrow screens it floats over the content
   instead, where there is no column to share. */
.util-rail {
  position: sticky;
  top: 1rem;
  z-index: 5;
  float: right;
  margin: 0 0 .5rem 1rem;
  padding: 0;
  list-style: none;
}
.util-rail-item { position: relative; }
.util-rail-trigger {
  display: grid;
  place-items: center;
  width: 2.2rem;
  height: 2.2rem;
  border: 1px solid var(--rule);
  border-radius: 50%;
  background: var(--surface);
  color: var(--ink-muted, var(--ink));
  opacity: .65;
  transition: opacity .15s ease, color .15s ease;
}
.util-rail-trigger:hover,
.util-rail-trigger:focus-visible { opacity: 1; color: var(--accent, var(--ink)); }

.util-rail-card {
  position: absolute;
  top: calc(100% + .4rem);
  right: 0;
  min-width: 14rem;
  display: none;
  flex-direction: column;
  gap: .35rem;
  padding: .7rem .8rem;
  border: 1px solid var(--rule);
  border-radius: .4rem;
  background: var(--surface);
  box-shadow: 0 6px 20px rgb(0 0 0 / 12%);
  font-size: .9rem;
}
.util-rail-item:hover .util-rail-card,
.util-rail-item:focus-within .util-rail-card { display: flex; }
.util-rail-cap {
  margin: 0 0 .15rem;
  font-size: .75rem;
  letter-spacing: .04em;
  text-transform: uppercase;
  color: var(--ink-muted, var(--ink));
}
.util-rail-note { display: block; font-size: .78rem; color: var(--ink-muted, var(--ink)); }

@media (max-width: 60rem) {
  .util-rail { position: fixed; top: auto; bottom: 1rem; right: 1rem; float: none; margin: 0; }
  .util-rail-card { top: auto; bottom: calc(100% + .4rem); }
}
@media print { .util-rail { display: none; } }
```

Confirm the token names against the top of `tokens.css` and substitute the
real ones if `--rule` / `--surface` / `--ink-muted` / `--accent` are spelled
differently there.

- [ ] **Step 4: Run test to verify it passes**

Run: `python runtests.py`
Expected: PASS

Then look at it: run the example site, open a section page, and check the rail
against the "On this page" rail at a wide width, at ~59rem, and on a phone
width — this is the one genuinely fiddly piece of visual work in the plan.

- [ ] **Step 5: Commit**

```bash
git add parody_web/templates/parody_web/_section_rail.html parody_web/templates/parody_web/section.html parody_web/templates/parody_web/chapter.html parody_web/templates/parody_web/index.html parody_web/views.py parody_web/static/parody_web/css/book.css parody_web/tests_printing.py
git commit -m "print: sticky utility rail offering the section PDF (task #583)"
```

---

### Task 8: Deploy wiring, the permissive-default warning, and docs

**Files:**
- Modify: `parody_web/apps.py`, `example_site/deploy/deploy.sh`, `example_site/deploy/site.env.example`, `example_site/deploy/nginx/parody-book-host.conf`, `example_site/booksite/settings.py`, `docs/host-integration.md`, `pyproject.toml`, `uv.lock`
- Test: `parody_web/tests_printing.py`

**Interfaces:**
- Produces: a startup warning when a gated book is served with a public full-book PDF.

- [ ] **Step 1: Write the failing test**

```python
# append to parody_web/tests_printing.py

class PublicBookPdfWarningTests(TestCase):
    def test_a_gated_book_with_a_public_full_pdf_warns(self):
        from parody_web.printing import public_book_pdf_warnings
        book = import_artifact()
        Section.objects.filter(book=book, slug="alpha").update(preview=True)
        with override_settings(PARODY_WEB_PUBLIC_BOOK_PDF=True):
            warnings = public_book_pdf_warnings()
        self.assertEqual(len(warnings), 1)
        self.assertIn("print-book", warnings[0])
        self.assertIn("PARODY_WEB_PUBLIC_BOOK_PDF", warnings[0])

    def test_a_fully_public_book_does_not_warn(self):
        import_artifact()
        with override_settings(PARODY_WEB_PUBLIC_BOOK_PDF=True):
            self.assertEqual(printing.public_book_pdf_warnings(), [])

    def test_no_warning_once_the_setting_is_off(self):
        book = import_artifact()
        Section.objects.filter(book=book, slug="alpha").update(preview=True)
        with override_settings(PARODY_WEB_PUBLIC_BOOK_PDF=False):
            self.assertEqual(printing.public_book_pdf_warnings(), [])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `DJANGO_SETTINGS_MODULE=tests.settings python -m django test parody_web.tests_printing.PublicBookPdfWarningTests -v 2`
Expected: FAIL — `ImportError: cannot import name 'public_book_pdf_warnings'`

- [ ] **Step 3a: Add the warning**

Append to `parody_web/printing.py`:

```python
def public_book_pdf_warnings():
    """Books whose full PDF is public while some of their sections are not.

    PARODY_WEB_PUBLIC_BOOK_PDF defaults to True, which is right for a wholly
    public book and wrong for a gated one — and the failure is silent, because
    serving the PDF looks like success. So say something: a gated book that has
    not turned the setting off is handing out the text its online artifact was
    built to withhold.
    """
    from django.conf import settings

    if not getattr(settings, "PARODY_WEB_PUBLIC_BOOK_PDF", True):
        return []
    from .models import Book

    messages = []
    for book in Book.objects.exclude(print_pdf="").prefetch_related("sections"):
        if any(s.preview for s in book.sections.all()):
            label = f"{book.slug}/{book.edition_id}" if book.edition_id \
                else book.slug
            messages.append(
                f"{label}: the full-book PDF is public "
                "(PARODY_WEB_PUBLIC_BOOK_PDF is True) but the book has "
                "preview-gated sections — the PDF hands out text the site "
                "withholds. Set PARODY_WEB_PUBLIC_BOOK_PDF = False.")
    return messages
```

Wire it into `apps.ready()`, after the validators — guarded, because `ready()`
runs before migrations exist on a fresh database:

```python
        import warnings as _warnings

        from django.db import DatabaseError

        from .printing import public_book_pdf_warnings
        try:
            for message in public_book_pdf_warnings():
                _warnings.warn(message, RuntimeWarning)
        except DatabaseError:
            pass  # no tables yet (migrate/collectstatic on a fresh install)
```

- [ ] **Step 3b: Wire the deploy**

In `example_site/deploy/site.env.example`, add:

```sh
PRINT_ASSET=print.zip                 # optional; omit if the book ships no print PDFs
BOOKSITE_PRINT_ROOT=/var/lib/parody-book-host/print
```

In `example_site/deploy/deploy.sh`, beside the media download, add:

```sh
  # Optional print PDFs (+ page maps). Served ONLY through parody-web's gated
  # /pdf/ views — never from the media tree, which nginx serves unauthenticated.
  if [ -n "${PRINT_ASSET:-}" ]; then
    install -d "${BOOKSITE_PRINT_ROOT:?set BOOKSITE_PRINT_ROOT for print PDFs}"
    gh release download "$TAG" -R "$CONTENT_REPO" -p "$PRINT_ASSET" \
      -O /tmp/print.zip --clobber && \
      unzip -oq /tmp/print.zip -d "${BOOKSITE_PRINT_ROOT}"
  fi
```

In `example_site/deploy/nginx/parody-book-host.conf`, add the internal
location:

```nginx
    # Print PDFs are NOT public: parody-web decides who may read one and then
    # hands the file to nginx with X-Accel-Redirect. `internal` makes a direct
    # request for this path impossible.
    location /print-internal/ {
        internal;
        alias /var/lib/parody-book-host/print/;
    }
```

In `example_site/booksite/settings.py`, add:

```python
PARODY_WEB_PRINT_ROOT = os.getenv("BOOKSITE_PRINT_ROOT", "")
PARODY_WEB_PRINT_XACCEL = os.getenv("BOOKSITE_PRINT_XACCEL", "")
# The full-book PDF is public by default. A book that gates any of its sections
# must set this False — see printing.public_book_pdf_warnings().
PARODY_WEB_PUBLIC_BOOK_PDF = (
    os.getenv("BOOKSITE_PUBLIC_BOOK_PDF", "1") == "1")
```

- [ ] **Step 3c: Document it**

Add a "Print PDFs" section to `docs/host-integration.md` covering: the four
settings, the `parody-web[print]` extra, the two policy hooks
(`can_download_section_pdf`, `can_download_book_pdf`), the `pdf_view.html`
annotation seam and its `data-section-key`, and the rule that
`PARODY_WEB_PRINT_ROOT` must never be inside `MEDIA_ROOT`.

- [ ] **Step 4: Run test to verify it passes**

Run: `python runtests.py`
Expected: PASS — whole suite

- [ ] **Step 5: Bump the version and commit**

Re-derive the version against `main` first (parallel sessions move it, and a
duplicate number merges without conflict and ships a broken release):

```bash
git fetch origin && git show origin/main:pyproject.toml | grep '^version'
```

Set the next minor above that, then:

```bash
uv lock
git add parody_web/printing.py parody_web/apps.py example_site/deploy/deploy.sh example_site/deploy/site.env.example example_site/deploy/nginx/parody-book-host.conf example_site/booksite/settings.py docs/host-integration.md parody_web/tests_printing.py pyproject.toml uv.lock
git commit -m "print: deploy wiring, gated-book warning, and host docs (task #583)"
```

---

## Verification

- [ ] `python runtests.py` — whole suite green, with and without `pypdf` installed (uninstall it and confirm the site renders with no PDF affordance and no errors).
- [ ] Import a real artifact built by `parody publish`, put its PDF in the print root, and confirm: a section downloads with the right pages; the page it opens on really is that section's first page; the viewer renders; the full-book link appears.
- [ ] Set `PARODY_WEB_PUBLIC_BOOK_PDF = False` and confirm `/pdf/` 404s for the public and serves for the owner.
- [ ] Visual pass on the rail at wide, ~59rem, and phone widths, in both light and dark themes.

## Deployment note

Shipping this to a live site is a cross-repo release chain — see the
`rtcbook-deploy-release-chain` and `electronics-ricopic-one-release-chain`
project memories for the exact steps and the PyPI propagation race. **rtcbook
must set `PARODY_WEB_PUBLIC_BOOK_PDF = False` in the same deploy that first
ships a print asset**, or its first deploy publishes the whole book.
