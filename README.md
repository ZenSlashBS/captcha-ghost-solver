# 👻 Captcha Solver — Ghost Grid

Solves the *"Select the number assigned in the box where the image is placed"* captcha.

The captcha is a **4×4 grid**. One cell contains a **ghost** icon. Every cell has a small
numbered circle in its **top-left corner**. The answer is the number printed in the
circle of the cell that holds the ghost.

```
+--------+--------+--------+--------+
| (22)   | (17)   | (52)   | (6)    |
+--------+--------+--------+--------+
| (68)   | (19)   | (90)   | (66)   |
+--------+--------+--------+--------+
| (4)    | (58)   | (48)   | (33)   |
+--------+--------+--------+--------+
| (30)   | (26)   | (18)👻 | (44)   |   <-- ghost here => answer: 18
+--------+--------+--------+--------+
```

## How it works

1. **Find the grid** — detects the largest square coloured region below the header.
2. **Split into 4×4 cells.**
3. **Locate the ghost** — the ghost is line-art drawn in near-white strokes. The
   top-left number circle (also white) is masked out per cell, then the cell with the
   most remaining white pixels is the ghost cell.
4. **OCR the number** — the ghost cell's top-left circle is cropped, upscaled,
   binarised, and read with `pytesseract` (digits-only whitelist).

## Install (Termux)

```bash
pkg update && pkg upgrade -y
pkg install python tesseract libjpeg-turbo libpng -y
pip install opencv-python-headless numpy pytesseract
```

> On Termux use `opencv-python-headless` (the plain `opencv-python` needs a display).
> On desktop Linux, either works.

## Install (desktop)

```bash
# system tesseract binary first:
#   Ubuntu/Debian:  sudo apt install tesseract-ocr
#   macOS (brew):   brew install tesseract
pip install -r requirements.txt
```

## Usage

```bash
# single image — give it the path to your captcha
python solver.py /sdcard/Download/captcha.png

# batch
python solver.py cap1.png cap2.png cap3.png

# debug mode dumps the detected grid / ghost cell / circle crop into ./debug
python solver.py --debug captcha.png
```

### Example output

```
captcha1.png  ->  answer: 18  (cell r3 c2, score=...)
captcha2.png  ->  answer: 90  (cell r3 c1, score=...)
captcha3.png  ->  answer: 55  (cell r0 c3, score=...)
```

## Verified answers for the sample captchas

| Sample     | Ghost location         | Answer |
|------------|------------------------|--------|
| captcha 1  | bottom row, 3rd column | **18** |
| captcha 2  | bottom row, 2nd column | **90** |
| captcha 3  | top row, 4th column     | **55** |

## Tuning

If a different captcha theme changes the colours, adjust the constants near the top of
`solver.py`:

- `WHITE_THRESH` — how bright a pixel must be to count as a ghost stroke.
- `CIRCLE_FRAC` — size of the top-left circle region that gets masked / OCR'd.
- `find_grid_bbox` fallback proportions — if grid auto-detection ever misses.

## Files

- `solver.py` — the solver.
- `requirements.txt` — Python deps.
- `samples/` — put your example captchas here.

## Notes

- Uses only classic CV + OCR — no external API, runs fully offline once tesseract is installed.
- The ghost-detection is colour-agnostic (works across the blue/cyan/green themes)
  because it keys on the white line-art, not the cell colour.
