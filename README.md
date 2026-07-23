# CUHK RAG Cell

A Retrieval-Augmented Generation system for single-cell biology question answering.

The project combines curated biological sources, a vector index, hybrid retrieval,
source-aware ranking, optional reranking, and a local Qwen3-32B answer model. The
large runtime artifacts are hosted on CCI; this repository contains the code,
documentation, examples, tests, and rebuild scripts.

## What This Repo Contains

This is a lightweight repository. It does **not** include model weights or corpus
artifacts.

Included:

- `src/`: API servers, corpus builders, retrieval, evaluation, and indexing code.
- `scripts/`: startup, rebuild, smoke-test, audit, tunnel, and utility scripts.
- `examples/`: small clients for the hosted API.
- `eval/`: smoke-test retrieval and answer cases.
- `demo/`: showcase questions.
- `docs/`: source, workflow, hosted backend, and audit notes.
- `.env.example`: configuration template.

Excluded by `.gitignore`:

- `models/`: Hugging Face model snapshots and reranker weights.
- `sources/`: server-side source registry and source metadata snapshots.
- `raw/`: downloaded source files and API exports.
- `processed/`: normalized records and alias files.
- `chunks/`: retrievable chunk JSONL files.
- `embeddings/`: `.npz` embedding matrices, metadata, and FAISS indexes.
- `secrets/`: API keys and local credentials.
- `logs/` and `reports/`: generated runtime output.

The full CCI runtime lives at:

```text
/data/L202500484/cell_rag
```

## Current System

Runtime stack:

```text
client
  -> hosted HTTPS URL
  -> Cloudflare quick tunnel on CCI
  -> public API wrapper on 127.0.0.1:8020
  -> RAG API on 127.0.0.1:8010
  -> vLLM Qwen3-32B endpoint on 127.0.0.1:8000/v1
```

Current corpus:

- `325,815` chunks.
- `2,712,338` aliases.
- Qwen3-Embedding-8B embeddings, dimension `4096`.
- Optional FAISS IVF-Flat vector index enabled on CCI.
- Optional MiniLM cross-encoder reranker enabled on CCI.
- Qwen3-32B answer model served by vLLM.

Active source families:

- Cell Ontology: cell type IDs, names, definitions, synonyms, hierarchy.
- Uberon: tissues, organs, and anatomy context.
- Gene Ontology: biological process, molecular function, cellular component terms.
- PATO: phenotype quality terms.
- CELLxGENE Census: summarized atlas metadata evidence.
- HGNC: human gene symbols, names, aliases, and cross-references.
- NCBI Gene: Entrez IDs, descriptions, chromosome/map-location metadata.
- UniProtKB reviewed human: protein names, functions, GO links, cross-references.
- CellMarker 3.0: marker gene sets.
- PanglaoDB: curated marker gene associations.

## Quickstart: Hosted API

Use this path if the CCI backend is already running. You only need Python and the
public API key. The key is intentionally not stored in GitHub; obtain it
separately from the server operator.

Clone the lightweight client repository:

```bash
git clone https://github.com/CenturiesLoD/CUHK_RAG_CELL.git
cd CUHK_RAG_CELL
```

The backend uses a Cloudflare quick-tunnel URL, which can change if the tunnel
process is restarted. The example clients therefore auto-discover the active URL
from this stable GitHub manifest:

```text
https://raw.githubusercontent.com/CenturiesLoD/CUHK_RAG_CELL/main/docs/current_endpoint.json
```

The current URL can also be checked on CCI with:

```bash
cd /data/L202500484/cell_rag
scripts/status_public_demo_tunnel.sh
```

Linux/macOS:

```bash
export CELL_RAG_DEMO_API_KEY="your-api-key"
python examples/smoke_hosted_demo.py
```

Windows PowerShell:

```powershell
$env:CELL_RAG_DEMO_API_KEY="your-api-key"
python examples\smoke_hosted_demo.py
```

The hosted client and smoke test use only the Python standard library. Do not
install `requirements.txt` just to query the hosted API; that file is for a CCI
server runtime.

Ask one question:

```bash
python examples/python_client.py \
  --api-key "$CELL_RAG_DEMO_API_KEY" \
  --question "What markers identify regulatory T cells?"
```

PowerShell wrapper:

```powershell
powershell -ExecutionPolicy Bypass -File examples\windows_client.ps1 `
  -ApiKey $env:CELL_RAG_DEMO_API_KEY `
  -Question "What is a regulatory T cell?"
```

If you want to override discovery, set `CELL_RAG_DEMO_URL` or pass `--base-url`.

Expected smoke-test behavior:

- `GET /health` returns `status: ok`.
- `GET /examples` returns example questions.
- unauthenticated `POST /ask` returns `401`.
- authenticated `POST /ask` returns a cited answer.
- authenticated `POST /search` returns retrieved source records.
- `citation_check.passed` is `true`.

