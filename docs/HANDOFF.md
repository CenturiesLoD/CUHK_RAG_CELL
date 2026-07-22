# Handoff Package

`scripts/package_handoff.sh` creates a self-contained report folder under `reports/handoff/<timestamp>/`.

It does not rebuild the RAG index and it does not change the running services. Its job is to collect the current project state so another person can inspect, run, and explain the system without hunting through the server.

The package includes:

- Current project documentation.
- Key runtime, ANN, reranker, answer-grounding, startup, and mentor API implementation files, including `src/rag_search_server.py`, `src/mentor_api_server.py`, `scripts/ensure_stack.sh`, `scripts/build_faiss_index.sh`, and `scripts/download_reranker_model.sh`.
- The latest audit report, if present.
- The latest demo report, if present.
- Fresh status, source-registry validation, and source-report logs.
- An artifact inventory listing key server-side source, processed, chunk, embedding, eval, and script files with file sizes and modified times.
- SSH config snippets and a short runbook.
- Active vector backend and reranker details from `/health`, including FAISS and neural reranker settings when enabled.
- Answer evaluation output that verifies returned citations against retrieved source blocks and the API `citation_check` field.
- Mentor API scripts and smoke-test output for `/health`, `/examples`, and `/ask`.
- Universal startup scripts for remote use and Windows use.
- Hosted-demo backend scripts, public tunnel status, and client examples.

Use it after major milestones:

```bash
scripts/package_handoff.sh
```

Use a named output directory when you want a stable label:

```bash
scripts/package_handoff.sh reports/handoff/final_review
```

The expected result is a `summary.txt` saying all package checks passed. If a check fails, open `status.tsv` first, then the referenced log under `logs/`.
