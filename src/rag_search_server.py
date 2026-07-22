#!/usr/bin/env python3
"""Persistent FastAPI service for Cell Ontology RAG search and answers."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import json
import numpy as np
import requests
import torch
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from transformers import AutoModel, AutoModelForSequenceClassification, AutoTokenizer

from search_hybrid_qwen import (
    DEFAULT_QUERY_TASK,
    bm25_scores,
    build_alias_index,
    build_text_index,
    exact_alias_matches,
    format_alias_reason,
    format_query,
    last_token_pool,
    load_jsonl,
    normalize,
    normalize_scores,
    tokenize,
    vector_scores,
)

ROOT = Path(__file__).resolve().parents[1]

DEFAULT_BASE_URL = "http://127.0.0.1:8000/v1"
DEFAULT_MODEL = "qwen3-32b"
THINK_BLOCK_RE = re.compile(r"^\s*<think>.*?</think>\s*", re.DOTALL)
CITATION_RE = re.compile(r"\[([^\[\]\n]+)\]")
DANGLING_CITATION_RE = re.compile(r"\s*\[[^\]\n]*$")
SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
QUERY_PREFIX_RE = re.compile(
    r"^(what|which|who|where|when|why|how)\s+(is|are|was|were|do|does|did|can|could|should|would)\s+",
    re.IGNORECASE,
)
ARTICLE_RE = re.compile(r"^(a|an|the)\s+", re.IGNORECASE)
UNIPROT_ACCESSION_RE = re.compile(r"\b(?:[OPQ][0-9][A-Z0-9]{3}[0-9]|[A-NR-Z][0-9](?:[A-Z][A-Z0-9]{2}[0-9]){1,2})\b")
GENE_SYMBOL_RE = re.compile(r"^[A-Z0-9][A-Z0-9-]{1,14}$")
SOURCE_EXACT_MATCH_WEIGHT = 2.0
SOURCE_SOFT_MATCH_WEIGHT = 0.18
SOURCE_TYPE_PREFERENCES = {
    "cell_definition": {
        "cell_ontology": 1.0,
        "single_cell_atlas_metadata": 0.35,
        "anatomy_ontology": 0.15,
        "gene_ontology": 0.05,
        "phenotype_quality_ontology": 0.0,
        "gene_nomenclature": -0.25,
        "protein_function": -0.45,
        "cell_marker_database": -0.2,
        "gene_reference": -0.2,
    },
    "protein_function": {
        "protein_function": 1.0,
        "gene_nomenclature": 0.25,
        "gene_reference": 0.25,
        "gene_ontology": 0.15,
        "cell_ontology": -0.25,
        "single_cell_atlas_metadata": -0.35,
        "anatomy_ontology": -0.25,
        "phenotype_quality_ontology": -0.15,
        "cell_marker_database": -0.35,
    },
    "gene_nomenclature": {
        "gene_nomenclature": 1.0,
        "gene_reference": 0.55,
        "protein_function": 0.35,
        "gene_ontology": 0.05,
        "cell_ontology": -0.2,
        "single_cell_atlas_metadata": -0.25,
        "anatomy_ontology": -0.2,
        "phenotype_quality_ontology": -0.1,
        "cell_marker_database": -0.25,
    },
    "protein_accession": {
        "protein_function": 1.0,
        "gene_nomenclature": 0.1,
        "gene_reference": 0.1,
        "gene_ontology": -0.1,
        "cell_ontology": -0.25,
        "single_cell_atlas_metadata": -0.25,
        "anatomy_ontology": -0.25,
        "phenotype_quality_ontology": -0.1,
        "cell_marker_database": -0.25,
    },
    "dataset_evidence": {
        "single_cell_atlas_metadata": 1.0,
        "cell_ontology": 0.3,
        "anatomy_ontology": 0.2,
        "gene_ontology": -0.1,
        "gene_nomenclature": -0.3,
        "gene_reference": -0.3,
        "protein_function": -0.35,
        "phenotype_quality_ontology": -0.1,
        "cell_marker_database": -0.2,
    },
    "cell_markers": {
        "cell_marker_database": 1.0,
        "cell_ontology": 0.35,
        "single_cell_atlas_metadata": 0.2,
        "gene_nomenclature": 0.1,
        "gene_reference": 0.1,
        "protein_function": 0.05,
        "anatomy_ontology": 0.0,
        "gene_ontology": -0.05,
        "phenotype_quality_ontology": -0.1,
    },
    "anatomy": {
        "anatomy_ontology": 1.0,
        "cell_ontology": 0.2,
        "single_cell_atlas_metadata": 0.15,
        "gene_ontology": -0.1,
        "gene_nomenclature": -0.25,
        "gene_reference": -0.25,
        "protein_function": -0.25,
        "phenotype_quality_ontology": 0.0,
        "cell_marker_database": -0.2,
    },
    "gene_ontology": {
        "gene_ontology": 1.0,
        "protein_function": 0.2,
        "gene_nomenclature": 0.1,
        "gene_reference": 0.2,
        "cell_ontology": -0.15,
        "single_cell_atlas_metadata": -0.2,
        "anatomy_ontology": -0.1,
        "phenotype_quality_ontology": 0.0,
        "cell_marker_database": -0.2,
    },
    "gene_reference": {
        "gene_reference": 1.0,
        "gene_nomenclature": 0.7,
        "protein_function": 0.45,
        "gene_ontology": 0.15,
        "cell_marker_database": -0.2,
        "cell_ontology": -0.25,
        "single_cell_atlas_metadata": -0.25,
        "anatomy_ontology": -0.2,
        "phenotype_quality_ontology": -0.1,
    },
    "general": {},
}
SYSTEM_PROMPT = """You answer cell biology and biomedical ontology questions using only the retrieved context.
Rules:
- Use only facts supported by the retrieved context.
- Cite every factual sentence with one or more retrieved source block IDs, such as [CL:0011031], [UBERON:0002106], [GO:0006915], [PATO:0000586], [HGNC:7315], [NCBIGene:931], [UniProt:P11836], [cellmarker3:human:t_cell:cl_0000084], or [panglaodb:mm_hs:t_cells].
- Use only source block IDs shown at the start of retrieved context blocks as citations. Do not cite related IDs that only appear inside the body text unless they are also source block IDs.
- Repeat citations on every sentence that makes a factual claim. Do not use one citation at the end of a paragraph to cover earlier uncited sentences.
- For CELLxGENE evidence, cite the full source block ID such as [cellxgene_census:cl_0000815:uberon_0000178:normal:10x_3_v2:316], not shorter embedded IDs such as [CL:0000815] or [UBERON:0000178].
- If the context does not contain enough information, say that the retrieved context is insufficient.
- Keep the answer concise and directly address the question.
- Do not output reasoning traces, hidden thoughts, or <think> tags.
"""


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


load_dotenv(ROOT / ".env")


def project_path(env_name: str, default: str) -> Path:
    configured = Path(os.environ.get(env_name, default))
    if configured.is_absolute():
        return configured
    return ROOT / configured


CHUNKS_PATH = project_path("RAG_CHUNKS_PATH", "chunks/cl_chunks.jsonl")
ALIASES_PATH = project_path("RAG_ALIASES_PATH", "processed/cl_aliases.jsonl")
MODEL_PATH = project_path("RAG_MODEL_PATH", "models/Qwen3-Embedding-8B")
EMBEDDINGS_PATH = project_path("RAG_EMBEDDINGS_PATH", "embeddings/cl_qwen3_embedding_8b.npz")
METADATA_PATH = project_path("RAG_METADATA_PATH", "embeddings/cl_qwen3_embedding_8b.metadata.json")
FAISS_INDEX_PATH = project_path(
    "RAG_FAISS_INDEX_PATH",
    str(EMBEDDINGS_PATH.with_suffix(".ivfflat.faiss").relative_to(ROOT))
    if EMBEDDINGS_PATH.is_relative_to(ROOT)
    else str(EMBEDDINGS_PATH.with_suffix(".ivfflat.faiss")),
)
VECTOR_BACKEND = os.environ.get("RAG_VECTOR_BACKEND", "exact").strip().casefold()
FAISS_CANDIDATES = int(os.environ.get("RAG_FAISS_CANDIDATES", "4096"))
FAISS_NPROBE = int(os.environ.get("RAG_FAISS_NPROBE", "64"))
RERANKER_ENABLED = os.environ.get("RAG_RERANKER_ENABLED", "false").strip().casefold() in {"1", "true", "yes", "on"}
RERANKER_MODEL_PATH = project_path("RAG_RERANKER_MODEL_PATH", "models/ms-marco-MiniLM-L-6-v2")
RERANKER_CANDIDATES = int(os.environ.get("RAG_RERANKER_CANDIDATES", "48"))
RERANKER_WEIGHT = float(os.environ.get("RAG_RERANKER_WEIGHT", "0.35"))
RERANKER_EXACT_MATCH_WEIGHT = float(os.environ.get("RAG_RERANKER_EXACT_MATCH_WEIGHT", "0.0"))
RERANKER_MAX_LENGTH = int(os.environ.get("RAG_RERANKER_MAX_LENGTH", "512"))
RERANKER_BATCH_SIZE = int(os.environ.get("RAG_RERANKER_BATCH_SIZE", "8"))

app = FastAPI(title="Cell RAG", version="0.2.0")


class SearchRequest(BaseModel):
    query: str
    top_k: int = Field(default=5, ge=1, le=50)
    bm25_weight: float = 0.45
    vector_weight: float = 0.55
    rerank_weight: float = Field(default=0.15, ge=0.0, le=1.0)
    max_length: int = 2048
    task: str = DEFAULT_QUERY_TASK
    use_neural_reranker: bool | None = None


class AnswerRequest(SearchRequest):
    base_url: str = Field(default_factory=lambda: os.environ.get("LUOSS_BASE_URL", DEFAULT_BASE_URL))
    model: str = Field(default_factory=lambda: os.environ.get("LUOSS_MODEL", DEFAULT_MODEL))
    api_key_env: str = "LUOSS_API_KEY"
    fallback_api_key_env: str = "OPENAI_API_KEY"
    temperature: float = Field(default=0.1, ge=0.0, le=2.0)
    max_tokens: int = Field(default=700, ge=1, le=8192)
    max_context_chars: int = Field(default=9000, ge=500, le=50000)
    allow_low_confidence: bool = False
    dry_run: bool = False


def lexical_rerank_score(query: str, chunk: dict[str, Any]) -> float:
    query_norm = normalize(query)
    if not query_norm:
        return 0.0
    query_candidates = {query_norm}
    stripped = query_norm.strip(" ?!.:,;()[]{}\"'")
    query_candidates.add(stripped)
    stripped = QUERY_PREFIX_RE.sub("", stripped).strip()
    stripped = ARTICLE_RE.sub("", stripped).strip()
    stripped = stripped.strip(" ?!.:,;()[]{}\"'")
    if stripped:
        query_candidates.add(stripped)

    metadata = chunk.get("metadata", {}) if isinstance(chunk.get("metadata"), dict) else {}
    title = normalize(str(chunk.get("title", "")))
    text = normalize(str(chunk.get("text", "")))
    ontology_id = normalize(str(metadata.get("ontology_id", "")))
    synonyms = [normalize(str(value)) for value in metadata.get("synonyms", [])]
    alt_ids = [normalize(str(value)) for value in metadata.get("alt_ids", [])]

    if any(candidate == title or candidate == ontology_id or candidate in synonyms or candidate in alt_ids for candidate in query_candidates):
        return 1.0
    if any(candidate and candidate in title for candidate in query_candidates):
        return 0.85
    if any(candidate and candidate in text for candidate in query_candidates):
        return 0.65

    query_tokens = set(tokenize(query))
    if not query_tokens:
        return 0.0
    title_tokens = set(tokenize(str(chunk.get("title", ""))))
    text_tokens = set(tokenize(str(chunk.get("text", ""))))
    title_overlap = len(query_tokens & title_tokens) / len(query_tokens)
    text_overlap = len(query_tokens & text_tokens) / len(query_tokens)
    return max(0.55 * title_overlap, 0.35 * text_overlap)


def query_focus(query: str) -> str:
    text = normalize(query).strip(" ?!.:,;()[]{}\"'")
    text = QUERY_PREFIX_RE.sub("", text).strip()
    text = ARTICLE_RE.sub("", text).strip()
    return text.strip(" ?!.:,;()[]{}\"'")


def classify_source_intent(query: str) -> str:
    q = normalize(query)
    focus = query_focus(query)
    raw_focus = query.strip(" ?!.:,;()[]{}\"'")
    raw_focus = QUERY_PREFIX_RE.sub("", raw_focus).strip()
    raw_focus = ARTICLE_RE.sub("", raw_focus).strip().strip(" ?!.:,;()[]{}\"'")

    if re.search(r"\b(cellxgene|census|dataset|evidence|cell count|assay|10x|single-cell atlas)\b", q):
        return "dataset_evidence"
    if re.search(r"\b(marker|markers|marker gene|marker genes|cell marker|cell markers|signature|marker panel|identify|annotation|annotate)\b", q):
        return "cell_markers"
    if UNIPROT_ACCESSION_RE.search(raw_focus):
        return "protein_accession"
    if re.search(r"\b(function|activity|pathway|protein function|what does .+ do|role of|roles of)\b", q):
        return "protein_function"
    if re.search(r"\b(what gene|which gene|gene symbol|official symbol|refer to|alias|aliases|nomenclature)\b", q):
        return "gene_nomenclature"
    if re.search(r"\b(entrez|ncbi gene|gene id|gene summary|gene description|chromosome|map location|locus|gene type)\b", q):
        return "gene_reference"
    if " cell" in f" {focus}" or focus in {"treg", "fibroblast", "neuron", "lymphocyte", "monocyte", "macrophage"}:
        return "cell_definition"
    if GENE_SYMBOL_RE.fullmatch(raw_focus):
        return "gene_nomenclature"
    if "forkhead box" in q:
        return "gene_nomenclature"
    if re.search(r"\b(tissue|organ|anatomy|blood|liver|lung|kidney|brain|heart|lymph node)\b", q):
        return "anatomy"
    if re.search(r"\b(gene ontology|biological process|molecular function|cellular component|go:)\b", q):
        return "gene_ontology"
    return "general"


def source_rank_score(intent: str, chunk: dict[str, Any]) -> float:
    metadata = chunk.get("metadata", {}) if isinstance(chunk.get("metadata"), dict) else {}
    source_type = str(metadata.get("source_type") or "")
    source_id = str(metadata.get("source_id") or "")
    preferences = SOURCE_TYPE_PREFERENCES.get(intent, {})
    return float(preferences.get(source_type, preferences.get(source_id, 0.0)))


def normalize_minmax_scores(scores: dict[str, float]) -> dict[str, float]:
    if not scores:
        return {}
    values = list(scores.values())
    min_score = min(values)
    max_score = max(values)
    if max_score == min_score:
        return {key: 1.0 for key in scores}
    return {key: (value - min_score) / (max_score - min_score) for key, value in scores.items()}


def assess_retrieval(results: list[dict[str, Any]]) -> dict[str, Any]:
    if not results:
        return {
            "confidence": "low",
            "should_answer": False,
            "reason": "no retrieval results",
        }

    top = results[0]
    reasons = [str(reason) for reason in top.get("reasons", [])]
    exact_match = any(reason.startswith("exact ") for reason in reasons)
    vector_score = float(top.get("vector_score") or 0.0)
    bm25_norm = float(top.get("bm25_norm") or 0.0)
    rerank_score = float(top.get("rerank_score") or 0.0)
    gap = None
    if len(results) > 1:
        gap = round(float(top.get("score") or 0.0) - float(results[1].get("score") or 0.0), 6)

    if exact_match:
        confidence = "high"
        reason = "top result has an exact alias/name/id match"
    elif vector_score >= 0.68 and (bm25_norm >= 0.08 or rerank_score >= 0.45):
        confidence = "high"
        reason = "top result has strong vector similarity plus lexical/rerank support"
    elif (vector_score >= 0.62 and (bm25_norm >= 0.04 or rerank_score >= 0.25)) or rerank_score >= 0.55:
        confidence = "medium"
        reason = "top result has partial retrieval support"
    else:
        confidence = "low"
        reason = "top result has weak retrieval support"

    return {
        "confidence": confidence,
        "should_answer": confidence in {"high", "medium"},
        "reason": reason,
        "top_doc_id": top.get("doc_id"),
        "top_title": top.get("title"),
        "top_score": top.get("score"),
        "score_gap": gap,
    }


class SearchEngine:
    def __init__(self) -> None:
        if not torch.cuda.is_available():
            raise RuntimeError("CUDA is not available; run this service on the GPU CCI.")

        self.chunks = load_jsonl(CHUNKS_PATH)
        self.aliases = load_jsonl(ALIASES_PATH)
        self.chunk_by_id = {str(chunk.get("doc_id")): chunk for chunk in self.chunks}
        self.alias_index = build_alias_index(self.aliases)
        self.token_counts, self.doc_freq, self.avg_doc_length = build_text_index(self.chunks)
        self.vector_metadata = json.loads(METADATA_PATH.read_text(encoding="utf-8"))
        self.embedding_matrix: np.ndarray | None = None
        self.faiss_index: Any | None = None
        self.vector_backend_requested = VECTOR_BACKEND
        self.vector_backend = "exact"
        self.vector_reason = "qwen3 vector match"
        self.faiss_candidates = max(1, FAISS_CANDIDATES)
        self.faiss_nprobe = max(1, FAISS_NPROBE)
        self.vector_count = len(self.vector_metadata)
        self.vector_dim = 0
        self.load_vector_backend()
        self.reranker_enabled = RERANKER_ENABLED
        self.reranker_model_path = RERANKER_MODEL_PATH
        self.reranker_candidates = max(1, RERANKER_CANDIDATES)
        self.reranker_weight = max(0.0, RERANKER_WEIGHT)
        self.reranker_exact_match_weight = max(0.0, RERANKER_EXACT_MATCH_WEIGHT)
        self.reranker_max_length = max(64, RERANKER_MAX_LENGTH)
        self.reranker_batch_size = max(1, RERANKER_BATCH_SIZE)
        self.reranker_tokenizer: Any | None = None
        self.reranker_model: Any | None = None
        self.load_reranker()
        self.tokenizer = AutoTokenizer.from_pretrained(MODEL_PATH, local_files_only=True, trust_remote_code=True)
        self.model = AutoModel.from_pretrained(
            MODEL_PATH,
            local_files_only=True,
            trust_remote_code=True,
            dtype=torch.float16,
            device_map="cuda",
        )
        self.model.eval()

    def load_reranker(self) -> None:
        if not self.reranker_enabled:
            return
        if not self.reranker_model_path.exists():
            raise RuntimeError(
                f"RAG_RERANKER_ENABLED=true but reranker model is missing: {self.reranker_model_path}. "
                "Download it first, for example: scripts/download_reranker_model.sh "
                "cross-encoder/ms-marco-MiniLM-L-6-v2 models/ms-marco-MiniLM-L-6-v2"
            )
        self.reranker_tokenizer = AutoTokenizer.from_pretrained(
            self.reranker_model_path,
            local_files_only=True,
            trust_remote_code=True,
        )
        self.reranker_model = AutoModelForSequenceClassification.from_pretrained(
            self.reranker_model_path,
            local_files_only=True,
            trust_remote_code=True,
            dtype=torch.float16,
            device_map="cuda",
        )
        self.reranker_model.eval()

    def load_vector_backend(self) -> None:
        if self.vector_backend_requested == "faiss":
            self.load_faiss_backend()
        elif self.vector_backend_requested in {"exact", "numpy"}:
            self.load_exact_backend()
        else:
            raise RuntimeError(
                f"Unsupported RAG_VECTOR_BACKEND={self.vector_backend_requested!r}. "
                "Use 'exact' or 'faiss'."
            )

    def load_exact_backend(self) -> None:
        self.embedding_matrix = np.load(EMBEDDINGS_PATH)["embeddings"].astype(np.float32)
        if len(self.embedding_matrix) != len(self.vector_metadata):
            raise RuntimeError(
                f"Embedding row count {len(self.embedding_matrix)} does not match "
                f"metadata row count {len(self.vector_metadata)}."
            )
        self.vector_backend = "exact"
        self.vector_reason = "qwen3 vector match"
        self.vector_count = int(self.embedding_matrix.shape[0])
        self.vector_dim = int(self.embedding_matrix.shape[1])

    def load_faiss_backend(self) -> None:
        try:
            import faiss  # type: ignore[import-not-found]
        except ImportError as exc:
            raise RuntimeError(
                "RAG_VECTOR_BACKEND=faiss requires the faiss-cpu package in qwen_env. "
                "Install it with: qwen_env/bin/python -m pip install faiss-cpu"
            ) from exc

        if not FAISS_INDEX_PATH.exists():
            raise RuntimeError(
                f"RAG_VECTOR_BACKEND=faiss but FAISS index is missing: {FAISS_INDEX_PATH}. "
                "Build it with scripts/build_faiss_index.sh."
            )

        self.faiss_index = faiss.read_index(str(FAISS_INDEX_PATH))
        if getattr(self.faiss_index, "ntotal", 0) != len(self.vector_metadata):
            raise RuntimeError(
                f"FAISS index row count {self.faiss_index.ntotal} does not match "
                f"metadata row count {len(self.vector_metadata)}."
            )
        if hasattr(self.faiss_index, "nprobe"):
            self.faiss_index.nprobe = self.faiss_nprobe
        self.vector_backend = "faiss"
        self.vector_reason = "qwen3 vector match (faiss ANN)"
        self.vector_count = int(self.faiss_index.ntotal)
        self.vector_dim = int(self.faiss_index.d)

    def embed_query(self, query: str, task: str, max_length: int) -> np.ndarray:
        inputs = self.tokenizer(
            format_query(task, query),
            return_tensors="pt",
            truncation=True,
            max_length=max_length,
        ).to(self.model.device)
        with torch.inference_mode():
            outputs = self.model(**inputs)
            embedding = last_token_pool(outputs.last_hidden_state, inputs["attention_mask"])
        return embedding.float().cpu().numpy()[0]

    def vector_search(self, query_vector: np.ndarray) -> dict[str, float]:
        if self.vector_backend == "faiss":
            return self.faiss_vector_scores(query_vector)
        if self.embedding_matrix is None:
            raise RuntimeError("Exact vector backend is active but embedding matrix is not loaded.")
        return vector_scores(query_vector, self.embedding_matrix, self.vector_metadata)

    def faiss_vector_scores(self, query_vector: np.ndarray) -> dict[str, float]:
        if self.faiss_index is None:
            raise RuntimeError("FAISS vector backend is active but no index is loaded.")

        query = np.ascontiguousarray(query_vector.reshape(1, -1).astype(np.float32))
        limit = min(self.faiss_candidates, len(self.vector_metadata))
        scores, indices = self.faiss_index.search(query, limit)
        result: dict[str, float] = {}
        for index, score in zip(indices[0], scores[0]):
            if index < 0:
                continue
            doc_id = str(self.vector_metadata[int(index)].get("doc_id"))
            result[doc_id] = float(score)
        return result

    def should_use_neural_reranker(self, request: SearchRequest) -> bool:
        if request.use_neural_reranker is not None:
            return bool(request.use_neural_reranker and self.reranker_model is not None)
        return self.reranker_model is not None

    def neural_rerank_scores(self, query: str, candidate_ids: list[str]) -> dict[str, float]:
        if self.reranker_tokenizer is None or self.reranker_model is None or not candidate_ids:
            return {}

        raw_scores: dict[str, float] = {}
        for start in range(0, len(candidate_ids), self.reranker_batch_size):
            batch_ids = candidate_ids[start : start + self.reranker_batch_size]
            pairs = [
                [
                    query,
                    f"{self.chunk_by_id[doc_id].get('title', '')}\n{self.chunk_by_id[doc_id].get('text', '')}",
                ]
                for doc_id in batch_ids
                if doc_id in self.chunk_by_id
            ]
            if not pairs:
                continue

            inputs = self.reranker_tokenizer(
                pairs,
                padding=True,
                truncation=True,
                max_length=self.reranker_max_length,
                return_tensors="pt",
            ).to(self.reranker_model.device)
            with torch.inference_mode():
                logits = self.reranker_model(**inputs).logits
            scores = logits.view(-1).float().cpu().tolist()
            for doc_id, score in zip(batch_ids, scores):
                raw_scores[doc_id] = float(score)
        return raw_scores

    def search(self, request: SearchRequest) -> list[dict[str, Any]]:
        source_intent = classify_source_intent(request.query)
        bm25_raw = bm25_scores(request.query, self.chunks, self.token_counts, self.doc_freq, self.avg_doc_length)
        query_vector = self.embed_query(request.query, request.task, request.max_length)
        vector_raw = self.vector_search(query_vector)

        bm25_norm = normalize_scores(bm25_raw)
        vector_norm = normalize_scores(vector_raw)
        scores: dict[str, float] = {}
        reasons: dict[str, list[str]] = {}
        for doc_id in set(bm25_norm) | set(vector_norm):
            scores[doc_id] = request.bm25_weight * bm25_norm.get(doc_id, 0.0) + request.vector_weight * vector_norm.get(doc_id, 0.0)
            reasons[doc_id] = []
            if doc_id in bm25_raw:
                reasons[doc_id].append("bm25 lexical match")
            if doc_id in vector_raw:
                reasons[doc_id].append(self.vector_reason)

        rerank_raw: dict[str, float] = {}
        for doc_id in list(scores):
            chunk = self.chunk_by_id.get(doc_id)
            if not chunk:
                continue
            rerank_raw[doc_id] = lexical_rerank_score(request.query, chunk)
            scores[doc_id] += request.rerank_weight * rerank_raw[doc_id]
            if rerank_raw[doc_id] >= 0.55:
                reasons[doc_id].append("lightweight lexical rerank support")

        exact_match_targets: set[str] = set()
        for row in exact_alias_matches(request.query, self.alias_index):
            target_id = str(row.get("target_id"))
            if target_id in self.chunk_by_id:
                if target_id not in exact_match_targets:
                    scores[target_id] = scores.get(target_id, 0.0) + 1000.0
                    exact_match_targets.add(target_id)
                rerank_raw[target_id] = max(rerank_raw.get(target_id, 0.0), 1.0)
                reason = format_alias_reason(row)
                if reason not in reasons.setdefault(target_id, []):
                    reasons[target_id].insert(0, reason)

        source_rank_raw: dict[str, float] = {}
        for doc_id in list(scores):
            chunk = self.chunk_by_id.get(doc_id)
            if not chunk:
                continue
            source_score = source_rank_score(source_intent, chunk)
            source_rank_raw[doc_id] = source_score
            if source_score == 0.0:
                continue
            has_exact_match = any(str(reason).startswith("exact ") for reason in reasons.get(doc_id, []))
            weight = SOURCE_EXACT_MATCH_WEIGHT if has_exact_match else SOURCE_SOFT_MATCH_WEIGHT
            scores[doc_id] += weight * source_score
            if abs(source_score) >= 0.2:
                metadata = chunk.get("metadata", {}) if isinstance(chunk.get("metadata"), dict) else {}
                source_type = metadata.get("source_type") or "unknown_source"
                reasons.setdefault(doc_id, []).append(
                    f"source-aware rank: intent={source_intent}, source_type={source_type}, preference={source_score:+.2f}"
                )

        neural_rerank_raw: dict[str, float] = {}
        neural_rerank_norm: dict[str, float] = {}
        if self.should_use_neural_reranker(request):
            candidate_ids = sorted(scores, key=lambda doc_id: scores[doc_id], reverse=True)[: self.reranker_candidates]
            neural_rerank_raw = self.neural_rerank_scores(request.query, candidate_ids)
            neural_rerank_norm = normalize_minmax_scores(neural_rerank_raw)
            for doc_id, reranker_score in neural_rerank_norm.items():
                has_exact_match = any(str(reason).startswith("exact ") for reason in reasons.get(doc_id, []))
                weight = self.reranker_exact_match_weight if has_exact_match else self.reranker_weight
                scores[doc_id] = scores.get(doc_id, 0.0) + weight * reranker_score
                if reranker_score >= 0.5:
                    reasons.setdefault(doc_id, []).append(
                        f"neural reranker support: model={self.reranker_model_path.name}, score={reranker_score:.3f}, weight={weight:.3f}"
                    )

        ranked_ids = sorted(scores, key=lambda doc_id: scores[doc_id], reverse=True)[: request.top_k]
        results: list[dict[str, Any]] = []
        for rank, doc_id in enumerate(ranked_ids, start=1):
            chunk = self.chunk_by_id[doc_id]
            metadata = chunk.get("metadata", {}) if isinstance(chunk.get("metadata"), dict) else {}
            results.append(
                {
                    "rank": rank,
                    "score": round(scores[doc_id], 6),
                    "bm25_score": round(bm25_raw.get(doc_id, 0.0), 6),
                    "bm25_norm": round(bm25_norm.get(doc_id, 0.0), 6),
                    "vector_score": round(vector_raw.get(doc_id, 0.0), 6),
                    "vector_norm": round(vector_norm.get(doc_id, 0.0), 6),
                    "rerank_score": round(rerank_raw.get(doc_id, 0.0), 6),
                    "neural_rerank_score": round(neural_rerank_raw.get(doc_id, 0.0), 6),
                    "neural_rerank_norm": round(neural_rerank_norm.get(doc_id, 0.0), 6),
                    "source_rank_score": round(source_rank_raw.get(doc_id, 0.0), 6),
                    "source_intent": source_intent,
                    "doc_id": doc_id,
                    "title": chunk.get("title"),
                    "source_id": metadata.get("source_id"),
                    "source_type": metadata.get("source_type"),
                    "data_version": metadata.get("data_version"),
                    "reasons": reasons.get(doc_id, ["hybrid match"]),
                    "text": chunk.get("text"),
                }
            )
        return results


def build_context(results: list[dict[str, Any]], max_chars: int) -> str:
    blocks: list[str] = []
    used = 0
    for result in results:
        doc_id = result.get("doc_id")
        title = result.get("title")
        score = result.get("score")
        text = str(result.get("text") or "")
        block = f"Source block ID: [{doc_id}]\nTitle: {title}\nRetrieval score: {score}\n{text}".strip()
        if used + len(block) > max_chars:
            remaining = max_chars - used
            if remaining <= 200:
                break
            block = block[:remaining].rstrip() + "\n[truncated]"
        blocks.append(block)
        used += len(block) + 2
        if used >= max_chars:
            break
    return "\n\n".join(blocks)


def build_messages(query: str, context: str) -> list[dict[str, str]]:
    user_prompt = f"""/no_think

