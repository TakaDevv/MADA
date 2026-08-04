"""
pdf_engine.py
=============
Minimal text-overlay engine used by field_maps/*.py to stamp values onto
the real DGI PDF forms. `F` describes one piece of text to draw at a PDF
coordinate (bottom-up — matches reportlab/PDF native coords, NOT
pdfplumber's top-down "top", which is why the field_maps do the
`y = PAGE_H - bottom + 2` conversion before building F()).

All overlaid text is bold by default (Helvetica-Bold), because the
official form's printed labels are thin and a bold overlay reads more
clearly as "what was filled in" versus "what was pre-printed" when the
PDF is scanned, photocopied, or viewed at small size — set `bold=False`
per-field only for the rare case where a lighter mark is wanted (e.g. an
"X" placed inside a checkbox that's already tight on space).
"""
from dataclasses import dataclass
from io import BytesIO
from typing import Optional

from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas


@dataclass
class F:
    x: float
    y: float
    text: str
    size: float = 9
    align: str = "left"   # "left" | "right" | "center"
    max_width: Optional[float] = None
    bold: bool = True


def _draw_field(c: canvas.Canvas, f: F):
    text = "" if f.text is None else str(f.text)
    if not text:
        return

    font_name = "Helvetica-Bold" if f.bold else "Helvetica"
    size = f.size
    if f.max_width:
        # Shrink to fit rather than overflow into the next box on a real
        # form. Bold glyphs run wider than regular ones at the same
        # point size, so this floor is lower (5pt vs 6pt previously) to
        # guarantee digit-box overlays (NIF/NIN/article number) never
        # bleed past their measured cell width.
        while size > 5 and c.stringWidth(text, font_name, size) > f.max_width:
            size -= 0.5

    c.setFont(font_name, size)
    if f.align == "right":
        c.drawRightString(f.x, f.y, text)
    elif f.align == "center":
        c.drawCentredString(f.x, f.y, text)
    else:
        c.drawString(f.x, f.y, text)


def fill_pdf(base_pdf_path: str, fields_by_page: dict) -> bytes:
    """
    fields_by_page: {page_index: [F, ...]}
    Pages not listed pass through untouched — still the real official
    page, just nothing pre-filled on it yet (matches the "NOT calibrated
    yet" pages noted in the field_maps).
    """
    reader = PdfReader(base_pdf_path)
    writer = PdfWriter()

    for i, base_page in enumerate(reader.pages):
        fields = fields_by_page.get(i)
        if fields:
            buf = BytesIO()
            c = canvas.Canvas(
                buf,
                pagesize=(float(base_page.mediabox.width), float(base_page.mediabox.height)),
            )
            for f in fields:
                _draw_field(c, f)
            c.save()
            buf.seek(0)
            base_page.merge_page(PdfReader(buf).pages[0])

        writer.add_page(base_page)

    out = BytesIO()
    writer.write(out)
    return out.getvalue()