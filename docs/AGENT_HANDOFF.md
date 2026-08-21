# Agent Handoff

This note is for a future coding agent asked to rebuild or repair the backend on
a new machine.

## Goal

Recreate a portable single-cell biology RAG backend from this repository. The
old CCI runtime should be treated as unavailable. Do not assume any old
`/data/...` path, Cloudflare URL, API key, generated embeddings, or local model
snapshot still exists.

## Repository Role

This repository is the backend blueprint:

- API servers.
- RAG retrieval and answer generation code.
- Corpus builders.
- Startup/status/smoke-test scripts.
- Evaluation and benchmark cases.
- Source/model registries.
- Rebuild documentation.

It is not a runtime artifact store.

## Important Runtime Directories

These directories are generated on the new host and should remain outside Git:

```text
models/
sources/
raw/
processed/
chunks/
embeddings/
logs/
reports/
secrets/
qwen_env/
vllm_env/
```

## Service Architecture

The backend has three layers:

1. `vLLM` serves the local answer model through an OpenAI-compatible endpoint.
2. `src/rag_search_server.py` performs routing, retrieval, reranking, prompt
   construction, model calls, and citation checking.
3. `src/public_api_server.py` exposes authenticated `/ask`, `/search`,
   `/health`, and `/examples` endpoints.

User-facing CLI:

```bash
python rag_chat.py
```

Lower-level hosted smoke test:

```bash
python examples/smoke_hosted_demo.py
```

## First Commands On A New Host

```bash
git clone https://github.com/CenturiesLoD/CUHK_RAG_BACKEND.git
cd CUHK_RAG_BACKEND
cp .env.example .env
scripts/bootstrap_machine.sh
scripts/download_models.sh
```

Then follow `docs/FRESH_MACHINE_REBUILD.md`.

## Configuration Anchors

Important `.env` variables:

```text
LUOSS_BASE_URL
LUOSS_MODEL
PUBLIC_API_KEY
RAG_CHUNKS_PATH
RAG_ALIASES_PATH
RAG_MODEL_PATH
RAG_EMBEDDINGS_PATH
RAG_METADATA_PATH
RAG_VECTOR_BACKEND
RAG_FAISS_INDEX_PATH
RAG_RERANKER_ENABLED
LLM_MODEL_PATH
LLM_MODEL_SOURCE_PATH
LLM_SERVED_MODEL_NAME
LLM_CUDA_VISIBLE_DEVICES
RAG_CUDA_VISIBLE_DEVICES
```

## Common Failure Points

- Missing `git`, `rsync`, `curl`, or `openssh-client`: run
  `scripts/bootstrap_machine.sh`.
- Model files not present: run `scripts/download_models.sh` or update `.env`
  to point to another model path.
- vLLM starts slowly: large model weights and CUDA graph warmup can take
  several minutes.
- Public URL stale: rerun `scripts/init_public_demo.sh --publish-endpoint`.
- Quick tunnel DNS issue from inside the host: test public HTTPS from an
  external machine.
- Casual prompts get random citations: inspect `src/query_guards.py`,
  `src/rag_search_server.py`, and guardrail tests.

## Verification Checklist

Run:

```bash
python -m compileall -q src examples scripts tests
python -m unittest discover -s tests -v
scripts/status_all.sh
scripts/smoke_all.sh
scripts/run_retrieval_eval.sh
scripts/run_answer_eval.sh
```

From an external client:

```bash
export CELL_RAG_DEMO_API_KEY=<public-api-key>
python examples/smoke_hosted_demo.py
scripts/run_single_cell_benchmark.sh --limit 10
```

## Do Not Do

- Do not commit `.env`, secrets, keys, model snapshots, raw data, generated
  chunks, embeddings, FAISS indexes, logs, or reports.
- Do not hardcode a temporary Cloudflare quick-tunnel URL into docs as a stable
  backend address.
- Do not assume the old CCI runtime path exists.
- Do not replace source-aware ranking or query guards without updating tests.

