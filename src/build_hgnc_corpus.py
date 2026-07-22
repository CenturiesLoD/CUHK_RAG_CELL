#!/usr/bin/env python3
"""Build HGNC gene normalization records, aliases, and RAG chunks."""

from __future__ import annotations

import argparse
import json
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SPACE = " "
DEFAULT_URL = "https://storage.googleapis.com/public-download-files/hgnc/json/json/hgnc_complete_set.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build HGNC gene normalization corpus.")
    parser.add_argument("--source-url", default=DEFAULT_URL)
    parser.add_argument("--raw-out", default="raw/hgnc_complete_set.json")
    parser.add_argument("--genes-out", default="processed/hgnc_genes.jsonl")
    parser.add_argument("--aliases-out", default="processed/hgnc_aliases.jsonl")
    parser.add_argument("--chunks-out", default="chunks/hgnc_chunks.jsonl")
    parser.add_argument("--report-out", default="processed/hgnc_report.json")
    parser.add_argument("--source-id", default="hgnc")
    parser.add_argument("--source-type", default="gene_nomenclature")
    parser.add_argument("--license", default="free use with attribution")
    return parser.parse_args()


def normalize(text: Any) -> str:
    return SPACE.join(str(text).casefold().strip().split())


def as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value).strip()
    return [text] if text else []


