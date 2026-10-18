"""The landscape side-by-side sheet: English page left, twin right (task #825)."""

import shutil
import subprocess

import pytest

pypdf = pytest.importorskip("pypdf")

from parody.twin.sidebyside import side_by_side  # noqa: E402


def _pdf(path, pages, shade):
    """A 6x9 in PDF whose every page is filled with one grey rectangle."""
    from pypdf.generic import DecodedStreamObject, NameObject
    writer = pypdf.PdfWriter()
    for _ in range(pages):
        page = writer.add_blank_page(width=432, height=648)
        stream = DecodedStreamObject()
        # an unbalanced "q": the page leaves a transform behind, as real ones can
        stream.set_data(f"q 2 0 0 2 0 0 cm {shade} g 10 10 196 304 re f".encode())
        page[NameObject("/Contents")] = writer._add_object(stream)
    writer.write(str(path))
    return path


def test_side_by_side_geometry(tmp_path):
    en = _pdf(tmp_path / "en.pdf", 5, 0.2)
    tw = _pdf(tmp_path / "tw.pdf", 2, 0.6)
    out = side_by_side(en, tw, [3, 4], tmp_path / "sbs.pdf")
    reader = pypdf.PdfReader(str(out))
    assert len(reader.pages) == 2
    box = reader.pages[0].mediabox
    assert (float(box.width), float(box.height)) == (792.0, 612.0)


@pytest.mark.skipif(not shutil.which("pdftoppm"), reason="needs pdftoppm")
def test_both_halves_carry_their_page(tmp_path):
    Image = pytest.importorskip("PIL.Image")
    en = _pdf(tmp_path / "en.pdf", 1, 0.2)
    tw = _pdf(tmp_path / "tw.pdf", 1, 0.6)
    out = side_by_side(en, tw, [1], tmp_path / "sbs.pdf")
    subprocess.run(["pdftoppm", "-r", "20", "-png", str(out), str(tmp_path / "r")], check=True)
    img = Image.open(next(tmp_path.glob("r*.png"))).convert("L")
    w, h = img.size
    left = img.crop((0, 0, w // 2, h)).getextrema()[0]
    right = img.crop((w // 2, 0, w, h)).getextrema()[0]
    # the English (dark) rectangle on the left, the twin (lighter) on the right
    assert left < 80 and 80 < right < 200
    # and the right half is not tinted by the left page's leftover transform
    assert img.crop((w // 2, 0, w, h)).getextrema()[0] > 80
