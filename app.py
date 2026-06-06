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
import re
import tempfile
from pathlib import Path

from flask import Flask, request, send_file, jsonify
from jinja2 import Environment, FileSystemLoader, meta, select_autoescape
from markupsafe import Markup
from playwright.sync_api import sync_playwright

app = Flask(__name__)

TEMPLATE_DIR = Path(__file__).parent
MARKETING_TEMPLATE_NAME = "marketingplan_template_makemypage.html"
LOGO_TEMPLATE_NAME = "logo-abstimmung-template.html"
BRAND_MANUAL_TEMPLATE_NAME = "brand-manual-template.html"

# erwartete Top-Level-Schlüssel (Konsistenz-Check, optional aber hilfreich)
MARKETING_REQUIRED_KEYS = [
    "meta", "cover", "toc", "projektziele", "zielgruppe", "ist1", "ist2",
    "optTraffic", "optConversion", "nurturing", "salesFunnel", "massnahmen", "closing",
]

HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
LOGO_VISUAL_KEYS = [f"LOGO_{i}_VISUAL" for i in range(1, 7)]

env = Environment(
    loader=FileSystemLoader(str(TEMPLATE_DIR)),
    autoescape=select_autoescape(["html"]),
)


def strip_html_comments(source):
    return HTML_COMMENT_RE.sub("", source)


def template_required_keys(template_name):
    source = (TEMPLATE_DIR / template_name).read_text(encoding="utf-8")
    source = strip_html_comments(source)
    parsed = env.parse(source)
    return sorted(meta.find_undeclared_variables(parsed))


LOGO_REQUIRED_KEYS = template_required_keys(LOGO_TEMPLATE_NAME)
BRAND_MANUAL_REQUIRED_KEYS = template_required_keys(BRAND_MANUAL_TEMPLATE_NAME)


def json_payload():
    try:
        data = request.get_json(force=True)
    except Exception as e:
        return None, jsonify(error=f"Ungueltiges JSON: {e}"), 400
    if not isinstance(data, dict):
        return None, jsonify(error="Body muss ein JSON-Objekt sein."), 400
    return data, None, None


def safe_filename(value, fallback):
    safe = "".join(
        c if c.isalnum() or c in " -_" else "_"
        for c in str(value or fallback)
    ).strip().replace(" ", "_")
    return safe or fallback


def render_template_html(template_name, data, *, safe_keys=None, strip_comments=False):
    render_data = dict(data)
    for key in safe_keys or []:
        if key in render_data and render_data[key] is not None:
            render_data[key] = Markup(str(render_data[key]))

    if strip_comments:
        source = (TEMPLATE_DIR / template_name).read_text(encoding="utf-8")
        source = strip_html_comments(source)
        return env.from_string(source).render(**render_data)

    return env.get_template(template_name).render(**render_data)


def html_to_pdf_bytes(html):
    with tempfile.TemporaryDirectory() as tmp:
        html_path = Path(tmp) / "page.html"
        pdf_path = Path(tmp) / "out.pdf"
        html_path.write_text(html, encoding="utf-8")
        with sync_playwright() as p:
            browser = p.chromium.launch(args=["--no-sandbox"])
            page = browser.new_page()
            page.goto(html_path.as_uri(), wait_until="networkidle")
            page.pdf(
                path=str(pdf_path),
                prefer_css_page_size=True,
                print_background=True,
            )
            browser.close()
        return pdf_path.read_bytes()


def render_pdf(template_name, data, *, required_keys, download_prefix,
               filename_value, safe_keys=None, strip_comments=False):
    missing = [k for k in required_keys if k not in data]
    if missing:
        return jsonify(error=f"Fehlende Schluessel: {missing}"), 400

    try:
        html = render_template_html(
            template_name,
            data,
            safe_keys=safe_keys,
            strip_comments=strip_comments,
        )
    except Exception as e:
        return jsonify(error=f"Template-Render-Fehler: {e}"), 400

    try:
        pdf_bytes = html_to_pdf_bytes(html)
    except Exception as e:
        return jsonify(error=f"PDF-Render-Fehler: {e}"), 500

    safe = safe_filename(filename_value, "Kunde")
    return send_file(
        io.BytesIO(pdf_bytes),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=f"{download_prefix}_{safe}.pdf",
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
        return jsonify(error=f"Ungueltiges JSON: {e}"), 400
    if not isinstance(data, dict):
        return jsonify(error="Body muss ein JSON-Objekt sein."), 400

    # 2) Pflichtschlüssel prüfen
    missing = [k for k in MARKETING_REQUIRED_KEYS if k not in data]
    if missing:
        return jsonify(error=f"Fehlende Schluessel: {missing}"), 400

    # 3) Jinja2 rendern
    try:
        html = env.get_template(MARKETING_TEMPLATE_NAME).render(**data)
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


@app.post("/render/logo-vorschlag")
@app.post("/render/logovorschlag")
def render_logo_vorschlag():
    data, error_response, status_code = json_payload()
    if error_response:
        return error_response, status_code

    return render_pdf(
        LOGO_TEMPLATE_NAME,
        data,
        required_keys=LOGO_REQUIRED_KEYS,
        download_prefix="Logovorschlag",
        filename_value=data.get("CLIENT_COMPANY") or data.get("PROJECT_NAME"),
        safe_keys=LOGO_VISUAL_KEYS,
        strip_comments=True,
    )


@app.post("/render/brand-manual")
@app.post("/render/brandmanual")
def render_brand_manual():
    data, error_response, status_code = json_payload()
    if error_response:
        return error_response, status_code

    return render_pdf(
        BRAND_MANUAL_TEMPLATE_NAME,
        data,
        required_keys=BRAND_MANUAL_REQUIRED_KEYS,
        download_prefix="Brand_Manual",
        filename_value=data.get("COMPANY_NAME") or data.get("COMPANY_LEGAL_NAME"),
        strip_comments=True,
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