def scalar(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return "; ".join(as_list(value))
    return str(value).strip()


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def load_raw(args: argparse.Namespace) -> dict[str, Any]:
    raw_path = Path(args.raw_out)
    if raw_path.exists() and raw_path.stat().st_size > 0:
        return json.loads(raw_path.read_text(encoding="utf-8"))
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(args.source_url, headers={"User-Agent": "cell-rag-hgnc-builder/1.0"})
    with urllib.request.urlopen(request, timeout=240) as response:
        raw = response.read()
    raw_path.write_bytes(raw)
    return json.loads(raw.decode("utf-8"))


def docs_from_raw(raw: dict[str, Any]) -> list[dict[str, Any]]:
    response = raw.get("response", {})
    docs = response.get("docs", [])
    if not isinstance(docs, list):
        raise ValueError("HGNC response did not contain response.docs list")
    return [doc for doc in docs if isinstance(doc, dict)]


def make_gene(doc: dict[str, Any], args: argparse.Namespace, data_version: str) -> dict[str, Any]:
    hgnc_id = scalar(doc.get("hgnc_id"))
    symbol = scalar(doc.get("symbol"))
    name = scalar(doc.get("name"))
    return {
        "hgnc_id": hgnc_id,
        "symbol": symbol,
        "name": name,
        "status": scalar(doc.get("status")),
        "locus_type": scalar(doc.get("locus_type")),
        "locus_group": scalar(doc.get("locus_group")),
        "alias_symbol": sorted(set(as_list(doc.get("alias_symbol")))),
        "alias_name": sorted(set(as_list(doc.get("alias_name")))),
        "prev_symbol": sorted(set(as_list(doc.get("prev_symbol")))),
        "prev_name": sorted(set(as_list(doc.get("prev_name")))),
        "ensembl_gene_id": scalar(doc.get("ensembl_gene_id")),
        "entrez_id": scalar(doc.get("entrez_id")),
        "uniprot_ids": sorted(set(as_list(doc.get("uniprot_ids")))),
        "ucsc_id": scalar(doc.get("ucsc_id")),
        "refseq_accession": sorted(set(as_list(doc.get("refseq_accession")))),
        "vega_id": scalar(doc.get("vega_id")),
        "ccds_id": sorted(set(as_list(doc.get("ccds_id")))),
        "data_version": data_version,
        "source_id": args.source_id,
        "source_type": args.source_type,
    }


def alias_candidates(gene: dict[str, Any]) -> list[tuple[str, str]]:
    candidates: list[tuple[str, str]] = [
        ("hgnc_id", gene["hgnc_id"]),
        ("symbol", gene["symbol"]),
        ("name", gene["name"]),
        ("ensembl_gene_id", gene["ensembl_gene_id"]),
        ("entrez_id", gene["entrez_id"]),
        ("ucsc_id", gene["ucsc_id"]),
        ("vega_id", gene["vega_id"]),
    ]
    for field in ("alias_symbol", "alias_name", "prev_symbol", "prev_name", "uniprot_ids", "refseq_accession", "ccds_id"):
        for value in gene.get(field, []):
            candidates.append((field, value))
    return [(kind, value) for kind, value in candidates if value]


def make_text(gene: dict[str, Any]) -> str:
    lines = [
        f"HGNC gene: {gene['symbol']} [{gene['hgnc_id']}].",
        f"Approved name: {gene['name']}.",
    ]
    if gene.get("status"):
        lines.append(f"Status: {gene['status']}.")
    if gene.get("locus_type"):
        lines.append(f"Locus type: {gene['locus_type']}.")
    if gene.get("alias_symbol"):
        lines.append("Alias symbols: " + "; ".join(gene["alias_symbol"]) + ".")
    if gene.get("alias_name"):
        lines.append("Alias names: " + "; ".join(gene["alias_name"]) + ".")
    if gene.get("prev_symbol"):
        lines.append("Previous symbols: " + "; ".join(gene["prev_symbol"]) + ".")
    if gene.get("prev_name"):
        lines.append("Previous names: " + "; ".join(gene["prev_name"]) + ".")
    refs = []
    if gene.get("ensembl_gene_id"):
        refs.append(f"Ensembl: {gene['ensembl_gene_id']}")
    if gene.get("entrez_id"):
        refs.append(f"Entrez: {gene['entrez_id']}")
    if gene.get("uniprot_ids"):
        refs.append("UniProt: " + "; ".join(gene["uniprot_ids"]))
    if refs:
        lines.append("Cross references: " + "; ".join(refs) + ".")
    lines.append(f"Data version: {gene['data_version']}.")
    return "\n".join(lines)


def build(raw: dict[str, Any], args: argparse.Namespace) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], str]:
    docs = docs_from_raw(raw)
    generated_at = datetime.now(UTC).date().isoformat()
    data_version = f"HGNC complete set downloaded {generated_at}"
    genes: list[dict[str, Any]] = []
    aliases_by_key: dict[tuple[str, str, str], dict[str, Any]] = {}
    chunks: list[dict[str, Any]] = []

    for doc in docs:
        gene = make_gene(doc, args, data_version)
        if not gene["hgnc_id"] or not gene["symbol"]:
            continue
        genes.append(gene)
        for alias_type, alias in alias_candidates(gene):
            key = (gene["hgnc_id"], alias_type, normalize(alias))
            aliases_by_key[key] = {
                "target_id": gene["hgnc_id"],
                "alias": alias,
                "alias_norm": normalize(alias),
                "alias_type": alias_type,
                "source_id": args.source_id,
            }
        chunks.append(
            {
                "chunk_id": f"{args.source_id}:{gene['hgnc_id'].replace(':', '_')}",
                "doc_id": gene["hgnc_id"],
                "title": f"HGNC gene: {gene['symbol']}",
                "text": make_text(gene),
                "metadata": {
                    "hgnc_id": gene["hgnc_id"],
                    "symbol": gene["symbol"],
                    "name": gene["name"],
                    "alias_symbol": gene["alias_symbol"],
                    "prev_symbol": gene["prev_symbol"],
                    "ensembl_gene_id": gene["ensembl_gene_id"],
                    "entrez_id": gene["entrez_id"],
                    "uniprot_ids": gene["uniprot_ids"],
                    "data_version": gene["data_version"],
                    "source_id": args.source_id,
                    "source_type": args.source_type,
                },
            }
        )

    genes.sort(key=lambda row: row["hgnc_id"])
    aliases = sorted(aliases_by_key.values(), key=lambda row: (row["target_id"], row["alias_type"], row["alias_norm"]))
    chunks.sort(key=lambda row: row["doc_id"])
    return genes, aliases, chunks, data_version


def main() -> int:
    args = parse_args()
    raw = load_raw(args)
    genes, aliases, chunks, data_version = build(raw, args)
    write_jsonl(Path(args.genes_out), genes)
    write_jsonl(Path(args.aliases_out), aliases)
    write_jsonl(Path(args.chunks_out), chunks)
    report = {
        "source_id": args.source_id,
        "source_type": args.source_type,
        "source_url": args.source_url,
        "raw_out": args.raw_out,
        "genes_out": args.genes_out,
        "aliases_out": args.aliases_out,
        "chunks_out": args.chunks_out,
        "data_version": data_version,
        "genes": len(genes),
        "aliases": len(aliases),
        "chunks": len(chunks),
    }
    Path(args.report_out).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
