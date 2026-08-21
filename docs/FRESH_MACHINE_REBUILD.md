# Fresh Machine Backend Rebuild

This guide is for rebuilding the backend on a new Linux GPU host after the
original CCI runtime is no longer available.

The repository intentionally does not contain model weights, generated corpora,
embeddings, FAISS indexes, logs, reports, or secrets. A fresh host rebuilds
those runtime artifacts from source URLs, model IDs, and scripts.

## Expected Host

Recommended baseline:

- Ubuntu 20.04 or newer.
- NVIDIA GPU with CUDA-compatible driver.
- Enough disk for model snapshots and generated artifacts.
- Root or sudo access for system packages.
- Network access to Hugging Face, OBO Foundry, HGNC, NCBI, UniProt, CELLxGENE,
  CellMarker, and PanglaoDB.

For Qwen3-32B, use a high-memory GPU host. Smaller OpenAI-compatible local
models can be substituted by changing `.env`.

## Repository Setup

```bash
git clone https://github.com/CenturiesLoD/CUHK_RAG_BACKEND.git
cd CUHK_RAG_BACKEND
```

Create runtime config:

```bash
cp .env.example .env
```

Edit `.env` for the new host. The most important values are:

```text
LLM_MODEL_PATH=models/Qwen3-32B
LLM_SERVED_MODEL_NAME=qwen3-32b
LUOSS_BASE_URL=http://127.0.0.1:8000/v1
LUOSS_MODEL=qwen3-32b
RAG_MODEL_PATH=models/Qwen3-Embedding-8B
RAG_VECTOR_BACKEND=faiss
PUBLIC_API_KEY=<new-private-demo-key>
```

Do not commit `.env`.

## Bootstrap System Packages And Python Environments

Run:

```bash
scripts/bootstrap_machine.sh
```

This checks/install basic system packages, creates `qwen_env`, installs the
main backend requirements, creates `vllm_env`, and installs vLLM. If the host
uses a special CUDA/PyTorch/vLLM combination, a future agent may need to adjust
the install command.

## Download Models

If Hugging Face rate limits downloads, set a token first:

```bash
export HF_TOKEN=<hugging-face-token>
```

Download the default model snapshots:

```bash
scripts/download_models.sh
```

Default paths:

```text
models/Qwen3-32B
models/Qwen3-Embedding-8B
models/ms-marco-MiniLM-L-6-v2
```

The large generation model may take a long time to download. If a smaller model
is used, update `LLM_MODEL_PATH`, `LLM_MODEL_SOURCE_PATH`, `LLM_SERVED_MODEL_NAME`,
and `LUOSS_MODEL` in `.env`.

## Rebuild Source Artifacts

The current source and model registries are documented in:

```text
docs/source_registry.template.json
docs/model_registry.json
docs/CORPUS.md
```

The full current rebuild expects raw/processed/chunk files for all active
sources, then combines and embeds them.

Typical source build order:

```bash
mkdir -p raw processed chunks embeddings sources

# Ontologies: prepare sources/ontology_sources.tsv from docs/source_registry.template.json,
# then run:
scripts/build_multi_source_rag.sh sources/ontology_sources.tsv

# Gene/protein/marker sources:
scripts/build_hgnc.sh
scripts/build_ncbi_gene.sh
scripts/build_uniprot.sh
scripts/build_marker_sources.sh

# CELLxGENE summary source:
scripts/build_cellxgene_human_primary.sh

# Combine all source chunks and embed the combined corpus:
scripts/build_combined_rag_with_cellxgene.sh
scripts/build_faiss_index.sh
```

If a source URL, schema, or license changes, update the builder and registry
before rebuilding.

## Start Backend

Start all local services:

```bash
scripts/start_all.sh
```

Or initialize the hosted public wrapper and endpoint manifest:

```bash
scripts/init_public_demo.sh --publish-endpoint
```

For a one-machine local rebuild without public tunnel publishing, use:

```bash
scripts/ensure_stack.sh
scripts/status_all.sh
```

## Smoke Test

Server-side smoke tests:

```bash
scripts/smoke_all.sh
scripts/run_retrieval_eval.sh
scripts/run_answer_eval.sh
```

Hosted client smoke test from another machine:

```bash
export CELL_RAG_DEMO_API_KEY=<public-api-key>
python examples/smoke_hosted_demo.py
```

Benchmark run:

```bash
export CELL_RAG_DEMO_API_KEY=<public-api-key>
scripts/run_single_cell_benchmark.sh --output reports/benchmark/latest.json
```

## What To Commit

Commit code, docs, tests, scripts, config templates, benchmark cases, and source
or model registries.

Do not commit:

```text
.env
secrets/
models/
sources/
raw/
processed/
chunks/
embeddings/
logs/
reports/
qwen_env/
vllm_env/
```

These are intentionally ignored by `.gitignore`.

