# Reproducible print builds

`parody pdf` shells out to a LaTeX toolchain (lualatex + latexmk + biber +
minted/pygmentize + pandoc-crossref). The Python/pandoc side is pinned in
`pyproject.toml`/`uv.lock`, but **TeX itself lives on the host** — so print
output depends on whatever TeX Live is installed. `Dockerfile.print` closes that
gap with a pinned, containerized TeX Live, the way the old meta-book Docker
container did.

## What is and isn't pinned

| Layer | Pin |
| --- | --- |
| pandoc | `pypandoc-binary==1.15` → pandoc 3.6.1 (`parody/toolchain.py`) |
| pandoc-crossref | `0.3.18.1` (built against that pandoc) |
| pygments / segno / … | `uv.lock` |
| **TeX Live** | **`Dockerfile.print` only** — by image digest (see below) |

On the host, TeX Live is *not* pinned; the container is the reproducible path.

## The image

`Dockerfile.print` starts from `texlive/texlive:latest-full`, **frozen by
digest** to the current release (TL2026 — the engine the golden print output was
validated against), and layers the parody toolchain on top. Notes:

- **`scheme-full`** so every package the profiles pull is present (circuitikz,
  pgfgantt, biblatex-chicago, newpx, algpseudocodex, minted, tkz-euclide, …) —
  no per-package whack-a-mole. It is a large image (~5 GB); that is the cost of
  not guessing at a package subset.
- **`linux/amd64`** on purpose: matches CI runners and the old container, so the
  engine bytes are identical everywhere. On Apple Silicon it runs under
  emulation (slower) — keep using host TeX for fast iteration and the image for
  reproducible/reference builds and CI.
- `latest-full` is a *rolling* tag; the `@sha256:` digest is what actually
  freezes it. When islandoftex publishes `TL2026-historic` (after TL2027 ships),
  switch the `FROM` to that named tag and drop the digest.

## Build and run

```
docker build --platform linux/amd64 -f Dockerfile.print -t parody-print:tl2026 .
```

The book — content plus any book-private profile with its licensed fonts — is
mounted at runtime, so the image stays book-agnostic and publishable:

```
docker run --rm -v "$PWD":/book -w /book parody-print:tl2026 pdf . --profile memoir -o print.pdf
```

For the book-private MIT profile, mount the book and point `--profile` at its
profile directory:

```
docker run --rm -v "$PWD":/book -w /book parody-print:tl2026 pdf . --profile profile-mitpress -o print.pdf
```

## Fonts in the container

Profiles that select **system fonts by family name** (`\setmainfont{Palatino}`)
rely on that font being installed on the host — which it is on macOS, but *not*
in the Linux image. Two portable patterns:

- The bundled **`memoir`** profile uses free clones shipped in TeX Live (a
  Palatino-alike + `newpxmath` + DejaVu/Latin Modern mono), so it builds in the
  container with no extra fonts.
- A profile that **bundles licensed font files** should load them *by path*
  (`\newfontfamily\x{File.otf}[Path=./]`) — those files are copied into the
  build dir and resolve in any environment. The MIT profile already does this
  for its licensed faces (`CashPointMono`, `NewsGothicStd`) but still selects
  Palatino *by name*; building the MIT profile in-container additionally needs
  Palatino made available to the container (see the profile's README).

## CI

`.github/workflows/print-image.yml` builds the image and smoke-tests a full
`parody pdf` of `tests/smoke-book/` with the `memoir` profile, so print
rendering is guarded on an amd64 runner with the pinned TeX Live.
