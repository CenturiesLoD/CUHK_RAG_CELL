#!/usr/bin/env python3
"""Embed Cell Ontology chunks with Qwen3-Embedding.

The model's sentence-transformers metadata specifies last-token pooling plus
normalization. Query text should receive the instruction prefix at search time;
document chunks are embedded as plain chunk text.

This script is incremental: if an existing embedding file and manifest match a
chunk's stable ID and text hash, the old vector is reused instead of recomputed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Iterable

import numpy as np
import torch
from tqdm import tqdm
from transformers import AutoModel, AutoTokenizer


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build Qwen embeddings for chunk JSONL.")
    parser.add_argument("--chunks", default="chunks/cl_chunks.jsonl", help="Input chunk JSONL path.")
    parser.add_argument("--model", default="models/Qwen3-Embedding-8B", help="Local Qwen model path.")
    parser.add_argument("--out-dir", default="embeddings", help="Output directory.")
    parser.add_argument("--name", default="cl_qwen3_embedding_8b", help="Output filename stem.")
    parser.add_argument("--batch-size", type=int, default=8, help="Embedding batch size.")
    parser.add_argument("--max-length", type=int, default=2048, help="Tokenizer max sequence length.")
    parser.add_argument("--limit", type=int, default=0, help="Only embed first N chunks; 0 means all.")
    parser.add_argument("--dtype", choices=("float16", "bfloat16", "float32"), default="float16")
    parser.add_argument("--force", action="store_true", help="Re-embed every chunk even if reusable vectors exist.")
    return parser.parse_args()


def load_jsonl(path: Path, limit: int = 0) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
                if limit and len(rows) >= limit:
                    break
    return rows


def text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def stable_chunk_id(row: dict[str, object], index: int) -> str:
    chunk_id = str(row.get("chunk_id") or "").strip()
    if chunk_id:
        return chunk_id
    metadata = row.get("metadata", {}) if isinstance(row.get("metadata"), dict) else {}
    source_id = str(metadata.get("source_id") or "unknown_source")
    doc_id = str(row.get("doc_id") or f"row_{index}")
    return f"{source_id}:{doc_id}:{index}"


def batched(rows: list[dict[str, object]], batch_size: int) -> Iterable[list[dict[str, object]]]:
    for start in range(0, len(rows), batch_size):
        yield rows[start : start + batch_size]


def torch_dtype(name: str) -> torch.dtype:
    if name == "bfloat16":
        return torch.bfloat16
    if name == "float32":
        return torch.float32
    return torch.float16


def last_token_pool(last_hidden_state: torch.Tensor, attention_mask: torch.Tensor) -> torch.Tensor:
    """Pool the final non-padding token for each sequence."""
    batch_size = last_hidden_state.shape[0]
    lengths = attention_mask.sum(dim=1) - 1
    pooled = last_hidden_state[torch.arange(batch_size, device=last_hidden_state.device), lengths]
    return torch.nn.functional.normalize(pooled, p=2, dim=1)


def embed_texts(texts: list[str], tokenizer, model, max_length: int) -> np.ndarray:
    inputs = tokenizer(
        texts,
        padding=True,
        truncation=True,
        max_length=max_length,
        return_tensors="pt",
    ).to(model.device)
    with torch.inference_mode():
        outputs = model(**inputs)
        embeddings = last_token_pool(outputs.last_hidden_state, inputs["attention_mask"])
    return embeddings.float().cpu().numpy()


def load_reusable_vectors(
    npz_path: Path,
    meta_path: Path,
    manifest_path: Path,
    current_hashes: dict[str, str],
    force: bool,
) -> dict[str, np.ndarray]:
    if force or not npz_path.exists() or not meta_path.exists():
        return {}

    matrix = np.load(npz_path)["embeddings"].astype(np.float32)
    metadata = json.loads(meta_path.read_text(encoding="utf-8"))
    if len(metadata) != matrix.shape[0]:
        return {}

    hashes_by_id: dict[str, str] = {}
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for entry in manifest.get("entries", []):
            chunk_id = str(entry.get("chunk_id") or "")
            chunk_hash = str(entry.get("text_hash") or "")
            if chunk_id and chunk_hash:
                hashes_by_id[chunk_id] = chunk_hash
    else:
        hashes_by_id = dict(current_hashes)

    reusable: dict[str, np.ndarray] = {}
    for index, meta in enumerate(metadata):
        chunk_id = str(meta.get("chunk_id") or "")
        if chunk_id and hashes_by_id.get(chunk_id) == current_hashes.get(chunk_id):
            reusable[chunk_id] = matrix[index]
    return reusable


def main() -> int:
    args = parse_args()
    chunks_path = Path(args.chunks)
    model_path = Path(args.model)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    npz_path = out_dir / f"{args.name}.npz"
    meta_path = out_dir / f"{args.name}.metadata.json"
    summary_path = out_dir / f"{args.name}.summary.json"
    manifest_path = out_dir / f"{args.name}.manifest.json"

    rows = load_jsonl(chunks_path, args.limit)
    if not rows:
        raise SystemExit(f"No chunks found in {chunks_path}")

    prepared_rows = []
    current_hashes: dict[str, str] = {}
    seen_chunk_ids: set[str] = set()
    for index, row in enumerate(rows):
        chunk_id = stable_chunk_id(row, index)
        if chunk_id in seen_chunk_ids:
            raise SystemExit(f"Duplicate chunk_id found: {chunk_id}")
        seen_chunk_ids.add(chunk_id)
        chunk_hash = text_hash(str(row.get("text", "")))
        current_hashes[chunk_id] = chunk_hash
        prepared_rows.append((chunk_id, chunk_hash, row))

    if not torch.cuda.is_available():
        raise SystemExit("CUDA is not available; run this on the GPU CCI.")

    print(f"chunks={len(rows)}")
    print(f"model={model_path.resolve()}")
    print("device=cuda")
    print(f"dtype={args.dtype}")

    reusable = load_reusable_vectors(npz_path, meta_path, manifest_path, current_hashes, args.force)
    to_embed = [(chunk_id, chunk_hash, row) for chunk_id, chunk_hash, row in prepared_rows if chunk_id not in reusable]
    print(f"reused={len(prepared_rows) - len(to_embed)}")
    print(f"to_embed={len(to_embed)}")

    tokenizer = None
    model = None
    if to_embed:
        tokenizer = AutoTokenizer.from_pretrained(model_path, local_files_only=True, trust_remote_code=True)
        model = AutoModel.from_pretrained(
            model_path,
            local_files_only=True,
            trust_remote_code=True,
            dtype=torch_dtype(args.dtype),
            device_map="cuda",
        )
        model.eval()

    new_vectors: dict[str, np.ndarray] = {}
    embed_rows = [{"_chunk_id": chunk_id, **row} for chunk_id, _, row in to_embed]
    for batch in tqdm(list(batched(embed_rows, args.batch_size)), desc="embedding"):
        if tokenizer is None or model is None:
            raise RuntimeError("Tokenizer/model were not loaded for chunks requiring embeddings.")
        texts = [str(row.get("text", "")) for row in batch]
        batch_vectors = embed_texts(texts, tokenizer, model, args.max_length)
        for row, vector in zip(batch, batch_vectors):
            new_vectors[str(row["_chunk_id"])] = vector

    vectors: list[np.ndarray] = []
    metadata: list[dict[str, object]] = []
    manifest_entries: list[dict[str, object]] = []
    for row_index, (chunk_id, chunk_hash, row) in enumerate(prepared_rows):
        vector = new_vectors.get(chunk_id)
        if vector is None:
            vector = reusable.get(chunk_id)
        if vector is None:
            raise RuntimeError(f"Missing vector for chunk_id={chunk_id}")
        vectors.append(np.asarray(vector, dtype=np.float32)[None, :])
        metadata.append(
            {
                "chunk_id": chunk_id,
                "doc_id": row.get("doc_id"),
                "title": row.get("title"),
                "metadata": row.get("metadata", {}),
            }
        )
        manifest_entries.append(
            {
                "row_index": row_index,
                "chunk_id": chunk_id,
                "doc_id": row.get("doc_id"),
                "title": row.get("title"),
                "text_hash": chunk_hash,
                "status": "embedded" if chunk_id in new_vectors else "reused",
            }
        )

    matrix = np.vstack(vectors).astype(np.float32)
    np.savez_compressed(npz_path, embeddings=matrix)
    meta_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "chunks_path": str(chunks_path),
                "model": str(model_path),
                "pooling": "last_token",
                "normalized": True,
                "embedding_dimension": int(matrix.shape[1]),
                "npz_path": str(npz_path),
                "metadata_path": str(meta_path),
                "entries": manifest_entries,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    summary_path.write_text(
        json.dumps(
            {
                "chunks": len(rows),
                "dimension": int(matrix.shape[1]),
                "model": str(model_path),
                "pooling": "last_token",
                "normalized": True,
                "dtype_saved": "float32",
                "chunks_path": str(chunks_path),
                "npz_path": str(npz_path),
                "metadata_path": str(meta_path),
                "manifest_path": str(manifest_path),
                "reused": len(prepared_rows) - len(to_embed),
                "embedded": len(to_embed),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"saved_embeddings={npz_path}")
    print(f"saved_metadata={meta_path}")
    print(f"saved_manifest={manifest_path}")
    print(f"saved_summary={summary_path}")
    print(f"shape={matrix.shape}")
    print(f"first_norm={float(np.linalg.norm(matrix[0])):.6f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
