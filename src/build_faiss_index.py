#!/usr/bin/env python3
"""Build a FAISS ANN index aligned to an existing RAG embedding matrix."""

from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np


ROOT = Path(__file__).resolve().parents[1]


def project_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a FAISS index for Cell RAG vectors.")
    parser.add_argument("--embeddings", default="embeddings/rag_qwen3_embedding_8b.npz")
    parser.add_argument("--metadata", default="embeddings/rag_qwen3_embedding_8b.metadata.json")
    parser.add_argument("--output", default="")
    parser.add_argument("--index-type", choices=["ivfflat", "flat"], default="ivfflat")
    parser.add_argument("--nlist", type=int, default=0, help="IVF cluster count. Default: sqrt(vector_count), capped.")
    parser.add_argument("--train-size", type=int, default=50000)
    parser.add_argument("--threads", type=int, default=0)
    parser.add_argument("--seed", type=int, default=13)
    parser.add_argument("--normalize", action="store_true", help="L2-normalize vectors before adding to FAISS.")
    return parser.parse_args()


def load_metadata(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, list):
        raise SystemExit(f"Expected metadata list in {path}")
    return data


def default_nlist(vector_count: int) -> int:
    return min(4096, max(64, int(math.sqrt(max(vector_count, 1)))))


def build_index(args: argparse.Namespace) -> dict[str, Any]:
    try:
        import faiss  # type: ignore[import-not-found]
    except ImportError as exc:
        raise SystemExit("Missing dependency: install faiss-cpu in qwen_env before building the index.") from exc

    if args.threads > 0:
        faiss.omp_set_num_threads(args.threads)

    embeddings_path = project_path(args.embeddings)
    metadata_path = project_path(args.metadata)
    output_path = project_path(args.output) if args.output else embeddings_path.with_suffix(".ivfflat.faiss")
    manifest_path = output_path.with_suffix(output_path.suffix + ".json")

    matrix = np.load(embeddings_path)["embeddings"].astype(np.float32)
    matrix = np.ascontiguousarray(matrix)
    metadata = load_metadata(metadata_path)
    if len(matrix) != len(metadata):
        raise SystemExit(f"Embedding rows ({len(matrix)}) do not match metadata rows ({len(metadata)}).")

    if args.normalize:
        faiss.normalize_L2(matrix)

    vector_count, dimensions = matrix.shape
    if args.index_type == "flat":
        index = faiss.IndexFlatIP(dimensions)
        train_size = 0
        nlist = 0
    else:
        nlist = args.nlist or default_nlist(vector_count)
        nlist = min(nlist, vector_count)
        quantizer = faiss.IndexFlatIP(dimensions)
        index = faiss.IndexIVFFlat(quantizer, dimensions, nlist, faiss.METRIC_INNER_PRODUCT)
        rng = np.random.default_rng(args.seed)
        train_size = min(max(args.train_size, nlist), vector_count)
        train_indices = rng.choice(vector_count, size=train_size, replace=False)
        training_matrix = np.ascontiguousarray(matrix[train_indices])
        index.train(training_matrix)

    index.add(matrix)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    faiss.write_index(index, str(output_path))

    manifest = {
        "created_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "index_path": str(output_path.relative_to(ROOT) if output_path.is_relative_to(ROOT) else output_path),
        "embeddings_path": str(embeddings_path.relative_to(ROOT) if embeddings_path.is_relative_to(ROOT) else embeddings_path),
        "metadata_path": str(metadata_path.relative_to(ROOT) if metadata_path.is_relative_to(ROOT) else metadata_path),
        "index_type": args.index_type,
        "metric": "inner_product",
        "vectors": int(vector_count),
        "dimensions": int(dimensions),
        "nlist": int(nlist),
        "train_size": int(train_size),
        "normalized_on_build": bool(args.normalize),
        "faiss_ntotal": int(index.ntotal),
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def main() -> int:
    manifest = build_index(parse_args())
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
