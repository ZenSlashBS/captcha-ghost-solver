import os
import uuid
import tempfile

from flask import Flask, request, jsonify, render_template

from solver import solve, VERSION

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024  # 8 MB upload cap

ALLOWED = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}


@app.route("/")
def index():
    return render_template("index.html", version=VERSION)


@app.route("/solve", methods=["POST"])
def solve_endpoint():
    if "image" not in request.files:
        return jsonify({"error": "No image uploaded."}), 400

    f = request.files["image"]
    if not f.filename:
        return jsonify({"error": "Empty filename."}), 400

    ext = os.path.splitext(f.filename)[1].lower()
    if ext not in ALLOWED:
        return jsonify({"error": f"Unsupported file type: {ext}"}), 400

    tmp_path = os.path.join(tempfile.gettempdir(), f"{uuid.uuid4().hex}{ext}")
    f.save(tmp_path)

    try:
        result = solve(tmp_path)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass

    answer = result.get("answer")
    if not answer:
        return jsonify({
            "error": "Could not read the number. Try a clearer image.",
            "detail": result,
        }), 422

    return jsonify({
        "answer": answer,
        "cell": {"row": result["ghost_cell_row"], "col": result["ghost_cell_col"]},
        "score": result["ghost_score"],
        "version": VERSION,
    })


@app.route("/version")
def version():
    return jsonify({"version": VERSION})


@app.route("/health")
def health():
    return jsonify({"status": "ok", "version": VERSION})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port)
