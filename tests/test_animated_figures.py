"""An animated figure (.gif, …) plays on the web and prints as a still.

The web has always worked. Print never did (task #785). print.lua resolved the
.gif and handed it to \\includegraphics, and LuaLaTeX has no GIF driver. Because
latexmk runs in force mode, the PDF built anyway, with an empty space above
the caption. Nothing warned, because the path DID resolve, so a book's
"print resolved every figure" CI check passed over a blank figure.

Now print swaps in a still: an explicit print-src=, a sibling .pdf/.png, or a
frame extracted at build time (still=). If none exists, it gives the
unresolved-figure warning. The caption also says the figure is animated online.
"""

import subprocess
import sys
from pathlib import Path

import pypandoc
import pytest
from PIL import Image

from parody.stills import extract_still, frame_index
from parody.writers.latex import build_pdf, have_tool

FILTERS = Path(__file__).parent.parent / "parody" / "filters"
PANDOC_FROM = "markdown-markdown_in_html_blocks+raw_tex+tex_math_dollars"
RED, GREEN, BLUE = (255, 0, 0), (0, 255, 0), (0, 0, 255)


def make_gif(path, colours=(RED, GREEN, BLUE)):
    frames = [Image.new("RGB", (8, 8), c) for c in colours]
    frames[0].save(path, save_all=True, append_images=frames[1:], duration=100,
                   loop=0)
    return path


def colour_of(png):
    with Image.open(png) as im:
        return im.convert("RGB").getpixel((4, 4))


# --- the frame extractor ---------------------------------------------------

@pytest.mark.parametrize("spec, n, want", [
    (None, 5, 0), ("first", 5, 0), ("last", 5, 4), ("2", 5, 2),
    ("99", 5, 4), ("0.5", 5, 2), ("1.0", 5, 4), ("0", 1, 0), ("last", 1, 0),
])
def test_frame_index(spec, n, want):
    assert frame_index(spec, n) == want


@pytest.mark.parametrize("spec", ["middle", "1.5", "-0.1"])
def test_frame_index_rejects_nonsense(spec):
    with pytest.raises(ValueError):
        frame_index(spec, 5)


@pytest.mark.parametrize("spec, want", [
    (None, RED), ("last", BLUE), ("1", GREEN), ("0.5", GREEN)])
def test_extract_still_picks_the_frame(tmp_path, spec, want):
    gif = make_gif(tmp_path / "spin.gif")
    out = tmp_path / "cache" / "spin.png"
    assert extract_still(gif, out, spec)
    assert colour_of(out) == want


def test_extract_still_refreshes_when_the_animation_changes(tmp_path):
    gif = make_gif(tmp_path / "spin.gif")
    out = tmp_path / "spin.png"
    extract_still(gif, out)
    assert colour_of(out) == RED
    make_gif(gif, (BLUE, GREEN))
    import os
    st = out.stat()
    os.utime(gif, (st.st_atime, st.st_mtime + 10))
    extract_still(gif, out)
    assert colour_of(out) == BLUE


def test_extract_still_fails_on_garbage(tmp_path):
    bad = tmp_path / "broken.gif"
    bad.write_bytes(b"not an image")
    out = tmp_path / "broken.png"
    assert not extract_still(bad, out)
    assert not out.exists()


# --- print.lua ---------------------------------------------------------------

@pytest.fixture
def chapter(tmp_path, monkeypatch):
    project = tmp_path / "book"
    chapter = project / "chapters" / "one"
    chapter.mkdir(parents=True)
    make_gif(chapter / "spin.gif")
    monkeypatch.setenv("PARODY_PROJECT_DIR", str(project))
    monkeypatch.setenv("PARODY_CHAPTER_DIR", str(chapter))
    monkeypatch.setenv("PARODY_SVG_CACHE", str(tmp_path / "cache"))
    monkeypatch.setenv("PARODY_PYTHON", sys.executable)
    monkeypatch.delenv("PARODY_ANIMATION_NOTE", raising=False)
    monkeypatch.delenv("PARODY_SECTION_URL", raising=False)
    return chapter


def render(md, chapter, fmt="latex", filt="print.lua"):
    """(output, stderr) — stderr is where the unresolved warning goes."""
    path = chapter / "section.md"
    path.write_text(md, encoding="utf-8")
    result = subprocess.run(
        [pypandoc.get_pandoc_path(), str(path), "-f", PANDOC_FROM, "-t", fmt,
         f"--lua-filter={FILTERS / filt}", "--wrap=none"],
        capture_output=True, text=True, cwd=chapter, check=True)
    return result.stdout, result.stderr


