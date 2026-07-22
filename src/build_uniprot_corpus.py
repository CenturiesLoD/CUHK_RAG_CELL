#!/usr/bin/env python3
"""Build UniProtKB reviewed human protein function records, aliases, and RAG chunks."""

from __future__ import annotations

import argparse
import csv
import json
import re
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import requests


DEFAULT_QUERY = "organism_id:9606 AND reviewed:true"
DEFAULT_FIELDS = ",".join(
    [
        "accession",
        "id",
        "reviewed",
        "protein_name",
        "gene_names",
        "gene_primary",
        "gene_synonym",
        "cc_function",
        "go_id",
        "xref_hgnc",
        "xref_geneid",
        "xref_ensembl",
    ]
)
DEFAULT_URL = "https://rest.uniprot.org/uniprotkb/search"
FUNCTION_PREFIX_RE = re.compile(r"^FUNCTION:\s*", re.IGNORECASE)
ECO_RE = re.compile(r"\s*\{ECO:[^}]+\}")
PUBMED_RE = re.compile(r"\s*\(PubMed:[^)]+\)")
SPACE_RE = re.compile(r"\s+")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build UniProt reviewed human RAG corpus.")
    parser.add_argument("--endpoint", default=DEFAULT_URL)
    parser.add_argument("--query", default=DEFAULT_QUERY)
    parser.add_argument("--fields", default=DEFAULT_FIELDS)
    parser.add_argument("--raw-out", default="raw/uniprot_human_reviewed.tsv")
    parser.add_argument("--records-out", default="processed/uniprot_human_reviewed_records.jsonl")
    parser.add_argument("--aliases-out", default="processed/uniprot_human_reviewed_aliases.jsonl")
    parser.add_argument("--chunks-out", default="chunks/uniprot_human_reviewed_chunks.jsonl")
    parser.add_argument("--report-out", default="processed/uniprot_human_reviewed_report.json")
    parser.add_argument("--source-id", default="uniprot_human_reviewed")
    parser.add_argument("--source-type", default="protein_function")
    parser.add_argument("--page-size", type=int, default=500)
    parser.add_argument("--retries", type=int, default=5)
    return parser.parse_args()


def normalize(text: Any) -> str:
    return SPACE_RE.sub(" ", str(text).casefold().strip())


def split_semicolon(value: str) -> list[str]:
    return [part.strip() for part in str(value or "").split(";") if part.strip()]


def split_space(value: str) -> list[str]:
    return [part.strip() for part in str(value or "").split() if part.strip()]


def clean_function(value: str) -> str:
    text = FUNCTION_PREFIX_RE.sub("", str(value or "").strip())
    text = ECO_RE.sub("", text)
    text = PUBMED_RE.sub("", text)
    return SPACE_RE.sub(" ", text).strip()


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def next_link(response: requests.Response) -> str:
    link = response.headers.get("Link", "")
    match = re.search(r"<([^>]+)>;\s*rel=\"next\"", link)
    return match.group(1) if match else ""


def request_text(session: requests.Session, url: str, retries: int) -> requests.Response:
    last_exc: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            response = session.get(url, timeout=180)
            response.raise_for_status()
            return response
        except requests.RequestException as exc:
            last_exc = exc
            if attempt == retries:
                break
    assert last_exc is not None
    raise last_exc


def download(args: argparse.Namespace) -> str:
    raw_path = Path(args.raw_out)
    if raw_path.exists() and raw_path.stat().st_size > 0:
        return raw_path.read_text(encoding="utf-8")
    params = urllib.parse.urlencode({"format": "tsv", "fields": args.fields, "query": args.query, "size": args.page_size})
    url = f"{args.endpoint}?{params}"
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    session.headers.update({"User-Agent": "cell-rag-uniprot-builder/1.0"})
    lines: list[str] = []
    header: str | None = None
    page = 0
    while url:
        page += 1
        response = request_text(session, url, args.retries)
        page_lines = response.text.splitlines()
        if not page_lines:
            break
        if header is None:
            header = page_lines[0]
            lines.append(header)
        elif page_lines[0] != header:
            raise ValueError(f"Unexpected UniProt TSV header on page {page}: {page_lines[0]}")
        lines.extend(page_lines[1:])
        url = next_link(response)
        print(f"downloaded UniProt page {page}: total_records={len(lines) - 1}", flush=True)
    text = "\n".join(lines) + "\n"
    raw_path.write_text(text, encoding="utf-8")
    return text


