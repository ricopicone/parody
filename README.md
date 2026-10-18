# parody

*A play on **parity**: keeping the print and web versions of a work in parity.*

One authoring toolchain for books and course notebooks: pandoc markdown
(with executed jupytext code cells) in, multiple targets out —

- **JSON artifact** (schema-versioned; the contract consumed by
  [ricopic.one](https://ricopic.one)'s Django importer and other tools)
- **standalone HTML preview** (no server needed; resolves the artifact's
  site-template tags itself)
- **print-quality PDF** via LaTeX profiles (lualatex/latexmk; generic
  profile bundled, book-private profiles pluggable)

Parody unifies and replaces the toolchains of two ancestor systems: the
homepage-django notebooks pipeline and the rtc-book `meta-*` book machinery.
See [NEW_PROJECT_SEED_PLAN.md](NEW_PROJECT_SEED_PLAN.md) for the full plan.

## Install / develop

Requires Python ≥ 3.11 and [pandoc](https://pandoc.org) (pinned version in
`parody/toolchain.py`), or use the Dockerfile/devcontainer.

```sh
uv sync          # create venv + install
uv run parody --help
uv run pytest    # golden tests need the ancestor corpora; see tests/golden/
```

## CLI

```
parody init <dir>                          # scaffold a content repo (incl. CI workflow)
parody build <project_dir> <output.json> [--clozes blank|key|full]  # JSON artifact
parody preview <project_dir> -o preview    # static HTML site for review
parody watch <project_dir>                 # rebuild on save (pip install 'parody[watch]')
parody pdf <project_dir> [--solutions] [--clozes MODE] [--section ch/sec]  # print PDF (needs TeX)
parody check <artifact.json>               # validate artifact against schema
parody check --toolchain                   # verify pinned toolchain versions
parody translate [project_dir] [--status] [--lang zh,de] [--section ch/sec]  # translations
parody twin [project_dir] --lang de [--chapter ch] [--side-by-side sbs.pdf]  # twin pages
```

Content repos use `parody.yaml` + `chapters/<ch>/<sec>.md`; the legacy
System A layout (`__meta.yaml` + `chapter_*/`) builds bit-compatibly and
remains covered by golden tests.

## Translations

A book opts in with a `translations:` key in `parody.yaml`:

```yaml
translations:
  languages: [zh, ko, de, fr, es]   # Simplified Chinese, Korean, German, French, Spanish
  engine: claude-code               # default; or anthropic-api (pip install 'parody[translate-api]')
  model: claude-opus-5-5            # default
```

`parody translate` translates every published section (drafts never) into
`translations/<lang>/<chapter>/<section>.md`. You review the result and commit
it. Each section is cut into chunks filed under a hash of their English. A
re-run translates only the chunks whose English changed, and leaves every
other chunk byte for byte as it was. Every chunk must keep its maths, blanks,
key terms, references, ids and code exactly, or it is retried and, failing
that, not written. A box's `title="…"` is the one attribute that is
translated, since readers see it as the box's heading. `--status` reports what
is missing or stale without translating anything. To redo a chunk (after a
change to what the translator is told, say), delete it from the translation
file and re-run.

Key terms (`[…]{.keyword}`) get the English term attached (`en="…"`). Each
language keeps a glossary at `translations/<lang>/glossary.yaml`, which every
later translation follows. You can edit it by hand.

The `claude-code` engine runs Claude Code headless (`claude -p`) on your own
Claude login, so it uses your subscription's limits, not API billing. In `-p`
mode Claude Code bills the API whenever `ANTHROPIC_API_KEY` is set, so the
engine removes it and `ANTHROPIC_AUTH_TOKEN` from Claude Code's environment.
Log in with `claude` once before the first run.

## Twin pages

`parody twin --lang de` builds a translated *twin* of the print PDF. Twin page
N holds exactly what English page N holds, on the same page size with the
same page number, in a slightly smaller type. `--side-by-side` also writes
each English page and its twin on one landscape letter sheet. It needs TeX
and `pip install 'parody[twin]'`. Chinese and Korean need a CJK font
installed; Noto Serif CJK is preferred (it is not part of TeX Live).

How it works:

1. The English is built a second time with invisible marks before every
   sentence. They are LuaTeX attributes, which add nothing to the page. The
   build checks that this marked copy pages identically to the published PDF,
   and names any page where it does not.
2. Each sentence goes to the page holding most of its English lines.
3. Each twin page is set at the book's own size in a column wider by 1/s,
   then scaled by s until it fits. The language's base scale is the one 90% of
   pages fit at (about 9.6 pt for German and 11 pt for Chinese in the
   electronics book). A denser page squeezes further, without limit, and is
   reported.
4. Untranslated text is set in English with a marker. Translations that may
   lag the English are marked as such.

Where a translation's sentences do not line up one to one with the English,
the cut is made at the nearest position and reported as approximate.

A TeX error in the twin fails the build, unless the English build has the
same error: that one is the book's, already in the published PDF, and is
reported but not fatal. An error in the marked English on a line that
carries a mark fails the build too: a mark is somewhere it must not be.

A build that passes every check also writes `<twin>.twin.json` beside the
twin. It holds the twin's sha256, the sha256 of the English PDF it twins, and
each section's twin page range. A book site uses it to serve per-section twins
and to refuse a twin of an older English build.

## Fill-in-the-blank (cloze) content

`[answer]{.cloze}` hides text behind a blank sized to it; `[]{.blank size=lg}`
is an empty blank with nothing behind it (`sm`/`md`/`lg`/`xl` = 2/5/10/20 em, or
`width=4cm`). Block forms: `::: {.blank lines=6}` for work space, `::: {.cloze}`
for a hidden passage. Inside math, use the macros — a span cannot live inside
`$…$`: `$\tau = \cloze{RC}$`, `$y = \clozeblank{3em}$`. A figure can carry
incomplete artwork with `cloze="fig-blank.pdf"`, or by putting a
`<stem>-cloze.<ext>` sibling next to it.

Three build modes, set by `--clozes` (or `cloze: {default: …}` in
`parody.yaml`), independent of `--solutions`:

| mode | who it is for |
|---|---|
| `blank` (default) | student handout — answers replaced by rules at build time |
| `key` | instructor copy — answers shown, accented |
| `full` | publication — answers as ordinary text, blanks dropped entirely |

```
parody pdf . --clozes blank
parody build . artifact/book-full.json --clozes full
```

In `blank` mode the answer never reaches the browser or the PDF content stream —
it is removed at build time, not hidden with CSS. Print measures the real box
with `\settowidth`, so widths are exact; the web estimates from character count.
A cloze inside an exercise solution always renders `full`.
