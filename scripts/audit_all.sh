#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

STAMP="${AUDIT_STAMP:-$(date -u +%Y%m%dT%H%M%SZ)}"
AUDIT_ROOT="${AUDIT_ROOT:-reports/audits}"
OUT_DIR="${1:-$AUDIT_ROOT/$STAMP}"
SUMMARY="$OUT_DIR/summary.txt"
STATUS_TSV="$OUT_DIR/step_status.tsv"

mkdir -p "$OUT_DIR"

echo "Cell RAG audit report" > "$SUMMARY"
echo "timestamp_utc: $STAMP" >> "$SUMMARY"
echo "project_root: $ROOT" >> "$SUMMARY"
echo "output_dir: $OUT_DIR" >> "$SUMMARY"
echo >> "$SUMMARY"
printf "status\tstep\tlog\n" > "$STATUS_TSV"

run_step() {
    local step="$1"
    shift
    local log="$OUT_DIR/${step}.log"

    echo "== $step =="
    echo "[$(date -Is)] START $step" >> "$SUMMARY"
    echo "command: $*" > "$log"
    echo >> "$log"

    set +e
    "$@" >> "$log" 2>&1
    local status=$?
    set -e

    printf "%s\t%s\t%s\n" "$status" "$step" "$log" >> "$STATUS_TSV"
    echo "[$(date -Is)] END $step status=$status log=$log" >> "$SUMMARY"
    echo >> "$SUMMARY"
    return 0
}

write_environment_snapshot() {
    local log="$OUT_DIR/00_environment_snapshot.log"
    {
        echo "timestamp_utc=$STAMP"
        echo "host=$(hostname)"
        echo "project_root=$ROOT"
        echo "user=$(id -un)"
        echo
        echo "git:"
        git rev-parse --short HEAD 2>/dev/null || echo "git_commit=unavailable"
        git status --short 2>/dev/null || echo "git_status=unavailable"
        echo
        echo "runtime .env:"
        if [[ -f .env ]]; then
            grep -E '^(RAG_|LUOSS_|CUDA_)' .env || true
        else
            echo ".env missing"
        fi
        echo
        echo "artifact sizes:"
        ls -lh \
            chunks/rag_chunks.jsonl \
            processed/rag_aliases.jsonl \
            embeddings/rag_qwen3_embedding_8b.npz \
            embeddings/rag_qwen3_embedding_8b.metadata.json \
            embeddings/rag_qwen3_embedding_8b.summary.json \
            sources/source_registry.json 2>/dev/null || true
        echo
        echo "line counts:"
        wc -l \
            chunks/rag_chunks.jsonl \
            processed/rag_aliases.jsonl \
            eval/queries.jsonl \
            eval/cellxgene_queries.jsonl \
            eval/answer_cases.jsonl \
            eval/cellxgene_answer_cases.jsonl 2>/dev/null || true
        echo
        echo "gpu:"
        nvidia-smi --query-gpu=name,memory.used,memory.total,utilization.gpu,temperature.gpu,power.draw --format=csv,noheader,nounits 2>/dev/null || true
    } > "$log" 2>&1
    printf "0\t%s\t%s\n" "environment_snapshot" "$log" >> "$STATUS_TSV"
}

write_environment_snapshot

run_step "01_start_all" scripts/start_all.sh
run_step "02_ensure_hosted_demo" scripts/ensure_hosted_demo.sh
run_step "03_status_initial" env STATUS_REQUIRE_PUBLIC_TUNNEL=1 PUBLIC_DEMO_SKIP_HEALTH=1 scripts/status_all.sh
run_step "04_validate_source_registry" scripts/validate_source_registry.sh
run_step "05_source_report" scripts/report_sources.sh
run_step "06_retrieval_eval_main" scripts/run_retrieval_eval.sh
run_step "07_retrieval_eval_cellxgene" scripts/run_retrieval_eval.sh --cases eval/cellxgene_queries.jsonl
run_step "08_answer_eval_main" scripts/run_answer_eval.sh
run_step "09_answer_eval_cellxgene" scripts/run_answer_eval.sh --cases eval/cellxgene_answer_cases.jsonl
run_step "10_status_final" env STATUS_REQUIRE_PUBLIC_TUNNEL=1 PUBLIC_DEMO_SKIP_HEALTH=1 scripts/status_all.sh
run_step "11_public_demo_state" env PUBLIC_DEMO_SKIP_HEALTH=1 scripts/status_public_demo_tunnel.sh

FAILED_STEPS="$(awk 'NR > 1 && $1 != 0 {print $2}' "$STATUS_TSV")"
{
    echo "Audit output: $OUT_DIR"
    echo
    if [[ -n "$FAILED_STEPS" ]]; then
        echo "FAILED steps:"
        echo "$FAILED_STEPS"
    else
        echo "All audit steps passed."
    fi
    echo
    echo "Step status:"
    column -t -s $'\t' "$STATUS_TSV" 2>/dev/null || cat "$STATUS_TSV"
} | tee -a "$SUMMARY"

if [[ -n "$FAILED_STEPS" ]]; then
    exit 1
fi
