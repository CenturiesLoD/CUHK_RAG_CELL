#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

STAMP="${HANDOFF_STAMP:-$(date -u +%Y%m%dT%H%M%SZ)}"
HANDOFF_ROOT="${HANDOFF_ROOT:-reports/handoff}"
OUT_DIR="${1:-$HANDOFF_ROOT/$STAMP}"
SUMMARY="$OUT_DIR/summary.txt"
STATUS_TSV="$OUT_DIR/status.tsv"

mkdir -p "$OUT_DIR"/{docs,logs,project_files,latest_audit,latest_demo,ann_reports,reranker_reports,citation_reports,api_reports,public_demo_reports,startup_ab_reports}

copy_project_file() {
    local src="$1"
    local dest="$OUT_DIR/project_files/$src"

    if [[ -e "$src" ]]; then
        mkdir -p "$(dirname "$dest")"
        cp -a "$src" "$dest"
    fi
}

latest_dir() {
    local parent="$1"

    [[ -d "$parent" ]] || return 1
    find "$parent" -mindepth 1 -maxdepth 1 -type d -printf '%T@ %p\n' 2>/dev/null \
        | sort -nr \
        | awk 'NR == 1 { $1=""; sub(/^ /, ""); print; exit }'
}

run_capture() {
    local step="$1"
    shift
    local log="$OUT_DIR/logs/${step}.log"

    echo "== $step =="
    echo "command: $*" > "$log"
    echo >> "$log"

    set +e
    "$@" >> "$log" 2>&1
    local status=$?
    set -e

    printf "%s\t%s\t%s\n" "$status" "$step" "$log" >> "$STATUS_TSV"
    return 0
}

write_file_inventory() {
    {
        printf "path\tsize_bytes\tmtime_utc\n"
        find scripts src docs sources eval demo chunks processed embeddings raw -maxdepth 2 -type f 2>/dev/null | sort | while read -r path; do
            local size
            local mtime
            size="$(stat -c '%s' "$path" 2>/dev/null || echo unknown)"
            mtime="$(date -u -r "$path" +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || echo unknown)"
            printf "%s\t%s\t%s\n" "$path" "$size" "$mtime"
        done
    } > "$OUT_DIR/artifact_inventory.tsv"
}

write_ssh_config() {
    cat > "$OUT_DIR/ssh_config.txt" <<'EOF'
Host lepton-cci-h100
    HostName <CCI_H100_HOSTNAME_OR_IP>
    Port 20484
    User root
    IdentityFile <PATH_TO_SSH_IDENTITY_FILE>
    IdentitiesOnly yes
    StrictHostKeyChecking no
    UserKnownHostsFile NUL

Host lepton-cci-old
    HostName <OLD_CCI_HOSTNAME_OR_IP>
    Port 20484
    User root
    IdentityFile <PATH_TO_SSH_IDENTITY_FILE>
    IdentitiesOnly yes
    StrictHostKeyChecking no
    UserKnownHostsFile NUL
EOF
}

