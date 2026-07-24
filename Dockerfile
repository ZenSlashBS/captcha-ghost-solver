FROM python:3.11-slim

# System dependency: the tesseract OCR binary + libs OpenCV needs at runtime.
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Railway injects $PORT at runtime; default to 8000 locally.
ENV PORT=8000
EXPOSE 8000

# gunicorn serves the Flask app (app.py -> `app`).
CMD ["sh", "-c", "gunicorn --bind 0.0.0.0:${PORT} --workers 2 --timeout 60 app:app"]
