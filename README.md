# parody

*A play on **parity**: keeping the print and web versions of a work in parity.*

One authoring toolchain for books and course notebooks: pandoc markdown
(with executed jupytext code cells) in, multiple targets out —

- **JSON artifact** (schema-versioned; the contract consumed by
  [ricopic.one](https://ricopic.one)'s Django importer and other tools)
- **standalone HTML preview** (planned, Phase 2)
- **print-quality PDF** via LaTeX profiles (planned, Phase 3)

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
parody build <notebook_dir> <output.json>   # build the JSON artifact
parody check <artifact.json>                # validate artifact against schema
```
