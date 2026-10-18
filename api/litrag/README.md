# litrag: literature search for the Professor / Postdoc / PhD agents

Retrieval over the team's plasma and etching literature, so the agents can look up physics, model setup details and typical values, and cite the source and page. Built 2026-10-07 for the AI Builder Cup entry.

## What is indexed

| id | kind | pages | passages | source |
|---|---|---|---|---|
| `lieberman2005` | textbook | 733 | 1105 | Lieberman & Lichtenberg, *Principles of Plasma Discharges and Materials Processing*, 2nd ed. |
| `bittencourt2004` | textbook | 666 | 765 | Bittencourt, *Fundamentals of Plasma Physics*, 3rd ed. (scanned, OCR text) |
| `chen1984_ch1` | textbook | 18 | 24 | Chen, *Introduction to Plasma Physics and Controlled Fusion*, ch. 1 (scanned, OCR text) |
| `comsol_icp_cf4o2` | vendor model | 46 | 51 | COMSOL Application Library: CF4/O2 ICP reactor with RF bias for Si etching (our low-power plasma reference case) |
| `shahbazian2025` | paper | 14 | 38 | AI-driven optimization of ICP source design using COMSOL, Phys. Plasmas 32, 113503 |
| `ertl2009` | paper | 8 | 15 | 3D plasma etching simulation with ray tracing and level sets, ECS Trans. 23, 61 |
| `nath2025` | paper | 10 | 40 | Neural master equation framework for plasma-surface processes, npj Comput. Mater. |
| `dwivedi2023` | paper | 12 | 24 | Orientation-dependent etching of Si by F2, JVST A 41, 052602 |
| `wang2022_jap` | paper | 8 | 16 | RT-TDDFT of laser-enhanced ALE of Si, JAP 132, 144303 |
| `wang2023_mssp` | paper | 6 | 16 | Photo-assisted ALE of chlorinated Si(111), MSSP 153, 107169 |

2,094 passages in total. Citation metadata (authors, venue, DOI) is in [sources.json](sources.json).

## How it works

1. **Extract** (`litrag/extract.py`): pypdfium2 text per page; drops publisher cover pages, running headers/footers, reference lists (papers) and contents/preface/index (books); fixes ligatures, line-break hyphens and the common symbol-font mis-mappings (`þ` is `+`, and for Lieberman `¼` is `=`, `=` is `/`, `ð Þ` are parentheses, and so on). Page numbers are PDF pages; textbooks also get printed page numbers and a "Chapter > Section" breadcrumb (from the PDF outline, or for a scan without one, from the running heads and numbered heading lines).
2. **Chunk** (`litrag/chunk.py`): sentence-aware passages of about 260 words with a 40-word overlap, never crossing a section boundary, each tagged with its page span and section. 260 words keeps passages inside EmbeddingGemma's 512-token window.
3. **Index** (`litrag/index.py`): BM25 keyword search (with stemming and plasma acronym expansion, e.g. ICP, ALE, EEDF) plus dense vectors, merged with reciprocal rank fusion.
4. **Embeddings** (`litrag/embed.py`): default is **EmbeddingGemma 300M** run locally through MediaPipe, from Google's public model bucket (downloaded on first use to `models/`, 184 MB). No API key, fits the Gemini/Gemma rule, about 0.5 s per query on CPU. A `gemini` backend (`gemini-embedding-001` through google-genai) is also written for when a key or Vertex AI credentials exist, but is untested because this environment has no key; rebuild the vectors with `embed --backend gemini` to switch, since queries must use the same model as the index.

## Retrieval quality

40 paraphrased questions with a known answer page, 10 of them on Bittencourt ([eval/questions.jsonl](eval/questions.jsonl), full run in [eval/results.md](eval/results.md)):

