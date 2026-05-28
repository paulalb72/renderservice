"""
MakeMyPage Marketingplan – Render-Service
JSON (vom n8n-LLM-Node)  ->  Jinja2-Template  ->  Chromium  ->  PDF

Start lokal:
    pip install -r requirements.txt
    playwright install chromium
    gunicorn -b 0.0.0.0:8000 -w 2 -t 120 app:app

Endpunkte:
    GET  /health   -> {"status": "ok"}
    POST /render   -> Body: das JSON des LLM-Nodes; Antwort: application/pdf
"""

import io
import tempfile
from pathlib import Path

from flask import Flask, request, send_file, jsonify
from jinja2 import Environment, FileSystemLoader, select_autoescape
from playwright.sync_api import sync_playwright

app = Flask(__name__)

TEMPLATE_DIR = Path(__file__).parent
TEMPLATE_NAME = "marketingplan_template_makemypage.html"   # muss neben app.py liegen

# erwartete Top-Level-Schlüssel (Konsistenz-Check, optional aber hilfreich)
REQUIRED_KEYS = [
    "meta", "cover", "toc", "projektziele", "zielgruppe", "ist1", "ist2",
    "optTraffic", "optConversion", "nurturing", "salesFunnel", "massnahmen", "closing",
]

env = Environment(
    loader=FileSystemLoader(str(TEMPLATE_DIR)),
    autoescape=select_autoescape(["html"]),
)


@app.get("/health")
def health():
    return jsonify(status="ok")


@app.post("/render")
def render():
    # 1) JSON entgegennehmen
    try:
        data = request.get_json(force=True)
    except Exception as e:
        return jsonify(error=f"Ungültiges JSON: {e}"), 400
    if not isinstance(data, dict):
        return jsonify(error="Body muss ein JSON-Objekt sein."), 400

    # 2) Pflichtschlüssel prüfen
    missing = [k for k in REQUIRED_KEYS if k not in data]
    if missing:
        return jsonify(error=f"Fehlende Schlüssel: {missing}"), 400

    # 3) Jinja2 rendern
    try:
        html = env.get_template(TEMPLATE_NAME).render(**data)
    except Exception as e:
        return jsonify(error=f"Template-Render-Fehler: {e}"), 400

    # 4) Chromium -> PDF
    try:
        with tempfile.TemporaryDirectory() as tmp:
            html_path = Path(tmp) / "page.html"
            pdf_path = Path(tmp) / "out.pdf"
            html_path.write_text(html, encoding="utf-8")
            with sync_playwright() as p:
                browser = p.chromium.launch(args=["--no-sandbox"])
                page = browser.new_page()
                page.goto(html_path.as_uri(), wait_until="networkidle")
                page.pdf(path=str(pdf_path),
                         prefer_css_page_size=True,
                         print_background=True)
                browser.close()
            pdf_bytes = pdf_path.read_bytes()
    except Exception as e:
        return jsonify(error=f"PDF-Render-Fehler: {e}"), 500

    # 5) Dateiname aus Kundenname ableiten und PDF zurückgeben
    client = (data.get("meta", {}) or {}).get("clientName", "Marketingplan")
    safe = "".join(c if c.isalnum() or c in " -_" else "_" for c in str(client)).strip().replace(" ", "_")
    return send_file(
        io.BytesIO(pdf_bytes),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=f"Marketingplan_{safe or 'Kunde'}.pdf",
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
