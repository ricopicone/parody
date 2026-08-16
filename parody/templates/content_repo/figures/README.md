# Figure sources

Everything here is **source** and belongs in git. `parody figures` builds it
into `build/figures/`, which does not.

```
figures/<name>.tex     a fragment — a tikzpicture, a circuitikz, whatever draws.
                       parody supplies the class and the type size (8pt), so
                       the fragment carries no \documentclass of its own.
figures/<name>.ai      Illustrator artwork. A .ai is already a PDF, so no
                       export step — but it also carries Illustrator's own
                       private data beside the drawing, so parody flattens it
                       with ghostscript rather than copying it. Measured on one
                       book's artwork: 3.8 MB of .ai, 216 kB of actual drawing.
figures/preamble.tex   optional: this book's own tikz styles, macros and
                       fonts. Point parody.yaml at it:

                           figures:
                             preamble: figures/preamble.tex
```

Each source builds to both forms the book needs:

```
build/figures/<name>.pdf   print
build/figures/<name>.svg   web
```

Run `parody figures .` after changing a source (`--force` to rebuild
everything). Referencing a figure from a section is unchanged — refer to it by
name and parody resolves it to whichever form the target needs.
