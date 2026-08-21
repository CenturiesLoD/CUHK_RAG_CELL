# Model Registry

The backend is model-agnostic as long as the generation model is served through
an OpenAI-compatible endpoint.

## Default Runtime Models

| Role | Default model | Local path | Access |
|---|---|---|---|
| Answer generation | Qwen3-32B | `models/Qwen3-32B` | https://huggingface.co/Qwen/Qwen3-32B |
| Embeddings | Qwen3-Embedding-8B | `models/Qwen3-Embedding-8B` | https://huggingface.co/Qwen/Qwen3-Embedding-8B |
| Active reranker | MS MARCO MiniLM cross-encoder | `models/ms-marco-MiniLM-L-6-v2` | https://huggingface.co/cross-encoder/ms-marco-MiniLM-L6-v2 |
| Optional reranker | BGE reranker base | `models/bge-reranker-base` | https://huggingface.co/BAAI/bge-reranker-base |

## Generation Model Swap

To compare another local model while keeping retrieval fixed:

```bash
export LLM_MODEL_PATH=models/<other-model>
export LLM_MODEL_SOURCE_PATH=models/<other-model>
export LLM_SERVED_MODEL_NAME=<served-name>
export LUOSS_MODEL=<served-name>

scripts/stop_llm_server.sh
scripts/start_llm_server.sh
scripts/stop_rag_server.sh
scripts/start_rag_server.sh
```

Then run:

```bash
scripts/run_single_cell_benchmark.sh --output reports/benchmark/<served-name>.json
```

Keep the same corpus, embeddings, FAISS index, reranker, prompt, and benchmark
cases when comparing answer models.

## External API Model Swap

The RAG answer layer calls an OpenAI-compatible chat completions endpoint. If a
provider exposes that interface, update:

```text
LUOSS_BASE_URL=<provider-compatible-base-url>
LUOSS_MODEL=<provider-model-name>
LUOSS_API_KEY=<provider-key>
```

Provider-specific authentication, rate limits, and model names are outside this
repo and should be documented in the deployment notes for that host.

