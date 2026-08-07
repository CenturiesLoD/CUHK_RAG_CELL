#!/usr/bin/env python3
"""Lightweight guards for requests that should not enter RAG retrieval."""

from __future__ import annotations

import re

SPACE_RE = re.compile(r"\s+")
EDGE_PUNCT_RE = re.compile(r"^[\s\"'`.,!?;:()\[\]{}<>]+|[\s\"'`.,!?;:()\[\]{}<>]+$")

CONVERSATIONAL_EXACT = {
    "hi",
    "hello",
    "hey",
    "hiya",
    "yo",
    "hi there",
    "hello there",
    "hey there",
    "good morning",
    "good afternoon",
    "good evening",
    "thanks",
    "thank you",
    "thx",
    "ty",
    "ok",
    "okay",
    "test",
    "testing",
    "help",
}

CONVERSATIONAL_PATTERNS = [
    re.compile(r"^(how are you|how are you doing|who are you|what are you)$"),
    re.compile(r"^(what can you do|what do you do|can you help|can you help me)$"),
    re.compile(r"^(are you there|ping|hello world)$"),
]


def normalize_query_for_guard(query: str) -> str:
    text = EDGE_PUNCT_RE.sub("", str(query or "").casefold())
    text = SPACE_RE.sub(" ", text).strip()
    return text


def is_conversational_query(query: str) -> bool:
    """Return true only for clear chat/control inputs, not biomedical terms."""

    normalized = normalize_query_for_guard(query)
    if not normalized:
        return False
    if normalized in CONVERSATIONAL_EXACT:
        return True
    return any(pattern.fullmatch(normalized) for pattern in CONVERSATIONAL_PATTERNS)


def conversational_answer(query: str) -> str:
    normalized = normalize_query_for_guard(query)
    if normalized in {"thanks", "thank you", "thx", "ty"}:
        return "You're welcome. Ask me a single-cell biology question when ready."
    if normalized in {"test", "testing", "ping", "are you there", "hello world"}:
        return "The hosted RAG API is reachable. Ask me a single-cell biology question when ready."
    if normalized in {"help", "what can you do", "what do you do", "can you help", "can you help me", "who are you", "what are you"}:
        return "I can answer single-cell biology questions using the hosted RAG knowledge base."
    return "Hello. Ask me a single-cell biology question when ready."


def conversational_retrieval_quality() -> dict[str, object]:
    return {
        "confidence": "none",
        "should_answer": True,
        "reason": "conversational query bypassed retrieval",
        "top_doc_id": None,
        "top_title": None,
        "top_score": None,
        "score_gap": None,
        "bypassed_retrieval": True,
    }


def conversational_citation_check() -> dict[str, object]:
    return {
        "passed": True,
        "abstained": False,
        "source_ids": [],
        "citations": [],
        "valid_citations": [],
        "invalid_citations": [],
        "claim_count": 0,
        "citationless_claims": [],
        "bypassed_retrieval": True,
    }
