#!/usr/bin/env python3
"""Evaluate the live RAG search endpoint against JSONL retrieval cases."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import requests


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate retrieval against expected doc IDs.")
    parser.add_argument("--cases", default="eval/queries.jsonl")
    parser.add_argument("--search-url", default="http://127.0.0.1:8010/search")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--use-neural-reranker", choices=["auto", "true", "false"], default="auto")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def load_cases(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def reciprocal_rank(results: list[dict[str, Any]], expected: set[str]) -> float:
    for index, result in enumerate(results, start=1):
        if str(result.get("doc_id")) in expected:
            return 1.0 / index
    return 0.0


def text_contains(result: dict[str, Any] | None, needles: list[str]) -> list[str]:
    if result is None:
        return list(needles)
    haystack = "\n".join(
        str(result.get(key, "")) for key in ("doc_id", "title", "source_id", "data_version", "text")
    ).casefold()
    return [needle for needle in needles if str(needle).casefold() not in haystack]


def normalized_set(values: Any) -> set[str]:
    if not values:
        return set()
    if isinstance(values, str):
        return {values}
    return {str(value) for value in values}


CONFIDENCE_ORDER = {"low": 0, "medium": 1, "high": 2}


def main() -> int:
    args = parse_args()
    cases = load_cases(Path(args.cases))
    rows: list[dict[str, Any]] = []

    for case in cases:
        expected = {str(value) for value in case.get("expected_doc_ids", [])}
        payload = {"query": case["query"], "top_k": int(case.get("top_k", args.top_k))}
        if args.use_neural_reranker != "auto":
            payload["use_neural_reranker"] = args.use_neural_reranker == "true"
        response = requests.post(args.search_url, json=payload, timeout=args.timeout)
        response.raise_for_status()
        data = response.json()
        results = list(data.get("results", []))
        found = [str(item.get("doc_id")) for item in results]
        found_source_types = [str(item.get("source_type") or "") for item in results]
        found_source_intents = [str(item.get("source_intent") or "") for item in results]
        require_hit_at_1 = bool(case.get("require_hit_at_1", False))
        top_result = results[0] if results else None
        top_doc_id = str(top_result.get("doc_id") or "") if top_result else ""
        top_source_type = str(top_result.get("source_type") or "") if top_result else ""
        top_source_intent = str(top_result.get("source_intent") or "") if top_result else ""
        top_must_contain = [str(value) for value in case.get("top_must_contain", [])]
        any_result_must_contain = [str(value) for value in case.get("any_result_must_contain", [])]
        missing_top_text = text_contains(top_result, top_must_contain)
        missing_any_text = [
            needle
            for needle in any_result_must_contain
            if all(text_contains(result, [needle]) for result in results)
        ]
        expected_top_source_types = normalized_set(case.get("expected_top_source_types"))
        expected_top_source_types |= normalized_set(case.get("expected_top_source_type"))
        expected_source_intents = normalized_set(case.get("expected_source_intents"))
        expected_source_intents |= normalized_set(case.get("expected_source_intent"))
        forbidden_top_doc_ids = normalized_set(case.get("forbidden_top_doc_ids"))
        forbidden_any_doc_ids = normalized_set(case.get("forbidden_any_doc_ids"))
        forbidden_top_source_types = normalized_set(case.get("forbidden_top_source_types"))
        forbidden_any_source_types = normalized_set(case.get("forbidden_any_source_types"))

        top_source_type_failed = bool(expected_top_source_types and top_source_type not in expected_top_source_types)
        source_intent_failed = bool(expected_source_intents and top_source_intent not in expected_source_intents)
        forbidden_top_doc_id = top_doc_id if top_doc_id in forbidden_top_doc_ids else ""
        forbidden_any_doc_ids_found = sorted(set(found) & forbidden_any_doc_ids)
        forbidden_top_source_type = top_source_type if top_source_type in forbidden_top_source_types else ""
        forbidden_any_source_types_found = sorted(set(found_source_types) & forbidden_any_source_types)
        min_confidence = str(case.get("min_confidence") or "")
        confidence = str(data.get("retrieval_quality", {}).get("confidence") or "")
        confidence_failed = bool(
            min_confidence
            and CONFIDENCE_ORDER.get(confidence, -1) < CONFIDENCE_ORDER.get(min_confidence, 999)
        )
        hit_at_1 = bool(found and found[0] in expected)
        hit_at_k = bool(expected & set(found))
        passed = (
            hit_at_k
            and (hit_at_1 or not require_hit_at_1)
            and not missing_top_text
            and not missing_any_text
            and not top_source_type_failed
            and not source_intent_failed
            and not forbidden_top_doc_id
            and not forbidden_any_doc_ids_found
            and not forbidden_top_source_type
            and not forbidden_any_source_types_found
            and not confidence_failed
        )
        rows.append(
            {
                "query": case["query"],
                "expected_doc_ids": sorted(expected),
                "found_doc_ids": found,
                "found_source_types": found_source_types,
                "found_source_intents": found_source_intents,
                "hit_at_1": hit_at_1,
                "hit_at_k": hit_at_k,
                "require_hit_at_1": require_hit_at_1,
                "top_source_type": top_source_type,
                "expected_top_source_types": sorted(expected_top_source_types),
                "top_source_type_failed": top_source_type_failed,
                "top_source_intent": top_source_intent,
                "expected_source_intents": sorted(expected_source_intents),
                "source_intent_failed": source_intent_failed,
                "forbidden_top_doc_id": forbidden_top_doc_id,
                "forbidden_any_doc_ids_found": forbidden_any_doc_ids_found,
                "forbidden_top_source_type": forbidden_top_source_type,
                "forbidden_any_source_types_found": forbidden_any_source_types_found,
                "min_confidence": min_confidence,
                "confidence_failed": confidence_failed,
                "missing_top_text": missing_top_text,
                "missing_any_text": missing_any_text,
                "passed": passed,
                "mrr": reciprocal_rank(results, expected),
                "retrieval_quality": data.get("retrieval_quality", {}),
            }
        )

    total = len(rows) or 1
    summary = {
        "cases": len(rows),
        "hit_at_1": round(sum(row["hit_at_1"] for row in rows) / total, 4),
        "hit_at_k": round(sum(row["hit_at_k"] for row in rows) / total, 4),
        "mrr": round(sum(row["mrr"] for row in rows) / total, 4),
        "failures": [row for row in rows if not row["passed"]],
        "low_confidence": [row for row in rows if row.get("retrieval_quality", {}).get("confidence") == "low"],
    }

    if args.json:
        print(json.dumps({"summary": summary, "cases": rows}, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        for row in rows:
            status = "PASS" if row["passed"] else "FAIL"
            print(
                f"{status} | {row['query']} | expected={row['expected_doc_ids']} | "
                f"found={row['found_doc_ids'][:5]} | top_source_type={row['top_source_type']}"
            )

    return 1 if summary["failures"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
