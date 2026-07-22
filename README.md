# Cell RAG

This repository is the lightweight code, documentation, and client-example layer
for a CCI-hosted single-cell biology RAG system.

The mentor demo is intentionally server-backed: the Qwen3-32B model, embedding
model, downloaded source files, processed records, chunks, embeddings, FAISS
index, logs, reports, and API secrets stay on CCI. A mentor cloning this repo
does not need to download the model or rebuild the corpus.

## Mentor Quickstart

Use the hosted CCI API URL and mentor API key provided separately:

```powershell
$env:CELL_RAG_DEMO_URL="https://your-public-demo-url"
$env:CELL_RAG_DEMO_API_KEY="your-mentor-api-key"
python examples\smoke_hosted_demo.py
```

Or call it from PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File examples\windows_client.ps1 `
  -BaseUrl "https://your-public-demo-url" `
  -ApiKey "your-mentor-api-key" `
  -Question "What markers identify regulatory T cells?"
```

The client requests go to:

```text
mentor machine
  -> public hosted demo URL
  -> CCI Cloudflare quick tunnel
  -> CCI mentor API on 127.0.0.1:8020
  -> CCI RAG API on 127.0.0.1:8010
  -> CCI vLLM Qwen3-32B endpoint on 127.0.0.1:8000/v1
```

## Repo Boundary

The GitHub repo should contain code, docs, examples, eval cases, and scripts
only. It should not contain runtime artifacts or source-data snapshots.

Excluded by `.gitignore`:

- `models/`: local Hugging Face model snapshots and reranker weights.
- `sources/`: source registry and source metadata snapshots kept on CCI.
- `raw/`: downloaded source files and API exports.
- `processed/`: normalized JSONL records and alias files.
- `chunks/`: retrievable chunk JSONL files.
- `embeddings/`: `.npz` embedding matrices, metadata, and FAISS indexes.
- `secrets/`: mentor API keys and local credentials.
- `logs/` and `reports/`: generated runtime and audit output.

The CCI runtime keeps those files under:

```text
/data/L202500484/cell_rag
```

The fast model cache, when enabled, is runtime-only:

```text
/dev/shm/cell_rag_models/Qwen3-32B
```

## CCI Runtime

The server-side `.env` points the CCI services at the combined RAG corpus:

- chunks: `chunks/rag_chunks.jsonl`
- aliases: `processed/rag_aliases.jsonl`
- embeddings: `embeddings/rag_qwen3_embedding_8b.npz`
- metadata: `embeddings/rag_qwen3_embedding_8b.metadata.json`
- optional FAISS ANN index: `embeddings/rag_qwen3_embedding_8b.ivfflat.faiss`
- embedding model: `models/Qwen3-Embedding-8B`
- optional neural reranker: `models/ms-marco-MiniLM-L-6-v2`
- answer model endpoint: `http://127.0.0.1:8000/v1`
- answer model name: `qwen3-32b`
- mentor-facing API endpoint: `http://127.0.0.1:8020`

For a new server runtime, copy `.env.example` to `.env` and adjust paths, model
locations, API keys, and GPU assignments. The real `.env` file is intentionally
ignored by Git.

## CCI Operator Run

Start the full stack from the project root:

```bash
scripts/start_all.sh
```

This delegates to `scripts/ensure_stack.sh`. It checks health first, avoids
restarting healthy services, removes stale PID files through the service start
scripts, waits for services that are already loading, and starts the local vLLM
server, RAG FastAPI server, and mentor-facing API wrapper only when needed.

From Windows, use the local wrapper:

```powershell
$env:CELL_RAG_SSH_HOST="<CCI_H100_HOSTNAME_OR_IP>"
$env:CELL_RAG_SSH_KEY="$HOME\.ssh\public_key"
powershell -ExecutionPolicy Bypass -File scripts\ensure_cell_rag_stack.ps1
```

Useful service commands:

```bash
scripts/ensure_stack.sh
scripts/status_all.sh
scripts/status_rag_server.sh
scripts/status_llm_server.sh
scripts/status_mentor_api.sh
scripts/stop_all.sh
```

Cold startup is dominated by loading the 61GB Qwen3-32B weights into vLLM and
warming kernels. A persistent SSH connection would reduce command overhead, but
not the model load itself. The LLM startup script now uses vLLM safetensors
prefetch by default:

```bash
LLM_SAFETENSORS_LOAD_STRATEGY=prefetch
LLM_SAFETENSORS_PREFETCH_NUM_THREADS=4
LLM_ENFORCE_EAGER=false
```

