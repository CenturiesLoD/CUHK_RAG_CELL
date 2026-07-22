#!/usr/bin/env python3
"""Build Cell Ontology terms, aliases, and RAG chunks from a CL OBO file."""

from __future__ import annotations

import argparse
import json
import re
import urllib.request
from pathlib import Path
from typing import Any


DEFAULT_SOURCE_URL = "http://purl.obolibrary.org/obo/cl.obo"
DEFAULT_SOURCE_ID = "cell_ontology_cl_obo"
DEFAULT_SOURCE_TYPE = "cell_ontology"
QUOTE_RE = re.compile(r'"([^"]+)"')
SPACE_RE = re.compile(r"\s+")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build Cell Ontology RAG files from OBO.")
    parser.add_argument("--obo", help="Path to a local cl.obo file.")
    parser.add_argument("--source-url", default=DEFAULT_SOURCE_URL)
    parser.add_argument("--raw-out", default="raw/cl.obo")
    parser.add_argument("--chunks-out", default="chunks/cl_chunks.jsonl")
    parser.add_argument("--terms-out", default="processed/cl_terms.jsonl")
    parser.add_argument("--aliases-out", default="processed/cl_aliases.jsonl")
    parser.add_argument("--data-version", default="", help="Override data version label.")
    parser.add_argument("--source-id", default=DEFAULT_SOURCE_ID)
    parser.add_argument("--source-type", default=DEFAULT_SOURCE_TYPE)
    return parser.parse_args()


def normalize(text: str) -> str:
    return SPACE_RE.sub(" ", text.strip().casefold())


