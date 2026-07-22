#!/usr/bin/env python3
"""Hybrid Cell Ontology retrieval: exact aliases + BM25 + Qwen vectors."""

from __future__ import annotations

import argparse
import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable

import numpy as np
import torch
from transformers import AutoModel, AutoTokenizer

TOKEN_RE = re.compile(r"[A-Za-z0-9]+(?::[A-Za-z0-9]+)?")
SPACE_RE = re.compile(r"\s+")
QUERY_PREFIX_RE = re.compile(
    r"^(what|which|who|where|when|why|how)\s+(is|are|was|were|do|does|did|can|could|should|would)\s+",
    re.IGNORECASE,
)
ARTICLE_RE = re.compile(r"^(a|an|the)\s+", re.IGNORECASE)
DEFAULT_QUERY_TASK = (
    "Given a single-cell biology question, retrieve relevant Cell Ontology "
    "passages that answer the question"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Hybrid Cell Ontology search with BM25 and Qwen vectors.")
    parser.add_argument("query", help="Question or search query.")
    parser.add_argument("--chunks", default="chunks/cl_chunks.jsonl")
    parser.add_argument("--aliases", default="processed/cl_aliases.jsonl")
    parser.add_argument("--model", default="models/Qwen3-Embedding-8B")
    parser.add_argument("--embeddings", default="embeddings/cl_qwen3_embedding_8b.npz")
    parser.add_argument("--metadata", default="embeddings/cl_qwen3_embedding_8b.metadata.json")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--bm25-weight", type=float, default=0.45)
    parser.add_argument("--vector-weight", type=float, default=0.55)
    parser.add_argument("--max-length", type=int, default=2048)
    parser.add_argument("--task", default=DEFAULT_QUERY_TASK)
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def normalize(text: str) -> str:
    return SPACE_RE.sub(" ", text.strip().casefold())


def tokenize(text: str) -> list[str]:
    return [token.casefold() for token in TOKEN_RE.findall(text)]


def load_jsonl(path: Path) -> list[dict[str, object]]:
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def normalize_scores(scores: dict[str, float]) -> dict[str, float]:
    if not scores:
        return {}
    max_score = max(scores.values())
    if max_score <= 0:
        return {key: 0.0 for key in scores}
    return {key: value / max_score for key, value in scores.items()}


def build_alias_index(aliases: Iterable[dict[str, object]]) -> dict[str, list[dict[str, object]]]:
    index: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in aliases:
        alias_norm = str(row.get("alias_norm") or normalize(str(row.get("alias", ""))))
        if alias_norm:
            index[alias_norm].append(row)
    return index


def exact_alias_matches(query: str, alias_index: dict[str, list[dict[str, object]]]) -> list[dict[str, object]]:
    query_norm = normalize(query)
    candidates = {query_norm}
    stripped = query_norm.strip(" ?!.:,;()[]{}\"'")
    candidates.add(stripped)
    stripped = QUERY_PREFIX_RE.sub("", stripped).strip()
    stripped = ARTICLE_RE.sub("", stripped).strip()
    stripped = stripped.strip(" ?!.:,;()[]{}\"'")
    if stripped:
        candidates.add(stripped)

    query_tokens = tokenize(query)
    for start in range(len(query_tokens)):
        for end in range(start + 1, min(len(query_tokens), start + 5) + 1):
            phrase = " ".join(query_tokens[start:end])
            if phrase:
                candidates.add(phrase)

    matches = []
    for candidate in candidates:
        matches.extend(alias_index.get(candidate, []))
        compact = candidate.replace(" ", "")
        if compact.startswith("cl:"):
            matches.extend(alias_index.get(compact, []))

    seen: set[tuple[str, str]] = set()
    unique: list[dict[str, object]] = []
    for row in matches:
        key = (str(row.get("target_id")), str(row.get("alias_type")))
        if key not in seen:
            unique.append(row)
            seen.add(key)
    return unique


def format_alias_reason(row: dict[str, object]) -> str:
    alias_type = str(row.get("alias_type") or "alias")
    alias = row.get("alias")
    if alias_type.startswith("synonym:"):
        return f"exact synonym match: {alias}"
    if alias_type == "id":
        return f"exact id match: {alias}"
    if alias_type == "name":
        return f"exact name match: {alias}"
    if alias_type == "alt_id":
        return f"exact alternate id match: {alias}"
    return f"exact {alias_type} match: {alias}"


def build_text_index(chunks: list[dict[str, object]]) -> tuple[list[Counter[str]], Counter[str], float]:
    token_counts: list[Counter[str]] = []
    doc_freq: Counter[str] = Counter()
    total_length = 0
    for chunk in chunks:
        counts = Counter(tokenize(str(chunk.get("text", ""))))
        token_counts.append(counts)
        total_length += sum(counts.values())
        doc_freq.update(counts.keys())
    avg_doc_length = total_length / len(chunks) if chunks else 0.0
    return token_counts, doc_freq, avg_doc_length


def phrase_boost(query_norm: str, chunk: dict[str, object]) -> float:
    if not query_norm:
        return 0.0
    title = normalize(str(chunk.get("title", "")))
    text = normalize(str(chunk.get("text", "")))
    metadata = chunk.get("metadata", {}) if isinstance(chunk.get("metadata"), dict) else {}
    ontology_id = normalize(str(metadata.get("ontology_id", "")))
    if query_norm == title or query_norm == ontology_id:
        return 100.0
    if query_norm in title:
        return 20.0
    if query_norm in text:
        return 12.0
    return 0.0


def bm25_scores(
    query: str,
    chunks: list[dict[str, object]],
    token_counts: list[Counter[str]],
    doc_freq: Counter[str],
    avg_doc_length: float,
) -> dict[str, float]:
    query_tokens = Counter(tokenize(query))
    if not query_tokens:
        return {}
    total_docs = max(len(chunks), 1)
    k1 = 1.5
    b = 0.75
    query_norm = normalize(query)
    scores: dict[str, float] = {}
    for chunk, counts in zip(chunks, token_counts):
        doc_length = sum(counts.values()) or 1
        score = 0.0
        for token, q_count in query_tokens.items():
            tf = counts.get(token, 0)
            if not tf:
                continue
            idf = math.log(1 + (total_docs - doc_freq[token] + 0.5) / (doc_freq[token] + 0.5))
            denominator = tf + k1 * (1 - b + b * doc_length / max(avg_doc_length, 1.0))
            score += idf * ((tf * (k1 + 1)) / denominator) * q_count
        score += phrase_boost(query_norm, chunk)
        if score > 0:
            scores[str(chunk.get("doc_id"))] = score
    return scores


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


def vector_scores(query_vector: np.ndarray, embedding_matrix: np.ndarray, metadata: list[dict[str, object]]) -> dict[str, float]:
    scores = embedding_matrix @ query_vector
    result: dict[str, float] = {}
    for index, score in enumerate(scores):
        doc_id = str(metadata[index].get("doc_id"))
        result[doc_id] = float(score)
    return result


def rank_results(args: argparse.Namespace) -> list[dict[str, object]]:
    chunks = load_jsonl(Path(args.chunks))
    aliases = load_jsonl(Path(args.aliases))
    chunk_by_id = {str(chunk.get("doc_id")): chunk for chunk in chunks}
    alias_index = build_alias_index(aliases)

    token_counts, doc_freq, avg_doc_length = build_text_index(chunks)
    bm25_raw = bm25_scores(args.query, chunks, token_counts, doc_freq, avg_doc_length)

    embedding_matrix = np.load(args.embeddings)["embeddings"].astype(np.float32)
    vector_metadata = json.loads(Path(args.metadata).read_text(encoding="utf-8"))
    query_vector = embed_query(args.query, args.task, Path(args.model), args.max_length)
    vector_raw = vector_scores(query_vector, embedding_matrix, vector_metadata)

    bm25_norm = normalize_scores(bm25_raw)
    vector_norm = normalize_scores(vector_raw)
    scores: dict[str, float] = {}
    reasons: dict[str, list[str]] = defaultdict(list)
    for doc_id in set(bm25_norm) | set(vector_norm):
        scores[doc_id] = args.bm25_weight * bm25_norm.get(doc_id, 0.0) + args.vector_weight * vector_norm.get(doc_id, 0.0)
        if doc_id in bm25_raw:
            reasons[doc_id].append("bm25 lexical match")
        if doc_id in vector_raw:
            reasons[doc_id].append("qwen3 vector match")

    for row in exact_alias_matches(args.query, alias_index):
        target_id = str(row.get("target_id"))
        if target_id in chunk_by_id:
            scores[target_id] = scores.get(target_id, 0.0) + 1000.0
            reasons[target_id].insert(0, format_alias_reason(row))

    ranked_ids = sorted(scores, key=lambda doc_id: scores[doc_id], reverse=True)[: args.top_k]
    results: list[dict[str, object]] = []
    for rank, doc_id in enumerate(ranked_ids, start=1):
        chunk = chunk_by_id[doc_id]
        metadata = chunk.get("metadata", {}) if isinstance(chunk.get("metadata"), dict) else {}
        results.append(
            {
                "rank": rank,
                "score": round(scores[doc_id], 6),
                "bm25_score": round(bm25_raw.get(doc_id, 0.0), 6),
                "bm25_norm": round(bm25_norm.get(doc_id, 0.0), 6),
                "vector_score": round(vector_raw.get(doc_id, 0.0), 6),
                "vector_norm": round(vector_norm.get(doc_id, 0.0), 6),
                "doc_id": doc_id,
                "title": chunk.get("title"),
                "source_id": metadata.get("source_id"),
                "data_version": metadata.get("data_version"),
                "reasons": reasons.get(doc_id, ["hybrid match"]),
                "text": chunk.get("text"),
            }
        )
    return results


def print_results(query: str, results: list[dict[str, object]]) -> None:
    print(f"Query: {query}")
    print("Mode: hybrid-qwen")
    if not results:
        print("No results found.")
        return
    for result in results:
        print("\n" + "=" * 80)
        print(f"Rank {result['rank']} | score={result['score']} | {result['doc_id']} | {result['title']}")
        print(
            "Signals: "
            f"bm25={result['bm25_score']} norm={result['bm25_norm']} | "
            f"qwen={result['vector_score']} norm={result['vector_norm']}"
        )
        print(f"Reason: {'; '.join(str(reason) for reason in result['reasons'])}")
        print("-" * 80)
        print(result["text"])


def main() -> int:
    args = parse_args()
    results = rank_results(args)
    if args.json:
        print(json.dumps({"query": args.query, "results": results}, ensure_ascii=False, indent=2))
    else:
        print_results(args.query, results)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
