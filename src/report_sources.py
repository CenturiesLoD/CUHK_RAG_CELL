#!/usr/bin/env python3
"""Report source registry, file counts, field coverage, and combined index state."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np


DEFAULT_FIELDS = [
    "ontology_id",
    "name",
    "definition",
    "synonyms",
    "alt_ids",
    "parents",
    "relationships",
    "xrefs",
    "namespace",
    "comments",
    "data_version",
    "source_id",
    "source_type",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Summarize RAG source registry and generated files.")
    parser.add_argument("--registry", default="sources/source_registry.json")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser.parse_args()


def load_jsonl(path: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rows: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    if not path.exists():
        return rows, [{"line": 0, "error": "file missing"}]
    with path.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except Exception as exc:
                errors.append({"line": line_no, "error": f"{type(exc).__name__}: {exc}"})
    return rows, errors


def file_info(root: Path, rel_path: str | None) -> dict[str, Any]:
    if not rel_path:
        return {"path": None, "exists": False}
    path = root / rel_path
    info: dict[str, Any] = {"path": rel_path, "exists": path.exists()}
    if path.exists():
        info["bytes"] = path.stat().st_size
    return info


def first_data_version(rows: list[dict[str, Any]]) -> str:
    for row in rows:
        value = row.get("data_version")
        if value:
            return str(value)
        value = row.get("census_version")
        if value:
            return str(value)
        metadata = row.get("metadata")
        if isinstance(metadata, dict) and metadata.get("data_version"):
            return str(metadata["data_version"])
        if isinstance(metadata, dict) and metadata.get("census_version"):
            return str(metadata["census_version"])
    return ""


def field_coverage(rows: list[dict[str, Any]], fields: list[str] = DEFAULT_FIELDS) -> dict[str, dict[str, Any]]:
    total = len(rows)
    coverage: dict[str, dict[str, Any]] = {}
    for field in fields:
        count = sum(1 for row in rows if row.get(field))
        coverage[field] = {
            "count": count,
            "total": total,
            "fraction": round(count / total, 4) if total else 0.0,
        }
    return coverage


def summarize_source(root: Path, source: dict[str, Any]) -> dict[str, Any]:
    terms, term_errors = load_jsonl(root / source["terms_path"])
    aliases, alias_errors = load_jsonl(root / source["aliases_path"])
    chunks, chunk_errors = load_jsonl(root / source["chunks_path"])
    summary = {
        "source_id": source["source_id"],
        "display_name": source["display_name"],
        "short_name": source.get("short_name", ""),
        "source_type": source["source_type"],
        "homepage": source.get("homepage", ""),
        "download_url": source.get("download_url", ""),
        "license": source.get("license", ""),
        "stage": source.get("stage", "active"),
        "purpose": source.get("purpose", ""),
        "data_version": first_data_version(terms) or first_data_version(chunks),
        "files": {
            "raw": file_info(root, source.get("raw_path")),
            "terms": file_info(root, source.get("terms_path")),
            "aliases": file_info(root, source.get("aliases_path")),
            "chunks": file_info(root, source.get("chunks_path")),
            "embedding": file_info(root, source.get("embedding_path")),
            "embedding_metadata": file_info(root, source.get("embedding_metadata_path")),
        },
        "counts": {
            "terms": len(terms),
            "aliases": len(aliases),
            "chunks": len(chunks),
        },
        "jsonl_errors": {
            "terms": term_errors,
            "aliases": alias_errors,
            "chunks": chunk_errors,
        },
        "field_coverage": field_coverage(terms, source.get("coverage_fields", DEFAULT_FIELDS)),
    }
    return summary


def summarize_combined(root: Path, combined: dict[str, Any]) -> dict[str, Any]:
    chunks, chunk_errors = load_jsonl(root / combined["chunks_path"])
    aliases, alias_errors = load_jsonl(root / combined["aliases_path"])
    embedding_path = root / combined["embedding_path"]
    embedding_shape = None
    if embedding_path.exists():
        embedding_shape = list(np.load(embedding_path)["embeddings"].shape)
    return {
        "chunks_path": combined["chunks_path"],
        "aliases_path": combined["aliases_path"],
        "embedding_path": combined["embedding_path"],
        "embedding_model": combined.get("embedding_model", ""),
        "counts": {
            "chunks": len(chunks),
            "aliases": len(aliases),
        },
        "embedding_shape": embedding_shape,
        "jsonl_errors": {
            "chunks": chunk_errors,
            "aliases": alias_errors,
        },
    }


def print_text(report: dict[str, Any]) -> None:
    print(f"Source registry: {report['registry_path']}")
    print()
    for source in report["sources"]:
        counts = source["counts"]
        print(f"== {source['display_name']} ({source['source_id']}) ==")
        print(f"type: {source['source_type']}")
        print(f"license: {source['license']}")
        print(f"stage: {source['stage']}")
        print(f"version: {source['data_version'] or 'unknown'}")
        print(f"homepage: {source['homepage']}")
        print(f"download: {source['download_url']}")
        print(f"purpose: {source['purpose']}")
        print(f"counts: terms={counts['terms']} aliases={counts['aliases']} chunks={counts['chunks']}")
        errors = sum(len(value) for value in source["jsonl_errors"].values())
        print(f"jsonl_errors: {errors}")
        print("field coverage:")
        for field, stats in source["field_coverage"].items():
            if stats["count"]:
                print(f"  {field}: {stats['count']}/{stats['total']} ({stats['fraction']:.3f})")
        print()
    combined = report["combined_index"]
    print("== Combined RAG Index ==")
    print(f"chunks: {combined['counts']['chunks']} -> {combined['chunks_path']}")
    print(f"aliases: {combined['counts']['aliases']} -> {combined['aliases_path']}")
    print(f"embedding: {combined['embedding_shape']} -> {combined['embedding_path']}")
    print(f"embedding_model: {combined['embedding_model']}")
    errors = sum(len(value) for value in combined["jsonl_errors"].values())
    print(f"jsonl_errors: {errors}")


def main() -> int:
    args = parse_args()
    registry_path = Path(args.registry)
    root = registry_path.resolve().parents[1]
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    report = {
        "registry_path": str(registry_path),
        "schema_version": registry.get("schema_version"),
        "project": registry.get("project"),
        "sources": [summarize_source(root, source) for source in registry["sources"]],
        "combined_index": summarize_combined(root, registry["combined_index"]),
    }
    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print_text(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
