#!/usr/bin/env python3
"""Build NCBI Gene human reference records, aliases, and RAG chunks."""

from __future__ import annotations

import argparse
import csv
import gzip
import json
import re
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable

SPACE_RE = re.compile(r"\s+")
DEFAULT_URL = "https://ftp.ncbi.nlm.nih.gov/gene/DATA/GENE_INFO/Mammalia/Homo_sapiens.gene_info.gz"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build NCBI Gene human corpus.")
    parser.add_argument("--source-url", default=DEFAULT_URL)
    parser.add_argument("--raw-out", default="raw/ncbi_homo_sapiens_gene_info.gz")
    parser.add_argument("--records-out", default="processed/ncbi_gene_human_records.jsonl")
    parser.add_argument("--aliases-out", default="processed/ncbi_gene_human_aliases.jsonl")
    parser.add_argument("--chunks-out", default="chunks/ncbi_gene_human_chunks.jsonl")
    parser.add_argument("--report-out", default="processed/ncbi_gene_human_report.json")
    parser.add_argument("--source-id", default="ncbi_gene_human")
    parser.add_argument("--source-type", default="gene_reference")
    return parser.parse_args()


def clean(value: Any) -> str:
    text = str(value or "").strip()
    return "" if text in {"", "-", "NA", "N/A", "None", "none", "null"} else text


def normalize(text: Any) -> str:
    return SPACE_RE.sub(" ", str(text or "").casefold().strip())


def split_pipe(value: Any) -> list[str]:
    text = clean(value)
    if not text:
        return []
    return [part.strip() for part in text.split("|") if clean(part)]


def download(args: argparse.Namespace) -> dict[str, str]:
    raw_path = Path(args.raw_out)
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    metadata = {"source_url": args.source_url}
    if raw_path.exists() and raw_path.stat().st_size > 0:
        metadata["raw_bytes"] = str(raw_path.stat().st_size)
        return metadata
    request = urllib.request.Request(args.source_url, headers={"User-Agent": "cell-rag-ncbi-gene-builder/1.0"})
    with urllib.request.urlopen(request, timeout=240) as response:
        metadata["last_modified"] = str(response.headers.get("last-modified") or "")
        metadata["content_length"] = str(response.headers.get("content-length") or "")
        raw_path.write_bytes(response.read())
    metadata["raw_bytes"] = str(raw_path.stat().st_size)
    return metadata


