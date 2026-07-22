#!/usr/bin/env python3
"""Build marker-set records, aliases, and RAG chunks for CellMarker and PanglaoDB."""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import re
import zipfile
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable

SPACE_RE = re.compile(r"\s+")
SLUG_RE = re.compile(r"[^a-z0-9]+")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build marker-source RAG corpora.")
    parser.add_argument("--cellmarker-zip", default="raw/marker_downloads/cellmarker_all_cell_marker.zip")
    parser.add_argument("--cellmarker-raw", default="raw/cellmarker_all_cell_marker/all_cell_marker.txt")
    parser.add_argument("--panglao-raw", default="raw/marker_downloads/panglaodb_markers_27_mar_2020.tsv.gz")
    parser.add_argument("--marker-limit", type=int, default=80)
    parser.add_argument("--alias-marker-limit", type=int, default=80)
    parser.add_argument("--cellmarker-sets-out", default="processed/cellmarker3_marker_sets.jsonl")
    parser.add_argument("--cellmarker-aliases-out", default="processed/cellmarker3_aliases.jsonl")
    parser.add_argument("--cellmarker-chunks-out", default="chunks/cellmarker3_chunks.jsonl")
    parser.add_argument("--cellmarker-report-out", default="processed/cellmarker3_report.json")
    parser.add_argument("--panglao-sets-out", default="processed/panglaodb_marker_sets.jsonl")
    parser.add_argument("--panglao-aliases-out", default="processed/panglaodb_aliases.jsonl")
    parser.add_argument("--panglao-chunks-out", default="chunks/panglaodb_chunks.jsonl")
    parser.add_argument("--panglao-report-out", default="processed/panglaodb_report.json")
    return parser.parse_args()


def normalize(text: Any) -> str:
    return SPACE_RE.sub(" ", str(text or "").casefold().strip())


def clean(text: Any) -> str:
    value = str(text or "").strip()
    return "" if value.upper() in {"NA", "N/A", "NULL", "NONE", "NAN"} else value


def normalize_ontology_id(value: Any) -> str:
    text = clean(value)
    if not text:
        return ""
    return text.replace("_", ":")


def slug(text: Any, fallback: str = "unknown") -> str:
    value = SLUG_RE.sub("_", normalize(text)).strip("_")
    return value or fallback


def top_counter(counter: Counter[str], limit: int) -> list[str]:
    return [key for key, _ in counter.most_common(limit) if key]


def add_alias(aliases: dict[tuple[str, str, str], dict[str, Any]], target_id: str, alias: str, alias_type: str, source_id: str) -> None:
    alias = clean(alias)
    alias_norm = normalize(alias)
    if not alias_norm:
        return
    key = (target_id, alias_type, alias_norm)
    aliases[key] = {
        "target_id": target_id,
        "alias": alias,
        "alias_norm": alias_norm,
        "alias_type": alias_type,
        "source_id": source_id,
    }


def cell_type_aliases(cell_type: str) -> list[str]:
    aliases = {cell_type}
    norm = normalize(cell_type)
    if norm.endswith(" cells"):
        aliases.add(cell_type[:-1])
    if norm.endswith(" cell"):
        aliases.add(cell_type + "s")
    if "regulatory t" in norm or "t regulatory" in norm:
        aliases.update({"Treg", "Tregs", "regulatory T cell", "regulatory T cells", "T regulatory cell", "T regulatory cells"})
    if norm == "t cells":
        aliases.add("T cell")
    if norm == "b cells":
        aliases.add("B cell")
    if norm == "nk cells":
        aliases.add("NK cell")
    return sorted(aliases)


