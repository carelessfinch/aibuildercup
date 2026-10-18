# Gemini embedding runbook (re-embed + eval on Agent Platform)

## When to use this

Switch from the default EmbeddingGemma backend to `gemini-embedding-001` via Vertex AI
so the demo index uses the same model family as the agents' Gemini calls. Only run this
with real Google Cloud credentials (paid billing, not a free AI Studio key).

## Prerequisites

```bash
# google-genai is already in litrag/requirements.txt (>= 2.28.0 tested).
pip install -r requirements.txt
# On Cloud Run or locally with gcloud: no API key needed if Vertex is configured.
```

## Environment variables

### Vertex AI / Agent Platform (recommended for Cloud Run and local dev with gcloud)

```bash
export GOOGLE_GENAI_USE_VERTEXAI=true
export GOOGLE_CLOUD_PROJECT=<project-a-id>        # the live-demo project
export GOOGLE_CLOUD_REGION=asia-southeast1        # confirmed region; fallback us-central1
```

No API key is needed: google-genai uses Application Default Credentials (gcloud /
workload identity / Cloud Run's built-in service account). Make sure the runtime
service account has the **Vertex AI User** role (`roles/aiplatform.user`).

### Gemini API key (development only — never in the demo)

```bash
export GOOGLE_API_KEY=<key>    # or GEMINI_API_KEY (both work; GOOGLE_API_KEY preferred)
# Do NOT set GOOGLE_GENAI_USE_VERTEXAI
```

## Re-embed the index

From the `litrag/` directory:

```bash
# Full rebuild (extract + chunk + embed): slower but always fresh.
python -m litrag build --embed gemini

# Add embeddings to an existing index (reuses unchanged-passage vectors when the
# backend/model matches; re-embeds everything when switching from gemma).
python -m litrag embed --backend gemini
# Optional: specify a non-default model.
python -m litrag embed --backend gemini --model gemini-embedding-001
```

Cost estimate for 2,094 passages at ~260 words each: ~3.4 M input tokens at the
embedding pricing tier (see [Vertex AI pricing](https://cloud.google.com/vertex-ai/pricing#generative-ai-models)).

## Run the 40-question eval

```bash
python -m litrag eval -k 5
# Keyword-only baseline (for comparison):
python -m litrag eval -k 5 --keyword-only
# Embedding-only (dense off means keyword only; to test dense only, compare against
# the BM25 result in eval/results.md).
```

## Acceptance gate

**hit@5 must be >= 0.90** (the EmbeddingGemma baseline is 0.93; a Gemini backend should
be comparable or better). If it fails, try `--model gemini-embedding-001` with a higher
`output_dimensionality` (e.g. 1536 or 3072 — edit `GeminiEmbedder(dim=…)` in
`litrag/embed.py` and re-run).

If it still fails after one retry, fall back to EmbeddingGemma (see below) and record
the result in `gemini_report.md` as "Gemini backend rejected, using EmbeddingGemma".

## Fallback: EmbeddingGemma container

If the Gemini backend fails with real credentials (auth error, model not found, or
eval < 0.90 after retry), revert to the default EmbeddingGemma backend:

```bash
python -m litrag embed --backend gemma
python -m litrag eval -k 5   # should reproduce the 0.93 baseline
```

The Cloud Run container needs `libegl1 libgles2` for MediaPipe:

```dockerfile
RUN apt-get update && apt-get install -y --no-install-recommends libegl1 libgles2
```

The Gemini backend avoids this dependency, which is the reason to try it first.

## Checklist

- [ ] `GOOGLE_GENAI_USE_VERTEXAI=true` and `GOOGLE_CLOUD_PROJECT` set
- [ ] Region `asia-southeast1` (or `us-central1` fallback)
- [ ] Service account has Vertex AI User role
- [ ] `python -m litrag embed --backend gemini` completes without errors
- [ ] `meta.json` in the index records `"backend": "gemini"` and the model name
- [ ] `python -m litrag eval -k 5` gives hit@5 >= 0.90
- [ ] Results recorded in `gemini_report.md`
- [ ] Index never committed to the public repo (corpus/, index/, models/ excluded)
