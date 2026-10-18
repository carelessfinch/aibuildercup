# rag-api: the literature RAG on Google Cloud

A FastAPI service on Cloud Run that serves the group's plasma and etching literature to the frontend. It has two parts:

- **Search** (`/v1/search`, `/v1/sources`, page reads): litrag's hybrid search (BM25 keywords plus EmbeddingGemma vectors) over 2,094 passages from 10 books and papers. No LLM, so it's fast and free.
- **Agents** (`/v1/chat`, `/v1/chat/stream`): two ADK agents on Gemini 3.8 Flash (through Agent Platform) that call litrag's tools and answer with citations. `literature_assistant` answers questions; `professor_reviewer` checks a simulation setup or result against the literature and gives a PASS / REVISE / ESCALATE verdict.

The frontend contract (endpoints, JSON shapes, streaming example) is in [API.md](API.md).

```
browser (the frontend)
   │  HTTPS, JSON / Server-Sent Events
   ▼
Cloud Run service "rag-api"  (runs as sa-agents)
   ├─ FastAPI routes
   ├─ ADK Runner ─► literature_assistant / professor_reviewer ─► Gemini 3.8 Flash (Agent Platform)
   │                         └─ tools: search_literature, read_source_pages, list_literature_sources
   └─ litrag index in memory ◄── copied at startup from gs://PROJECT_A-litrag-index/index/ (private)
```

## What's in this folder

| Path | What |
|---|---|
| `app/main.py` | FastAPI app: routes, sessions, streaming, rate limits |
| `app/agents.py` | The two ADK agents and their instructions |
| `app/config.py` | Every setting, read from environment variables |
| `app/index_store.py` | Copies the private index from Cloud Storage and loads it |
| `litrag/` | Copy of the litrag package from the RAG build (code only) |
| `tests/test_api.py` | End-to-end API tests with a scripted stand-in for Gemini |
| `Dockerfile` | The container Cloud Run runs |
| `API.md` | Guide for the frontend |

It's self-contained, so it can go in the repo as e.g. `services/rag-api/`. The index, corpus and model files are **not** here and must never go in the public repo (`.gitignore` covers them): they're derived from copyrighted books and papers. `litrag/` is a copy; if you change litrag elsewhere, copy it here again.

## Settings (Cloud Run environment variables)

| Variable | Value | Notes |
|---|---|---|
| `GEMINI_MODEL` | `gemini-3.8-flash` | Change here when a newer model ships; no code change |
| `GOOGLE_GENAI_USE_VERTEXAI` | `TRUE` | Call Gemini through Agent Platform (paid, no training on our data), not an AI Studio key |
| `GOOGLE_CLOUD_PROJECT` | your project A id | |
| `GOOGLE_CLOUD_LOCATION` | `global` or your region | Whatever worked for Gemini in Part 1 of the console walkthrough |
| `LITRAG_INDEX_URI` | `gs://PROJECT_A-litrag-index/index` | Where you uploaded the index |
| `CORS_ORIGINS` | `*` while building; later the frontend's URL(s), comma-separated | |
| `AUTH_SECRET`, `SERVICE_KEY`, `DEMO_USERS` | Secret Manager references | Login and protected-route authorization; set all three in deployment. `X-Service-Key` is for research-api only |
| `LOGIN_PER_MINUTE_PER_IP` | `5` | Login-attempt limit per instance |
| `CHAT_PER_MINUTE_PER_IP`, `CHAT_PER_DAY_TOTAL`, `SEARCH_PER_MINUTE_PER_IP` | 10, 2000, 60 | Spending brakes for the open demo link. Counters are per instance |

## Deploy it (Cloud Console)

This uses these names: project A, bucket `PROJECT_A-litrag-index`, service account `sa-agents` (it already has Agent Platform User and read access to that bucket, which is exactly what this service needs).

### 1. Upload the index (once, and again whenever the index is rebuilt)

