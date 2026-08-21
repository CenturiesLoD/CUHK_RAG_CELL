#!/usr/bin/env python3
"""Run the curated single-cell benchmark against the hosted public RAG API."""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.hosted_endpoint import resolve_base_url  # noqa: E402


CITATION_RE = re.compile(r"\[([^\[\]\n]+)\]")
CONFIDENCE_ORDER = {"none": -1, "low": 0, "medium": 1, "high": 2}


RECOVERY_HINT = """Hosted backend may be down or the published tunnel URL may be stale.
If you have CCI SSH access, restart and republish the hosted stack:

cd <runtime-dir> && scripts/init_public_demo.sh --publish-endpoint

Then rerun:
python src/evaluate_single_cell_benchmark.py"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the single-cell hosted RAG benchmark.")
    parser.add_argument("--cases", default="eval/single_cell_benchmark.jsonl")
    parser.add_argument("--base-url", default=os.environ.get("CELL_RAG_DEMO_URL", ""))
    parser.add_argument("--api-key", default=os.environ.get("CELL_RAG_DEMO_API_KEY", ""))
    parser.add_argument("--category", action="append", default=[])
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--skip-search", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--output", default="")
    parser.add_argument("--csv-output", default="")
    return parser.parse_args()


def load_cases(path: Path) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            case = json.loads(line)
            case["_line"] = line_number
            cases.append(case)
    return cases


def request_json(
    method: str,
    url: str,
    *,
    api_key: str,
    payload: dict[str, Any] | None = None,
    timeout: int,
) -> tuple[int, dict[str, Any]]:
    headers = {}
    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = response.read().decode("utf-8")
        return response.status, json.loads(body) if body else {}


def as_set(value: Any) -> set[str]:
    if value is None or value == "":
        return set()
    if isinstance(value, str):
        return {value}
    return {str(item) for item in value}


def lower_contains_all(haystack: str, needles: list[str]) -> list[str]:
    folded = haystack.casefold()
    return [needle for needle in needles if str(needle).casefold() not in folded]


def extract_citations(answer: str) -> list[str]:
    seen: set[str] = set()
    citations: list[str] = []
    for match in CITATION_RE.finditer(answer):
        citation = match.group(1).strip()
        if citation and citation not in seen:
            seen.add(citation)
            citations.append(citation)
    return citations


def score_case(
    case: dict[str, Any],
    *,
    base_url: str,
    api_key: str,
    timeout: int,
    skip_search: bool,
) -> dict[str, Any]:
    query = str(case["query"])
    top_k = int(case.get("top_k", 5))
    max_tokens = int(case.get("max_tokens", 220))
    expected_route = str(case.get("expected_route") or "")
    expected_citations = case.get("expected_citations")
    expected_sources = case.get("expected_sources")

    ask_payload = {"question": query, "top_k": top_k, "max_tokens": max_tokens}
    started = time.perf_counter()
    ask_status, ask_body = request_json(
        "POST",
        f"{base_url}/ask",
        api_key=api_key,
        payload=ask_payload,
        timeout=timeout,
    )
    latency = round(time.perf_counter() - started, 3)

    answer = str(ask_body.get("answer") or "")
    answer_citations = extract_citations(answer)
    sources = list(ask_body.get("sources") or [])
    source_ids = [str(source.get("doc_id") or "") for source in sources]
    source_types = [str(source.get("source_type") or "") for source in sources]
    top_source_type = source_types[0] if source_types else ""
    citation_check = ask_body.get("citation_check") or {}
    retrieval_quality = ask_body.get("retrieval_quality") or {}
    intent = ""
    query_intent = retrieval_quality.get("query_intent")
    if isinstance(query_intent, dict):
        intent = str(query_intent.get("intent") or "")

    failures: list[str] = []
    if ask_status != 200:
        failures.append(f"ask_status={ask_status}")
    if expected_route and not intent:
        failures.append(f"missing query intent; expected {expected_route}")
    elif expected_route and intent != expected_route:
        failures.append(f"route expected {expected_route}, got {intent}")
    if isinstance(citation_check, dict) and citation_check.get("passed") is False:
        failures.append("citation_check failed")

    missing_answer_text = lower_contains_all(answer, [str(item) for item in case.get("must_contain", [])])
    missing_claims = lower_contains_all(answer, [str(item) for item in case.get("required_claims", [])])
    forbidden_text = [
        item for item in case.get("must_not_contain", []) if str(item).casefold() in answer.casefold()
    ]
    forbidden_claims = [
        item for item in case.get("forbidden_claims", []) if str(item).casefold() in answer.casefold()
    ]
    if missing_answer_text:
        failures.append(f"missing text: {missing_answer_text}")
    if missing_claims:
        failures.append(f"missing claims: {missing_claims}")
    if forbidden_text:
        failures.append(f"forbidden text: {forbidden_text}")
    if forbidden_claims:
        failures.append(f"forbidden claims: {forbidden_claims}")

    expected_doc_ids = as_set(case.get("expected_doc_ids"))
    missing_doc_ids = sorted(expected_doc_ids - set(source_ids))
    if missing_doc_ids:
        failures.append(f"missing source doc_ids: {missing_doc_ids}")

    expected_source_types = as_set(case.get("expected_source_types"))
    missing_source_types = sorted(expected_source_types - set(source_types))
    if missing_source_types:
        failures.append(f"missing source types: {missing_source_types}")

    expected_top_source_types = as_set(case.get("expected_top_source_types"))
    expected_top_source_types |= as_set(case.get("expected_top_source_type"))
    if expected_top_source_types and top_source_type not in expected_top_source_types:
        failures.append(f"top source type expected {sorted(expected_top_source_types)}, got {top_source_type}")

    if expected_citations is False and answer_citations:
        failures.append(f"unexpected citations: {answer_citations}")
    if expected_citations is True and not answer_citations:
        failures.append("missing citations")
    if expected_sources is False and source_ids:
        failures.append(f"unexpected sources: {source_ids}")
    if expected_sources is True and not source_ids:
        failures.append("missing sources")

    min_confidence = str(case.get("min_confidence") or "")
    confidence = str(retrieval_quality.get("confidence") or "")
    if min_confidence and CONFIDENCE_ORDER.get(confidence, -99) < CONFIDENCE_ORDER.get(min_confidence, 99):
        failures.append(f"confidence expected >= {min_confidence}, got {confidence}")

    search_body: dict[str, Any] = {}
    search_ids: list[str] = []
    search_hit = None
    if not skip_search and expected_route != "conversational":
        _, search_body = request_json(
            "POST",
            f"{base_url}/search",
            api_key=api_key,
            payload={"query": query, "top_k": top_k},
            timeout=timeout,
        )
        search_results = list(search_body.get("results") or [])
        search_ids = [str(result.get("doc_id") or "") for result in search_results]
        if expected_doc_ids:
            search_hit = bool(expected_doc_ids & set(search_ids))
            if not search_hit:
                failures.append(f"search missed expected doc_ids: {sorted(expected_doc_ids)}")
    elif not skip_search:
        _, search_body = request_json(
            "POST",
            f"{base_url}/search",
            api_key=api_key,
            payload={"query": query, "top_k": top_k},
            timeout=timeout,
        )
        search_results = list(search_body.get("results") or [])
        search_ids = [str(result.get("doc_id") or "") for result in search_results]
        if search_ids:
            failures.append(f"conversational search returned results: {search_ids}")

    return {
        "id": case["id"],
        "category": case["category"],
        "query": query,
        "passed": not failures,
        "failures": failures,
        "latency_seconds": latency,
        "intent": intent,
        "confidence": confidence,
        "answer": answer,
        "citations": answer_citations,
        "source_ids": source_ids,
        "source_types": source_types,
        "top_source_type": top_source_type,
        "search_ids": search_ids,
        "search_hit": search_hit,
        "citation_check": citation_check,
    }


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "id",
                "category",
                "passed",
                "latency_seconds",
                "intent",
                "confidence",
                "failures",
                "citations",
                "source_ids",
                "search_ids",
                "query",
                "answer",
            ],
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "id": row["id"],
                    "category": row["category"],
                    "passed": row["passed"],
                    "latency_seconds": row["latency_seconds"],
                    "intent": row["intent"],
                    "confidence": row["confidence"],
                    "failures": "; ".join(row["failures"]),
                    "citations": "|".join(row["citations"]),
                    "source_ids": "|".join(row["source_ids"]),
                    "search_ids": "|".join(row["search_ids"]),
                    "query": row["query"],
                    "answer": row["answer"],
                }
            )


def main() -> int:
    args = parse_args()
    if not args.api_key:
        print("Set CELL_RAG_DEMO_API_KEY or pass --api-key.", file=sys.stderr)
        return 2

    base_url = resolve_base_url(args.base_url)
    cases = load_cases(ROOT / args.cases)
    if args.category:
        allowed = set(args.category)
        cases = [case for case in cases if case.get("category") in allowed]
    if args.limit:
        cases = cases[: args.limit]

    rows: list[dict[str, Any]] = []
    try:
        for case in cases:
            row = score_case(
                case,
                base_url=base_url,
                api_key=args.api_key,
                timeout=args.timeout,
                skip_search=args.skip_search,
            )
            rows.append(row)
            if not args.json:
                status = "PASS" if row["passed"] else "FAIL"
                print(f"{status} | {row['id']} | intent={row['intent']} | sources={row['source_ids'][:3]}")
                if row["failures"]:
                    print(f"  failures: {'; '.join(row['failures'])}")
    except (urllib.error.URLError, TimeoutError, RuntimeError) as exc:
        print(json.dumps({"errors": [str(exc)], "recovery_hint": RECOVERY_HINT}, indent=2))
        return 1

    by_category: dict[str, dict[str, int]] = defaultdict(lambda: {"cases": 0, "passed": 0})
    for row in rows:
        by_category[row["category"]]["cases"] += 1
        by_category[row["category"]]["passed"] += int(bool(row["passed"]))

    summary = {
        "base_url": base_url,
        "started_utc": datetime.now(timezone.utc).isoformat(),
        "cases": len(rows),
        "passed": sum(int(row["passed"]) for row in rows),
        "failed": sum(int(not row["passed"]) for row in rows),
        "pass_rate": round(sum(int(row["passed"]) for row in rows) / (len(rows) or 1), 4),
        "by_category": by_category,
    }
    result = {"summary": summary, "cases": rows}

    if args.output:
        output_path = Path(args.output)
        if not output_path.is_absolute():
            output_path = ROOT / output_path
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.csv_output:
        csv_path = Path(args.csv_output)
        if not csv_path.is_absolute():
            csv_path = ROOT / csv_path
        write_csv(csv_path, rows)

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if summary["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