Question:
{query}

Retrieved context:
{context}

Answer with citations using only the retrieved source block IDs shown in square brackets at the start of context blocks. Every factual sentence must include its own citation."""
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]


def compact_sources(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "rank": item.get("rank"),
            "doc_id": item.get("doc_id"),
            "title": item.get("title"),
            "score": item.get("score"),
            "source_id": item.get("source_id"),
            "source_type": item.get("source_type"),
            "source_intent": item.get("source_intent"),
            "confidence_signals": {
                "bm25_norm": item.get("bm25_norm"),
                "vector_norm": item.get("vector_norm"),
                "rerank_score": item.get("rerank_score"),
                "neural_rerank_norm": item.get("neural_rerank_norm"),
                "source_rank_score": item.get("source_rank_score"),
            },
            "reasons": item.get("reasons", []),
        }
        for item in results
    ]


def get_api_key(request: AnswerRequest) -> str | None:
    return os.environ.get(request.api_key_env) or os.environ.get(request.fallback_api_key_env)


def call_chat(request: AnswerRequest, messages: list[dict[str, str]]) -> str:
    api_key = get_api_key(request)
    if not api_key:
        raise HTTPException(
            status_code=500,
            detail=f"Missing API key. Set {request.api_key_env} or {request.fallback_api_key_env}.",
        )

    url = request.base_url.rstrip("/") + "/chat/completions"
    try:
        response = requests.post(
            url,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": request.model,
                "messages": messages,
                "temperature": request.temperature,
                "max_tokens": request.max_tokens,
            },
            timeout=180,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail=f"LLM call failed: {exc}") from exc

    data = response.json()
    answer = data["choices"][0]["message"]["content"]
    return THINK_BLOCK_RE.sub("", answer).strip()


def citation_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.casefold()).strip("_")


def map_citation_to_source(citation: str, source_ids: list[str]) -> str | None:
    if citation in source_ids:
        return citation
    key = citation_key(citation)
    if not key:
        return None
    for source_id in source_ids:
        source_key = citation_key(source_id)
        if key == source_key or key in source_key:
            return source_id
    return None


def trim_incomplete_tail(answer: str) -> str:
    answer = DANGLING_CITATION_RE.sub("", answer.rstrip()).rstrip()
    if not answer or answer.endswith((".", "?", "!", "]")):
        return answer
    last_end = max(answer.rfind("."), answer.rfind("?"), answer.rfind("!"))
    if last_end >= 0:
        return answer[: last_end + 1].rstrip()
    return answer


def normalize_answer_citations(answer: str, source_ids: list[str]) -> str:
    def replace(match: re.Match[str]) -> str:
        citation = match.group(1).strip()
        mapped = map_citation_to_source(citation, source_ids)
        return f"[{mapped}]" if mapped else match.group(0)

    return CITATION_RE.sub(replace, answer)


def append_sentence_citation(sentence: str, citation: str) -> str:
    stripped = sentence.rstrip()
    if not stripped:
        return sentence
    if stripped.endswith((".", "?", "!")):
        return f"{stripped[:-1]} [{citation}]{stripped[-1]}"
    return f"{stripped} [{citation}]"


def ensure_sentence_citations(answer: str, default_source_id: str) -> str:
    output_lines: list[str] = []
    for line in answer.splitlines():
        stripped = line.strip()
        if (
            not stripped
            or stripped.endswith(":")
            or "retrieved context is insufficient" in stripped.casefold()
        ):
            output_lines.append(line)
            continue

        prefix = ""
        content = line
        bullet = re.match(r"^(\s*[-*]\s+)(.*)$", line)
        if bullet:
            prefix = bullet.group(1)
            content = bullet.group(2)

        pieces = re.split(r"(?<=[.!?])\s+", content.strip())
        fixed_pieces = []
        for piece in pieces:
            if not piece:
                continue
            if len(piece) >= 12 and not CITATION_RE.search(piece):
                piece = append_sentence_citation(piece, default_source_id)
            fixed_pieces.append(piece)
        output_lines.append(prefix + " ".join(fixed_pieces))
    return "\n".join(output_lines).strip()


def extract_answer_citations(answer: str) -> list[str]:
    seen: set[str] = set()
    citations: list[str] = []
    for match in CITATION_RE.finditer(answer):
        citation = match.group(1).strip()
        if citation and citation not in seen:
            seen.add(citation)
            citations.append(citation)
    return citations


def answer_claim_units(answer: str) -> list[str]:
    units: list[str] = []
    for raw_line in answer.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        line = re.sub(r"^[-*]\s+", "", line).strip()
        if not line or line.endswith(":"):
            continue
        for piece in SENTENCE_SPLIT_RE.split(line):
            piece = piece.strip()
            if len(piece) < 12:
                continue
            if "retrieved context is insufficient" in piece.casefold():
                continue
            units.append(piece)
    return units


def audit_answer_citations(answer: str, sources: list[dict[str, Any]]) -> dict[str, Any]:
    source_ids = [str(source.get("doc_id")) for source in sources if source.get("doc_id")]
    source_id_set = set(source_ids)
    citations = extract_answer_citations(answer)
    claim_units = answer_claim_units(answer)
    valid_citations = [citation for citation in citations if citation in source_id_set]
    invalid_citations = [citation for citation in citations if citation not in source_id_set]
    citationless_claims = [unit for unit in claim_units if not CITATION_RE.search(unit)]
    abstained = "retrieved context is insufficient" in answer.casefold()
    passed = abstained or (not invalid_citations and not citationless_claims)

    return {
        "passed": passed,
        "abstained": abstained,
        "source_ids": source_ids,
        "citations": citations,
        "valid_citations": valid_citations,
        "invalid_citations": invalid_citations,
        "claim_count": len(claim_units),
        "citationless_claims": citationless_claims,
    }


def ground_answer(answer: str, sources: list[dict[str, Any]]) -> str:
    source_ids = [str(source.get("doc_id")) for source in sources if source.get("doc_id")]
    answer = trim_incomplete_tail(THINK_BLOCK_RE.sub("", answer).strip())
    if not answer or "retrieved context is insufficient" in answer.casefold() or not source_ids:
        return answer
    answer = normalize_answer_citations(answer, source_ids)
    return ensure_sentence_citations(answer, source_ids[0])


def ground_answer_with_audit(raw_answer: str, sources: list[dict[str, Any]]) -> tuple[str, dict[str, Any]]:
    cleaned_answer = trim_incomplete_tail(THINK_BLOCK_RE.sub("", raw_answer).strip())
    pre_grounding_check = audit_answer_citations(cleaned_answer, sources)
    grounded_answer = ground_answer(cleaned_answer, sources)
    citation_check = audit_answer_citations(grounded_answer, sources)
    citation_check["grounding_modified_answer"] = grounded_answer != cleaned_answer
    citation_check["pre_grounding_passed"] = pre_grounding_check["passed"]
    citation_check["pre_grounding_invalid_citations"] = pre_grounding_check["invalid_citations"]
    citation_check["pre_grounding_citationless_claims"] = pre_grounding_check["citationless_claims"]
    return grounded_answer, citation_check


engine = SearchEngine()


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "chunks_path": str(CHUNKS_PATH.relative_to(ROOT) if CHUNKS_PATH.is_relative_to(ROOT) else CHUNKS_PATH),
        "embeddings_path": str(EMBEDDINGS_PATH.relative_to(ROOT) if EMBEDDINGS_PATH.is_relative_to(ROOT) else EMBEDDINGS_PATH),
        "vector_backend_requested": engine.vector_backend_requested,
        "vector_backend": engine.vector_backend,
        "faiss_index_path": str(FAISS_INDEX_PATH.relative_to(ROOT) if FAISS_INDEX_PATH.is_relative_to(ROOT) else FAISS_INDEX_PATH),
        "faiss_candidates": engine.faiss_candidates,
        "faiss_nprobe": engine.faiss_nprobe if engine.vector_backend == "faiss" else None,
        "reranker_enabled": engine.reranker_enabled,
        "reranker_loaded": engine.reranker_model is not None,
        "reranker_model_path": str(engine.reranker_model_path.relative_to(ROOT) if engine.reranker_model_path.is_relative_to(ROOT) else engine.reranker_model_path),
        "reranker_candidates": engine.reranker_candidates,
        "reranker_weight": engine.reranker_weight,
        "reranker_exact_match_weight": engine.reranker_exact_match_weight,
        "reranker_max_length": engine.reranker_max_length,
        "chunks": len(engine.chunks),
        "embedding_shape": [engine.vector_count, engine.vector_dim],
        "cuda_available": torch.cuda.is_available(),
        "gpu": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
    }


@app.post("/search")
def search(request: SearchRequest) -> dict[str, Any]:
    results = engine.search(request)
    return {"query": request.query, "retrieval_quality": assess_retrieval(results), "results": results}


@app.post("/answer")
def answer(request: AnswerRequest) -> dict[str, Any]:
    results = engine.search(request)
    retrieval_quality = assess_retrieval(results)
    context = build_context(results, request.max_context_chars)
    messages = build_messages(request.query, context)
    sources = compact_sources(results)

    if request.dry_run:
        return {"query": request.query, "retrieval_quality": retrieval_quality, "sources": sources, "messages": messages}

    if not retrieval_quality["should_answer"] and not request.allow_low_confidence:
        answer_text = "The retrieved context is insufficient to answer this question with confidence."
        return {
            "query": request.query,
            "answer": answer_text,
            "retrieval_quality": retrieval_quality,
            "sources": sources,
            "citation_check": audit_answer_citations(answer_text, sources),
        }

    answer_text, citation_check = ground_answer_with_audit(call_chat(request, messages), sources)
    return {
        "query": request.query,
        "answer": answer_text,
        "retrieval_quality": retrieval_quality,
        "sources": sources,
        "citation_check": citation_check,
    }
