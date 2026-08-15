"""Figure srcs must be resolved in print whether or not the image is labelled.

A src written in the MEDIA hierarchy (``notebooks/<slug>/<name>``) is a
web-side path. In print it has to be resolved against the source tree, or
kpathsea searches TEXINPUTS for that literal relative path, never finds it,
and the figure is simply absent from the PDF — silently, because
``\\includestandalone`` is \\providecommand'd to ``\\includegraphics``.

The gap this pins (task #587): print.lua's Image handler only resolved srcs
for images carrying a non-empty identifier, so a captionless, id-less
``![](notebooks/…){.figure .standalone}`` kept its web path. ~70 refs in the
electronics book rendered as missing figures.
"""

from pathlib import Path

import pypandoc
import pytest

FILTER = Path(__file__).parent.parent / "parody" / "filters" / "print.lua"
PANDOC_FROM = "markdown-markdown_in_html_blocks+raw_tex+tex_math_dollars"


@pytest.fixture
def notebook_chapter(tmp_path, monkeypatch):
    """A project whose chapter dir holds the figure the media path names."""
    project = tmp_path / "book"
    chapter = project / "chapters" / "one"
    chapter.mkdir(parents=True)
    # the standalone figure, as the migrator leaves it: in the chapter dir,
    # while the markdown refers to it by its media-hierarchy path
    (chapter / "sec-widget.pdf").write_bytes(b"%PDF-1.7\n")
    (chapter / "sec-plain.png").write_bytes(b"\x89PNG\r\n")
    monkeypatch.setenv("PARODY_PROJECT_DIR", str(project))
    monkeypatch.setenv("PARODY_CHAPTER_DIR", str(chapter))
    return chapter


def render(md, chapter):
    path = chapter / "section.md"
    path.write_text(md, encoding="utf-8")
    return pypandoc.convert_file(
        str(path), "latex", format=PANDOC_FROM,
        extra_args=[f"--lua-filter={FILTER}", "--biblatex", "--wrap=none"],
        cworkdir=str(chapter),
    )


def test_captionless_idless_standalone_resolves(notebook_chapter):
    # THE bug: no caption, no #id. Previously fell through to pandoc's default
    # writer with the web media path intact.
    out = render("![](notebooks/book/sec-widget){.figure .standalone}\n",
                 notebook_chapter)
    assert "notebooks/book/sec-widget" not in out, out
    assert "\\includestandalone" in out
    assert "{sec-widget}" in out


def test_identified_standalone_still_resolves(notebook_chapter):
    # regression guard: the path that already worked must keep working
    out = render(
        "![](notebooks/book/sec-widget){#fig:w .figure .standalone}\n",
        notebook_chapter)
    assert "notebooks/book/sec-widget" not in out, out
    assert "\\includestandalone" in out
    assert "\\figcaption" in out  # still wrapped as a numbered float


def test_captioned_standalone_still_resolves(notebook_chapter):
    # a caption makes it a pandoc Figure, handled by figurer, not Image
    out = render(
        "![A widget](notebooks/book/sec-widget){#fig:w .figure .standalone}\n",
        notebook_chapter)
    assert "notebooks/book/sec-widget" not in out, out
    assert "\\includestandalone" in out


def test_subfigure_srcs_resolve_too(notebook_chapter):
    # Subfigures build their \includegraphics directly from the src, bypassing
    # imager entirely — a third site with the same root cause (#587).
    (notebook_chapter / "sec-left.pdf").write_bytes(b"%PDF-1.7\n")
    (notebook_chapter / "sec-right.pdf").write_bytes(b"%PDF-1.7\n")
    out = render(
        "::: {#fig:pair .figure .subfigures rows=1}\n\n"
        "![left.](notebooks/book/sec-left){#fig:l .subfigure .figure .standalone}\n\n"
        "![right.](notebooks/book/sec-right){#fig:r .subfigure .figure .standalone}\n\n"
        "A pair.\n"
        ":::\n",
        notebook_chapter)
    assert "notebooks/book/sec-left" not in out, out
    assert "notebooks/book/sec-right" not in out, out
    assert "{sec-left}" in out
    assert "\\subcaptionbox" in out


def test_a_src_that_already_carries_its_extension_resolves(notebook_chapter):
    # Some refs are written with the extension (…/sources-real.pdf) rather than
    # extensionless. Appending another extension finds nothing; the bare name
    # has to be tried too.
    (notebook_chapter / "sec-real.pdf").write_bytes(b"%PDF-1.7\n")
    out = render(
        "![Real source.](notebooks/book/sec-real.pdf){#fig:real .figure}\n",
        notebook_chapter)
    # resolve_asset returns an absolute path (its contract for every src it
    # resolves); what matters is that the web media path is gone.
    assert "notebooks/book/sec-real.pdf" not in out, out
    assert "sec-real.pdf}" in out
    assert str(notebook_chapter) in out