@dataclass
class MarkerGroup:
    source_id: str
    source_type: str
    species: str
    cell_type: str
    cell_type_ontology_term_id: str = ""
    cell_class: str = ""
    tissues: Counter[str] = field(default_factory=Counter)
    tissue_ontology_term_ids: Counter[str] = field(default_factory=Counter)
    diseases: Counter[str] = field(default_factory=Counter)
    germ_layers: Counter[str] = field(default_factory=Counter)
    organs: Counter[str] = field(default_factory=Counter)
    markers: Counter[str] = field(default_factory=Counter)
    canonical_markers: Counter[str] = field(default_factory=Counter)
    marker_products: dict[str, str] = field(default_factory=dict)
    marker_aliases: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))
    marker_sources: Counter[str] = field(default_factory=Counter)
    methods: Counter[str] = field(default_factory=Counter)
    pmids: Counter[str] = field(default_factory=Counter)
    years: Counter[str] = field(default_factory=Counter)
    evidence_count: int = 0


def group_doc_id(source_id: str, species: str, cell_type: str, ontology_id: str = "") -> str:
    pieces = [source_id, slug(species), slug(cell_type)]
    if ontology_id:
        pieces.append(slug(ontology_id))
    digest = hashlib.sha1(f"{source_id}|{species}|{cell_type}|{ontology_id}".encode("utf-8")).hexdigest()[:8]
    pieces.append(digest)
    return ":".join(pieces)


def sorted_records(groups: dict[tuple[str, ...], MarkerGroup], data_version: str, marker_limit: int) -> list[dict[str, Any]]:
    records = []
    for group in groups.values():
        doc_id = group_doc_id(group.source_id, group.species, group.cell_type, group.cell_type_ontology_term_id)
        markers = top_counter(group.markers, marker_limit)
        records.append(
            {
                "doc_id": doc_id,
                "species": group.species,
                "cell_type": group.cell_type,
                "cell_type_ontology_term_id": group.cell_type_ontology_term_id,
                "cell_class": group.cell_class,
                "tissues": top_counter(group.tissues, 30),
                "tissue_ontology_term_ids": top_counter(group.tissue_ontology_term_ids, 30),
                "diseases": top_counter(group.diseases, 20),
                "germ_layers": top_counter(group.germ_layers, 20),
                "organs": top_counter(group.organs, 30),
                "markers": markers,
                "canonical_markers": [marker for marker in markers if group.canonical_markers.get(marker)],
                "marker_count": len(group.markers),
                "evidence_count": group.evidence_count,
                "marker_sources": top_counter(group.marker_sources, 20),
                "methods": top_counter(group.methods, 20),
                "pmids": top_counter(group.pmids, 20),
                "years": top_counter(group.years, 20),
                "data_version": data_version,
                "source_id": group.source_id,
                "source_type": group.source_type,
            }
        )
    return sorted(records, key=lambda row: (row["source_id"], row["species"], row["cell_type"], row["cell_type_ontology_term_id"]))


def marker_text(record: dict[str, Any]) -> str:
    lines = [
        f"Cell marker set: {record['cell_type']} ({record['species']}) [{record['doc_id']}].",
    ]
    if record.get("cell_type_ontology_term_id"):
        lines.append(f"Cell Ontology ID: {record['cell_type_ontology_term_id']}.")
    if record.get("cell_class"):
        lines.append(f"Cell class: {record['cell_class']}.")
    if record.get("tissues"):
        lines.append("Tissues: " + "; ".join(record["tissues"][:20]) + ".")
    if record.get("tissue_ontology_term_ids"):
        lines.append("Tissue ontology IDs: " + "; ".join(record["tissue_ontology_term_ids"][:20]) + ".")
    if record.get("organs"):
        lines.append("Organs: " + "; ".join(record["organs"][:20]) + ".")
    if record.get("germ_layers"):
        lines.append("Germ layers: " + "; ".join(record["germ_layers"][:10]) + ".")
    if record.get("diseases"):
        lines.append("Disease contexts: " + "; ".join(record["diseases"][:12]) + ".")
    if record.get("canonical_markers"):
        lines.append("Canonical markers: " + "; ".join(record["canonical_markers"][:40]) + ".")
    if record.get("markers"):
        lines.append("Markers: " + "; ".join(record["markers"][:80]) + ".")
    if record.get("marker_sources"):
        lines.append("Marker sources: " + "; ".join(record["marker_sources"][:12]) + ".")
    if record.get("methods"):
        lines.append("Methods: " + "; ".join(record["methods"][:12]) + ".")
    if record.get("pmids"):
        lines.append("PMIDs: " + "; ".join(record["pmids"][:12]) + ".")
    lines.append(f"Evidence rows: {record['evidence_count']}; unique markers before truncation: {record['marker_count']}.")
    lines.append(f"Data version: {record['data_version']}.")
    return "\n".join(lines)