def included(tex):
    import re
    return re.findall(r"\\includegraphics(?:\[[^]]*\])?\{([^}]*)\}", tex)


def test_a_gif_prints_as_an_extracted_still(chapter, tmp_path):
    tex, err = render("![Door frames.](spin.gif){#fig:spin}\n", chapter)
    (src,) = included(tex)
    assert src.endswith(".png") and src.startswith(str(tmp_path / "cache")), tex
    assert colour_of(src) == RED
    assert "unresolved" not in err


def test_the_media_path_form_resolves_too(chapter):
    # the form the robotics notes use
    tex, _ = render(
        "![Door frames.](notebooks/book/spin.gif){#fig:spin}\n", chapter)
    (src,) = included(tex)
    assert src.endswith(".png") and ".gif" not in tex


def test_still_attribute_picks_the_frame(chapter):
    tex, _ = render("![Spin.](spin.gif){#fig:spin still=last}\n", chapter)
    (src,) = included(tex)
    assert colour_of(src) == BLUE
    # and a different frame is a different cache entry, never a stale hit
    tex2, _ = render("![Spin.](spin.gif){#fig:spin}\n", chapter)
    assert included(tex2)[0] != src


def test_a_sibling_still_wins_over_extraction(chapter):
    (chapter / "spin.pdf").write_bytes(b"%PDF-1.4\n")
    tex, _ = render("![Spin.](spin.gif){#fig:spin}\n", chapter)
    assert included(tex) == [str(chapter / "spin.pdf")]


def test_print_src_names_the_still(chapter):
    Image.new("RGB", (8, 8), GREEN).save(chapter / "poster.png")
    tex, _ = render(
        "![Spin.](spin.gif){#fig:spin print-src=poster.png}\n", chapter)
    assert included(tex) == [str(chapter / "poster.png")]


def test_the_caption_says_it_is_animated(chapter):
    tex, _ = render("![Door frames.](spin.gif){#fig:spin}\n", chapter)
    assert "Door frames. (Animated in the online edition.)" in tex


def test_a_book_wide_note_and_a_per_figure_override(chapter, monkeypatch):
    monkeypatch.setenv("PARODY_ANIMATION_NOTE", "See the *online* notes.")
    tex, _ = render("![Spin.](spin.gif){#fig:spin}\n", chapter)
    assert "Spin. See the \\emph{online} notes." in tex
    tex, _ = render('![Spin.](spin.gif){#fig:spin print-note=""}\n', chapter)
    assert "online" not in tex and "Spin.}" in tex
    monkeypatch.setenv("PARODY_ANIMATION_NOTE", "")
    tex, _ = render("![Spin.](spin.gif){#fig:spin}\n", chapter)
    assert "Animated" not in tex


def test_the_note_links_to_the_figure_online(chapter, monkeypatch):
    monkeypatch.setenv("PARODY_SECTION_URL", "https://bk.example/one/sec/")
    tex, _ = render("![Spin.](spin.gif){#fig:spin}\n", chapter)
    assert ("Spin. \\href{https://bk.example/one/sec/\\#fig:spin}"
            "{(Animated in the online edition.)}") in tex, tex


def test_no_site_means_a_plain_note(chapter):
    tex, _ = render("![Spin.](spin.gif){#fig:spin}\n", chapter)
    assert "\\href" not in tex


def test_a_still_image_caption_is_untouched(chapter):
    Image.new("RGB", (8, 8), RED).save(chapter / "plain.png")
    tex, _ = render("![Plain.](plain.png){#fig:plain}\n", chapter)
    assert "Animated" not in tex


def test_no_still_is_reported_as_unresolved(chapter):
    # THE silent failure: the path resolves, but nothing LaTeX can include
    # exists. It must warn the way an unresolved figure does, because that
    # is what a book's CI greps for.
    (chapter / "broken.gif").write_bytes(b"not an image")
    tex, err = render("![Broken.](broken.gif){#fig:broken}\n", chapter)
    assert "unresolved figure (omitting): broken.gif" in err, err
    assert included(tex) == []
    assert ".gif" not in tex


def test_an_animated_subfigure_panel_prints_its_still(chapter):
    Image.new("RGB", (8, 8), RED).save(chapter / "plain.png")
    md = (
        "::: {#fig:pair .figure .subfigures}\n"
        "![A](plain.png){#fig:a}\n\n"
        "![B](spin.gif){#fig:b still=last}\n\n"
        "The pair.\n"
        ":::\n")
    tex, _ = render(md, chapter)
    srcs = included(tex)
    assert len(srcs) == 2 and ".gif" not in tex, tex
    assert colour_of(srcs[1]) == BLUE
    assert "(Animated in the online edition.)" in tex