def test_an_unresolvable_media_path_warns(notebook_chapter):
    """Nothing on disk backs this one.

    It is left in place (it might still resolve via another TEXINPUTS entry,
    and dropping a figure is worse than keeping a suspect one) — but it must
    not pass in silence. This exact shape produced ~70 missing figures in
    electronics with no distinct error in the log.
    """
    import subprocess

    path = notebook_chapter / "absent.md"
    path.write_text("![](notebooks/book/sec-absent){.figure .standalone}\n",
                    encoding="utf-8")
    proc = subprocess.run(
        ["pandoc", str(path), "-t", "latex", "-f", PANDOC_FROM,
         f"--lua-filter={FILTER}", "--wrap=none"],
        cwd=notebook_chapter, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    assert "sec-absent" in proc.stderr
    assert "media path" in proc.stderr


def test_a_bare_extensionless_src_is_left_for_texinputs(notebook_chapter):
    """rtc's shape: id-less, no caption, src is a bare extensionless name.

    These already work — kpathsea resolves them against TEXINPUTS (the chapter
    dirs), trying extensions. resolve_asset instead demands an exact filename
    match, so routing them through it drops the figure. An earlier attempt at
    #587 did exactly that and blanked 3 rtc sections' figures.
    """
    (notebook_chapter / "gate-not.pdf").write_bytes(b"%PDF-1.7\n")
    out = render("![](gate-not){.figure}\n", notebook_chapter)
    assert "gate-not" in out, out
    assert "includegraphics" in out


def test_non_notebook_projects_are_untouched(tmp_path, monkeypatch):
    # Outside a parody content repo (no PARODY_PROJECT_DIR) srcs are authored
    # relative to the .tex and must pass through verbatim.
    monkeypatch.delenv("PARODY_PROJECT_DIR", raising=False)
    monkeypatch.delenv("PARODY_CHAPTER_DIR", raising=False)
    chapter = tmp_path / "plain"
    chapter.mkdir()
    out = render("![](figures/thing){.figure .standalone}\n", chapter)
    assert "figures/thing" in out


PARODY_YAML_SCALED = """\
title: Scale Test
slug: scale-test
authors: [Tester]
print:
  figure_scale: 0.86
chapters:
  - slug: one
    title: Chapter One
    sections: [only]
"""


def _scaled_project(tmp_path, monkeypatch, yaml_text):
    monkeypatch.setattr("parody.writers.latex.shutil.which", lambda *a, **k: None)
    root = tmp_path / "scale-test"
    ch = root / "chapters" / "one"
    ch.mkdir(parents=True)
    (root / "parody.yaml").write_text(yaml_text)
    (ch / "fig.pdf").write_bytes(b"%PDF-1.7\n")
    (ch / "only.md").write_text(
        "---\ntitle: Only\nslug: only\n---\n\n"
        "![](notebooks/scale-test/fig){.figure .standalone}\n")
    return root


def test_figure_scale_applies_when_the_book_declares_one(tmp_path, monkeypatch):
    from parody.writers.latex import build_pdf
    root = _scaled_project(tmp_path, monkeypatch, PARODY_YAML_SCALED)
    build_pdf(root)
    build = root / "build" / "print"
    assert "\\parodyfigwidth" in (
        build / "sections" / "one" / "only.tex").read_text()
    main = (build / "main.tex").read_text()
    assert "\\def\\parodyfigscale{0.86}" in main
    assert "\\usepackage{parody-figscale}" in main
    # the \def must precede the package, whose \providecommand defaults it to 1
    assert main.index("\\def\\parodyfigscale") < main.index(
        "\\usepackage{parody-figscale}")
    assert (build / "parody-figscale.sty").is_file()


def test_without_the_setting_the_output_is_unchanged(tmp_path, monkeypatch):
    from parody.writers.latex import build_pdf
    plain = PARODY_YAML_SCALED.replace("print:\n  figure_scale: 0.86\n", "")
    root = _scaled_project(tmp_path, monkeypatch, plain)
    build_pdf(root)
    build = root / "build" / "print"
    tex = (build / "sections" / "one" / "only.tex").read_text()
    assert "width=\\maxwidth" in tex
    assert "parodyfigwidth" not in tex
    assert not (build / "parody-figscale.sty").exists()
