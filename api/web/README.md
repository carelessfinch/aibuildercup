# web — Cloud Run UI (W5)

FastAPI backend + React (Vite, TypeScript) frontend, deployed as one Cloud
Run service on Project A. API: `POST /runs`, SSE
`GET /runs/{id}/events`, plots, `POST /runs/{id}/signoff`. The headline timer
runs from submit to human sign-off (I3), and judge-link limits are wired from
environment/config (J4/J5).

## Local run

```bash
uv run python -m web.backend          # API on http://127.0.0.1:8000
cd web/frontend && npm install && npm run dev
```

Vite proxies `/runs` and `/health` to the API. `WEB_FLOW_BACKEND=mock` uses the
demo research-group progression; W3's ADK adapter implements the same
`RunFlow` protocol in `web/backend/store.py`.