## Initialize The Hosted Demo

Use this before sharing or testing the hosted backend. It runs on the CCI runtime
and creates or refreshes the public URL.

From CCI:

```bash
cd /data/L202500484/cell_rag
scripts/init_public_demo.sh
```

From Windows, using SSH:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\init_public_demo_from_windows.ps1
```

The Windows helper checks `CELL_RAG_SSH_KEY`, then looks for `public_key`,
`id_ed25519`, or `id_rsa` under the current user's `.ssh` directory. For a key
stored elsewhere, pass `-IdentityFile C:\path\to\key`.

Force a fresh quick-tunnel URL:

```bash
scripts/init_public_demo.sh --restart-tunnel
```

Update and push the GitHub endpoint manifest after generating a URL:

```bash
scripts/init_public_demo.sh --publish-endpoint
```

For automatic publishing from CCI, configure a write-enabled GitHub deploy key
once:

```bash
scripts/setup_public_endpoint_publisher.sh
```

Add the printed public key to the GitHub repo as a deploy key with write access.
After that, `scripts/init_public_demo.sh --publish-endpoint` can update
`docs/current_endpoint.json`, commit it in the lightweight endpoint checkout, and
push it to `main`.

The publisher uses a separate checkout at `.endpoint_repo/` by default. It does
not turn the CCI runtime directory into a Git repo, so runtime artifacts such as
models, corpus files, embeddings, logs, and secrets remain outside Git.

This does not make Cloudflare quick tunnels permanent. It makes URL rotation
operational: the server operator refreshes the URL, the repo stores the current
URL in one stable manifest, and client scripts discover it automatically.

## API Usage

### Health

```bash
curl "$CELL_RAG_DEMO_URL/health"
```

### Ask

```bash
curl -s "$CELL_RAG_DEMO_URL/ask" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $CELL_RAG_DEMO_API_KEY" \
  -d '{"question":"What is a regulatory T cell?","top_k":5,"max_tokens":300}'
```

The response includes:

- `answer`: cited natural-language answer.
- `sources`: compact source records used for the answer.
- `retrieval_quality`: confidence/ranking metadata.
- `citation_check`: machine-readable citation audit.

### Search

```bash
curl -s "$CELL_RAG_DEMO_URL/search" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $CELL_RAG_DEMO_API_KEY" \
  -d '{"query":"FOXP3 function","top_k":5}'