def jsonl_write(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def load_obo(args: argparse.Namespace) -> tuple[str, str]:
    if args.obo:
        path = Path(args.obo)
        return path.read_text(encoding="utf-8"), str(path)

    raw_path = Path(args.raw_out)
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(args.source_url, timeout=120) as response:
        text = response.read().decode("utf-8")
    raw_path.write_text(text, encoding="utf-8")
    return text, args.source_url


def parse_header(lines: list[str]) -> dict[str, str]:
    header: dict[str, str] = {}
    for line in lines:
        if ": " not in line:
            continue
        key, value = line.split(": ", 1)
        if key in {"data-version", "date", "format-version"}:
            header[key] = value
    return header


def parse_obo(text: str) -> tuple[dict[str, str], list[dict[str, Any]]]:
    header_lines: list[str] = []
    terms: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    section: str | None = None

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("!"):
            continue
        if line.startswith("[") and line.endswith("]"):
            if section is None:
                header = parse_header(header_lines)
            if current and section == "Term":
                terms.append(current)
            section = line.strip("[]")
            current = {} if section == "Term" else None
            continue

        if section is None:
            header_lines.append(line)
            continue
        if section != "Term" or current is None or ": " not in line:
            continue

        key, value = line.split(": ", 1)
        if key in {"id", "name"}:
            current[key] = value
        elif key == "def":
            match = QUOTE_RE.search(value)
            current["definition"] = match.group(1) if match else value
        elif key == "synonym":
            match = QUOTE_RE.search(value)
            if match:
                current.setdefault("synonyms", []).append(match.group(1))
        elif key == "alt_id":
            current.setdefault("alt_ids", []).append(value)
        elif key == "xref":
            current.setdefault("xrefs", []).append(value)
        elif key == "is_a":
            current.setdefault("parents", []).append(value)
        elif key == "relationship":
            current.setdefault("relationships", []).append(value)
        elif key == "is_obsolete":
            current["is_obsolete"] = value.lower() == "true"

    if current and section == "Term":
        terms.append(current)

    return locals().get("header", parse_header(header_lines)), terms


def clean_ref(value: str) -> str:
    return value.strip()


def build_text(term: dict[str, Any]) -> str:
    lines = [
        f"Cell Ontology term: {term['name']}",
        f"ID: {term['ontology_id']}",
    ]
    if term.get("definition"):
        lines.append(f"Definition: {term['definition']}")
    if term.get("synonyms"):
        lines.append("Synonyms: " + "; ".join(term["synonyms"]))
    if term.get("alt_ids"):
        lines.append("Alternate IDs: " + "; ".join(term["alt_ids"]))
    if term.get("parents"):
        lines.append("Parent classes: " + "; ".join(term["parents"]))
    if term.get("relationships"):
        lines.append("Relationships: " + "; ".join(term["relationships"]))
    if term.get("xrefs"):
        lines.append("External references: " + "; ".join(term["xrefs"]))
    return "\n".join(lines)


def prepare_rows(raw_terms: list[dict[str, Any]], args: argparse.Namespace, data_version: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    terms: list[dict[str, Any]] = []
    aliases: list[dict[str, Any]] = []
    chunks: list[dict[str, Any]] = []

    for raw in raw_terms:
        ontology_id = str(raw.get("id", "")).strip()
        name = str(raw.get("name", "")).strip()
        if not ontology_id.startswith("CL:") or not name or raw.get("is_obsolete"):
            continue

        term = {
            "ontology_id": ontology_id,
            "name": name,
            "definition": str(raw.get("definition", "")).strip(),
            "synonyms": sorted(set(str(value).strip() for value in raw.get("synonyms", []) if str(value).strip())),
            "alt_ids": sorted(set(str(value).strip() for value in raw.get("alt_ids", []) if str(value).strip())),
            "parents": [clean_ref(value) for value in raw.get("parents", [])],
            "relationships": [clean_ref(value) for value in raw.get("relationships", [])],
            "xrefs": [clean_ref(value) for value in raw.get("xrefs", [])],
            "data_version": data_version,
            "source_id": args.source_id,
            "source_type": args.source_type,
        }
        terms.append(term)

        for alias_type, values in (
            ("id", [ontology_id, ontology_id.replace(":", "_"), ontology_id.replace(":", "")]),
            ("name", [name]),
            ("alt_id", term["alt_ids"]),
            ("synonym:obo", term["synonyms"]),
        ):
            for alias in values:
                aliases.append(
                    {
                        "target_id": ontology_id,
                        "alias": alias,
                        "alias_norm": normalize(alias),
                        "alias_type": alias_type,
                        "source_id": args.source_id,
                    }
                )

        text = build_text(term)
        chunks.append(
            {
                "chunk_id": "cl:" + ontology_id.replace(":", "_"),
                "doc_id": ontology_id,
                "title": name,
                "text": text,
                "metadata": {
                    "ontology_id": ontology_id,
                    "name": name,
                    "synonyms": term["synonyms"],
                    "alt_ids": term["alt_ids"],
                    "xrefs": term["xrefs"],
                    "data_version": data_version,
                    "source_id": args.source_id,
                    "source_type": args.source_type,
                },
            }
        )

    aliases = list({(row["target_id"], row["alias_type"], row["alias_norm"]): row for row in aliases}.values())
    terms.sort(key=lambda row: row["ontology_id"])
    aliases.sort(key=lambda row: (row["target_id"], row["alias_type"], row["alias_norm"]))
    chunks.sort(key=lambda row: row["doc_id"])
    return terms, aliases, chunks


def main() -> int:
    args = parse_args()
    text, source = load_obo(args)
    header, raw_terms = parse_obo(text)
    data_version = args.data_version or header.get("data-version") or source
    terms, aliases, chunks = prepare_rows(raw_terms, args, data_version)

    jsonl_write(Path(args.terms_out), terms)
    jsonl_write(Path(args.aliases_out), aliases)
    jsonl_write(Path(args.chunks_out), chunks)

    print(json.dumps(
        {
            "source": source,
            "data_version": data_version,
            "terms": len(terms),
            "aliases": len(aliases),
            "chunks": len(chunks),
            "terms_out": args.terms_out,
            "aliases_out": args.aliases_out,
            "chunks_out": args.chunks_out,
        },
        indent=2,
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
