#!/usr/bin/env python3
"""Convert generic JSONL documents into RAG chunks and alias rows."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


SPACE_RE = re.compile(r"\s+")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build RAG chunks from JSONL documents.")
    parser.add_argument("--input", required=True, help="JSONL with doc_id/title/text and optional aliases/metadata.")
    parser.add_argument("--chunks-out", default="chunks/extra_chunks.jsonl")
    parser.add_argument("--aliases-out", default="processed/extra_aliases.jsonl")
    parser.add_argument("--source-id", default="user_jsonl")
    parser.add_argument("--source-type", default="text")
    parser.add_argument("--data-version", default="local")
    parser.add_argument("--chunk-chars", type=int, default=2200)
    parser.add_argument("--overlap-chars", type=int, default=250)
    return parser.parse_args()


def normalize(text: str) -> str:
    return SPACE_RE.sub(" ", text.strip().casefold())


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def chunk_text(text: str, chunk_chars: int, overlap_chars: int) -> list[str]:
    text = SPACE_RE.sub(" ", text).strip()
    if not text:
        return []
    if len(text) <= chunk_chars:
        return [text]

    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(len(text), start + chunk_chars)
        if end < len(text):
            boundary = max(text.rfind(". ", start, end), text.rfind("\n", start, end))
            if boundary > start + chunk_chars * 0.55:
                end = boundary + 1
        chunks.append(text[start:end].strip())
        if end >= len(text):
            break
        start = max(end - overlap_chars, start + 1)
    return chunks


def main() -> int:
    args = parse_args()
    docs = load_jsonl(Path(args.input))
    chunks: list[dict[str, Any]] = []
    aliases: list[dict[str, Any]] = []

    for index, doc in enumerate(docs):
        doc_id = str(doc.get("doc_id") or f"{args.source_id}:{index}")
        title = str(doc.get("title") or doc_id)
        text = str(doc.get("text") or "")
        metadata = dict(doc.get("metadata") or {})
        metadata.setdefault("source_id", doc.get("source_id") or args.source_id)
        metadata.setdefault("source_type", doc.get("source_type") or args.source_type)
        metadata.setdefault("data_version", doc.get("data_version") or args.data_version)

        for chunk_index, chunk in enumerate(chunk_text(text, args.chunk_chars, args.overlap_chars)):
            chunk_id = f"{doc_id}:chunk:{chunk_index}".replace(" ", "_")
            chunks.append(
                {
                    "chunk_id": chunk_id,
                    "doc_id": doc_id,
                    "title": title,
                    "text": f"{title}\n{chunk}",
                    "metadata": {**metadata, "chunk_index": chunk_index},
                }
            )

        for alias_type, values in (
            ("id", [doc_id]),
            ("title", [title]),
            ("alias", doc.get("aliases", [])),
        ):
            for alias in values:
                alias = str(alias).strip()
                if not alias:
                    continue
                aliases.append(
                    {
                        "target_id": doc_id,
                        "alias": alias,
                        "alias_norm": normalize(alias),
                        "alias_type": alias_type,
                        "source_id": metadata["source_id"],
                    }
                )

    aliases = list({(row["target_id"], row["alias_type"], row["alias_norm"]): row for row in aliases}.values())
    write_jsonl(Path(args.chunks_out), chunks)
    write_jsonl(Path(args.aliases_out), aliases)
    print(json.dumps({"documents": len(docs), "chunks": len(chunks), "aliases": len(aliases)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