def parse_tsv(text: str, args: argparse.Namespace, data_version: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    reader = csv.DictReader(text.splitlines(), delimiter="\t")
    for raw in reader:
        accession = str(raw.get("Entry", "")).strip()
        if not accession:
            continue
        hgnc_ids = [value.rstrip(";") for value in split_semicolon(raw.get("HGNC", ""))]
        record = {
            "accession": accession,
            "entry_name": str(raw.get("Entry Name", "")).strip(),
            "reviewed": str(raw.get("Reviewed", "")).strip(),
            "protein_name": str(raw.get("Protein names", "")).strip(),
            "gene_names": split_space(raw.get("Gene Names", "")),
            "gene_primary": str(raw.get("Gene Names (primary)", "")).strip(),
            "gene_synonym": split_space(raw.get("Gene Names (synonym)", "")),
            "function": clean_function(raw.get("Function [CC]", "")),
            "go_ids": split_semicolon(raw.get("Gene Ontology IDs", "")),
            "hgnc_ids": hgnc_ids,
            "gene_ids": [value.rstrip(";") for value in split_semicolon(raw.get("GeneID", ""))],
            "ensembl_transcripts": split_semicolon(raw.get("Ensembl", "")),
            "organism": "Homo sapiens",
            "data_version": data_version,
            "source_id": args.source_id,
            "source_type": args.source_type,
        }
        rows.append(record)
    rows.sort(key=lambda row: row["accession"])
    return rows


def alias_candidates(record: dict[str, Any]) -> list[tuple[str, str]]:
    candidates = [
        ("accession", record["accession"]),
        ("entry_name", record["entry_name"]),
        ("protein_name", record["protein_name"]),
        ("gene_primary", record["gene_primary"]),
    ]
    for field in ("gene_names", "gene_synonym", "go_ids", "hgnc_ids", "gene_ids"):
        for value in record.get(field, []):
            candidates.append((field, value))
    return [(kind, value) for kind, value in candidates if value]


def make_aliases(records: list[dict[str, Any]], source_id: str) -> list[dict[str, Any]]:
    aliases: dict[tuple[str, str, str], dict[str, Any]] = {}
    for record in records:
        target_id = f"UniProt:{record['accession']}"
        for alias_type, alias in alias_candidates(record):
            key = (target_id, alias_type, normalize(alias))
            aliases[key] = {
                "target_id": target_id,
                "alias": alias,
                "alias_norm": normalize(alias),
                "alias_type": alias_type,
                "source_id": source_id,
            }
    return sorted(aliases.values(), key=lambda row: (row["target_id"], row["alias_type"], row["alias_norm"]))


def make_text(record: dict[str, Any]) -> str:
    lines = [
        f"UniProt protein: {record['protein_name']} [UniProt:{record['accession']}].",
        f"Entry name: {record['entry_name']}. Reviewed status: {record['reviewed']}.",
    ]
    if record.get("gene_primary"):
        lines.append(f"Primary gene symbol: {record['gene_primary']}.")
    if record.get("gene_synonym"):
        lines.append("Gene synonyms: " + "; ".join(record["gene_synonym"]) + ".")
    if record.get("function"):
        lines.append("Function: " + record["function"])
    if record.get("hgnc_ids"):
        lines.append("HGNC cross references: " + "; ".join(record["hgnc_ids"]) + ".")
    if record.get("go_ids"):
        lines.append("Gene Ontology IDs: " + "; ".join(record["go_ids"][:20]) + ".")
    if record.get("gene_ids"):
        lines.append("NCBI Gene IDs: " + "; ".join(record["gene_ids"]) + ".")
    lines.append(f"Data version: {record['data_version']}.")
    return "\n".join(lines)


def make_chunks(records: list[dict[str, Any]], source_id: str) -> list[dict[str, Any]]:
    chunks = []
    for record in records:
        doc_id = f"UniProt:{record['accession']}"
        chunks.append(
            {
                "chunk_id": f"{source_id}:{record['accession']}",
                "doc_id": doc_id,
                "title": f"UniProt protein: {record['accession']} {record.get('gene_primary') or record.get('entry_name')}",
                "text": make_text(record),
                "metadata": {
                    "accession": record["accession"],
                    "entry_name": record["entry_name"],
                    "gene_primary": record["gene_primary"],
                    "gene_synonym": record["gene_synonym"],
                    "hgnc_ids": record["hgnc_ids"],
                    "go_ids": record["go_ids"],
                    "data_version": record["data_version"],
                    "source_id": source_id,
                    "source_type": record["source_type"],
                },
            }
        )
    return chunks


def main() -> int:
    args = parse_args()
    text = download(args)
    data_version = f"UniProtKB reviewed human stream downloaded {datetime.now(UTC).date().isoformat()}"
    records = parse_tsv(text, args, data_version)
    aliases = make_aliases(records, args.source_id)
    chunks = make_chunks(records, args.source_id)
    write_jsonl(Path(args.records_out), records)
    write_jsonl(Path(args.aliases_out), aliases)
    write_jsonl(Path(args.chunks_out), chunks)
    report = {
        "source_id": args.source_id,
        "source_type": args.source_type,
        "endpoint": args.endpoint,
        "query": args.query,
        "fields": args.fields,
        "raw_out": args.raw_out,
        "records_out": args.records_out,
        "aliases_out": args.aliases_out,
        "chunks_out": args.chunks_out,
        "data_version": data_version,
        "records": len(records),
        "aliases": len(aliases),
        "chunks": len(chunks),
        "records_with_function": sum(1 for row in records if row.get("function")),
        "records_with_hgnc": sum(1 for row in records if row.get("hgnc_ids")),
    }
    Path(args.report_out).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