Override those environment variables before startup if prefetch needs to be
disabled or tuned. To compare normal CUDA graph warmup against eager execution,
run:

```bash
scripts/benchmark_llm_startup.sh
```

`LLM_ENFORCE_EAGER=true` passes `--enforce-eager` to vLLM. It can reduce CUDA
graph startup work, but may slow steady generation.

To inspect whether model files are on fast local storage:

```bash
scripts/inspect_model_storage.sh
```

If CCI provides a faster scratch/NVMe path with enough free space, prepare a
runtime copy with:

```bash
scripts/prepare_fast_model_cache.sh /path/to/fast-scratch/Qwen3-32B
```

Then set `LLM_MODEL_PATH=/path/to/fast-scratch/Qwen3-32B` before starting vLLM.
For an automatic per-runtime cache, configure:

```bash
scripts/configure_fast_model_cache.sh /dev/shm/cell_rag_models/Qwen3-32B
```

With `LLM_FAST_MODEL_CACHE_ENABLED=true`, `scripts/start_llm_server.sh` prepares
the cache if missing and starts vLLM from `LLM_FAST_MODEL_CACHE_PATH`.

The API is served by `src/rag_search_server.py`.
The mentor-facing wrapper is served by `src/mentor_api_server.py`.

## API

### `GET /health`

`/health` is a readiness check for the loaded RAG server. It returns:

- `status`: `"ok"` if the FastAPI app initialized successfully.
- `chunks_path`: the chunk JSONL file the server loaded.
- `embeddings_path`: the embedding matrix file the server loaded.
- `vector_backend_requested`: configured backend, usually `exact` or `faiss`.
- `vector_backend`: backend actually loaded.
- `faiss_index_path`: configured FAISS index path.
- `faiss_candidates`: number of FAISS candidates requested before hybrid reranking.
- `faiss_nprobe`: IVF probe count when FAISS is active.
- `reranker_enabled`: whether the neural reranker is configured.
- `reranker_loaded`: whether the reranker model loaded successfully.
- `reranker_model_path`: configured reranker model path.
- `reranker_candidates`: number of pre-ranked candidates reranked by the cross-encoder.
- `reranker_weight`: score weight added after neural reranking.
- `reranker_exact_match_weight`: score weight used for exact alias/name/ID matches.
- `reranker_max_length`: maximum query-passage token length for reranking.
- `chunks`: number of loaded retrievable chunks.
- `embedding_shape`: matrix shape, expected to match chunk count and embedding dimension.
- `cuda_available`: whether PyTorch can see CUDA.
- `gpu`: the GPU name used by the embedding model.

Use it after startup to confirm the server loaded the intended corpus and embedding artifact.

Example:

```bash
curl http://127.0.0.1:8010/health
```

### `POST /search`

Runs retrieval only. It combines exact alias matching, BM25-style lexical scoring, Qwen3 vector similarity, lightweight lexical reranking, optional neural reranking, and source-aware ranking. The vector scorer can run as exact in-process NumPy search or as a FAISS ANN candidate search.

Example:

```bash
curl -s http://127.0.0.1:8010/search \
  -H 'Content-Type: application/json' \
  -d '{"query":"What is a T cell?","top_k":5}'
```

The response includes `retrieval_quality`, which estimates whether the top result is strong enough to answer from.

## Vector Backend

The default vector backend is exact NumPy search:

```bash
RAG_VECTOR_BACKEND=exact scripts/start_rag_server.sh
```

Build the optional FAISS IVF-Flat index from the existing embedding matrix:

```bash
scripts/build_faiss_index.sh \
  --embeddings embeddings/rag_qwen3_embedding_8b.npz \
  --metadata embeddings/rag_qwen3_embedding_8b.metadata.json \
  --output embeddings/rag_qwen3_embedding_8b.ivfflat.faiss
```

Start the RAG API with FAISS candidate retrieval:

```bash
RAG_VECTOR_BACKEND=faiss \
RAG_FAISS_INDEX_PATH=embeddings/rag_qwen3_embedding_8b.ivfflat.faiss \
RAG_FAISS_CANDIDATES=4096 \
RAG_FAISS_NPROBE=64 \
scripts/start_rag_server.sh
```

FAISS narrows the vector search to a candidate set before the existing BM25, alias, rerank, and source-aware scoring logic chooses final results. Exact search remains the reference fallback.

## Neural Reranker