def load_rows(path: Path) -> list[dict[str, str]]:
    with gzip.open(path, "rt", encoding="utf-8", errors="replace", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if reader.fieldnames and reader.fieldnames[0].startswith("#"):
            reader.fieldnames[0] = reader.fieldnames[0].lstrip("#")
        return [dict(row) for row in reader if row.get("tax_id") == "9606"]


def build_record(row: dict[str, str], args: argparse.Namespace, data_version: str) -> dict[str, Any]:
    gene_id = clean(row.get("GeneID"))
    symbol = clean(row.get("Symbol"))
    synonyms = split_pipe(row.get("Synonyms"))
    db_xrefs = split_pipe(row.get("dbXrefs"))
    other_designations = split_pipe(row.get("Other_designations"))
    return {
        "gene_id": gene_id,
        "entrez_id": gene_id,
        "symbol": symbol,
        "locus_tag": clean(row.get("LocusTag")),
        "synonyms": synonyms,
        "db_xrefs": db_xrefs,
        "chromosome": clean(row.get("chromosome")),
        "map_location": clean(row.get("map_location")),
        "description": clean(row.get("description")),
        "type_of_gene": clean(row.get("type_of_gene")),
        "nomenclature_symbol": clean(row.get("Symbol_from_nomenclature_authority")),
        "nomenclature_name": clean(row.get("Full_name_from_nomenclature_authority")),
        "nomenclature_status": clean(row.get("Nomenclature_status")),
        "other_designations": other_designations,
        "modification_date": clean(row.get("Modification_date")),
        "feature_type": clean(row.get("Feature_type")),
        "organism": "Homo sapiens",
        "tax_id": "9606",
        "data_version": data_version,
        "source_id": args.source_id,
        "source_type": args.source_type,
    }


def alias_candidates(record: dict[str, Any]) -> Iterable[tuple[str, str]]:
    yield "gene_id", record["gene_id"]
    yield "entrez_id", record["entrez_id"]
    yield "symbol", record["symbol"]
    yield "description", record["description"]
    yield "nomenclature_symbol", record["nomenclature_symbol"]
    yield "nomenclature_name", record["nomenclature_name"]
    for field in ("synonyms", "db_xrefs", "other_designations"):
        for value in record.get(field, []):
            yield field, value


def make_text(record: dict[str, Any]) -> str:
    doc_id = f"NCBIGene:{record['gene_id']}"
    lines = [
        f"NCBI Gene: {record['symbol']} [{doc_id}].",
        f"Entrez Gene ID: {record['gene_id']}.",
    ]
    if record.get("description"):
        lines.append(f"Description: {record['description']}.")
    if record.get("nomenclature_name"):
        lines.append(f"Nomenclature name: {record['nomenclature_name']}.")
    if record.get("nomenclature_symbol") and record["nomenclature_symbol"] != record.get("symbol"):
        lines.append(f"Nomenclature symbol: {record['nomenclature_symbol']}.")
    if record.get("type_of_gene"):
        lines.append(f"Gene type: {record['type_of_gene']}.")
    location = []
    if record.get("chromosome"):
        location.append(f"chromosome {record['chromosome']}")
    if record.get("map_location"):
        location.append(f"map location {record['map_location']}")
    if location:
        lines.append("Genomic location: " + "; ".join(location) + ".")
    if record.get("synonyms"):
        lines.append("Synonyms: " + "; ".join(record["synonyms"][:40]) + ".")
    if record.get("other_designations"):
        lines.append("Other designations: " + "; ".join(record["other_designations"][:30]) + ".")
    if record.get("db_xrefs"):
        lines.append("Cross references: " + "; ".join(record["db_xrefs"][:30]) + ".")
    if record.get("modification_date"):
        lines.append(f"NCBI modification date: {record['modification_date']}.")
    lines.append(f"Data version: {record['data_version']}.")
    return "\n".join(lines)


def build(args: argparse.Namespace, metadata: dict[str, str]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    raw_path = Path(args.raw_out)
    downloaded = datetime.now(UTC).date().isoformat()
    data_version = f"NCBI Gene Homo sapiens gene_info downloaded {downloaded}"
    rows = load_rows(raw_path)
    records = [build_record(row, args, data_version) for row in rows]
    records = [record for record in records if record["gene_id"] and record["symbol"]]
    records.sort(key=lambda row: int(row["gene_id"]) if str(row["gene_id"]).isdigit() else 10**18)

    aliases_by_key: dict[tuple[str, str, str], dict[str, Any]] = {}
    chunks: list[dict[str, Any]] = []
    for record in records:
        doc_id = f"NCBIGene:{record['gene_id']}"
        for alias_type, alias in alias_candidates(record):
            alias = clean(alias)
            alias_norm = normalize(alias)
            if not alias_norm:
                continue
            aliases_by_key[(doc_id, alias_type, alias_norm)] = {
                "target_id": doc_id,
                "alias": alias,
                "alias_norm": alias_norm,
                "alias_type": alias_type,
                "source_id": args.source_id,
            }
        chunks.append(
            {
                "chunk_id": f"{args.source_id}:{record['gene_id']}",
                "doc_id": doc_id,
                "title": f"NCBI Gene: {record['symbol']}",
                "text": make_text(record),
                "metadata": {
                    "gene_id": record["gene_id"],
                    "symbol": record["symbol"],
                    "description": record["description"],
                    "type_of_gene": record["type_of_gene"],
                    "chromosome": record["chromosome"],
                    "map_location": record["map_location"],
                    "nomenclature_symbol": record["nomenclature_symbol"],
                    "nomenclature_name": record["nomenclature_name"],
                    "data_version": record["data_version"],
                    "source_id": args.source_id,
                    "source_type": args.source_type,
                },
            }
        )

    aliases = sorted(aliases_by_key.values(), key=lambda row: (row["target_id"], row["alias_type"], row["alias_norm"]))
    report = {
        "source_id": args.source_id,
        "source_type": args.source_type,
        "source_url": args.source_url,
        "raw_out": args.raw_out,
        "records_out": args.records_out,
        "aliases_out": args.aliases_out,
        "chunks_out": args.chunks_out,
        "data_version": data_version,
        "download_metadata": metadata,
        "records": len(records),
        "aliases": len(aliases),
        "chunks": len(chunks),
    }
    return records, aliases, chunks, report


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def main() -> int:
    args = parse_args()
    metadata = download(args)
    records, aliases, chunks, report = build(args, metadata)
    write_jsonl(Path(args.records_out), records)
    write_jsonl(Path(args.aliases_out), aliases)
    write_jsonl(Path(args.chunks_out), chunks)
    Path(args.report_out).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
