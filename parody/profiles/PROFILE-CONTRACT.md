# Parody print profile contract

`parody/filters/print.lua` converts each section's Markdown to LaTeX that calls a
fixed set of environments and commands. A **print profile** is a directory of
LaTeX support files (class, style, fonts, `latexmkrc`, `main.tex.template`) that
defines those names. As long as a profile implements this contract, the same
filter output compiles against it — that is what lets one book use the bundled
`memoir` profile and another use a book-private `mitpress` profile.

The build writer (`parody/writers/latex.py`) copies every file in the profile
directory (except `main.tex.template`) flat into the build dir, then fills the
template. Profiles are selected with `parody pdf --profile <name-or-dir>`; a bare
name resolves to a bundled profile under `parody/profiles/<name>/`.

## Required `main.tex.template` substitutions

`$flags $title $author $chapters $bibresource $bibliography` — see
`latex.py:build_pdf`. The writer emits standard `\chapter{Title}\label{...}`,
`\appendix`, and `\setcounter{chapter}{n}`, so the class must use a stock
`\chapter` (single title argument), `\frontmatter`/`\mainmatter`/`\backmatter`,
and `\printindex`.

## Environments (with argument signatures)

- `definition{title}{label}`, `theorem`, `lemma`, `corollary`, `proposition`
  — `{title}{label}`; counter `thmctr`, parenthesized-free `\crefname`.
- `infobox[opts]{title}` — counter `infoboxctr`, `\crefname` "box/boxes".
- `myexample[version]{id}{hash}` — counter `examplectr`, `\crefname`
  "example/examples".
- `listingsbox{style}{caption}{id}` and
  `listingsboxfloat{style}{caption}{id}{pos}` — minted-backed; `style` encodes
  the language (`clisting*`, `pythonlisting`, `armlisting`, `textlisting`);
  counter `listingctr`.
- `mintedwrapper`, `algorithmcenter`, `algorithm[H]`, `formattedoutput`.
- xsim: `exercise`/`solution` and `labexercise`/`labsolution`, with
  `\DeclareExerciseProperty{hash}` and `solution/print` gated on `\issolution`.

## Commands

- `\figcaption[short][float|nofloat]{id}{caption}`,
  `\tabcaption[short][float|nofloat]{id}{caption}`, `\algcaption{label}{caption}`.
- `\inputpgf{path}`, `\includestandalone`, `\maxwidth`, `\pandocbounded`,
  `\mathdefault`, `\tightlist`, `\ul`.
- `\keyword`, `\mykeys`, `\unicoder`, `\lref`, `\myindex`, `\indexc`,
  `\myurl`/`\myurlbottom`/`\myurlinline`, `\numberthis`.

## Build flags (set via `\def` before the class options take effect)

`\issolution` (solutions manual), `\ispartial` (sample build), `\nocropmarks`.

## Theme layer (recommended, not required by the filter)

Profiles that want swappable colors/fonts should put a named palette and the
font setup in a separate `parody-theme-*.sty` and reference only the named
colors from the environments. The bundled `memoir` profile defines:
`parodyaccent`, `parodyaccent2`, and `parody{thm,info,ex,out}{back,frame}`.