```

Use `/search` when you want retrieval results without generation.

## How Retrieval Works

The RAG API combines several ranking signals:

1. Exact matching against curated aliases, ontology IDs, gene symbols, and accessions.
2. BM25-style lexical scoring.
3. Qwen3 vector similarity.
4. Optional FAISS approximate nearest-neighbor candidate retrieval.
5. Lightweight lexical reranking.
6. Optional neural cross-encoder reranking.
7. Source-aware ranking based on query type.

Source-aware ranking helps route questions to the most appropriate source family:

- cell definition questions prefer Cell Ontology;
- tissue/anatomy questions prefer Uberon;
- gene-symbol questions prefer HGNC;
- Entrez/chromosome questions prefer NCBI Gene;
- protein-function questions prefer UniProt;
- marker questions prefer CellMarker/PanglaoDB;
- atlas evidence questions prefer CELLxGENE Census summaries.

The answer endpoint then builds a cited context prompt and calls the local
OpenAI-compatible Qwen3-32B endpoint. It abstains when retrieval confidence is
too low and returns a `citation_check` audit for the final answer.

## Running On CCI

Use this path only if you have access to the server-side runtime artifacts.

```bash
cd /data/L202500484/cell_rag
scripts/ensure_stack.sh
scripts/status_all.sh
```

Start or repair the public hosted API:

```bash
scripts/init_public_demo.sh
scripts/status_public_demo_tunnel.sh
```

Run smoke tests:

```bash
scripts/smoke_all.sh
scripts/smoke_public_demo.sh
```

Common service commands:

```bash
scripts/start_all.sh
scripts/stop_all.sh
scripts/status_all.sh
scripts/status_rag_server.sh
scripts/status_llm_server.sh
scripts/status_public_api.sh
```

## Local Configuration

For a new server runtime, copy:

```bash
cp .env.example .env
```

Then edit paths and service settings in `.env`.

Important runtime paths:

```text
RAG_CHUNKS_PATH=chunks/rag_chunks.jsonl
RAG_ALIASES_PATH=processed/rag_aliases.jsonl
RAG_EMBEDDINGS_PATH=embeddings/rag_qwen3_embedding_8b.npz
RAG_METADATA_PATH=embeddings/rag_qwen3_embedding_8b.metadata.json
LLM_MODEL_PATH=models/Qwen3-32B
LLM_MODEL_SOURCE_PATH=models/Qwen3-32B
LLM_FAST_MODEL_CACHE_PATH=/dev/shm/cell_rag_models/Qwen3-32B
```

The real `.env` is ignored by Git.

## Faster Model Startup

Cold startup is dominated by:

- loading the Qwen3-32B checkpoint;
- allocating GPU memory;
- vLLM compile/warmup work.

The CCI runtime uses:

```bash
LLM_SAFETENSORS_LOAD_STRATEGY=prefetch
LLM_SAFETENSORS_PREFETCH_NUM_THREADS=4
LLM_ENFORCE_EAGER=false
LLM_FAST_MODEL_CACHE_ENABLED=true
LLM_FAST_MODEL_CACHE_PATH=/dev/shm/cell_rag_models/Qwen3-32B
```

Inspect storage speed:

```bash
scripts/inspect_model_storage.sh
```

Prepare a fast runtime copy:

```bash
scripts/prepare_fast_model_cache.sh /dev/shm/cell_rag_models/Qwen3-32B
```

Configure the automatic fast cache:

```bash
scripts/configure_fast_model_cache.sh /dev/shm/cell_rag_models/Qwen3-32B
```

Benchmark startup settings:

```bash
scripts/benchmark_llm_startup.sh
```

## Rebuilding The Corpus

Rebuild the combined maintained corpus:

```bash
scripts/build_combined_rag_with_cellxgene.sh
```

This merges the active source chunk files, combines aliases, and rebuilds the
Qwen3 embedding matrix.

Rebuild the optional FAISS index after embeddings change:

```bash
scripts/build_faiss_index.sh
```

Rebuild only the Cell Ontology-focused debug corpus:

```bash
scripts/rebuild_cell_rag.sh
```

Use a specific local OBO file:

```bash
CL_OBO_PATH=/path/to/cl.obo scripts/rebuild_cell_rag.sh
```

## Adding Your Own Documents

Create JSONL records with this shape:

```json
{"doc_id":"doc:1","title":"Example","text":"Document text...","aliases":["optional alias"],"metadata":{"source":"optional"}}
```

Build and embed the added corpus:

```bash
EXTRA_CORPUS_NAME=my_docs scripts/build_extra_jsonl_corpus.sh /path/to/docs.jsonl
```

Then start the server with the expanded paths printed by the script, or update
`.env` to point at the new combined artifacts.

## Evaluation

Run the dependency-free fresh-clone checks on any machine with Python 3.12+:

```bash
python -m compileall -q src examples scripts tests
python -m unittest discover -s tests -v
```

GitHub Actions runs these checks, validates shell and PowerShell syntax, and
rejects accidentally committed models, generated corpora, indexes, or secrets.

Server-side evaluation requires the CCI runtime artifacts.

Run retrieval eval:

```bash
scripts/run_retrieval_eval.sh
scripts/run_retrieval_eval.sh --cases eval/cellxgene_queries.jsonl
```

Run answer eval:

```bash
scripts/run_answer_eval.sh
scripts/run_answer_eval.sh --cases eval/cellxgene_answer_cases.jsonl
```

Run the full smoke suite:

```bash
scripts/smoke_all.sh
```

Run a saved audit:

```bash
scripts/audit_all.sh
```

For an audit launched over SSH, use the detached runner so a dropped connection
does not kill a long evaluation:

```bash
scripts/start_detached_audit.sh
scripts/status_detached_audit.sh
```

The full audit also initializes and verifies the hosted HTTPS tunnel. Core-only
status checks treat the tunnel as optional; use
`STATUS_REQUIRE_PUBLIC_TUNNEL=1 scripts/status_all.sh` when public availability
must be part of the pass/fail result.

Because some CCI images cannot resolve their own quick-tunnel hostname, the
server audit verifies the tunnel process and URL state with
`PUBLIC_DEMO_SKIP_HEALTH=1`. The external hosted smoke test remains the final
HTTPS reachability check.

Current smoke coverage:

- main retrieval cases: `33`
- CELLxGENE retrieval cases: `5`
- main answer cases: `21`
- CELLxGENE answer cases: `2`

## Known Limits

- Evaluation is smoke-level, not a full scientific benchmark.
- CELLxGENE is summarized from `obs` metadata only. It does not include dataset
  titles, publication links, donor-level metadata, expression matrices,
  marker-expression evidence, or differential expression.
- Literature sources are not included yet.
- FAISS is available, but BM25 still scans chunks in process. Larger literature
  ingestion should add a persistent lexical index and may need a managed vector
  database or distributed FAISS.
- The reranker is a general MiniLM cross-encoder, not a single-cell-specific
  reranker.

## Repository Safety Checklist

Before pushing changes, confirm large runtime directories are not present:

```bash
find . -maxdepth 2 -type d | grep -E 'models|sources|raw|processed|chunks|embeddings|secrets|logs|reports'
```

Expected result: no runtime artifact directories from the list above.
