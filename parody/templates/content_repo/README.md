# $title

Content repo built with [parody](https://pypi.org/project/parody/).

```sh
pip install "parody==$parody_version"

parody build . artifact/$slug.json   # JSON artifact
parody preview . -o preview          # static HTML to review your changes
parody watch .                       # rebuild on save
```

Layout: one chapter per directory under `chapters/`, one section per `.md`
file (pandoc markdown + YAML frontmatter), executed Python in jupytext
`.py` files included via ` ```{.include-py path="..."} `. See
`chapters/introduction/overview.md` for a worked example.

CI builds the artifact on every PR and attaches artifact + checksums to a
release on every `v*` tag (see `.github/workflows/build.yml`).
