#!/usr/bin/env python3
"""Neural vector search over Qwen3-embedded Cell Ontology chunks."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import torch
from transformers import AutoModel, AutoTokenizer


DEFAULT_QUERY_TASK = (
    "Given a single-cell biology question, retrieve relevant Cell Ontology "
    "passages that answer the question"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Search Qwen vector embeddings.")
    parser.add_argument("query", help="Question or search query.")
    parser.add_argument("--model", default="models/Qwen3-Embedding-8B", help="Local Qwen model path.")
    parser.add_argument("--embeddings", default="embeddings/cl_qwen3_embedding_8b.npz")
    parser.add_argument("--metadata", default="embeddings/cl_qwen3_embedding_8b.metadata.json")
    parser.add_argument("--chunks", default="chunks/cl_chunks.jsonl")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--max-length", type=int, default=2048)
    parser.add_argument("--task", default=DEFAULT_QUERY_TASK)
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def load_jsonl(path: Path) -> list[dict[str, object]]:
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def last_token_pool(last_hidden_state: torch.Tensor, attention_mask: torch.Tensor) -> torch.Tensor:
    batch_size = last_hidden_state.shape[0]
    lengths = attention_mask.sum(dim=1) - 1
    pooled = last_hidden_state[torch.arange(batch_size, device=last_hidden_state.device), lengths]
    return torch.nn.functional.normalize(pooled, p=2, dim=1)


def format_query(task: str, query: str) -> str:
    return f"Instruct: {task}\nQuery: {query}"


def embed_query(query: str, task: str, model_path: Path, max_length: int) -> np.ndarray:
    if not torch.cuda.is_available():
        raise SystemExit("CUDA is not available; run this on the GPU CCI.")

    tokenizer = AutoTokenizer.from_pretrained(model_path, local_files_only=True, trust_remote_code=True)
    model = AutoModel.from_pretrained(
        model_path,
        local_files_only=True,
        trust_remote_code=True,
        dtype=torch.float16,
        device_map="cuda",
    )
    model.eval()

    inputs = tokenizer(
        format_query(task, query),
        return_tensors="pt",
        truncation=True,
        max_length=max_length,
    ).to(model.device)
    with torch.inference_mode():
        outputs = model(**inputs)
        embedding = last_token_pool(outputs.last_hidden_state, inputs["attention_mask"])
    return embedding.float().cpu().numpy()[0]


def main() -> int:
    args = parse_args()
    embedding_matrix = np.load(args.embeddings)["embeddings"].astype(np.float32)
    metadata = json.loads(Path(args.metadata).read_text(encoding="utf-8"))
    chunks = {str(row.get("doc_id")): row for row in load_jsonl(Path(args.chunks))}

    query_vector = embed_query(args.query, args.task, Path(args.model), args.max_length)
    scores = embedding_matrix @ query_vector
    top_indices = np.argsort(-scores)[: args.top_k]

    results = []
    for rank, index in enumerate(top_indices, start=1):
        meta = metadata[int(index)]
        doc_id = str(meta.get("doc_id"))
        chunk = chunks.get(doc_id, {})
        results.append(
            {
                "rank": rank,
                "score": round(float(scores[int(index)]), 6),
                "doc_id": doc_id,
                "title": meta.get("title"),
                "reason": "qwen3 embedding cosine match",
                "text": chunk.get("text"),
            }
        )

    if args.json:
        print(json.dumps({"query": args.query, "results": results}, ensure_ascii=False, indent=2))
        return 0

    print(f"Query: {args.query}")
    print("Mode: qwen-vector")
    for result in results:
        print("\n" + "=" * 80)
        print(f"Rank {result['rank']} | score={result['score']} | {result['doc_id']} | {result['title']}")
        print(f"Reason: {result['reason']}")
        print("-" * 80)
        print(result["text"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
