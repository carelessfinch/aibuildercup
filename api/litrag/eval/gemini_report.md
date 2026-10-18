# Gemini embedding eval report

Fill this in after running the commands in [gemini_runbook.md](gemini_runbook.md)
with real Google Cloud credentials.

## Run metadata

| Field | Value |
|---|---|
| Date | _YYYY-MM-DD_ |
| Runner | _your name_ |
| Project | `<project-a-id>` (Project A) |
| Region | `asia-southeast1` |
| Embedding backend | `gemini` |
| Model | `gemini-embedding-001` |
| Output dimensionality | 768 |
| N chunks embedded | 2094 |
| Embed cost (USD) | |
| Embed wall time | |

## Retrieval metrics (40 questions, eval/questions.jsonl)

| Mode | hit@1 | hit@5 | MRR |
|---|---|---|---|
| Keyword only (BM25 baseline) | 0.42 | 0.78 | 0.56 |
| EmbeddingGemma only (prior run) | 0.38 | 0.85 | 0.55 |
| EmbeddingGemma hybrid (prior run) | 0.60 | 0.93 | 0.72 |
| Gemini hybrid (this run) | | | |

## Gate

- [ ] hit@5 >= 0.90 (PASS / FAIL)

If FAIL, describe the fallback taken:

## Per-subset breakdown (optional)

| Subset | N | hit@1 | hit@5 | MRR |
|---|---|---|---|---|
| Papers + COMSOL (20) | | | | |
| Lieberman (10) | | | | |
| Bittencourt (10) | | | | |

## Notes

<!-- Anything notable: better/worse subsets vs EmbeddingGemma, cold-start, retries, etc. -->
