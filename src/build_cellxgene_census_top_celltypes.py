#!/usr/bin/env python3
"""Build CELLxGENE Census chunks for top human primary cell types.

The script uses census_info.summary_cell_counts to choose cell types, then
queries obs per cell type so memory stays bounded. For each cell type it keeps
the largest tissue/disease/assay groups.
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

REQUIRED = ["cell_type", "cell_type_ontology_term_id", "dataset_id", "is_primary_data"]
OPTIONAL = [
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
GROUP = ["cell_type", "cell_type_ontology_term_id", "tissue", "tissue_ontology_term_id", "disease", "assay"]
ID_TOKEN_RE = re.compile(r"[^A-Za-z0-9]+")
DEFAULT_CENSUS_VERSION = "2025-11-17"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build CELLxGENE Census top-cell-type RAG summaries.")
    parser.add_argument("--census-version", default=DEFAULT_CENSUS_VERSION)
    parser.add_argument("--organism", default="homo_sapiens")
    parser.add_argument("--max-cell-types", type=int, default=200, help="0 means all human cell types.")
    parser.add_argument("--top-n-per-cell-type", type=int, default=5)
    parser.add_argument("--min-unique-cells", type=int, default=1000)
    parser.add_argument("--source-id", default="cellxgene_census")
    parser.add_argument("--source-type", default="single_cell_atlas_metadata")
    parser.add_argument("--raw-out", default="raw/cellxgene_census_human_primary_top_groups.parquet")
    parser.add_argument("--processed-out", default="processed/cellxgene_census_human_primary_counts.jsonl")
    parser.add_argument("--aliases-out", default="processed/cellxgene_census_human_primary_aliases.jsonl")
    parser.add_argument("--chunks-out", default="chunks/cellxgene_census_human_primary_chunks.jsonl")
    parser.add_argument("--report-out", default="processed/cellxgene_census_human_primary_report.json")
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


def safe(value: Any) -> str:
    if pd.isna(value):
        return "unknown"
    text = str(value).strip()
    return text if text else "unknown"


def normalize(text: str) -> str:
    return " ".join(text.casefold().strip().split())


def id_token(value: Any, fallback: str = "unknown") -> str:
    text = safe(value)
    if text == "unknown":
        text = fallback
    token = ID_TOKEN_RE.sub("_", text).strip("_").lower()
    return token or fallback


def alias_values(value: Any) -> list[str]:
    text = safe(value)
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


def get_cell_types(census: Any, organism: str, max_cell_types: int, min_unique_cells: int) -> pd.DataFrame:
    counts = (
        census["census_info"]["summary_cell_counts"]
        .read(value_filter=f"organism == '{organism}' and category == 'cell_type'")
        .concat()
        .to_pandas()
    )
    counts = counts[counts["ontology_term_id"].astype(str).str.startswith("CL:")].copy()
    counts = counts[counts["unique_cell_count"] >= min_unique_cells].copy()
    counts = counts.sort_values("unique_cell_count", ascending=False)
    if max_cell_types:
        counts = counts.head(max_cell_types)
    return counts.reset_index(drop=True)


def aggregate_one(obs_node: Any, cell_type_id: str, column_names: list[str]) -> pd.DataFrame:
    value_filter = f"is_primary_data == True and cell_type_ontology_term_id == '{cell_type_id}'"
    obs = (
        obs_node.read(value_filter=value_filter, column_names=column_names)
        .concat()
        .to_pandas()
    )
    if obs.empty:
        return pd.DataFrame()
    group_cols = [col for col in GROUP if col in obs.columns]
    return (
        obs.groupby(group_cols, dropna=False, observed=True)
        .agg(cell_count=("dataset_id", "size"), dataset_count=("dataset_id", "nunique"))
        .reset_index()
        .sort_values(["cell_count", "dataset_count"], ascending=False)
    )


def make_rows(summary: pd.DataFrame, args: argparse.Namespace, generated_at: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for record in summary.to_dict(orient="records"):
        row = {
            "cell_type": safe(record.get("cell_type")),
            "cell_type_ontology_term_id": safe(record.get("cell_type_ontology_term_id")),
            "tissue": safe(record.get("tissue")),
            "tissue_ontology_term_id": safe(record.get("tissue_ontology_term_id")),
            "disease": safe(record.get("disease")),
            "assay": safe(record.get("assay")),
            "cell_count": int(record.get("cell_count") or 0),
            "dataset_count": int(record.get("dataset_count") or 0),
            "source_id": args.source_id,
            "source_type": args.source_type,
            "census_version": args.census_version,
            "organism": args.organism,
            "generated_at": generated_at,
        }
        rows.append(row)
    return rows


def make_aliases(rows: list[dict[str, Any]], source_id: str) -> list[dict[str, Any]]:
    aliases: dict[tuple[str, str, str], dict[str, Any]] = {}
    for index, row in enumerate(rows):
        target_id = evidence_doc_id(row, source_id, index)
        candidates: list[tuple[str, str]] = []
        for alias_type, value in [
            ("cell_type", row.get("cell_type")),
            ("cell_type_id", row.get("cell_type_ontology_term_id")),
            ("cell_type_id_compact", row.get("cell_type_ontology_term_id", "").replace(":", "")),
            ("cell_type_id_underscore", row.get("cell_type_ontology_term_id", "").replace(":", "_")),
            ("tissue", row.get("tissue")),
            ("tissue_id", row.get("tissue_ontology_term_id")),
            ("disease", row.get("disease")),
            ("assay", row.get("assay")),
        ]:
            for alias in alias_values(value):
                candidates.append((alias_type, alias))
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


def chunk_text(row: dict[str, Any]) -> str:
    lines = [
        f"CELLxGENE Census evidence for {row['cell_type']} [{row['cell_type_ontology_term_id']}].",
        f"Organism: {row['organism']}. Census version: {row['census_version']}.",
        f"Cell count: {row['cell_count']}. Dataset count: {row['dataset_count']}.",
        f"Tissue: {row['tissue']} [{row['tissue_ontology_term_id']}].",
        f"Disease/condition label: {row['disease']}.",
        f"Assay: {row['assay']}.",
    ]
    return "\n".join(lines)


def make_chunks(rows: list[dict[str, Any]], source_id: str) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        doc_id = evidence_doc_id(row, source_id, index)
        chunks.append(
            {
                "chunk_id": doc_id,
                "doc_id": doc_id,
                "title": f"CELLxGENE Census evidence: {row['cell_type']}",
                "text": chunk_text(row),
                "metadata": {
                    "source_id": source_id,
                    "source_type": row["source_type"],
                    "census_version": row["census_version"],
                    "data_version": row["census_version"],
                    "organism": row["organism"],
                    "cell_type": row["cell_type"],
                    "cell_type_ontology_term_id": row["cell_type_ontology_term_id"],
                    "tissue": row["tissue"],
                    "tissue_ontology_term_id": row["tissue_ontology_term_id"],
                    "disease": row["disease"],
                    "assay": row["assay"],
                    "cell_count": row["cell_count"],
                    "dataset_count": row["dataset_count"],
                },
            }
        )
    return chunks


def main() -> int:
    args = parse_args()
    generated_at = datetime.now(UTC).isoformat()
    per_cell_reports: list[dict[str, Any]] = []
    frames: list[pd.DataFrame] = []

    with cellxgene_census.open_soma(census_version=args.census_version) as census:
        obs_node = census["census_data"][args.organism].obs
        available = schema_names(obs_node.schema)
        missing_required = [col for col in REQUIRED if col not in available]
        optional_missing = [col for col in OPTIONAL if col not in available]
        if missing_required:
            raise SystemExit(f"Missing required Census columns: {missing_required}")

        column_names = REQUIRED + [col for col in OPTIONAL if col in available]
        cell_types = get_cell_types(census, args.organism, args.max_cell_types, args.min_unique_cells)
        for index, cell in cell_types.iterrows():
            cell_id = str(cell["ontology_term_id"])
            label = str(cell["label"])
            print(f"[{index + 1}/{len(cell_types)}] {label} {cell_id}", flush=True)
            try:
                summary = aggregate_one(obs_node, cell_id, column_names)
                if args.top_n_per_cell_type:
                    summary = summary.head(args.top_n_per_cell_type)
                frames.append(summary)
                per_cell_reports.append(
                    {
                        "cell_type": label,
                        "cell_type_ontology_term_id": cell_id,
                        "unique_cell_count_summary": int(cell["unique_cell_count"]),
                        "groups_kept": int(len(summary)),
                        "status": "ok",
                    }
                )
            except Exception as exc:
                per_cell_reports.append(
                    {
                        "cell_type": label,
                        "cell_type_ontology_term_id": cell_id,
                        "unique_cell_count_summary": int(cell["unique_cell_count"]),
                        "groups_kept": 0,
                        "status": "error",
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )

    combined = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    rows = make_rows(combined, args, generated_at)
    aliases = make_aliases(rows, args.source_id)
    chunks = make_chunks(rows, args.source_id)

    raw_out = Path(args.raw_out)
    raw_out.parent.mkdir(parents=True, exist_ok=True)
    combined.to_parquet(raw_out, index=False)
    write_jsonl(Path(args.processed_out), rows)
    write_jsonl(Path(args.aliases_out), aliases)
    write_jsonl(Path(args.chunks_out), chunks)

    report = {
        "source_id": args.source_id,
        "status": "ok",
        "census_version": args.census_version,
        "organism": args.organism,
        "max_cell_types": args.max_cell_types,
        "top_n_per_cell_type": args.top_n_per_cell_type,
        "min_unique_cells": args.min_unique_cells,
        "cell_types_considered": len(per_cell_reports),
        "cell_types_ok": sum(1 for row in per_cell_reports if row["status"] == "ok"),
        "cell_types_error": sum(1 for row in per_cell_reports if row["status"] != "ok"),
        "groups_written": len(rows),
        "aliases_written": len(aliases),
        "chunks_written": len(chunks),
        "required_missing": [],
        "optional_missing": optional_missing,
        "generated_at": generated_at,
        "raw_out": args.raw_out,
        "processed_out": args.processed_out,
        "aliases_out": args.aliases_out,
        "chunks_out": args.chunks_out,
        "per_cell_reports": per_cell_reports,
    }
    report_out = Path(args.report_out)
    report_out.parent.mkdir(parents=True, exist_ok=True)
    report_out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items() if key != "per_cell_reports"}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