The neural reranker is an optional cross-encoder pass after initial hybrid retrieval. It scores query-passage pairs directly, then adds a normalized reranker score to the existing ranking.

Download the default reranker:

```bash
scripts/download_reranker_model.sh cross-encoder/ms-marco-MiniLM-L-6-v2 models/ms-marco-MiniLM-L-6-v2
```

Enable it in `.env` or for one server start:

```bash
RAG_RERANKER_ENABLED=true \
RAG_RERANKER_MODEL_PATH=models/ms-marco-MiniLM-L-6-v2 \
RAG_RERANKER_CANDIDATES=48 \
RAG_RERANKER_WEIGHT=0.35 \
RAG_RERANKER_EXACT_MATCH_WEIGHT=0.0 \
RAG_RERANKER_MAX_LENGTH=512 \
RAG_RERANKER_BATCH_SIZE=8 \
scripts/start_rag_server.sh
```

The exact-match weight defaults to `0.0` because curated aliases, IDs, and
names are more reliable than a general reranker for short biomedical symbols.

Per request, `use_neural_reranker` can disable or request reranking:

```bash
curl -s http://127.0.0.1:8010/search \
  -H 'Content-Type: application/json' \
  -d '{"query":"What markers identify Tregs?","top_k":5,"use_neural_reranker":true}'
```

Use `false` to compare against the same server without the neural reranker.

### `POST /answer`

Runs retrieval, builds a cited context prompt, and calls the configured OpenAI-compatible chat endpoint.

By default the endpoint abstains when retrieval confidence is low. Set `allow_low_confidence` to `true` only for debugging.

The response includes `citation_check`, a machine-readable audit of the final answer. It reports the retrieved source block IDs, citations used by the answer, invalid citations, uncited factual-looking claim units, and whether the final answer passed the citation hygiene check. The server also records whether deterministic grounding changed the raw model output.

Example:

```bash
curl -s http://127.0.0.1:8010/answer \
  -H 'Content-Type: application/json' \
  -d '{"query":"What is a regulatory T cell?","top_k":5}'
```

## Mentor API

The mentor API is a cleaner demonstration layer over the internal RAG API. It runs on the CCI server at:

```text
http://127.0.0.1:8020
```

It stays bound to localhost by default. For a mentor demo from Windows, open an SSH tunnel with:

```powershell
$env:CELL_RAG_SSH_HOST="<CCI_H100_HOSTNAME_OR_IP>"
$env:CELL_RAG_SSH_KEY="$HOME\.ssh\public_key"
powershell -ExecutionPolicy Bypass -File scripts\mentor_rag_api_tunnel.ps1
```

Then open the interactive API docs:

```text
http://127.0.0.1:8020/docs
```

To test the tunnel once and automatically close it:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\mentor_rag_api_tunnel.ps1 -OneShot
```

Endpoints:

- `GET /health`: checks the mentor API and internal RAG service.
- `GET /examples`: returns demo questions.
- `POST /ask`: returns a cited answer, retrieval quality, citation audit, and compact sources.
- `POST /search`: returns retrieval-only results for debugging.

The remote lifecycle commands are:

```bash
scripts/start_mentor_api.sh
scripts/status_mentor_api.sh
scripts/smoke_mentor_api.sh
scripts/stop_mentor_api.sh
```

If the API must be exposed beyond an SSH tunnel, set `MENTOR_API_KEY` and bind
`MENTOR_API_HOST=0.0.0.0` only after the CCI network/firewall rules are known.

## Hosted Demo Backend

The hosted demo backend keeps the model and RAG artifacts on CCI while letting a
mentor call a public API URL. Because the current CCI public mapping exposes SSH
but not port `8020`, the hosted demo uses an outbound Cloudflare quick tunnel.

Start or repair the hosted demo backend on CCI:

```bash
scripts/ensure_hosted_demo.sh
```

Show the public URL:

```bash
scripts/status_public_demo_tunnel.sh
```

The mentor API key is stored on CCI in:

```text
secrets/mentor_api_key.txt
```

Mentor requests to `/ask` and `/search` must include:

```text
Authorization: Bearer <mentor-api-key>
```

Client examples are in:

- `examples/python_client.py`
- `examples/smoke_hosted_demo.py`
- `examples/windows_client.ps1`
- `examples/curl_examples.md`

External public smoke test:

```bash
export CELL_RAG_DEMO_URL="https://your-public-demo-url"
export CELL_RAG_DEMO_API_KEY="your-mentor-api-key"
python examples/smoke_hosted_demo.py
```

Windows client example:

```powershell
powershell -ExecutionPolicy Bypass -File examples\windows_client.ps1 `
  -BaseUrl "https://your-public-demo-url" `
  -ApiKey "your-mentor-api-key" `
  -Question "What markers identify regulatory T cells?"
```