1. Download `litrag-index.zip` (attached in the project thread; it's private) and unzip it. You get a folder called `index` with `meta.json`, `chunks.jsonl`, `embeddings.npy`, `pages/` and a few more.
2. **Cloud Storage → Buckets → PROJECT_A-litrag-index → Upload → Upload folder**, and pick that `index` folder.
3. Check that `PROJECT_A-litrag-index/index/meta.json` exists.

**Why a bucket:** the index is derived from copyrighted books, so it can't be in the public repo or the image. Cloud Run copies it to the container's disk at startup (9 MB, a second or two).

### 2. Create the Cloud Run service

Once this folder is in the GitHub repo:

1. **Cloud Run → Deploy container → Service**, then choose **Continuously deploy from a repository**, and **Set up with Cloud Build**.
2. Connect GitHub if asked, pick `aleddo-pj/plasma-etch-agents`, branch `^main$`.
3. Build type **Dockerfile**, source location `/services/rag-api/Dockerfile` (or wherever you put this folder). Save.
4. Service name `rag-api`, your region.
5. **Authentication: Allow public access**, so the browser can reach `/health` and login. Protected `/v1` routes require a bearer token; the service key is only for research-api.
6. **Billing: Request-based**. **Service scaling: min 0, max 3** instances.
7. Open **Containers, Volumes, Networking, Security**:
   - Container port `8080`. Memory **2 GiB**, CPU **2**. Turn on **Startup CPU boost**.
   - Request timeout `300` seconds (an agent answer can take a while). Max concurrent requests per instance `20`.
   - **Variables & Secrets**: add the variables from the table above.
   - **Security tab → Service account: `sa-agents`**.
   - **Networking tab: Session affinity on**, so a user's follow-up messages go to the instance holding their conversation.
8. **Create**. The first build takes several minutes.

**Before the repo is ready**, you can deploy straight from this folder instead: open Cloud Shell, upload the `rag-api` folder (⋮ menu → Upload), `cd` into it and run `gcloud run deploy rag-api --source . --region REGION`. It asks the same questions; set the rest in the console afterwards with **Edit & deploy new revision**.

### 3. Check it

1. Open `https://YOUR-URL/health` (on Cloud Run `/healthz` is a reserved path and 404s; locally both work). You want `"status": "ok"`, `"passages": 2094` and `"search_mode": "hybrid"`. If it says `keyword`, `dense_error` says why (usually a missing system library); search still works but is less accurate (hit@5 0.78 instead of 0.93).
2. Open `https://YOUR-URL/docs`, expand **POST /v1/chat**, click **Try it out**, and send `{"message": "Why is the electron temperature nearly independent of power in a global model?"}`. You should get an answer with citations in square brackets.
3. If chat fails with a permission error, check that `sa-agents` has **Agent Platform User** and that `GOOGLE_GENAI_USE_VERTEXAI=TRUE`. If the service won't start, **Logs** shows whether the index copy failed (bucket path or bucket permission).
4. Point the frontend at the URL (see [API.md](API.md)).

## Run it locally

```bash
pip install -r requirements-dev.txt          # Debian/Ubuntu also: apt-get install libegl1 libgles2 libgl1 libxcb1
export LITRAG_INDEX_URI=/path/to/index       # the unzipped index folder (or a gs:// path with gcloud auth)
export LITRAG_GEMMA_TASK=/path/to/embedding_gemma.task   # downloaded on first run if missing
export GOOGLE_GENAI_USE_VERTEXAI=TRUE GOOGLE_CLOUD_PROJECT=... GOOGLE_CLOUD_LOCATION=global
gcloud auth application-default login
uvicorn app.main:app --port 8080              # then open http://localhost:8080/docs
TEST_INDEX_DIR=/path/to/index pytest -q tests # no Gemini needed: a scripted model stands in
```

## Design notes

- **Agents run inside this service**, not on Agent Runtime. The architecture plan (B2) puts the main workflow's agents on Agent Runtime; for a request/response RAG backend, running ADK's Runner in the same Cloud Run service is one deploy instead of two, has no extra hop, and streams straight to the browser. The agents are plain ADK `Agent`s in `app/agents.py`, so they can move to Agent Runtime later without changes.
- **Sessions are in memory.** Fine for the demo with session affinity; they're lost on scale-to-zero. If that matters, switch `InMemorySessionService` in `app/main.py` to ADK's `VertexAiSessionService` (Agent Runtime sessions) or `DatabaseSessionService` (Cloud SQL).
- **Embeddings are still EmbeddingGemma**, run inside the container for each query (about 0.4 s). Decision G4 moves them to the Gemini embedding model on Agent Platform; that needs the index re-embedded (`python -m litrag embed --backend gemini` with Agent Platform credentials) and the 40-question eval re-run. The service reads which backend to use from the index's `meta.json`, so after re-embedding you only upload the new index; no code change.
- **Gemini is called through Agent Platform** (`GOOGLE_GENAI_USE_VERTEXAI=TRUE`), which doesn't train on prompts. Don't use a free AI Studio key once lab data is involved.