| Mode | hit@1 | hit@5 | MRR |
|---|---|---|---|
| Keyword only | 0.42 | 0.78 | 0.56 |
| EmbeddingGemma only | 0.38 | 0.85 | 0.55 |
| **Hybrid (default)** | **0.60** | **0.93** | **0.72** |

## Using it

Command line (from this folder):

```bash
pip install -r requirements.txt        # Debian/Ubuntu also: apt-get install libegl1 libgles2
python -m litrag build --embed gemma   # extract + chunk + embed everything listed in sources.json (~9 min on 4 CPUs from scratch)
python -m litrag sources               # what is indexed
python -m litrag search "Bohm flux to the wafer in a low-pressure ICP" -k 5
python -m litrag search "etch rate versus RF bias" --source comsol_icp_cf4o2
python -m litrag eval                  # retrieval hit-rate
python -m litrag ask "Why is Te nearly independent of power in a global model?"   # needs GEMINI_API_KEY; untested so far (no key here)
```

From an ADK agent (checked with google-adk 2.11: the three functions produce valid tool schemas):

```python
from google.adk.agents import Agent
from litrag.tools import search_literature, read_source_pages, list_literature_sources

professor = Agent(
    model="gemini-flash-latest",
    name="professor",
    instruction="... Check results against the literature with search_literature and cite the 'citation' field ...",
    tools=[search_literature, read_source_pages, list_literature_sources],
)
```

- `search_literature(query, top_k=5, source_ids=None, kind=None)` returns passages with `citation` (e.g. "Lieberman & Lichtenberg (2005). ... p. 334, PDF p. 371."), `section`, `pdf_pages` and `text`.
- `read_source_pages(source_id, first_pdf_page, last_pdf_page=None)` returns the full text of up to 4 pages, for when an agent needs the surrounding equation or table.
- `list_literature_sources()` lists the documents and what each covers.

## Adding a paper

Put the PDF in `corpus/pdf/`, add an entry to `sources.json` (`file` must match the file name; `kind` is `paper`, `textbook` or `vendor_model`), then run `python -m litrag build --embed gemma`. Vectors of unchanged passages are reused (`index/embedding_keys.json`), so only the new paper is embedded. For a book that only exists as a plain-text export, set `text_file`, `pdf_page_offset` and `roman_page_offset` instead (see the Lieberman entry).

## Deploying with the agents (Cloud Run)

- The code in `litrag/` plus `sources.json`, `eval/` and this README can go in the public repo.
- **`corpus/`, `index/` and `models/` must stay private** (`.gitignore` covers them): the PDFs, the extracted page text and the passages are copyrighted (Wiley, Springer, AIP, Elsevier, COMSOL licence). Ship `index/` inside the private container image or a private GCS bucket and point `LITRAG_INDEX_DIR` at it. The EmbeddingGemma bundle can be downloaded at image build time from `https://storage.googleapis.com/mediapipe-models/text_embedder/embedding_gemma/int4int8/latest/embedding_gemma.task` (Gemma terms of use).
- Container needs `libegl1 libgles2` for MediaPipe. Measured here with all 2,094 passages: index load 5.7 s, peak memory 445 MB, about 0.4 s per search; `index/` is 9 MB.

## Known limitations

- **Equations are approximate.** PDF math fonts extract badly, and Lieberman's Greek letters come out as Latin look-alikes (`v` for ω, `n` for ν, `l` for λ, `G` for Γ). Prose, tables of values and equation numbers are reliable; agents should read a formula from the cited page rather than trust the extracted symbols.
- **Lieberman comes from a text export**, not the PDF: pages were rebuilt from running heads (PDF page = printed page + 37, checked against Drive's page-marked export for the first 156 pages). A few pages split by blank lines may be off by one.
- **Chen ch. 1 and Bittencourt are scans** with OCR text, so their equations are mostly unreadable. Bittencourt's main section headings are often missing from the scan's text layer, so its section breadcrumb falls back to the chapter where a heading was lost; chapter and printed page numbers are reliable.
