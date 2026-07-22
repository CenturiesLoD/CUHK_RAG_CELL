# Release Package

`scripts/package_handoff.sh` creates a self-contained report folder under
`reports/handoff/<timestamp>/`. The script name is retained for compatibility
with earlier server runs.

It does not rebuild the RAG index and it does not change running services. Its
job is to collect the current project state so another person can inspect, run,
and explain the system without searching through the server.

The package includes:

- Current project documentation.
- Key runtime, ANN, reranker, answer-grounding, startup, and API implementation files.
- The latest audit report, if present.
- The latest demo report, if present.
- Fresh status, source-registry validation, and source-report logs.
- An artifact inventory with server-side source, processed, chunk, embedding,
  eval, and script file sizes and modified times.
- SSH config snippets and a short runbook.
- Active vector backend and reranker details from `/health`.
- Answer evaluation output that verifies returned citations against retrieved
  source blocks and the API `citation_check` field.
- Public API smoke-test output for `/health`, `/examples`, and `/ask`.
- Hosted-backend scripts, public tunnel status, and client examples.

Use it after major milestones:

```bash
scripts/package_handoff.sh
```

Use a named output directory when you want a stable label:

```bash
scripts/package_handoff.sh reports/handoff/final_review
```

The expected result is a `summary.txt` saying all package checks passed. If a
check fails, open `status.tsv` first, then the referenced log under `logs/`.
