# Audit Workflow

`scripts/audit_all.sh` creates a timestamped evidence package for the current
RAG runtime.

Run from the project root:

```bash
scripts/ensure_stack.sh
scripts/audit_all.sh
```

When starting an audit through SSH, prefer the detached wrapper. It keeps the
evaluation running on CCI if the SSH connection closes and records the current
PID, output directory, and log under `logs/`:

```bash
scripts/start_detached_audit.sh
scripts/status_detached_audit.sh
```

Use `scripts/ensure_stack.sh` before audits or demos when the stack may have
been stopped by the runtime. It starts only missing services and leaves healthy
services running.

By default, output is written to:

```text
reports/audits/<UTC timestamp>/
```

You can override the output directory:

```bash
scripts/audit_all.sh reports/audits/manual_check
```

## Captured Files

Each audit directory contains:

- `summary.txt`: high-level run summary and pass/fail status.
- `step_status.tsv`: exit status for each audit step.
- `00_environment_snapshot.log`: host, project root, Git state if available,
  runtime `.env` settings, artifact file sizes, line counts, and GPU state.
- `01_start_all.log`: local LLM and RAG startup result.
- `02_ensure_hosted_demo.log`: public API authentication and Cloudflare tunnel startup.
- `03_status_initial.log`: initial server, model, tunnel, and GPU health.
- `04_validate_source_registry.log`: source registry and artifact consistency
  validation.
- `05_source_report.log`: active source counts and field coverage.
- `06_retrieval_eval_main.log`: main retrieval eval.
- `07_retrieval_eval_cellxgene.log`: CELLxGENE retrieval eval.
- `08_answer_eval_main.log`: main answer-grounding and citation-audit eval.
- `09_answer_eval_cellxgene.log`: CELLxGENE answer-grounding and citation-audit eval.
- `10_status_final.log`: final server, model, vector backend, reranker, tunnel, and GPU health.
- `11_public_demo_state.log`: live tunnel process and current URL-file validation.

The public API wrapper also has a focused smoke test:

```bash
scripts/smoke_public_api.sh
```

It verifies `/health`, `/examples`, and `/ask`, including the returned
`citation_check`.

## What Passing Means

A passing audit means:

- the configured RAG and LLM services can start or are already running;
- the combined chunk, alias, and embedding artifacts are internally consistent;
- all active sources in `sources/source_registry.json` validate;
- the configured vector backend and reranker load and report settings through `/health`;
- retrieval routing still passes the current source-aware smoke tests;
- generated answers pass citation and grounding hygiene checks, including the API-returned `citation_check`;
- the public API wrapper can call the internal RAG API and return a cited answer through `/ask`;
- the Cloudflare tunnel process is live and has a current public URL;
- the stack remains healthy at the end of the run.

Some CCI runtime images cannot resolve their own `trycloudflare.com` hostname.
For that reason, public HTTPS reachability is tested from an external client,
not counted from CCI DNS. Run `python examples/smoke_hosted_demo.py` externally
with the API key after the server-side audit.

## What Passing Does Not Mean

The audit is not a full scientific benchmark. It does not prove exhaustive
biological correctness, recall across all possible single-cell queries, or
literature-scale performance. It also does not cover deferred work such as
richer CELLxGENE dataset/publication/donor/expression integration, production
vector database migration, replacing the in-process BM25 scan with a persistent
lexical index, or fine-tuning the reranker on single-cell-specific relevance
judgments.
