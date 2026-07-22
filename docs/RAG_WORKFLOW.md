# RAG Build Workflow

This project keeps each source in the same rough pipeline:

```text
raw source file or API
  -> processed source records
  -> source aliases
  -> source chunks
  -> combined chunks and aliases
  -> Qwen3 embedding matrix
  -> optional FAISS ANN vector index
  -> optional neural reranker
  -> answer grounding and citation audit
  -> public API wrapper
  -> optional public hosted-demo tunnel
  -> live RAG service
```

## Directory Contract

- `raw/`: downloaded source files or API exports.
- `processed/`: normalized JSONL records and source-specific alias files.
- `chunks/`: retrievable text chunks. Each chunk has a stable `doc_id`, `title`, `text`, and `metadata`.
- `embeddings/`: `.npz` embedding matrices plus metadata, manifest, summary files, and optional FAISS indexes.
- `models/`: local embedding, reranker, and LLM model snapshots.
- `sources/source_registry.json`: server-side provenance and intended-use metadata for every active source.
- `eval/`: retrieval and answer smoke tests.
- `scripts/ensure_cell_rag_stack.ps1`: Windows helper for remote stack startup.
- `docs/HOSTED_DEMO.md`: hosted public demo backend workflow.

The `models/`, `sources/`, `raw/`, `processed/`, `chunks/`, `embeddings/`,
`secrets/`, `logs/`, and `reports/` directories are CCI runtime state and are
intentionally ignored by Git. The repo stays small; the hosted CCI backend owns
model loading, retrieval artifacts, and source-data storage.

## Source Build Scripts

| Script | Builds | Main outputs |
|---|---|---|
| `scripts/rebuild_cell_rag.sh` | Cell Ontology focused corpus | `processed/cl_terms.jsonl`, `chunks/cl_chunks.jsonl`, `embeddings/cl_qwen3_embedding_8b.npz` |
| `scripts/build_cellxgene_human_primary.sh` | CELLxGENE Census summaries | `processed/cellxgene_census_human_primary_counts.jsonl`, `chunks/cellxgene_census_human_primary_chunks.jsonl` |
| `scripts/build_hgnc.sh` | HGNC gene nomenclature | `processed/hgnc_genes.jsonl`, `chunks/hgnc_chunks.jsonl` |
| `scripts/build_ncbi_gene.sh` | NCBI Gene Human | `processed/ncbi_gene_human_records.jsonl`, `chunks/ncbi_gene_human_chunks.jsonl` |
| `scripts/build_uniprot.sh` | UniProtKB reviewed human proteins | `processed/uniprot_human_reviewed_records.jsonl`, `chunks/uniprot_human_reviewed_chunks.jsonl` |
| `scripts/build_marker_sources.sh` | CellMarker 3.0 and PanglaoDB | `chunks/cellmarker3_chunks.jsonl`, `chunks/panglaodb_chunks.jsonl` |
| `scripts/build_combined_rag_with_cellxgene.sh` | Combined runtime corpus | `chunks/rag_chunks.jsonl`, `processed/rag_aliases.jsonl`, `embeddings/rag_qwen3_embedding_8b.npz` |
| `scripts/build_faiss_index.sh` | Optional FAISS ANN index | `embeddings/rag_qwen3_embedding_8b.ivfflat.faiss` |
| `scripts/download_reranker_model.sh` | Optional neural reranker model | `models/ms-marco-MiniLM-L-6-v2` |
| `scripts/start_public_api.sh` | Public API wrapper | `http://127.0.0.1:8020` |
| `scripts/ensure_hosted_demo.sh` | Public hosted demo backend | Cloudflare quick-tunnel URL |

## Rebuild Order

For source changes:

1. Build or refresh the individual source.
2. Confirm the source report:

```bash
scripts/report_sources.sh
```

3. Rebuild the combined corpus:

```bash
CUDA_VISIBLE_DEVICES=1 scripts/build_combined_rag_with_cellxgene.sh
```

4. If FAISS retrieval is enabled, rebuild the FAISS index so it matches the new embedding matrix:

```bash
scripts/build_faiss_index.sh
```

5. If the neural reranker is enabled and missing locally, download it:

```bash
scripts/download_reranker_model.sh cross-encoder/ms-marco-MiniLM-L-6-v2 models/ms-marco-MiniLM-L-6-v2
```

6. Restart the RAG server:

```bash
scripts/stop_rag_server.sh
scripts/start_rag_server.sh
```

7. Run smoke tests:

```bash
scripts/run_retrieval_eval.sh
scripts/run_retrieval_eval.sh --cases eval/cellxgene_queries.jsonl
scripts/run_answer_eval.sh
scripts/run_answer_eval.sh --cases eval/cellxgene_answer_cases.jsonl
scripts/smoke_public_api.sh
```

When the neural reranker is loaded, compare with and without it:

```bash
scripts/run_retrieval_eval.sh --use-neural-reranker true
scripts/run_retrieval_eval.sh --use-neural-reranker false
```

Or run the full validation and smoke-test sequence:

```bash
scripts/smoke_all.sh
```

For a reproducible run with saved logs:

```bash
scripts/audit_all.sh
```