For full hosted-demo notes, see `docs/HOSTED_DEMO.md`.

## Evaluate

The current evals are smoke tests, not a full benchmark.

Run retrieval eval:

```bash
scripts/run_retrieval_eval.sh
```

When the server has the neural reranker loaded, compare reranked and non-reranked retrieval without restarting:

```bash
scripts/run_retrieval_eval.sh --use-neural-reranker true
scripts/run_retrieval_eval.sh --use-neural-reranker false
```

This reads `eval/queries.jsonl`. Each line has:

- `query`: text sent to `/search`.
- `expected_doc_ids`: acceptable returned document IDs.
- `top_k`: requested number of results.

The runner reports:

- `hit_at_1`: expected doc is the top result.
- `hit_at_k`: expected doc appears anywhere in the returned top K.
- `mrr`: reciprocal-rank score, where rank 1 is `1.0`, rank 2 is `0.5`, and missing is `0.0`.
- `failures`: cases where the expected source was not retrieved.
- `low_confidence`: cases where retrieval returned a low-confidence assessment.

Run answer eval:

```bash
scripts/run_answer_eval.sh
```

The answer eval accepts the same reranker flag:

```bash
scripts/run_answer_eval.sh --use-neural-reranker true
scripts/run_answer_eval.sh --use-neural-reranker false
```

This reads `eval/answer_cases.jsonl`. Each line has:

- `name`: stable case name.
- `query`: text sent to `/answer`.
- `expected_doc_ids`: source IDs that should appear in returned sources.
- `must_contain`: strings that must appear in the generated answer.
- `must_not_contain`: strings that must not appear, such as `<think>`.
- `should_abstain`: whether the answer should refuse because retrieval is insufficient.
- `top_k`: requested number of retrieval results.

The answer eval checks both source grounding and answer text. It also requires the API-provided `citation_check` field to exist and pass. It is useful for catching regressions such as missing citations, retrieval failures, unwanted reasoning tags, invalid source IDs, and failed abstention behavior.

Run the full smoke-test sequence:

```bash
scripts/smoke_all.sh
```

Create a timestamped audit report for handoff or reproducibility:

```bash
scripts/audit_all.sh
```

The audit writes logs under `reports/audits/<timestamp>/`. It captures startup,
server status, GPU/model status, source registry validation, source counts,
retrieval evals, answer evals, and final service status. See `docs/AUDIT.md`
for details.

Create a curated demo pack with representative questions and cited answers:

```bash
scripts/run_demo_pack.sh
```

The demo writes outputs under `reports/demos/<timestamp>/`, including
`summary.txt`, `answers.jsonl`, and `answers.md`. See
`docs/PROJECT_SUMMARY.md` for the final project explanation and demo scope.

## Rebuild

Rebuild the Cell Ontology-only corpus:

```bash
scripts/rebuild_cell_rag.sh
```

To rebuild from a local OBO file:

```bash
CL_OBO_PATH=/path/to/cl.obo scripts/rebuild_cell_rag.sh
```

Build the current combined runtime corpus:

```bash
scripts/build_combined_rag_with_cellxgene.sh
```

That combined script currently merges Cell Ontology, Uberon, GO, PATO,
CELLxGENE Census summaries, HGNC, NCBI Gene Human, UniProtKB reviewed human,
CellMarker 3.0, and PanglaoDB.

After rebuilding embeddings, rebuild the FAISS index if `RAG_VECTOR_BACKEND=faiss` will be used:

```bash
scripts/build_faiss_index.sh
```

The reranker model does not need rebuilding when corpus embeddings change. It only needs to exist locally if `RAG_RERANKER_ENABLED=true`.

For source details and rebuild order, see:

- `docs/CORPUS.md`
- `docs/RAG_WORKFLOW.md`

## Expand The Corpus

Create a JSONL file where each row has:

```json
{"doc_id":"paper:1","title":"Example","text":"Document text...","aliases":["optional alias"],"metadata":{"source":"optional"}}
```

Then run:

```bash
EXTRA_CORPUS_NAME=my_docs scripts/build_extra_jsonl_corpus.sh /path/to/docs.jsonl
```

Start the server with the expanded paths printed by that script, or update `.env` to point at the new combined artifacts.
