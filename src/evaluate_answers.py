#!/usr/bin/env python3
"""Smoke-level answer generation evaluation for the local RAG API."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

import requests


CITATION_RE = re.compile(r"\[([^\[\]\n]+)\]")
SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate generated RAG answers.")
    parser.add_argument("--cases", default="eval/answer_cases.jsonl")
    parser.add_argument("--answer-url", default="http://127.0.0.1:8010/answer")
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--max-tokens", type=int, default=220)
    parser.add_argument("--use-neural-reranker", choices=["auto", "true", "false"], default="auto")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def load_cases(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def normalized_set(values: Any) -> set[str]:
    if not values:
        return set()
    if isinstance(values, str):
        return {values}
    return {str(value) for value in values}


CONFIDENCE_ORDER = {"low": 0, "medium": 1, "high": 2}


def extract_citations(answer: str) -> list[str]:
    seen: set[str] = set()
    citations: list[str] = []
    for match in CITATION_RE.finditer(answer):
        citation = match.group(1).strip()
        if citation and citation not in seen:
            seen.add(citation)
            citations.append(citation)
    return citations


def claim_units(answer: str) -> list[str]:
    units: list[str] = []
    for raw_line in answer.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        line = re.sub(r"^[-*]\s+", "", line).strip()
        if not line or line.endswith(":"):
            continue
        for piece in SENTENCE_SPLIT_RE.split(line):
            piece = piece.strip()
            if len(piece) < 12:
                continue
            if "retrieved context is insufficient" in piece.casefold():
                continue
            units.append(piece)
    return units


def evaluate_case(case: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    payload = {
        "query": case["query"],
        "top_k": int(case.get("top_k", 3)),
        "max_tokens": int(case.get("max_tokens", args.max_tokens)),
        "temperature": float(case.get("temperature", 0.1)),
    }
    if args.use_neural_reranker != "auto":
        payload["use_neural_reranker"] = args.use_neural_reranker == "true"
    response = requests.post(args.answer_url, json=payload, timeout=args.timeout)
    body = response.json()
    answer = str(body.get("answer") or "")
    answer_lower = answer.casefold()
    sources = list(body.get("sources", []))
    source_ids = [str(item.get("doc_id")) for item in sources]
    source_types = [str(item.get("source_type") or "") for item in sources]
    top_source_type = source_types[0] if source_types else ""
    quality = body.get("retrieval_quality", {})
    api_citation_check = body.get("citation_check")
    api_citation_check_missing = "citation_check" not in body
    api_citation_check_failed = api_citation_check_missing or bool(
        isinstance(api_citation_check, dict) and api_citation_check.get("passed") is False
    )
    citations = extract_citations(answer)

    missing_expected_sources = [
        doc_id for doc_id in case.get("expected_doc_ids", []) if doc_id not in source_ids
    ]
    missing_text = [
        text for text in case.get("must_contain", []) if str(text).casefold() not in answer_lower
    ]
    forbidden_text = [
        text for text in case.get("must_not_contain", []) if str(text).casefold() in answer_lower
    ]
    expected_abstain = bool(case.get("should_abstain", False))
    did_abstain = "insufficient" in answer_lower or quality.get("should_answer") is False
    expected_source_types = normalized_set(case.get("expected_source_types"))
    expected_top_source_types = normalized_set(case.get("expected_top_source_types"))
    expected_top_source_types |= normalized_set(case.get("expected_top_source_type"))
    forbidden_source_ids = normalized_set(case.get("forbidden_source_ids"))
    forbidden_source_types = normalized_set(case.get("forbidden_source_types"))
    forbidden_top_source_types = normalized_set(case.get("forbidden_top_source_types"))
    missing_expected_source_types = sorted(expected_source_types - set(source_types))
    top_source_type_failed = bool(expected_top_source_types and top_source_type not in expected_top_source_types)
    forbidden_source_ids_found = sorted(set(source_ids) & forbidden_source_ids)
    forbidden_source_types_found = sorted(set(source_types) & forbidden_source_types)
    forbidden_top_source_type = top_source_type if top_source_type in forbidden_top_source_types else ""
    min_confidence = str(case.get("min_confidence") or "")
    confidence = str(quality.get("confidence") or "")
    confidence_failed = bool(
        min_confidence
        and CONFIDENCE_ORDER.get(confidence, -1) < CONFIDENCE_ORDER.get(min_confidence, 999)
    )
    require_citations = bool(case.get("require_citations", not expected_abstain))
    require_claim_citations = bool(case.get("require_claim_citations", not expected_abstain))
    allow_unretrieved_citations = bool(case.get("allow_unretrieved_citations", False))
    required_citations = normalized_set(case.get("must_cite"))
    if not required_citations and require_citations and not expected_abstain:
        required_citations = normalized_set(case.get("expected_doc_ids"))
    forbidden_citations = normalized_set(case.get("must_not_cite"))
    missing_required_citations = sorted(required_citations - set(citations))
    forbidden_citations_found = sorted(set(citations) & forbidden_citations)
    citations_outside_sources = sorted(set(citations) - set(source_ids))
    citationless_claims = [
        unit for unit in claim_units(answer) if not CITATION_RE.search(unit)
    ] if require_claim_citations else []
    citation_check_failed = bool(
        (require_citations and not citations)
        or missing_required_citations
        or forbidden_citations_found
        or (citations_outside_sources and not allow_unretrieved_citations)
        or citationless_claims
    )

    passed = (
        response.status_code == 200
        and not missing_expected_sources
        and not missing_expected_source_types
        and not missing_text
        and not forbidden_text
        and did_abstain == expected_abstain
        and not top_source_type_failed
        and not forbidden_source_ids_found
        and not forbidden_source_types_found
        and not forbidden_top_source_type
        and not confidence_failed
        and not citation_check_failed
        and not api_citation_check_failed
    )

    return {
        "name": case.get("name", case["query"]),
        "query": case["query"],
        "passed": passed,
        "status_code": response.status_code,
        "answer": answer,
        "source_ids": source_ids,
        "source_types": source_types,
        "top_source_type": top_source_type,
        "citations": citations,
        "api_citation_check": api_citation_check,
        "api_citation_check_missing": api_citation_check_missing,
        "api_citation_check_failed": api_citation_check_failed,
        "retrieval_quality": quality,
        "missing_expected_sources": missing_expected_sources,
        "missing_expected_source_types": missing_expected_source_types,
        "missing_text": missing_text,
        "forbidden_text": forbidden_text,
        "forbidden_source_ids_found": forbidden_source_ids_found,
        "forbidden_source_types_found": forbidden_source_types_found,
        "forbidden_top_source_type": forbidden_top_source_type,
        "expected_top_source_types": sorted(expected_top_source_types),
        "top_source_type_failed": top_source_type_failed,
        "min_confidence": min_confidence,
        "confidence_failed": confidence_failed,
        "require_citations": require_citations,
        "require_claim_citations": require_claim_citations,
        "missing_required_citations": missing_required_citations,
        "forbidden_citations_found": forbidden_citations_found,
        "citations_outside_sources": citations_outside_sources,
        "citationless_claims": citationless_claims,
        "expected_abstain": expected_abstain,
        "did_abstain": did_abstain,
    }


def main() -> int:
    args = parse_args()
    rows = [evaluate_case(case, args) for case in load_cases(Path(args.cases))]
    summary = {
        "cases": len(rows),
        "passed": sum(row["passed"] for row in rows),
        "failed": [row for row in rows if not row["passed"]],
    }

    if args.json:
        print(json.dumps({"summary": summary, "cases": rows}, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        for row in rows:
            status = "PASS" if row["passed"] else "FAIL"
            print(
                f"{status} | {row['name']} | sources={row['source_ids']} | "
                f"top_source_type={row['top_source_type']} | citations={row['citations']} | "
                f"api_citation_check_failed={row['api_citation_check_failed']} | "
                f"answer={row['answer']}"
            )

    return 1 if summary["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
