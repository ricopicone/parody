"""Preview writer: Django-tag resolution and site generation."""

from parody.cli import main
from parody.writers.preview import TagResolver, write_preview

SAMPLE_BIB = """\
@article{doe2020,
  author = {Doe, Jane},
  title = {A Fine Article},
  journal = {Journal of Examples},
  year = {2020},
}
"""


def make_artifact(html, solutions=None):
    section = {"title": "Sec", "slug": "sec", "html": html, "anchors": []}
    if solutions:
        section["has_solutions"] = True
        section["solutions"] = solutions
    return {
        "schema_version": 1, "generator": "parody test",
        "title": "T", "slug": "t", "author": ["A"],
        "description": "", "acronym": "", "cover_image": "", "pdf_file": "",
        "chapters": [{"title": "Ch", "slug": "ch", "sections": [section]}],
    }


def test_tag_resolution_without_bib():
    r = TagResolver()
    html = (
        "<img src=\"{% media 'notebooks/t/ch/fig.svg' %}\">"
        " {% cite 'doe2020' %} {% cite_many \"a1\" \"a2\" %}"
        " <a href=\"{% url 'teaching:export' x %}\">x</a>"
        " {% get_cell \"obs\" 1 2 %} {% csrf_token %}"
        " {% auth_button href='t/file.zip' label='Get file' %}"
        " {% something_unknown 'x' %}"
    )
    out = r.resolve(html, prefix="../")
    assert 'src="../media/notebooks/t/ch/fig.svg"' in out
    assert "[doe2020]" in out and "[a1]" in out and "[a2]" in out
    assert 'href="#"' in out
    assert "get-cell-placeholder" in out
    assert "csrf" not in out
    assert 'href="../media/t/file.zip"' in out and ">Get file</a>" in out
    assert "unresolved site tag: something_unknown" in out
    assert "{%" not in out, "unresolved Django tags remain"


def test_write_preview_site(tmp_path):
    artifact = make_artifact(
        "<p>body {% cite 'doe2020' %}</p>",
        solutions={"exe:q1": {"content": "<p>answer</p>", "title": "Q1"}},
    )
    out = write_preview(artifact, tmp_path / "site")
    index = (out / "index.html").read_text()
    page = (out / "ch" / "sec.html").read_text()
    assert "T" in index and 'href="ch/sec.html"' in index
    assert "body" in page and "{%" not in page
    assert "Solution: Q1" in page and "answer" in page
    assert (out / "style.css").is_file()


def test_preview_no_solutions(tmp_path):
    artifact = make_artifact(
        "<p>b</p>", solutions={"exe:q1": {"content": "<p>secret</p>", "title": None}}
    )
    out = write_preview(artifact, tmp_path / "site", include_solutions=False)
    page = (out / "ch" / "sec.html").read_text()
    assert "secret" not in page


def test_preview_citeproc_with_bib(tmp_path):
    bib = tmp_path / "book.bib"
    bib.write_text(SAMPLE_BIB)
    artifact = make_artifact("<p>see {% cite 'doe2020' %}</p>")
    out = write_preview(artifact, tmp_path / "site", bib_path=bib)
    page = (out / "ch" / "sec.html").read_text()
    assert "Doe" in page, "citation not rendered through citeproc"
    refs = (out / "references.html").read_text()
    assert "A Fine Article" in refs
    assert 'href="references.html"' in (out / "index.html").read_text()


def test_preview_cli_end_to_end(tmp_path):
    project = tmp_path / "demo"
    assert main(["init", str(project), "--title", "Demo"]) == 0
    out = tmp_path / "site"
    assert main(["preview", str(project), "-o", str(out)]) == 0
    assert (out / "index.html").is_file()
    page = (out / "introduction" / "overview.html").read_text()
    assert "{%" not in page
    assert "Solution" in page


def test_media_assembly_from_project_tree(tmp_path):
    """Refs missing from the media/ tree are gathered from the project
    (content repos co-locate assets in chapters/); .pgf refs swap to their
    .svg siblings and extensionless refs resolve by extension."""
    proj = tmp_path / "proj"
    chdir = proj / "chapters" / "ch"
    chdir.mkdir(parents=True)
    (chdir / "fig.png").write_bytes(b"\x89PNG fake")
    (chdir / "plot.pgf").write_text("% pgf source")
    (chdir / "plot.svg").write_text("<svg/>")
    (chdir / "bare.png").write_bytes(b"\x89PNG fake")
    artifact = make_artifact(
        "<img src=\"{% media 'fig.png' %}\">"
        "<img src=\"{% media 'plot.pgf' %}\">"
        "<img src=\"{% media 'bare' %}\">"
    )
    out = write_preview(artifact, tmp_path / "site", media_src=proj)
    media = out / "media"
    assert (media / "fig.png").is_file()
    assert (media / "plot.svg").is_file(), "svg sibling not shipped"
    assert (media / "bare.png").is_file(), "extensionless ref not resolved"
    page = (out / "ch" / "sec.html").read_text()
    assert 'src="../media/fig.png"' in page
    assert 'src="../media/plot.svg"' in page, "pgf ref not rewritten to svg"
    assert 'src="../media/bare.png"' in page
