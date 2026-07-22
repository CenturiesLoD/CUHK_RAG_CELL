#!/usr/bin/env python3
"""Build RAG-ready CELLxGENE Census metadata summaries.

This script reads CELLxGENE Census obs metadata, validates the available
columns, aggregates cell-level rows into compact evidence records, and writes
raw parquet, processed JSONL, alias JSONL, chunk JSONL, and a validation report.
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import cellxgene_census
import pandas as pd


DEFAULT_REQUIRED = [
    "cell_type",
    "cell_type_ontology_term_id",
    "dataset_id",
    "is_primary_data",
]
DEFAULT_OPTIONAL = [
    "tissue",
    "tissue_ontology_term_id",
    "tissue_general",
    "tissue_general_ontology_term_id",
    "disease",
    "assay",
    "suspension_type",
    "development_stage",
    "sex",
]
DEFAULT_GROUP = [
    "cell_type",
    "cell_type_ontology_term_id",
    "tissue",
    "tissue_ontology_term_id",
    "disease",
    "assay",
]
ID_TOKEN_RE = re.compile(r"[^A-Za-z0-9]+")
DEFAULT_CENSUS_VERSION = "2025-11-17"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build CELLxGENE Census RAG summaries.")
    parser.add_argument("--census-version", default=DEFAULT_CENSUS_VERSION)
    parser.add_argument("--organism", default="homo_sapiens", choices=("homo_sapiens", "mus_musculus"))
    parser.add_argument("--value-filter", default="is_primary_data == True")
    parser.add_argument("--source-id", default="cellxgene_census")
    parser.add_argument("--source-type", default="single_cell_atlas_metadata")
    parser.add_argument("--raw-out", default="raw/cellxgene_census_obs_summary.parquet")
    parser.add_argument("--processed-out", default="processed/cellxgene_census_celltype_tissue_counts.jsonl")
    parser.add_argument("--aliases-out", default="processed/cellxgene_census_aliases.jsonl")
    parser.add_argument("--chunks-out", default="chunks/cellxgene_census_chunks.jsonl")
    parser.add_argument("--report-out", default="processed/cellxgene_census_validation_report.json")
    parser.add_argument("--max-rows", type=int, default=0, help="Keep only first N obs rows after query; 0 means no limit.")
    parser.add_argument("--top-n-per-cell-type", type=int, default=0, help="Keep largest N groups per cell type; 0 means all.")
    return parser.parse_args()


def schema_names(schema: Any) -> list[str]:
    if hasattr(schema, "names"):
        return list(schema.names)
    return [field.name for field in schema]


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def safe_value(value: Any) -> str:
    if pd.isna(value):
        return "unknown"
    text = str(value).strip()
    return text if text else "unknown"


def normalize(text: str) -> str:
    return " ".join(text.casefold().strip().split())


def id_token(value: Any, fallback: str = "unknown") -> str:
    text = safe_value(value)
    if text == "unknown":
        text = fallback
    token = ID_TOKEN_RE.sub("_", text).strip("_").lower()
    return token or fallback


def alias_values(value: Any) -> list[str]:
    text = safe_value(value)
    if text == "unknown":
        return []
    values = [text]
    simplified = text.replace("'", "")
    if simplified != text:
        values.append(simplified)
    return values


def evidence_doc_id(row: dict[str, Any], source_id: str, index: int) -> str:
    cell_id = id_token(row.get("cell_type_ontology_term_id"))
    tissue_id = id_token(row.get("tissue_ontology_term_id"))
    disease = id_token(row.get("disease"))
    assay = id_token(row.get("assay"))
    return f"{source_id}:{cell_id}:{tissue_id}:{disease}:{assay}:{index}"


def make_processed_rows(summary: pd.DataFrame, args: argparse.Namespace, used_optional: list[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    optional_set = set(used_optional)
    for record in summary.to_dict(orient="records"):
        row = {
            "cell_type": safe_value(record.get("cell_type")),
            "cell_type_ontology_term_id": safe_value(record.get("cell_type_ontology_term_id")),
            "cell_count": int(record.get("cell_count") or 0),
            "dataset_count": int(record.get("dataset_count") or 0),
            "source_id": args.source_id,
            "source_type": args.source_type,
            "census_version": args.census_version,
            "organism": args.organism,
            "value_filter": args.value_filter,
            "generated_at": datetime.now(UTC).isoformat(),
        }
        for key in DEFAULT_OPTIONAL:
            if key in optional_set:
                row[key] = safe_value(record.get(key))
        rows.append(row)
    return rows


def make_alias_rows(rows: list[dict[str, Any]], source_id: str) -> list[dict[str, Any]]:
    aliases: dict[tuple[str, str, str], dict[str, Any]] = {}
    for index, row in enumerate(rows):
        target_id = evidence_doc_id(row, source_id, index)
        candidates: list[tuple[str, str]] = []
        for alias_type, value in [
            ("cell_type", row.get("cell_type")),
            ("cell_type_id", row.get("cell_type_ontology_term_id")),
            ("cell_type_id_compact", str(row.get("cell_type_ontology_term_id", "")).replace(":", "")),
            ("cell_type_id_underscore", str(row.get("cell_type_ontology_term_id", "")).replace(":", "_")),
        ]:
            for alias in alias_values(value):
                candidates.append((alias_type, alias))
        if row.get("tissue"):
            for alias in alias_values(row.get("tissue")):
                candidates.append(("tissue", alias))
        if row.get("tissue_ontology_term_id"):
            for alias in alias_values(row.get("tissue_ontology_term_id")):
                candidates.append(("tissue_id", alias))
        if row.get("disease"):
            for alias in alias_values(row.get("disease")):
                candidates.append(("disease", alias))
        if row.get("assay"):
            for alias in alias_values(row.get("assay")):
                candidates.append(("assay", alias))
        for alias_type, alias in candidates:
            key = (target_id, alias_type, normalize(alias))
            aliases[key] = {
                "target_id": target_id,
                "alias": alias,
                "alias_norm": normalize(alias),
                "alias_type": alias_type,
                "source_id": source_id,
            }
    return sorted(aliases.values(), key=lambda row: (row["target_id"], row["alias_type"], row["alias_norm"]))


def make_chunk_text(row: dict[str, Any]) -> str:
    lines = [
        f"CELLxGENE Census evidence for {row['cell_type']} [{row['cell_type_ontology_term_id']}].",
        f"Organism: {row['organism']}. Census version: {row['census_version']}.",
        f"Cell count: {row['cell_count']}. Dataset count: {row['dataset_count']}.",
    ]
    if row.get("tissue") and row.get("tissue") != "unknown":
        tissue_id = row.get("tissue_ontology_term_id")
        tissue_text = f"Tissue: {row['tissue']}"
        if tissue_id and tissue_id != "unknown":
            tissue_text += f" [{tissue_id}]"
        lines.append(tissue_text + ".")
    if row.get("tissue_general") and row.get("tissue_general") != "unknown":
        lines.append(f"General tissue: {row['tissue_general']}.")
    if row.get("disease") and row.get("disease") != "unknown":
        lines.append(f"Disease/condition label: {row['disease']}.")
    if row.get("assay") and row.get("assay") != "unknown":
        lines.append(f"Assay: {row['assay']}.")
    if row.get("suspension_type") and row.get("suspension_type") != "unknown":
        lines.append(f"Suspension type: {row['suspension_type']}.")
    if row.get("development_stage") and row.get("development_stage") != "unknown":
        lines.append(f"Development stage: {row['development_stage']}.")
    if row.get("sex") and row.get("sex") != "unknown":
        lines.append(f"Sex label: {row['sex']}.")
    return "\n".join(lines)


def make_chunk_rows(rows: list[dict[str, Any]], source_id: str) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        chunk_id = evidence_doc_id(row, source_id, index)
        chunks.append(
            {
                "chunk_id": chunk_id,
                "doc_id": chunk_id,
                "title": f"CELLxGENE Census evidence: {row['cell_type']}",
                "text": make_chunk_text(row),
                "metadata": {
                    "source_id": source_id,
                    "source_type": row["source_type"],
                    "census_version": row["census_version"],
                    "data_version": row["census_version"],
                    "organism": row["organism"],
                    "cell_type": row["cell_type"],
                    "cell_type_ontology_term_id": row["cell_type_ontology_term_id"],
                    "tissue": row.get("tissue"),
                    "tissue_ontology_term_id": row.get("tissue_ontology_term_id"),
                    "disease": row.get("disease"),
                    "assay": row.get("assay"),
                    "cell_count": row["cell_count"],
                    "dataset_count": row["dataset_count"],
                    "value_filter": row["value_filter"],
                },
            }
        )
    return chunks


def main() -> int:
    args = parse_args()
    raw_out = Path(args.raw_out)
    processed_out = Path(args.processed_out)
    aliases_out = Path(args.aliases_out)
    chunks_out = Path(args.chunks_out)
    report_out = Path(args.report_out)

    with cellxgene_census.open_soma(census_version=args.census_version) as census:
        obs_node = census["census_data"][args.organism].obs
        available = schema_names(obs_node.schema)
        required_missing = [col for col in DEFAULT_REQUIRED if col not in available]
        optional_missing = [col for col in DEFAULT_OPTIONAL if col not in available]
        if required_missing:
            report = {
                "source_id": args.source_id,
                "status": "failed",
                "reason": "required columns missing",
                "required_missing": required_missing,
                "optional_missing": optional_missing,
                "available_columns": available,
            }
            report_out.parent.mkdir(parents=True, exist_ok=True)
            report_out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            raise SystemExit(f"Required CELLxGENE columns missing: {required_missing}")

        used_optional = [col for col in DEFAULT_OPTIONAL if col in available]
        column_names = DEFAULT_REQUIRED + used_optional
        obs = (
            obs_node.read(value_filter=args.value_filter, column_names=column_names)
            .concat()
            .to_pandas()
        )

    if args.max_rows and len(obs) > args.max_rows:
        obs = obs.head(args.max_rows).copy()

    raw_out.parent.mkdir(parents=True, exist_ok=True)
    obs.to_parquet(raw_out, index=False)

    group_cols = [col for col in DEFAULT_GROUP if col in obs.columns]
    summary = (
        obs.groupby(group_cols, dropna=False, observed=True)
        .agg(cell_count=("dataset_id", "size"), dataset_count=("dataset_id", "nunique"))
        .reset_index()
        .sort_values(["cell_count", "dataset_count"], ascending=False)
    )
    if args.top_n_per_cell_type:
        summary = (
            summary.groupby("cell_type_ontology_term_id", group_keys=False, observed=True)
            .head(args.top_n_per_cell_type)
            .reset_index(drop=True)
        )

    processed_rows = make_processed_rows(summary, args, used_optional)
    alias_rows = make_alias_rows(processed_rows, args.source_id)
    chunk_rows = make_chunk_rows(processed_rows, args.source_id)

    write_jsonl(processed_out, processed_rows)
    write_jsonl(aliases_out, alias_rows)
    write_jsonl(chunks_out, chunk_rows)

    report = {
        "source_id": args.source_id,
        "status": "ok",
        "census_version": args.census_version,
        "organism": args.organism,
        "value_filter": args.value_filter,
        "required_columns": DEFAULT_REQUIRED,
        "optional_columns": DEFAULT_OPTIONAL,
        "available_columns": available,
        "used_columns": column_names,
        "required_missing": [],
        "optional_missing": optional_missing,
        "rows_read": int(len(obs)),
        "groups_written": int(len(processed_rows)),
        "aliases_written": int(len(alias_rows)),
        "chunks_written": int(len(chunk_rows)),
        "raw_out": str(raw_out),
        "processed_out": str(processed_out),
        "aliases_out": str(aliases_out),
        "chunks_out": str(chunks_out),
        "generated_at": datetime.now(UTC).isoformat(),
    }
    report_out.parent.mkdir(parents=True, exist_ok=True)
    report_out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