def make_outputs(records: list[dict[str, Any]], source_id: str, alias_marker_limit: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    aliases: dict[tuple[str, str, str], dict[str, Any]] = {}
    chunks = []
    for record in records:
        doc_id = record["doc_id"]
        for alias in cell_type_aliases(record["cell_type"]):
            add_alias(aliases, doc_id, alias, "cell_type", source_id)
        for value in [record.get("cell_type_ontology_term_id"), record.get("cell_class"), record.get("species")]:
            add_alias(aliases, doc_id, str(value or ""), "metadata", source_id)
        for field in ("tissues", "organs", "germ_layers"):
            for value in record.get(field, [])[:20]:
                add_alias(aliases, doc_id, value, field[:-1], source_id)
        for marker in record.get("markers", [])[:alias_marker_limit]:
            add_alias(aliases, doc_id, marker, "marker_gene", source_id)
        chunks.append(
            {
                "chunk_id": f"{source_id}:{slug(doc_id)}",
                "doc_id": doc_id,
                "title": f"{source_id} marker set: {record['cell_type']} ({record['species']})",
                "text": marker_text(record),
                "metadata": {
                    "species": record["species"],
                    "cell_type": record["cell_type"],
                    "cell_type_ontology_term_id": record.get("cell_type_ontology_term_id", ""),
                    "cell_class": record.get("cell_class", ""),
                    "markers": record.get("markers", []),
                    "canonical_markers": record.get("canonical_markers", []),
                    "tissues": record.get("tissues", []),
                    "organs": record.get("organs", []),
                    "data_version": record["data_version"],
                    "source_id": source_id,
                    "source_type": record["source_type"],
                },
            }
        )
    return sorted(aliases.values(), key=lambda row: (row["target_id"], row["alias_type"], row["alias_norm"])), chunks


def ensure_cellmarker_raw(zip_path: Path, raw_path: Path) -> None:
    if raw_path.exists() and raw_path.stat().st_size > 0:
        return
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as archive:
        archive.extractall(raw_path.parent)


def build_cellmarker(args: argparse.Namespace) -> dict[str, Any]:
    source_id = "cellmarker3"
    source_type = "cell_marker_database"
    raw_path = Path(args.cellmarker_raw)
    ensure_cellmarker_raw(Path(args.cellmarker_zip), raw_path)
    data_version = f"CellMarker 3.0 all_cell_marker downloaded {datetime.now(UTC).date().isoformat()}"
    groups: dict[tuple[str, ...], MarkerGroup] = {}
    rows = 0
    with raw_path.open("r", encoding="utf-8", errors="replace", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        for row in reader:
            rows += 1
            species = clean(row.get("species")) or "unknown"
            cell_type = clean(row.get("cell_name")) or clean(row.get("cell_name_class")) or "unknown"
            ontology_id = normalize_ontology_id(row.get("cellontology_id"))
            key = (species, cell_type, ontology_id)
            group = groups.setdefault(
                key,
                MarkerGroup(
                    source_id=source_id,
                    source_type=source_type,
                    species=species,
                    cell_type=cell_type,
                    cell_type_ontology_term_id=ontology_id,
                    cell_class=clean(row.get("cell_name_class")),
                ),
            )
            group.evidence_count += 1
            for attr, column in [
                ("tissues", "tissue_type"),
                ("tissue_ontology_term_ids", "uberon_id"),
                ("diseases", "disease"),
                ("marker_sources", "marker_source"),
                ("methods", "method_details"),
                ("pmids", "pmid"),
                ("years", "year"),
            ]:
                value = normalize_ontology_id(row.get(column)) if column == "uberon_id" else clean(row.get(column))
                if value:
                    getattr(group, attr)[value] += 1
            marker = clean(row.get("marker")) or clean(row.get("symbol"))
            if marker:
                group.markers[marker] += 1
                if clean(row.get("gene_name")) and marker not in group.marker_products:
                    group.marker_products[marker] = clean(row.get("gene_name"))
                if clean(row.get("symbol")) and clean(row.get("symbol")) != marker:
                    group.marker_aliases[marker].add(clean(row.get("symbol")))
    records = sorted_records(groups, data_version, args.marker_limit)
    aliases, chunks = make_outputs(records, source_id, args.alias_marker_limit)
    return write_source_outputs(records, aliases, chunks, args.cellmarker_sets_out, args.cellmarker_aliases_out, args.cellmarker_chunks_out, args.cellmarker_report_out, source_id, source_type, rows, data_version)


def build_panglao(args: argparse.Namespace) -> dict[str, Any]:
    source_id = "panglaodb"
    source_type = "cell_marker_database"
    data_version = "PanglaoDB markers 27 Mar 2020"
    groups: dict[tuple[str, ...], MarkerGroup] = {}
    rows = 0
    skipped_rows = 0
    with gzip.open(args.panglao_raw, "rt", encoding="utf-8", errors="replace", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        for row in reader:
            rows += 1
            species = clean(row.get("species")) or "unknown"
            if species not in {"Mm", "Hs", "Mm Hs"}:
                skipped_rows += 1
                continue
            cell_type = clean(row.get("cell type")) or "unknown"
            key = (species, cell_type)
            group = groups.setdefault(
                key,
                MarkerGroup(source_id=source_id, source_type=source_type, species=species, cell_type=cell_type),
            )
            group.evidence_count += 1
            for attr, column in [("germ_layers", "germ layer"), ("organs", "organ")]:
                value = clean(row.get(column))
                if value:
                    getattr(group, attr)[value] += 1
            marker = clean(row.get("official gene symbol"))
            if marker:
                group.markers[marker] += 1
                if clean(row.get("canonical marker")) == "1":
                    group.canonical_markers[marker] += 1
                if clean(row.get("product description")) and marker not in group.marker_products:
                    group.marker_products[marker] = clean(row.get("product description"))
                for alias in clean(row.get("nicknames")).split("|"):
                    if clean(alias):
                        group.marker_aliases[marker].add(clean(alias))
    records = sorted_records(groups, data_version, args.marker_limit)
    aliases, chunks = make_outputs(records, source_id, args.alias_marker_limit)
    report = write_source_outputs(records, aliases, chunks, args.panglao_sets_out, args.panglao_aliases_out, args.panglao_chunks_out, args.panglao_report_out, source_id, source_type, rows, data_version)
    report["skipped_rows"] = skipped_rows
    Path(args.panglao_report_out).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def write_source_outputs(
    records: list[dict[str, Any]],
    aliases: list[dict[str, Any]],
    chunks: list[dict[str, Any]],
    records_out: str,
    aliases_out: str,
    chunks_out: str,
    report_out: str,
    source_id: str,
    source_type: str,
    raw_rows: int,
    data_version: str,
) -> dict[str, Any]:
    write_jsonl(Path(records_out), records)
    write_jsonl(Path(aliases_out), aliases)
    write_jsonl(Path(chunks_out), chunks)
    report = {
        "source_id": source_id,
        "source_type": source_type,
        "data_version": data_version,
        "raw_rows": raw_rows,
        "marker_sets": len(records),
        "aliases": len(aliases),
        "chunks": len(chunks),
        "records_out": records_out,
        "aliases_out": aliases_out,
        "chunks_out": chunks_out,
    }
    Path(report_out).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def main() -> int:
    args = parse_args()
    reports = [build_cellmarker(args), build_panglao(args)]
    print(json.dumps({"sources": reports}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
