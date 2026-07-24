#!/usr/bin/env python3
"""
Captcha Solver — "Select the number assigned in the box where the image is placed"

The captcha is a 4x4 grid. One cell contains a ghost icon (line-art drawn in
white/light strokes). Every cell has a small numbered circle in its TOP-LEFT
corner. The correct answer is the number printed in the circle of the cell that
holds the ghost.

Strategy
--------
1. Locate the grid region (the large square below the teal header).
2. Split it into a 4x4 matrix of cells.
3. Detect which cell holds the ghost:
     - The ghost is drawn with near-white strokes on a coloured cell.
     - We ignore the top-left circle area (which is also white) so it does not
       fool the detector, then count the remaining white ghost pixels per cell.
     - The cell with the most "white stroke" pixels (excluding its circle) wins.
4. OCR the number inside that winning cell's top-left circle with pytesseract.

Usage
-----
    python solver.py path/to/captcha.png
    python solver.py img1.png img2.png img3.png      # batch
    python solver.py --debug path/to/captcha.png     # dumps crops to ./debug

Requires: opencv-python, numpy, pytesseract  (+ the tesseract binary)
"""

import sys
import os
import cv2
import numpy as np

try:
    import pytesseract
except ImportError:
    pytesseract = None

# ----------------------------------------------------------------------------
# Tuning constants
# ----------------------------------------------------------------------------
GRID_ROWS = 4
GRID_COLS = 4

# Fraction of a cell (from its top-left corner) occupied by the number circle.
# We blank this region out before counting ghost pixels so the white circle
# does not get mistaken for the ghost.
CIRCLE_FRAC = 0.34

# A pixel counts as "white stroke" if all channels are above this value.
WHITE_THRESH = 205


def find_grid_bbox(img):
    """
    Find the bounding box of the 4x4 grid.

    The grid is the big square below the teal title bar and above the teal
    footer. We detect it by finding the largest roughly-square contour in the
    central area of the image. Falls back to a proportional crop if that fails.
    """
    h, w = img.shape[:2]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # The grid cells are coloured; background is white. Threshold to isolate
    # non-white (coloured) regions, then find the big blob.
    _, mask = cv2.threshold(gray, 245, 255, cv2.THRESH_BINARY_INV)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    best = None
    best_area = 0
    for c in contours:
        x, y, cw, ch = cv2.boundingRect(c)
        area = cw * ch
        aspect = cw / float(ch) if ch else 0
        # square-ish, large, and sitting in the middle band of the image
        if 0.75 < aspect < 1.3 and area > best_area and area > 0.15 * w * h:
            best = (x, y, cw, ch)
            best_area = area

    if best is not None:
        return best

    # Fallback: fixed proportions tuned to the sample layout.
    x0 = int(0.035 * w)
    x1 = int(0.745 * w)
    y0 = int(0.185 * h)
    y1 = int(0.895 * h)
    return (x0, y0, x1 - x0, y1 - y0)


def split_cells(grid):
    """Return a 2D list of (cell_img, (r, c)) for the 4x4 grid."""
    gh, gw = grid.shape[:2]
    ch = gh // GRID_ROWS
    cw = gw // GRID_COLS
    cells = []
    for r in range(GRID_ROWS):
        row = []
        for c in range(GRID_COLS):
            y0, y1 = r * ch, (r + 1) * ch
            x0, x1 = c * cw, (c + 1) * cw
            row.append((grid[y0:y1, x0:x1], (r, c)))
        cells.append(row)
    return cells, ch, cw


def white_ghost_score(cell):
    """
    Count near-white pixels in a cell, EXCLUDING the top-left circle region.

    The ghost is line-art in white strokes. The numbered circle is also white,
    so we mask it out first. The cell holding the ghost will have many more
    remaining white pixels than any other cell.
    """
    work = cell.copy()
    ch, cw = work.shape[:2]

    # Blank out the top-left circle area.
    cy = int(ch * CIRCLE_FRAC)
    cx = int(cw * CIRCLE_FRAC)
    work[0:cy, 0:cx] = (0, 0, 0)

    b, g, r = cv2.split(work)
    white = (b > WHITE_THRESH) & (g > WHITE_THRESH) & (r > WHITE_THRESH)
    return int(np.count_nonzero(white))


def locate_ghost(cells):
    """Return the (r, c) of the cell most likely to hold the ghost."""
    best_rc = (0, 0)
    best_score = -1
    for row in cells:
        for cell, rc in row:
            score = white_ghost_score(cell)
            if score > best_score:
                best_score = score
                best_rc = rc
    return best_rc, best_score


def extract_circle(cell):
    """Crop the top-left numbered circle from a cell for OCR."""
    ch, cw = cell.shape[:2]
    cy = int(ch * CIRCLE_FRAC)
    cx = int(cw * CIRCLE_FRAC)
    return cell[0:cy, 0:cx]


def ocr_number(circle_img):
    """Read the digits inside the circle crop using pytesseract."""
    if pytesseract is None:
        raise RuntimeError(
            "pytesseract is not installed. Run: pip install pytesseract "
            "and install the tesseract binary (pkg install tesseract on Termux)."
        )

    # Upscale for better OCR on small text.
    scaled = cv2.resize(circle_img, None, fx=4, fy=4, interpolation=cv2.INTER_CUBIC)
    gray = cv2.cvtColor(scaled, cv2.COLOR_BGR2GRAY)

    # The circle has a white fill with black digits. Binarise to black text on
    # white background (Otsu handles the varying cell colours around it).
    _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    # Ensure dark text on light background.
    if np.mean(thresh) < 127:
        thresh = cv2.bitwise_not(thresh)

    config = "--psm 7 -c tessedit_char_whitelist=0123456789"
    text = pytesseract.image_to_string(thresh, config=config)
    digits = "".join(ch for ch in text if ch.isdigit())
    return digits


def solve(path, debug=False):
    img = cv2.imread(path)
    if img is None:
        raise FileNotFoundError(f"Could not read image: {path}")

    x, y, gw, gh = find_grid_bbox(img)
    grid = img[y:y + gh, x:x + gw]

    cells, ch, cw = split_cells(grid)
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
            result = solve(path, debug=debug)
            print(
                f"{result['path']}  ->  answer: {result['answer'] or '??'}  "
                f"(cell r{result['ghost_cell_row']} c{result['ghost_cell_col']}, "
                f"score={result['ghost_score']})"
            )
        except Exception as e:
            print(f"{path}  ->  ERROR: {e}")


if __name__ == "__main__":
    main()
