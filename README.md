# Plasma Research Group — AI Builder Cup 2026

A multi-agent "research group" (Professor, Postdoc, PhD agents) on Google Cloud
that turns 4M experiment metadata (Machine, Material, Method, Man) into a
validated plasma simulation with a human sign-off. Headline KPI: about 2 hours
of expert simulation set-up down to 20 minutes.

## Layout

| Folder | What it is |
|---|---|
| `api/` | Backend: ADK agents and role contracts, `simtools` solver interface, `litrag` literature search, FastAPI research API (`web/backend`), eval suite and KPI harness, design docs (`docs/`). See `api/README.md`. |
| `frontend/` | React (CRA + craco, Tailwind, shadcn/ui) research workspace: chat, literature search, validation flow. See `frontend/README.md`. |
| `infra/` | Cloud Run deployment: `deploy.sh`, the `rag-api` literature service, the frontend Dockerfile and nginx config, and a password-hashing helper. |

## Quick start

```bash
# backend
cd api && uv sync && uv run pytest -q

# frontend
cd frontend/frontend && npm install --legacy-peer-deps && npm start
```

## What is deliberately not included

To keep this bundle free of confidential and copyrighted material, these are left out:

- The literature corpus (copyrighted PDFs), its extracted text, the search index and embeddings. `api/litrag/sources.json` lists the citations; build your own index with `python -m litrag`.
- Real lab records and any training data, LoRA adapters or model weights. The EmbeddingGemma query model is downloaded from Google's public bucket at build time.
- Demo account passwords, `.env` files, service-account keys and Secret Manager values. `infra/deploy.sh` creates or reads secrets at deploy time and needs a `demo-users.json` you generate with `infra/tools/hash_password.py`.
- Git history, `node_modules`, virtualenvs and build output.

All eval cases and fixtures under `api/evals` are synthetic or taken from published models (Lieberman & Lichtenberg; Kimura & Noto 2006).