write_runbook() {
    cat > "$OUT_DIR/RUNBOOK.md" <<'EOF'
# Cell RAG Runbook

## Connect

```powershell
ssh lepton-cci-h100
```

Or without editing SSH config:

```powershell
ssh -p 20484 -i <PATH_TO_SSH_IDENTITY_FILE> -o IdentitiesOnly=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=NUL root@<CCI_H100_HOSTNAME_OR_IP>
```

## Project Root

```bash
cd /data/L202500484/cell_rag
```

## Runtime Checks

```bash
scripts/ensure_stack.sh
scripts/ensure_hosted_demo.sh
scripts/status_all.sh
scripts/status_public_api.sh
scripts/status_public_demo_tunnel.sh
scripts/smoke_all.sh
scripts/smoke_public_api.sh
scripts/smoke_public_demo.sh
scripts/audit_all.sh
scripts/run_demo_pack.sh
scripts/package_handoff.sh
scripts/ensure_cell_rag_stack.ps1
scripts/ensure_cell_rag_stack.ps1
```

From Windows, the one-command remote startup wrapper is:

```powershell
scripts\ensure_cell_rag_stack.ps1 -HostName <CCI_H100_HOSTNAME_OR_IP> -IdentityFile <PATH_TO_SSH_IDENTITY_FILE>
```

## Services

```bash
scripts/start_all.sh
scripts/stop_all.sh
```

## Query The Local RAG API

```bash
curl -s -X POST http://127.0.0.1:8010/answer \
  -H 'Content-Type: application/json' \
  -d '{"question":"What markers identify regulatory T cells in blood?","top_k":8}'
```

## Public API

The public API wrapper runs on the server at `127.0.0.1:8020` and wraps the
internal RAG API with simpler endpoints:

```bash
scripts/status_public_api.sh
scripts/smoke_public_api.sh
```

From Windows, run the local tunnel script:

```powershell
scripts\ensure_cell_rag_stack.ps1 -HostName <CCI_H100_HOSTNAME_OR_IP> -IdentityFile <PATH_TO_SSH_IDENTITY_FILE>
```

Then open:

```text
http://127.0.0.1:8020/docs
```

For a one-time connectivity check that closes the tunnel automatically:

```powershell
scripts\ensure_cell_rag_stack.ps1 -HostName <CCI_H100_HOSTNAME_OR_IP> -IdentityFile <PATH_TO_SSH_IDENTITY_FILE>
```

## Current Core Artifacts

- `chunks/rag_chunks.jsonl`: combined searchable text chunks.
- `processed/rag_aliases.jsonl`: alias/synonym lookup records.
- `embeddings/rag_qwen3_embedding_8b.npz`: NumPy embedding matrix aligned one-to-one with `chunks/rag_chunks.jsonl`.
- `embeddings/rag_qwen3_embedding_8b.ivfflat.faiss`: optional FAISS ANN index built from the embedding matrix.
- `models/ms-marco-MiniLM-L-6-v2`: optional cross-encoder reranker used after initial retrieval.
- `sources/source_registry.json`: server-side pinned source registry with URLs, licenses, versions, and ingestion status.

The `/answer` response includes `citation_check`, which verifies that final answer citations refer to retrieved source block IDs.
The public API `/ask` endpoint returns the same citation audit in a cleaner demonstration response.
Use `scripts/ensure_stack.sh` for startup; it avoids restarting healthy services
and waits for already-loading services before taking corrective action.
Use `scripts/ensure_hosted_demo.sh` to start the public hosted demo backend.
EOF
}

write_handoff_summary() {
    local latest_audit="$1"
    local latest_demo="$2"
    local failed_steps="$3"

    {
        echo "Cell RAG handoff package"
        echo "timestamp_utc: $STAMP"
        echo "project_root: $ROOT"
        echo "output_dir: $OUT_DIR"
        echo
        echo "Included project documentation:"
        echo "- README.md"
        echo "- docs/PROJECT_SUMMARY.md"
        echo "- docs/CORPUS.md"
        echo "- docs/RAG_WORKFLOW.md"
        echo "- docs/HOSTED_DEMO.md"
        echo "- docs/AUDIT.md"
        echo "- docs/RELEASE_PACKAGE.md"
        echo "- examples/python_client.py"
        echo "- examples/smoke_hosted_demo.py"
        echo "- examples/windows_client.ps1"
        echo "- examples/curl_examples.md"
        echo "- scripts/benchmark_llm_startup.sh"
        echo "- scripts/configure_fast_model_cache.sh"
        echo "- scripts/inspect_model_storage.sh"
        echo "- scripts/prepare_fast_model_cache.sh"
        echo
        echo "Included generated reports:"
        if [[ -n "$latest_audit" ]]; then
            echo "- latest audit: $latest_audit"
        else
            echo "- latest audit: none found"
        fi
        if [[ -n "$latest_demo" ]]; then
            echo "- latest demo: $latest_demo"
        else
            echo "- latest demo: none found"
        fi
        echo
        echo "Fresh checks captured in this package:"
        echo "- status_all"
        echo "- validate_source_registry"
        echo "- report_sources"
        echo
        echo "Milestone report folders copied when present:"
        echo "- ann_reports"
        echo "- reranker_reports"
        echo "- citation_reports"
        echo "- api_reports"
        echo "- public_demo_reports"
        echo "- startup_ab_reports"
        echo
        if [[ -n "$failed_steps" ]]; then
            echo "FAILED checks:"
            echo "$failed_steps"
        else
            echo "All package checks passed."
        fi
        echo
        echo "Files to open first:"
        echo "- RUNBOOK.md"
        echo "- summary.txt"
        echo "- project_files/docs/PROJECT_SUMMARY.md"
        echo "- project_files/docs/HOSTED_DEMO.md"
        echo "- project_files/examples/smoke_hosted_demo.py"
        echo "- latest_demo/answers.md"
        echo "- latest_audit/summary.txt"
        echo
        echo "Step status:"
        column -t -s $'\t' "$STATUS_TSV" 2>/dev/null || cat "$STATUS_TSV"
    } > "$SUMMARY"
}

