#!/usr/bin/env python3
"""Run curated RAG demo questions and save cited answers."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests


CITATION_RE = re.compile(r"\[([^\[\]\n]+)\]")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run curated demo queries against the RAG answer API.")
    parser.add_argument("--cases", default="demo/showcase_queries.jsonl")
    parser.add_argument("--answer-url", default="http://127.0.0.1:8010/answer")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--temperature", type=float, default=0.1)
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


def extract_citations(answer: str) -> list[str]:
    seen: set[str] = set()
    citations: list[str] = []
    for match in CITATION_RE.finditer(answer):
        citation = match.group(1).strip()
        if citation and citation not in seen:
            seen.add(citation)
            citations.append(citation)
    return citations


def run_case(case: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    payload = {
        "query": case["question"],
        "top_k": int(case.get("top_k", 5)),
        "max_tokens": int(case.get("max_tokens", 240)),
        "temperature": float(case.get("temperature", args.temperature)),
    }
    response = requests.post(args.answer_url, json=payload, timeout=args.timeout)
    try:
        body = response.json()
    except ValueError:
        body = {"answer": response.text}

    answer = str(body.get("answer") or "")
    answer_lower = answer.casefold()
    sources = list(body.get("sources", []))
    source_ids = [str(item.get("doc_id")) for item in sources]
    source_types = [str(item.get("source_type") or "") for item in sources]
    top_source_type = source_types[0] if source_types else ""
    citations = extract_citations(answer)
    retrieval_quality = body.get("retrieval_quality", {})

    should_abstain = bool(case.get("should_abstain", False))
    did_abstain = "insufficient" in answer_lower or retrieval_quality.get("should_answer") is False
    expected_source_types = normalized_set(case.get("expected_source_types"))
    expected_top_source_type = str(case.get("expected_top_source_type") or "")
    must_cite = normalized_set(case.get("must_cite"))
    must_contain = [str(value) for value in case.get("must_contain", [])]

    failures: list[str] = []
    if response.status_code != 200:
        failures.append(f"HTTP status {response.status_code}")
    if not answer:
        failures.append("missing answer")
    if "<think>" in answer_lower:
        failures.append("answer contains <think>")
    if should_abstain != did_abstain:
        failures.append(f"abstention mismatch: expected={should_abstain} actual={did_abstain}")
    if not should_abstain:
        if not sources:
            failures.append("missing sources")
        if not citations:
            failures.append("missing citations")
        outside_sources = sorted(set(citations) - set(source_ids))
        if outside_sources:
            failures.append(f"citations outside retrieved sources: {outside_sources}")
    if expected_top_source_type and top_source_type != expected_top_source_type:
        failures.append(f"top source type {top_source_type!r} != {expected_top_source_type!r}")
    missing_source_types = sorted(expected_source_types - set(source_types))
    if missing_source_types:
        failures.append(f"missing expected source types: {missing_source_types}")
    missing_citations = sorted(must_cite - set(citations))
    if missing_citations:
        failures.append(f"missing required citations: {missing_citations}")
    missing_text = [text for text in must_contain if text.casefold() not in answer_lower]
    if missing_text:
        failures.append(f"missing required answer text: {missing_text}")

    return {
        "id": case.get("id"),
        "category": case.get("category"),
        "question": case["question"],
        "passed": not failures,
        "failures": failures,
        "answer": answer,
        "citations": citations,
        "source_ids": source_ids,
        "source_types": source_types,
        "top_source_type": top_source_type,
        "retrieval_quality": retrieval_quality,
        "sources": sources,
    }


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def write_markdown(path: Path, rows: list[dict[str, Any]]) -> None:
    lines = [
        "# Cell RAG Demo Answers",
        "",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        "",
        "## Summary",
        "",
        "| Category | Cases | Passed |",
        "|---|---:|---:|",
    ]
    by_category: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_category.setdefault(str(row["category"]), []).append(row)
    for category in sorted(by_category):
        category_rows = by_category[category]
        lines.append(f"| `{category}` | {len(category_rows)} | {sum(row['passed'] for row in category_rows)} |")
    lines.extend(["", "## Answers", ""])
    for row in rows:
        status = "PASS" if row["passed"] else "FAIL"
        lines.extend(
            [
                f"### {row['id']} - {status}",
                "",
                f"Category: `{row['category']}`",
                "",
                f"Question: {row['question']}",
                "",
                "Answer:",
                "",
                row["answer"],
                "",
                f"Retrieval confidence: `{row.get('retrieval_quality', {}).get('confidence', '')}`",
                "",
                f"Top source type: `{row['top_source_type']}`",
                "",
                "Sources:",
            ]
        )
        for source in row["sources"]:
            lines.append(
                f"- `{source.get('doc_id')}` | `{source.get('source_type')}` | {source.get('title')}"
            )
        if row["failures"]:
            lines.extend(["", "Failures:"])
            lines.extend(f"- {failure}" for failure in row["failures"])
        lines.append("")
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def write_summary(path: Path, rows: list[dict[str, Any]], cases_path: Path) -> None:
    category_counts = Counter(str(row["category"]) for row in rows)
    source_type_counts = Counter(
        source_type for row in rows for source_type in row["source_types"] if source_type
    )
    failed = [row for row in rows if not row["passed"]]
    lines = [
        "Cell RAG demo pack summary",
        f"generated_utc: {datetime.now(timezone.utc).isoformat()}",
        f"cases_file: {cases_path}",
        f"cases: {len(rows)}",
        f"passed: {sum(row['passed'] for row in rows)}",
        f"failed: {len(failed)}",
        "",
        "categories:",
    ]
    lines.extend(f"  {category}: {count}" for category, count in sorted(category_counts.items()))
    lines.extend(["", "retrieved_source_types:"])
    lines.extend(f"  {source_type}: {count}" for source_type, count in sorted(source_type_counts.items()))
    if failed:
        lines.extend(["", "failed_cases:"])
        for row in failed:
            lines.append(f"  {row['id']}: {'; '.join(row['failures'])}")
    else:
        lines.extend(["", "all demo cases passed."])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    cases_path = Path(args.cases)
    rows = [run_case(case, args) for case in load_cases(cases_path)]

    write_jsonl(output_dir / "answers.jsonl", rows)
    write_markdown(output_dir / "answers.md", rows)
    write_summary(output_dir / "summary.txt", rows, cases_path)

    failed = [row for row in rows if not row["passed"]]
    print(json.dumps({
        "output_dir": str(output_dir),
        "cases": len(rows),
        "passed": len(rows) - len(failed),
        "failed": [{"id": row["id"], "failures": row["failures"]} for row in failed],
    }, ensure_ascii=False, indent=2))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
