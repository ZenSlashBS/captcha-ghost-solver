#!/usr/bin/env python3
"""
Captcha Solver — "Select the number assigned in the box where the image is placed"

The captcha is a 4x4 grid. One cell contains a ghost icon (line-art drawn in
white/light strokes). Every cell has a small numbered circle in its TOP-LEFT
corner. The correct answer is the number printed in the circle of the cell that
holds the ghost.

Pipeline
--------
1. Locate the grid square (robust: strips the teal header/footer bands first).
2. Split it into a 4x4 matrix of cells.
3. Detect which cell holds the ghost (white line-art, circle region masked out).
4. Find the white number-circle inside that cell precisely (contour), then OCR
   the digits with several preprocessing passes until one yields digits.

Usage
-----
    python solver.py path/to/captcha.png
    python solver.py img1.png img2.png img3.png      # batch
    python solver.py --debug path/to/captcha.png     # dumps crops to ./debug

Requires: opencv-python(-headless), numpy, pytesseract  (+ tesseract binary)
"""

import sys
import os
import cv2
import numpy as np

try:
    import pytesseract
except ImportError:
    pytesseract = None

GRID_ROWS = 4
GRID_COLS = 4

# A pixel counts as "white" (ghost stroke or circle fill) if every channel is
# above this value. Kept a little lenient so anti-aliased strokes still count.
WHITE_THRESH = 200

# Fraction of the cell (top-left) searched for the number circle.
CIRCLE_SEARCH_FRAC = 0.40


# ---------------------------------------------------------------------------
# Grid location
# ---------------------------------------------------------------------------
def find_grid_bbox(img):
    """
    Return (x, y, w, h) of the 4x4 grid.

    The captcha has a teal header band at the top and a teal footer band at the
    bottom; the coloured grid sits between them on a white page. Naively taking
    the largest coloured blob can grab the header, so we:

      1. Build a mask of all non-white pixels.
      2. Zero out the teal bands (detected by their strong teal hue) so only the
         grid cells remain.
      3. Take the largest remaining roughly-square contour.

    Falls back to proportional crop if detection is unconvincing.
    """
    h, w = img.shape[:2]
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # Non-white mask.
    _, nonwhite = cv2.threshold(gray, 244, 255, cv2.THRESH_BINARY_INV)

    # Teal band mask (the header/footer). Teal ~ hue 85-110 in OpenCV's 0-180.
    teal = cv2.inRange(hsv, (85, 60, 60), (110, 255, 200))
    teal = cv2.dilate(teal, np.ones((5, 5), np.uint8), iterations=2)

    # Remove teal from the non-white mask -> only grid cells (and stray text).
    grid_mask = cv2.bitwise_and(nonwhite, cv2.bitwise_not(teal))
    grid_mask = cv2.morphologyEx(
        grid_mask, cv2.MORPH_CLOSE, np.ones((15, 15), np.uint8)
    )

    contours, _ = cv2.findContours(
        grid_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )

    best, best_area = None, 0
    for c in contours:
        x, y, cw, ch = cv2.boundingRect(c)
        area = cw * ch
        aspect = cw / float(ch) if ch else 0
        if 0.80 < aspect < 1.25 and area > best_area and area > 0.18 * w * h:
            best, best_area = (x, y, cw, ch), area

    if best is not None:
        return best

    # Fallback proportions tuned to the sample layout.
    x0, x1 = int(0.035 * w), int(0.745 * w)
    y0, y1 = int(0.185 * h), int(0.895 * h)
    return (x0, y0, x1 - x0, y1 - y0)


def split_cells(grid):
    gh, gw = grid.shape[:2]
    ch, cw = gh // GRID_ROWS, gw // GRID_COLS
    cells = []
    for r in range(GRID_ROWS):
        row = []
        for c in range(GRID_COLS):
            row.append((grid[r * ch:(r + 1) * ch, c * cw:(c + 1) * cw], (r, c)))
        cells.append(row)
    return cells, ch, cw


# ---------------------------------------------------------------------------
# Ghost location
# ---------------------------------------------------------------------------
def white_mask(bgr):
    b, g, r = cv2.split(bgr)
    return (b > WHITE_THRESH) & (g > WHITE_THRESH) & (r > WHITE_THRESH)


def ghost_score(cell):
    """
    White-stroke pixel count in a cell, with the top-left circle region masked
    so the number circle (also white) doesn't inflate the score.
    """
    work = cell.copy()
    ch, cw = work.shape[:2]
    cy, cx = int(ch * CIRCLE_SEARCH_FRAC), int(cw * CIRCLE_SEARCH_FRAC)
    work[0:cy, 0:cx] = 0
    return int(np.count_nonzero(white_mask(work)))


def locate_ghost(cells):
    best_rc, best = (0, 0), -1
    for row in cells:
        for cell, rc in row:
            s = ghost_score(cell)
            if s > best:
                best, best_rc = s, rc
    return best_rc, best


