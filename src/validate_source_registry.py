#!/usr/bin/env python3
"""Validate source registry paths, generated JSONL, and combined embedding alignment."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np


SOURCE_REQUIRED_FIELDS = [
    "source_id",
    "display_name",
    "source_type",
    "homepage",
    "download_url",
    "terms_path",
    "aliases_path",
    "chunks_path",
    "license",
    "purpose",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate RAG source registry and generated artifacts.")
    parser.add_argument("--registry", default="sources/source_registry.json")
    parser.add_argument("--json", action="store_true", help="Print machine-readable report.")
    return parser.parse_args()


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_jsonl(path: Path) -> tuple[int, list[str], dict[str, Any] | None]:
    errors: list[str] = []
    count = 0
    first_row: dict[str, Any] | None = None
    with path.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except Exception as exc:
                errors.append(f"{path}:{line_no}: {type(exc).__name__}: {exc}")
                continue
            if not isinstance(row, dict):
                errors.append(f"{path}:{line_no}: row is not a JSON object")
                continue
            if first_row is None:
                first_row = row
            count += 1
    return count, errors, first_row


def require_file(root: Path, rel_path: str | None, errors: list[str], *, required: bool = True) -> Path | None:
    if not rel_path:
        if required:
            errors.append("missing required path value")
        return None
    path = root / rel_path
    if required and not path.exists():
        errors.append(f"missing file: {rel_path}")
    return path


def validate_source(root: Path, source: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    source_id = str(source.get("source_id") or "<missing>")

    for field in SOURCE_REQUIRED_FIELDS:
        if not source.get(field):
            errors.append(f"{source_id}: missing required registry field: {field}")

    raw_path = require_file(root, source.get("raw_path"), errors, required=bool(source.get("raw_path")))
    terms_path = require_file(root, source.get("terms_path"), errors)
    aliases_path = require_file(root, source.get("aliases_path"), errors)
    chunks_path = require_file(root, source.get("chunks_path"), errors)
    report_path = require_file(root, source.get("report_path"), warnings, required=False)

    terms_count = aliases_count = chunks_count = 0
    first_chunk: dict[str, Any] | None = None

    if terms_path and terms_path.exists():
        terms_count, jsonl_errors, _ = load_jsonl(terms_path)
        errors.extend(f"{source_id}: {error}" for error in jsonl_errors)
        if terms_count == 0:
            errors.append(f"{source_id}: terms file has no rows: {source.get('terms_path')}")

    if aliases_path and aliases_path.exists():
        aliases_count, jsonl_errors, _ = load_jsonl(aliases_path)
        errors.extend(f"{source_id}: {error}" for error in jsonl_errors)
        if aliases_count == 0:
            warnings.append(f"{source_id}: aliases file has no rows: {source.get('aliases_path')}")

    if chunks_path and chunks_path.exists():
        chunks_count, jsonl_errors, first_chunk = load_jsonl(chunks_path)
        errors.extend(f"{source_id}: {error}" for error in jsonl_errors)
        if chunks_count == 0:
            errors.append(f"{source_id}: chunks file has no rows: {source.get('chunks_path')}")

    if first_chunk:
        for key in ("doc_id", "title", "text", "metadata"):
            if key not in first_chunk:
                errors.append(f"{source_id}: first chunk missing key: {key}")
        metadata = first_chunk.get("metadata", {})
        if isinstance(metadata, dict):
            chunk_source_id = metadata.get("source_id")
            chunk_source_type = metadata.get("source_type")
            if chunk_source_id and chunk_source_id != source_id:
                warnings.append(f"{source_id}: first chunk metadata source_id is {chunk_source_id!r}")
            if chunk_source_type and chunk_source_type != source.get("source_type"):
                warnings.append(f"{source_id}: first chunk metadata source_type is {chunk_source_type!r}")
        else:
            errors.append(f"{source_id}: first chunk metadata is not an object")

    if report_path and not report_path.exists():
        warnings.append(f"{source_id}: report file not found: {source.get('report_path')}")
    if raw_path and not raw_path.exists():
        errors.append(f"{source_id}: raw file not found: {source.get('raw_path')}")

    return {
        "source_id": source_id,
        "display_name": source.get("display_name"),
        "source_type": source.get("source_type"),
        "counts": {
            "terms": terms_count,
            "aliases": aliases_count,
            "chunks": chunks_count,
        },
        "errors": errors,
        "warnings": warnings,
    }


def validate_combined(root: Path, combined: dict[str, Any], source_reports: list[dict[str, Any]]) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    chunks_path = require_file(root, combined.get("chunks_path"), errors)
    aliases_path = require_file(root, combined.get("aliases_path"), errors)
    embedding_path = require_file(root, combined.get("embedding_path"), errors)
    metadata_path = require_file(root, combined.get("embedding_metadata_path"), errors)

    chunks_count = aliases_count = metadata_count = 0
    embedding_shape = None

    if chunks_path and chunks_path.exists():
        chunks_count, jsonl_errors, _ = load_jsonl(chunks_path)
        errors.extend(f"combined chunks: {error}" for error in jsonl_errors)

    if aliases_path and aliases_path.exists():
        aliases_count, jsonl_errors, _ = load_jsonl(aliases_path)
        errors.extend(f"combined aliases: {error}" for error in jsonl_errors)

    if metadata_path and metadata_path.exists():
        metadata = load_json(metadata_path)
        if isinstance(metadata, list):
            metadata_count = len(metadata)
        else:
            errors.append("combined metadata file is not a JSON list")

    if embedding_path and embedding_path.exists():
        try:
            with np.load(embedding_path) as data:
                matrix = data["embeddings"]
                embedding_shape = list(matrix.shape)
        except Exception as exc:
            errors.append(f"combined embedding failed to load: {type(exc).__name__}: {exc}")

    source_chunks = sum(report["counts"]["chunks"] for report in source_reports)
    source_aliases = sum(report["counts"]["aliases"] for report in source_reports)
    if chunks_count != source_chunks:
        errors.append(f"combined chunks count {chunks_count} != source chunk sum {source_chunks}")
    if aliases_count != source_aliases:
        errors.append(f"combined aliases count {aliases_count} != source alias sum {source_aliases}")
    if embedding_shape and embedding_shape[0] != chunks_count:
        errors.append(f"embedding rows {embedding_shape[0]} != combined chunks {chunks_count}")
    if metadata_count and metadata_count != chunks_count:
        errors.append(f"metadata rows {metadata_count} != combined chunks {chunks_count}")
    if embedding_shape and embedding_shape[1] != 4096:
        warnings.append(f"embedding dimension is {embedding_shape[1]}, expected 4096 for Qwen3-Embedding-8B")

    return {
        "counts": {
            "chunks": chunks_count,
            "aliases": aliases_count,
            "metadata": metadata_count,
        },
        "embedding_shape": embedding_shape,
        "errors": errors,
        "warnings": warnings,
    }


def main() -> int:
    args = parse_args()
    registry_path = Path(args.registry)
    root = registry_path.resolve().parents[1]
    registry = load_json(registry_path)

    errors: list[str] = []
    warnings: list[str] = []
    if registry.get("schema_version") != 1:
        warnings.append(f"schema_version is {registry.get('schema_version')!r}, expected 1")
    if not isinstance(registry.get("sources"), list):
        errors.append("registry.sources must be a list")
        source_reports: list[dict[str, Any]] = []
    else:
        source_reports = [validate_source(root, source) for source in registry["sources"]]

    source_ids = [report["source_id"] for report in source_reports]
    duplicates = sorted({source_id for source_id in source_ids if source_ids.count(source_id) > 1})
    for source_id in duplicates:
        errors.append(f"duplicate source_id: {source_id}")

    combined_report = validate_combined(root, registry.get("combined_index", {}), source_reports)

    for report in source_reports:
        errors.extend(report["errors"])
        warnings.extend(report["warnings"])
    errors.extend(combined_report["errors"])
    warnings.extend(combined_report["warnings"])

    report = {
        "registry": str(registry_path),
        "sources": len(source_reports),
        "combined_index": combined_report,
        "errors": errors,
        "warnings": warnings,
        "source_counts": {
            item["source_id"]: item["counts"] for item in source_reports
        },
    }

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        status = "PASS" if not errors else "FAIL"
        print(f"{status}: source registry validation")
        print(f"sources={len(source_reports)}")
        print(f"combined_chunks={combined_report['counts']['chunks']}")
        print(f"combined_aliases={combined_report['counts']['aliases']}")
        print(f"embedding_shape={combined_report['embedding_shape']}")
        if warnings:
            print("warnings:")
            for warning in warnings:
                print(f"  - {warning}")
        if errors:
            print("errors:")
            for error in errors:
                print(f"  - {error}")

    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
