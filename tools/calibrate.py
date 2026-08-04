"""
tools/calibrate.py
===================

Finishing the remaining pages (G50 TVA/TLS/timbre pages, all of G1) means
measuring where each blank sits. This script does the two things that
make that fast and exact, instead of eyeballing a screenshot:

1. `grid`  -> renders a page to PNG with a labelled coordinate grid
              (every 20pt) so you can read off an approximate x/y by eye.
2. `words` -> dumps every text run on a page with its EXACT bounding box
              (x0, top, x1, bottom), which is how every coordinate in
              field_maps/g12.py and field_maps/g50.py was produced.
              Search the output for the label next to the blank you want
              to fill, then use its x1/bottom as your anchor.

Usage
-----
    python tools/calibrate.py grid  static/forms/g1.pdf 2      # page index 2
    python tools/calibrate.py words static/forms/g1.pdf 2

Remember: pdfplumber coordinates are top-down. Convert to the bottom-up
PDF coordinate pdf_engine.py expects with:

    y = page_height - bottom_from_pdfplumber + small_offset(~2)
"""
import sys
from pdf2image import convert_from_path
from PIL import ImageDraw
import pdfplumber


def grid(pdf_path, page_index, dpi=150):
    imgs = convert_from_path(pdf_path, dpi=dpi, first_page=page_index + 1, last_page=page_index + 1)
    img = imgs[0]
    with pdfplumber.open(pdf_path) as pdf:
        pw = pdf.pages[page_index].width
        ph = pdf.pages[page_index].height
    scale_x = img.width / pw
    scale_y = img.height / ph

    draw = ImageDraw.Draw(img)
    step = 20
    for x in range(0, int(pw) + 1, step):
        px = int(x * scale_x)
        draw.line([(px, 0), (px, img.height)], fill=(255, 0, 0, 60), width=1)
        draw.text((px + 2, 2), str(x), fill=(200, 0, 0))
    for ytop in range(0, int(ph) + 1, step):
        py = int(ytop * scale_y)
        draw.line([(0, py), (img.width, py)], fill=(0, 0, 255, 60), width=1)
        draw.text((2, py + 1), str(ytop), fill=(0, 0, 200))

    out = f"calibration_{page_index}.png"
    img.save(out)
    print(f"Saved {out} — red numbers are x (left->right), blue numbers are "
          f"'top' (distance from the TOP of the page), matching pdfplumber's "
          f"coordinate system.")


def words(pdf_path, page_index):
    with pdfplumber.open(pdf_path) as pdf:
        p = pdf.pages[page_index]
        print(f"page size: {p.width} x {p.height}")
        for w in p.extract_words(use_text_flow=False, keep_blank_chars=False):
            print(f"{w['x0']:.1f}\t{w['top']:.1f}\t{w['x1']:.1f}\t{w['bottom']:.1f}\t{w['text']!r}")


if __name__ == "__main__":
    if len(sys.argv) < 4:
        print(__doc__)
        sys.exit(1)
    cmd, path, idx = sys.argv[1], sys.argv[2], int(sys.argv[3])
    if cmd == "grid":
        grid(path, idx)
    elif cmd == "words":
        words(path, idx)
    else:
        print(__doc__)
