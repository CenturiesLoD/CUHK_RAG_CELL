#!/usr/bin/env python3
"""Mentor-facing API wrapper for the local Cell RAG service."""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any

import requests
from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[1]


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

RAG_BASE_URL = os.environ.get("MENTOR_RAG_BASE_URL", "http://127.0.0.1:8010").rstrip("/")
MENTOR_API_KEY = os.environ.get("MENTOR_API_KEY", "").strip()
MAX_TOP_K = int(os.environ.get("MENTOR_MAX_TOP_K", "10"))
MAX_SOURCE_TEXT_CHARS = int(os.environ.get("MENTOR_MAX_SOURCE_TEXT_CHARS", "700"))
REQUEST_TIMEOUT = int(os.environ.get("MENTOR_RAG_TIMEOUT_SECONDS", "300"))

app = FastAPI(
    title="Single-Cell RAG Mentor API",
    version="1.0.0",
    description=(
        "A small demonstration API for querying the local single-cell biology RAG "
        "system. Use /ask for cited answers and /search for retrieval-only checks."
    ),
)


class AskRequest(BaseModel):
    question: str = Field(..., min_length=2, max_length=2000)
    top_k: int = Field(default=5, ge=1, le=MAX_TOP_K)
    max_tokens: int = Field(default=450, ge=50, le=1200)
    temperature: float = Field(default=0.1, ge=0.0, le=1.0)
    include_sources: bool = True
    use_neural_reranker: bool | None = None
    allow_low_confidence: bool = False


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=2, max_length=2000)
    top_k: int = Field(default=5, ge=1, le=MAX_TOP_K)
    include_text: bool = False
    use_neural_reranker: bool | None = None


def require_api_key(
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None),
) -> None:
    if not MENTOR_API_KEY:
        return

    bearer_token = None
    if authorization and authorization.casefold().startswith("bearer "):
        bearer_token = authorization[7:].strip()
    supplied = bearer_token or x_api_key

    if supplied != MENTOR_API_KEY:
        raise HTTPException(status_code=401, detail="Missing or invalid mentor API key.")


def rag_request(method: str, path: str, **kwargs: Any) -> dict[str, Any]:
    url = f"{RAG_BASE_URL}{path}"
    try:
        response = requests.request(method, url, timeout=REQUEST_TIMEOUT, **kwargs)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail=f"Internal RAG service call failed: {exc}") from exc
    return response.json()


def compact_source(source: dict[str, Any], include_text: bool = False) -> dict[str, Any]:
    compact = {
        "rank": source.get("rank"),
        "doc_id": source.get("doc_id"),
        "title": source.get("title"),
        "source_id": source.get("source_id"),
        "source_type": source.get("source_type"),
        "data_version": source.get("data_version"),
        "score": source.get("score"),
        "source_intent": source.get("source_intent"),
        "reasons": source.get("reasons", []),
    }

    confidence_signals = source.get("confidence_signals")
    if confidence_signals is None:
        confidence_signals = {
            "bm25_norm": source.get("bm25_norm"),
            "vector_norm": source.get("vector_norm"),
            "rerank_score": source.get("rerank_score"),
            "neural_rerank_norm": source.get("neural_rerank_norm"),
            "source_rank_score": source.get("source_rank_score"),
        }
    compact["confidence_signals"] = confidence_signals

    text = str(source.get("text") or "")
    if include_text and text:
        compact["text"] = text[:MAX_SOURCE_TEXT_CHARS]
    elif text:
        compact["snippet"] = text[:300]
    return compact


@app.get("/")
def root() -> dict[str, Any]:
    return {
        "service": "Single-Cell RAG Mentor API",
        "docs": "/docs",
        "health": "/health",
        "ask": "POST /ask",
        "search": "POST /search",
        "examples": "/examples",
        "auth_required": bool(MENTOR_API_KEY),
    }


@app.get("/health")
def health() -> dict[str, Any]:
    started = time.time()
    rag_health = rag_request("GET", "/health")
    return {
        "status": "ok",
        "mentor_api": "ok",
        "auth_required": bool(MENTOR_API_KEY),
        "rag_base_url": RAG_BASE_URL,
        "rag_status": rag_health.get("status"),
        "vector_backend": rag_health.get("vector_backend"),
        "reranker_loaded": rag_health.get("reranker_loaded"),
        "chunks": rag_health.get("chunks"),
        "latency_ms": round((time.time() - started) * 1000, 2),
    }


@app.get("/examples")
def examples() -> dict[str, Any]:
    return {
        "examples": [
            {"question": "What is a regulatory T cell?", "top_k": 5},
            {"question": "What markers identify Tregs?", "top_k": 5},
            {"question": "What does CD20 do?", "top_k": 5},
            {"question": "What is the official gene symbol for CD20?", "top_k": 5},
            {
                "question": "CELLxGENE Census evidence for regulatory T cell in blood normal 10x 3 v2",
                "top_k": 5,
            },
        ]
    }


@app.post("/ask", dependencies=[Depends(require_api_key)])
def ask(request: AskRequest) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "query": request.question.strip(),
        "top_k": request.top_k,
        "max_tokens": request.max_tokens,
        "temperature": request.temperature,
        "allow_low_confidence": request.allow_low_confidence,
    }
    if request.use_neural_reranker is not None:
        payload["use_neural_reranker"] = request.use_neural_reranker

    body = rag_request("POST", "/answer", json=payload)
    response: dict[str, Any] = {
        "question": body.get("query", request.question),
        "answer": body.get("answer"),
        "retrieval_quality": body.get("retrieval_quality"),
        "citation_check": body.get("citation_check"),
    }
    if request.include_sources:
        response["sources"] = [compact_source(source) for source in body.get("sources", [])]
    return response


@app.post("/search", dependencies=[Depends(require_api_key)])
def search(request: SearchRequest) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "query": request.query.strip(),
        "top_k": request.top_k,
    }
    if request.use_neural_reranker is not None:
        payload["use_neural_reranker"] = request.use_neural_reranker

    body = rag_request("POST", "/search", json=payload)
    return {
        "query": body.get("query", request.query),
        "retrieval_quality": body.get("retrieval_quality"),
        "results": [
            compact_source(result, include_text=request.include_text)
            for result in body.get("results", [])
        ],
    }
