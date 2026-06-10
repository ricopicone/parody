# Contributing to $title

You need Python ≥ 3.11. No LaTeX, no Django, no special setup:

```sh
git clone <this repo> && cd $slug
pip install "parody==$parody_version"
parody preview . -o preview && open preview/index.html
```

Edit `chapters/<chapter>/<section>.md`, run `parody watch .` for
rebuild-on-save, and open a PR. CI builds your branch and will catch
anything broken — you never need to install the production stack to
contribute content.

Notes:

- Sections are pandoc markdown with YAML frontmatter (`title`, `slug`, `id`).
- Executed code lives in jupytext `.py` files; `parody build` runs them and
  caches results, `parody watch`/`--no-execute` skip execution for speed.
- Exercise solutions go in `::: {.exercise-solution}` divs inside the
  exercise; they're extracted at build time and access-controlled at serve
  time, so keep them out of regular prose.
