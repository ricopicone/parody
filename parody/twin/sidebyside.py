"""English page and its twin on one landscape sheet (task #825, spec D4).

Letter landscape (11 × 8.5 in). Each page is scaled to fit its half, about
92% for a 6 × 9 in book, and centred in it. Each page is merged onto a fresh
blank sheet, so neither inherits a graphics state the other left open (see
``pdf-composition-gotchas`` in project memory).
"""

from pathlib import Path

SHEET_W, SHEET_H = 792.0, 612.0  # letter landscape, points


def side_by_side(english_pdf, twin_pdf, abspages, out):
    """Write ``out``: English abspage ``abspages[i]`` beside twin page ``i``."""
    from pypdf import PageObject, PdfReader, PdfWriter, Transformation

    english, twin = PdfReader(str(english_pdf)), PdfReader(str(twin_pdf))
    writer = PdfWriter()
    for i, abspage in enumerate(abspages):
        sheet = PageObject.create_blank_page(width=SHEET_W, height=SHEET_H)
        for half, page in enumerate((english.pages[abspage - 1], twin.pages[i])):
            box = page.mediabox
            w, h = float(box.width), float(box.height)
            scale = min((SHEET_W / 2) / w, SHEET_H / h)
            tx = half * SHEET_W / 2 + (SHEET_W / 2 - w * scale) / 2 - float(box.left) * scale
            ty = (SHEET_H - h * scale) / 2 - float(box.bottom) * scale
            sheet.merge_transformed_page(page, Transformation().scale(scale).translate(tx, ty))
        writer.add_page(sheet)
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "wb") as f:
        writer.write(f)
    return out