printf "status\tstep\tlog\n" > "$STATUS_TSV"

for path in \
    README.md \
    docs/PROJECT_SUMMARY.md \
    docs/CORPUS.md \
    docs/RAG_WORKFLOW.md \
    docs/HOSTED_DEMO.md \
    docs/AUDIT.md \
    docs/RELEASE_PACKAGE.md \
    examples/python_client.py \
    examples/smoke_hosted_demo.py \
    examples/windows_client.ps1 \
    examples/curl_examples.md \
    requirements.txt \
    src/rag_search_server.py \
    src/public_api_server.py \
    src/build_faiss_index.py \
    src/evaluate_retrieval.py \
    src/evaluate_answers.py \
    scripts/ensure_stack.sh \
    scripts/ensure_hosted_demo.sh \
    scripts/ensure_cell_rag_stack.ps1 \
    scripts/install_cloudflared.sh \
    scripts/configure_public_api_auth.sh \
    scripts/start_public_demo_tunnel.sh \
    scripts/stop_public_demo_tunnel.sh \
    scripts/status_public_demo_tunnel.sh \
    scripts/smoke_public_demo.sh \
    scripts/start_all.sh \
    scripts/stop_all.sh \
    scripts/status_all.sh \
    scripts/start_llm_server.sh \
    scripts/benchmark_llm_startup.sh \
    scripts/configure_fast_model_cache.sh \
    scripts/inspect_model_storage.sh \
    scripts/prepare_fast_model_cache.sh \
    scripts/start_public_api.sh \
    scripts/stop_public_api.sh \
    scripts/status_public_api.sh \
    scripts/smoke_public_api.sh \
    scripts/build_faiss_index.sh \
    scripts/download_reranker_model.sh \
    scripts/run_retrieval_eval.sh \
    scripts/run_answer_eval.sh \
    scripts/package_handoff.sh \
    demo/showcase_queries.jsonl
do
    copy_project_file "$path"
done

latest_audit="$(latest_dir reports/audits || true)"
latest_demo="$(latest_dir reports/demos || true)"

if [[ -n "$latest_audit" ]]; then
    cp -a "$latest_audit"/. "$OUT_DIR/latest_audit"/
fi

if [[ -n "$latest_demo" ]]; then
    cp -a "$latest_demo"/. "$OUT_DIR/latest_demo"/
fi

if [[ -d reports/ann ]]; then
    find reports/ann -maxdepth 1 -type f -exec cp -a {} "$OUT_DIR/ann_reports"/ \;
fi

if [[ -d reports/reranker ]]; then
    find reports/reranker -maxdepth 1 -type f -exec cp -a {} "$OUT_DIR/reranker_reports"/ \;
fi

if [[ -d reports/citation_audit ]]; then
    find reports/citation_audit -maxdepth 1 -type f -exec cp -a {} "$OUT_DIR/citation_reports"/ \;
fi

if [[ -d reports/public_api ]]; then
    find reports/public_api -maxdepth 1 -type f -exec cp -a {} "$OUT_DIR/api_reports"/ \;
fi

if [[ -d reports/public_demo ]]; then
    find reports/public_demo -maxdepth 1 -type f -exec cp -a {} "$OUT_DIR/public_demo_reports"/ \;
fi

latest_startup_ab="$(latest_dir reports/startup_ab || true)"
if [[ -n "$latest_startup_ab" ]]; then
    cp -a "$latest_startup_ab"/. "$OUT_DIR/startup_ab_reports"/
fi

write_file_inventory
write_ssh_config
write_runbook

run_capture "01_status_all" scripts/status_all.sh
run_capture "02_validate_source_registry" scripts/validate_source_registry.sh
run_capture "03_report_sources" scripts/report_sources.sh

FAILED_STEPS="$(awk 'NR > 1 && $1 != 0 {print $2}' "$STATUS_TSV" || true)"
write_handoff_summary "$latest_audit" "$latest_demo" "$FAILED_STEPS"

cat "$SUMMARY"

if [[ -n "$FAILED_STEPS" ]]; then
    exit 1
fi
