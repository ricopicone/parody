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
parody build <project_dir> <output.json>   # build the JSON artifact (executes code)
parody preview <project_dir> -o preview    # static HTML site for review
parody watch <project_dir>                 # rebuild on save (pip install 'parody[watch]')
parody pdf <project_dir> [--solutions] [--section ch/sec]   # print PDF (needs TeX)
parody check <artifact.json>               # validate artifact against schema
parody check --toolchain                   # verify pinned toolchain versions
```

Content repos use `parody.yaml` + `chapters/<ch>/<sec>.md`; the legacy
System A layout (`__meta.yaml` + `chapter_*/`) builds bit-compatibly and
remains covered by golden tests.