# --- web ---------------------------------------------------------------------

def test_web_keeps_the_gif_and_loads_it_lazily(chapter):
    html, _ = render("![Spin.](notebooks/book/spin.gif){#fig:spin}\n",
                     chapter, fmt="html", filt="filter.lua")
    assert "spin.gif" in html and 'loading="lazy"' in html, html
    html, _ = render("![Plain.](notebooks/book/plain.png){#fig:plain}\n",
                     chapter, fmt="html", filt="filter.lua")
    assert "loading=" not in html


# --- the whole print build ---------------------------------------------------

PARODY_YAML = """\
title: GIF Test
slug: gif-test
authors: [Tester]
chapters:
  - slug: one
    title: Chapter One
    sections: [a-section]
"""

SECTION_MD = """\
---
title: A Section
slug: a-section
---

# A section {#sec-a}

See [fig:spin]{.hashref}.

![A spinning frame.](notebooks/gif-test/spin.gif){#fig:spin}
"""


@pytest.fixture
def gif_book(tmp_path, monkeypatch):
    for key in ("PARODY_PROJECT_DIR", "PARODY_CHAPTER_DIR", "PARODY_SVG_CACHE",
                "PARODY_PYTHON", "PARODY_ANIMATION_NOTE", "PARODY_SECTION_URL"):
        monkeypatch.delenv(key, raising=False)
    project = tmp_path / "gif-test"
    chapter = project / "chapters" / "one"
    chapter.mkdir(parents=True)
    (project / "parody.yaml").write_text(PARODY_YAML)
    (chapter / "a-section.md").write_text(SECTION_MD)
    make_gif(project / "spin.gif")
    return project


def _section_tex(project):
    return (project / "build" / "print" / "sections" / "one"
            / "a-section.tex").read_text()


def test_the_print_build_includes_the_still(gif_book, monkeypatch):
    monkeypatch.setattr("parody.writers.latex.shutil.which", lambda *a, **k: None)
    build_pdf(gif_book)
    tex = _section_tex(gif_book)
    (src,) = included(tex)
    assert Path(src).is_file() and src.endswith(".png")
    assert "svg-cache" in src
    assert "(Animated in the online edition.)" in tex


def test_print_animation_note_false_drops_the_note(gif_book, monkeypatch):
    monkeypatch.setattr("parody.writers.latex.shutil.which", lambda *a, **k: None)
    (gif_book / "parody.yaml").write_text(
        PARODY_YAML + "print:\n  animation_note: false\n")
    build_pdf(gif_book)
    assert "Animated" not in _section_tex(gif_book)


def test_print_online_url_links_the_section(gif_book, monkeypatch):
    monkeypatch.setattr("parody.writers.latex.shutil.which", lambda *a, **k: None)
    (gif_book / "parody.yaml").write_text(
        PARODY_YAML + "print:\n  online_url: https://bk.example/\n")
    build_pdf(gif_book)
    assert ("\\href{https://bk.example/one/a-section/\\#fig:spin}"
            in _section_tex(gif_book))


def test_companion_url_is_the_fallback_site(gif_book, monkeypatch):
    monkeypatch.setattr("parody.writers.latex.shutil.which", lambda *a, **k: None)
    (gif_book / "parody.yaml").write_text(
        PARODY_YAML + "book:\n  companion_url: https://cmp.example\n")
    build_pdf(gif_book)
    assert "\\href{https://cmp.example/one/a-section/" in _section_tex(gif_book)


@pytest.mark.pdf
@pytest.mark.skipif(not (have_tool("latexmk") and have_tool("lualatex")),
                    reason="TeX (latexmk + lualatex) not available")
def test_the_pdf_page_carries_the_image_and_the_link(gif_book):
    from pypdf import PdfReader
    (gif_book / "parody.yaml").write_text(
        PARODY_YAML + "print:\n  online_url: https://bk.example\n")
    pdf = build_pdf(gif_book)
    assert pdf is not None and pdf.exists()
    pages = PdfReader(pdf).pages
    images = [img for page in pages for img in page.images]
    assert images, "the figure printed as an empty space"
    uris = [a.get_object()["/A"].get("/URI") for page in pages
            for a in page.get("/Annots") or []
            if a.get_object().get("/A")]
    assert "https://bk.example/one/a-section/#fig:spin" in uris, uris