The audit script runs the same validation families as `smoke_all.sh`, but saves
each step to `reports/audits/<timestamp>/` and writes a `summary.txt` plus
`step_status.tsv`. Use this after source additions, ranking changes, answer
prompt changes, or before sharing the project state.

For a presentation-ready demo with curated questions and saved cited answers:

```bash
scripts/run_demo_pack.sh
```

The demo output is written to `reports/demos/<timestamp>/`. It is intended for
showing what the system can answer, while the audit output is intended for
proving the runtime and tests passed.

## Runtime Services

The full stack is:

- local vLLM server serving `qwen3-32b` on `127.0.0.1:8000/v1`
- FastAPI RAG server on `127.0.0.1:8010`
- FastAPI public API wrapper on `127.0.0.1:8020`
- optional Cloudflare quick tunnel exposing the public API through a public HTTPS URL
- vector retrieval backend selected by `RAG_VECTOR_BACKEND`, either `exact` or `faiss`
- optional cross-encoder reranker selected by `RAG_RERANKER_ENABLED`
- structured citation audit returned by `/answer` as `citation_check`

Use:

```bash
scripts/ensure_stack.sh
scripts/start_all.sh
scripts/status_all.sh
scripts/stop_all.sh
```

`scripts/start_all.sh` delegates to `scripts/ensure_stack.sh`. The ensure script
is the preferred startup entry point because it checks health endpoints before
starting anything, waits for services that are already loading, and restarts an
unhealthy service once only after its wait budget is exhausted. This makes the
normal warm path fast while keeping cold-start behavior explicit.

Cold starts are still bounded by vLLM loading the Qwen3-32B checkpoint and
compiling/warming kernels. To improve that path, `scripts/start_llm_server.sh`
sets `LLM_SAFETENSORS_LOAD_STRATEGY=prefetch` by default and passes
`--safetensors-prefetch-num-threads` when prefetch is enabled.

`LLM_ENFORCE_EAGER=true` passes `--enforce-eager` to vLLM, disabling CUDA graph
execution. Use `scripts/benchmark_llm_startup.sh` to compare normal CUDA graph
mode with eager mode. The benchmark measures startup-to-health and first
completion latency, then leaves the server restored in default CUDA graph mode.

Model load time also depends on storage. Use `scripts/inspect_model_storage.sh`
to check the current filesystem and sample read throughput. If CCI exposes a
faster scratch/NVMe mount with enough free space, use
`scripts/prepare_fast_model_cache.sh /path/to/fast-scratch/Qwen3-32B`, then set
`LLM_MODEL_PATH` to that copied model directory before starting vLLM.
For repeatable runtime startup, use `scripts/configure_fast_model_cache.sh` to
write `LLM_FAST_MODEL_CACHE_ENABLED=true` and `LLM_FAST_MODEL_CACHE_PATH` into
`.env`; `scripts/start_llm_server.sh` will then prepare the cache if it is
missing and start from the fast path.

When `RAG_VECTOR_BACKEND=faiss`, the RAG server loads `RAG_FAISS_INDEX_PATH`
and searches `RAG_FAISS_CANDIDATES` vector candidates with `RAG_FAISS_NPROBE`
IVF probes before applying the existing hybrid scoring. The `/health` endpoint
reports the active vector backend and FAISS settings.

When `RAG_RERANKER_ENABLED=true`, the RAG server loads
`RAG_RERANKER_MODEL_PATH`, reranks the top `RAG_RERANKER_CANDIDATES` hybrid
candidates, and adds `RAG_RERANKER_WEIGHT` times the normalized neural reranker
score before final top-K selection. Exact alias/name/ID matches use
`RAG_RERANKER_EXACT_MATCH_WEIGHT`, which defaults to `0.0`, so the generic
cross-encoder cannot override curated identifier matches. Per request,
`use_neural_reranker=false` can disable this pass for comparison.

The `/answer` endpoint validates the final cited response after deterministic
grounding. The returned `citation_check` lists retrieved source block IDs,
answer citations, valid and invalid citations, uncited factual-looking claim
units, and a `passed` flag. Answer smoke tests require this field to exist and
pass, so citation regressions are caught through the normal eval path.

The public API wrapper exposes a smaller surface
for live demonstration:

- `GET /health`
- `GET /examples`
- `POST /ask`
- `POST /search`

It calls the internal RAG API rather than loading models itself. By default it
binds only to `127.0.0.1`; use the Windows tunnel script for local external access.

For external access without SSH, use the hosted demo backend:

```bash
scripts/ensure_hosted_demo.sh
scripts/status_public_demo_tunnel.sh
```

This starts an outbound Cloudflare quick tunnel from the CCI server to the
localhost public API wrapper. The model remains hosted on CCI; the public URL only
forwards API requests to the CCI runtime. Because quick-tunnel URLs are
ephemeral, use a named Cloudflare Tunnel, custom domain, or CCI port mapping for
a stable long-lived demo URL.

## Current Deferred Work

These are intentionally not part of the immediate gap-plugging pass:

- richer CELLxGENE dataset/publication/donor/expression integration
- a production vector database service such as Chroma, Milvus, or distributed FAISS
- a persistent lexical index to replace the current in-process BM25 scan at literature scale
