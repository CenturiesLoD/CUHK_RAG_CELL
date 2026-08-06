# CUHK RAG Cell

A Retrieval-Augmented Generation system for single-cell biology question answering.

The project combines curated biological sources, a vector index, hybrid retrieval,
source-aware ranking, optional reranking, and a local Qwen3-32B answer model. The
large runtime artifacts are hosted on CCI; this repository contains the code,
documentation, examples, tests, and rebuild scripts.

## Step-By-Step: Run The Hosted Model

Use this first if you want to test the model without downloading model weights,
source files, embeddings, or vector indexes. The full model runs on the CCI
server; your local machine only sends API requests.

### 1. Clone The Repository

```bash
git clone https://github.com/CenturiesLoD/CUHK_RAG_CELL.git
cd CUHK_RAG_CELL
```

If `git clone` is unavailable, download the GitHub ZIP archive for `main` and
open a terminal in the extracted folder.

### 2. Set The API Key

Linux/macOS:

```bash
export CELL_RAG_DEMO_API_KEY="your-api-key"
```

Windows PowerShell:

```powershell
$env:CELL_RAG_DEMO_API_KEY="your-api-key"
```

Do not commit real keys. The API key is only needed for `/ask` and `/search`.

### 3. Start Or Repair The CCI Backend

Skip this step if someone has already started the hosted backend.

If you have SSH access to the CCI runtime, start the full hosted stack with one
remote command:

```bash
ssh -p 20484 -i /path/to/private_key root@118.145.32.133 \
  "cd /data/L202500484/cell_rag && scripts/init_public_demo.sh --publish-endpoint"
```

Windows PowerShell:

```powershell
ssh -p 20484 -i C:\path\to\private_key root@118.145.32.133 "cd /data/L202500484/cell_rag && scripts/init_public_demo.sh --publish-endpoint"
```

That command starts or repairs the local vLLM model server, RAG API, public API
wrapper, and Cloudflare tunnel. It also publishes the current public endpoint to:

```text
https://raw.githubusercontent.com/CenturiesLoD/CUHK_RAG_CELL/main/docs/current_endpoint.json
```

### 4. Running From A Different CCI Image

The startup command works from another CCI image only if the shared runtime
directory is mounted and visible in that image.

Check the required runtime paths first:

```bash
ls -lah /data/L202500484/cell_rag
ls -lah /data/L202500484/cell_rag/models/Qwen3-32B
ls -lah /data/L202500484/cell_rag/embeddings/rag_qwen3_embedding_8b.npz
```

If those paths exist, run:

```bash
cd /data/L202500484/cell_rag
scripts/init_public_demo.sh --publish-endpoint
```

Fresh CCI images may not include Git. If endpoint publishing fails with
`Required command is missing: git`, install Git and rerun:

```bash
apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y git
cd /data/L202500484/cell_rag
scripts/init_public_demo.sh --publish-endpoint
```

If the `/data/L202500484/cell_rag` path is missing, the GitHub repo alone is not
enough to run the backend. The model weights, corpus chunks, embeddings, FAISS
index, source registry, secrets, and Python environments live in that shared CCI
runtime directory.

### 5. Smoke Test The Hosted API

The smoke test uses only the Python standard library. If you are only querying
the already-hosted API from your laptop, you do not need to install
`requirements.txt`. If you are running or rebuilding the backend on CCI, install
the server dependencies from `requirements.txt` in the runtime environment.

```bash
python examples/smoke_hosted_demo.py
```

If this fails with `Name or service not known`, `getaddrinfo failed`, or another
host/connection error, the hosted backend may be stopped or the published
Cloudflare tunnel URL may be stale. Restart and republish it from a machine with
CCI SSH access:

Linux/macOS:

```bash
ssh -p 20484 -i /path/to/private_key root@118.145.32.133 \
  "cd /data/L202500484/cell_rag && scripts/init_public_demo.sh --publish-endpoint"
```

Windows PowerShell:

```powershell
ssh -p 20484 -i C:\path\to\private_key root@118.145.32.133 "cd /data/L202500484/cell_rag && scripts/init_public_demo.sh --publish-endpoint"
```

Then rerun:

```bash
python examples/smoke_hosted_demo.py
```

Expected result:

- `/health` returns `status: ok`.
- `/examples` returns example questions.
- unauthenticated `/ask` returns `401`.
- authenticated `/ask` returns a cited answer.
- `/search` returns retrieved source records.
- `citation_check.passed` is `true`.

### 6. Ask A Question

Linux/macOS:

```bash
python examples/python_client.py \
  --api-key "$CELL_RAG_DEMO_API_KEY" \
  --question "What markers identify regulatory T cells?"
```

Windows PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File examples\windows_client.ps1 `
  -ApiKey $env:CELL_RAG_DEMO_API_KEY `
  -Question "What is a regulatory T cell?"
```

The example clients discover the current public URL from
`docs/current_endpoint.json`. If the Cloudflare quick tunnel restarts, the URL
may change, but the CCI startup command above republishes the manifest so users
do not need to edit client code.

## What This Repo Contains

This is a lightweight repository. It does **not** include model weights or corpus
artifacts.

Included:

- `src/`: API servers, corpus builders, retrieval, evaluation, and indexing code.
- `scripts/`: startup, rebuild, smoke-test, audit, tunnel, and utility scripts.
- `examples/`: small clients for the hosted API.
- `tools/debug/`: low-level diagnostic scripts that are not part of normal serving.
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

- Combined chunks and aliases are generated from the active source families on CCI.
- Qwen3-Embedding-8B embeddings are stored with metadata alignment files.
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
public API key.

The hosted endpoint is discovered from this stable GitHub manifest:

```text
https://raw.githubusercontent.com/CenturiesLoD/CUHK_RAG_CELL/main/docs/current_endpoint.json
```

The actual backend URL is a Cloudflare quick-tunnel URL, so it can change when
the tunnel restarts. Use the manifest or the example clients instead of
hardcoding the tunnel hostname.

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

The hosted client and smoke test use only the Python standard library. Install
`requirements.txt` when you are setting up or repairing a CCI backend runtime,
not when you are only calling the hosted API as a client.

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
scripts/init_public_demo.sh --publish-endpoint
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
scripts/init_public_demo.sh --restart-tunnel --publish-endpoint
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

For server-side retrieval debugging, use the hybrid CLI when you want behavior
close to the RAG search stack:

```bash
python src/search_hybrid_qwen.py "What markers identify regulatory T cells?"
```

The vector-only diagnostic lives under `tools/debug/` because it intentionally
isolates dense embedding search and skips aliases, BM25, FAISS, reranking, and
answer generation:

```bash
python tools/debug/search_qwen_vectors.py "What is a regulatory T cell?"
```

## Running On CCI

Use this path only if you have access to the server-side runtime artifacts.

```bash
cd /data/L202500484/cell_rag
scripts/ensure_stack.sh
scripts/status_all.sh
```

Start or repair the public hosted API:

```bash
scripts/init_public_demo.sh --publish-endpoint
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
python -m compileall -q src examples scripts tools tests
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
