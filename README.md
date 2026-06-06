# MakeMyPage Render Service

Small Flask service that renders a marketing-plan JSON payload into a PDF using
Jinja2 and Playwright/Chromium.

## Coolify deployment

- Build pack: Dockerfile
- Base directory: `/`
- Port exposes: `8000`
- Health check path: `/health`
- Start command: defined in `Dockerfile`

The Docker image includes a `HEALTHCHECK` that calls `http://127.0.0.1:8000/health`.

## Endpoints

- `GET /health` returns `{"status":"ok"}`
- `POST /render` accepts the marketing-plan JSON payload and returns a PDF
- `POST /render/logo-vorschlag` accepts the logo proposal JSON payload and returns a PDF
- `POST /render/brand-manual` accepts the brand manual JSON payload and returns a PDF

Aliases without hyphen are also available:

- `POST /render/logovorschlag`
- `POST /render/brandmanual`