# ---------------------------------------------------------------------------
# Number circle extraction + OCR
# ---------------------------------------------------------------------------
def extract_circle(cell):
    """
    Precisely crop the small white number-circle from a cell's top-left area.

    We search the top-left region for the white circle blob (its fill is bright),
    take its bounding box, and return a tight, padded crop. Falls back to a
    fixed proportional crop if no clean blob is found.
    """
    ch, cw = cell.shape[:2]
    sy, sx = int(ch * CIRCLE_SEARCH_FRAC), int(cw * CIRCLE_SEARCH_FRAC)
    region = cell[0:sy, 0:sx]

    mask = white_mask(region).astype(np.uint8) * 255
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    best, best_area = None, 0
    for c in contours:
        x, y, bw, bh = cv2.boundingRect(c)
        area = bw * bh
        aspect = bw / float(bh) if bh else 0
        # A circle is roughly square and a decent chunk of the search region.
        if 0.6 < aspect < 1.7 and area > best_area and area > 0.05 * sy * sx:
            best, best_area = (x, y, bw, bh), area

    if best is not None:
        x, y, bw, bh = best
        pad = int(0.12 * max(bw, bh))
        x0, y0 = max(0, x - pad), max(0, y - pad)
        x1, y1 = min(sx, x + bw + pad), min(sy, y + bh + pad)
        return region[y0:y1, x0:x1]

    return region  # fallback: whole search region


def _ocr_variants(gray):
    """Yield several binarised versions of the circle for OCR to try."""
    # Otsu.
    _, otsu = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    yield otsu
    yield cv2.bitwise_not(otsu)
    # Fixed thresholds catch cases Otsu splits badly.
    for t in (110, 140, 170):
        _, b = cv2.threshold(gray, t, 255, cv2.THRESH_BINARY)
        yield b
        yield cv2.bitwise_not(b)
    # Adaptive.
    adp = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 21, 8
    )
    yield adp
    yield cv2.bitwise_not(adp)


def ocr_number(circle_img):
    """
    Read digits from the circle crop. Tries multiple upscales, binarisations,
    and tesseract page-segmentation modes; returns the most-voted result.
    """
    if pytesseract is None:
        raise RuntimeError(
            "pytesseract not installed. pip install pytesseract and install the "
            "tesseract binary (pkg install tesseract on Termux)."
        )

    base = cv2.cvtColor(circle_img, cv2.COLOR_BGR2GRAY)
    whitelist = "-c tessedit_char_whitelist=0123456789"

    candidates = {}  # digits -> vote count
    for scale in (4, 6, 8):
        up = cv2.resize(base, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
        for variant in _ocr_variants(up):
            # Ensure dark text on light background (tesseract prefers it).
            v = variant if np.mean(variant) >= 127 else cv2.bitwise_not(variant)
            v = cv2.copyMakeBorder(v, 12, 12, 12, 12, cv2.BORDER_CONSTANT, value=255)
            for psm in (7, 8, 10, 6):
                cfg = f"--psm {psm} {whitelist}"
                text = pytesseract.image_to_string(v, config=cfg)
                digits = "".join(c for c in text if c.isdigit())
                if 1 <= len(digits) <= 3:
                    candidates[digits] = candidates.get(digits, 0) + 1

    if not candidates:
        return ""
    # Most-voted reading wins; ties broken by longer (2-digit) numbers.
    return max(candidates, key=lambda d: (candidates[d], len(d)))


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------
def solve(path, debug=False):
    img = cv2.imread(path)
    if img is None:
        raise FileNotFoundError(f"Could not read image: {path}")

    x, y, gw, gh = find_grid_bbox(img)
    grid = img[y:y + gh, x:x + gw]
    cells, _, _ = split_cells(grid)
    (gr, gc), score = locate_ghost(cells)

    ghost_cell = cells[gr][gc][0]
    circle = extract_circle(ghost_cell)
    number = ocr_number(circle)

    if debug:
        os.makedirs("debug", exist_ok=True)
        base = os.path.splitext(os.path.basename(path))[0]
        cv2.imwrite(f"debug/{base}_grid.png", grid)
        cv2.imwrite(f"debug/{base}_ghost_cell.png", ghost_cell)
        cv2.imwrite(f"debug/{base}_circle.png", circle)

    return {
        "path": path,
        "ghost_cell_row": gr,
        "ghost_cell_col": gc,
        "ghost_score": score,
        "answer": number,
    }


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    debug = "--debug" in sys.argv
    if not args:
        print("Usage: python solver.py [--debug] <captcha.png> [more.png ...]")
        sys.exit(1)
    for path in args:
        try:
            r = solve(path, debug=debug)
            print(
                f"{r['path']}  ->  answer: {r['answer'] or '??'}  "
                f"(cell r{r['ghost_cell_row']} c{r['ghost_cell_col']}, "
                f"score={r['ghost_score']})"
            )
        except Exception as e:
            print(f"{path}  ->  ERROR: {e}")


if __name__ == "__main__":
    main()
