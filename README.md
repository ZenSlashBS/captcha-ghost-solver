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

## Two ways to use it

- **CLI** (`solver.py`) — run in Termux / any terminal against a file path.
- **Web app** (`app.py`) — drag-and-drop a captcha, it auto-solves and shows the answer.

The web app imports the same `solve()` from `solver.py`, so the solving logic is shared.

## How it works

1. **Find the grid** — detects the largest square coloured region below the header.
2. **Split into 4×4 cells.**
3. **Locate the ghost** — the ghost is line-art drawn in near-white strokes. The
   top-left number circle (also white) is masked out per cell, then the cell with the
   most remaining white pixels is the ghost cell.
4. **OCR the number** — the ghost cell's top-left circle is cropped, upscaled,
   binarised, and read with `pytesseract` (digits-only whitelist).

---

## CLI usage (Termux)

```bash
pkg update && pkg upgrade -y
pkg install python tesseract libjpeg-turbo libpng -y
pip install opencv-python-headless numpy pytesseract

python solver.py /sdcard/Download/captcha.png
```

Batch and debug:

```bash
python solver.py cap1.png cap2.png cap3.png
python solver.py --debug captcha.png   # dumps crops to ./debug
```

Example output:

```
captcha1.png  ->  answer: 18  (cell r3 c2, score=...)
captcha2.png  ->  answer: 90  (cell r3 c1, score=...)
captcha3.png  ->  answer: 55  (cell r0 c3, score=...)
```

---

## Web app (local)

```bash
pip install -r requirements.txt
# needs the tesseract binary installed (see below)
python app.py
# open http://localhost:8000
```

Drop a captcha image into the box — it uploads, solves, and shows the number instantly.
No button to click.

### API

`POST /solve` with multipart form field `image` returns:

```json
{ "answer": "18", "cell": { "row": 3, "col": 2 }, "score": 1234 }
```

`GET /health` returns `{"status":"ok"}` (used by the Railway health check).

---

## Deploy to Railway (Docker)

The repo ships a `Dockerfile` and `railway.json`, so Railway builds it with Docker and
installs the tesseract binary automatically — no extra config needed.

1. Push this repo to GitHub (already done).
2. On [railway.app](https://railway.app): **New Project → Deploy from GitHub repo** → pick
   `captcha-ghost-solver`.
3. Railway detects the `Dockerfile` and builds. It injects `$PORT` automatically — the
   app already reads it.
4. Once deployed, open the generated URL. Done.

The health check hits `/health`; gunicorn serves the app with 2 workers.

### Run the Docker image locally

```bash
docker build -t ghost-solver .
docker run -p 8000:8000 ghost-solver
# open http://localhost:8000
```

---

## Install notes (desktop, non-Docker)

```bash
# system tesseract binary first:
#   Ubuntu/Debian:  sudo apt install tesseract-ocr
#   macOS (brew):   brew install tesseract
pip install -r requirements.txt
```

## Tuning

If a different captcha theme changes the colours, adjust the constants near the top of
`solver.py`:

- `WHITE_THRESH` — how bright a pixel must be to count as a ghost stroke.
- `CIRCLE_FRAC` — size of the top-left circle region that gets masked / OCR'd.
- `find_grid_bbox` fallback proportions — if grid auto-detection ever misses.

## Files

- `solver.py` — the solver (CLI + shared `solve()` backend).
- `app.py` — Flask web app.
- `templates/index.html` — drag-and-drop UI.
- `Dockerfile` / `railway.json` / `.dockerignore` — deployment.
- `requirements.txt` — Python deps.

## Notes

- Uses only classic CV + OCR — no external API, runs fully offline once tesseract is installed.
- The ghost-detection is colour-agnostic (works across the blue/cyan/green themes)
  because it keys on the white line-art, not the cell colour.
