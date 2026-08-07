#!/usr/bin/env python3
"""Lightweight guards for requests that should not enter RAG retrieval."""

from __future__ import annotations

import re

SPACE_RE = re.compile(r"\s+")
EDGE_PUNCT_RE = re.compile(r"^[\s\"'`.,!?;:~()\[\]{}<>]+|[\s\"'`.,!?;:~()\[\]{}<>]+$")
CITATION_RE = re.compile(r"\s*\[[^\[\]\n]+\]")
GENE_SYMBOL_RE = re.compile(r"\b[A-Z][A-Z0-9-]{1,11}\b")
ONTOLOGY_ID_RE = re.compile(r"\b(?:CL|GO|HP|PATO|UBERON|HGNC|NCBIGene):[A-Za-z0-9_:-]+\b", re.IGNORECASE)

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
    "talk to me",
    "just talk to me",
    "just talk to me then",
    "chat with me",
    "just chat with me",
    "lets chat",
    "let's chat",
}

CONVERSATIONAL_PATTERNS = [
    re.compile(r"^h+i+$"),
    re.compile(r"^he+y+$"),
    re.compile(r"^yo+$"),
    re.compile(r"^(how are you|how are you doing|who are you|what are you)$"),
    re.compile(r"^(what can you do|what do you do|can you help|can you help me)$"),
    re.compile(r"^(are you there|ping|hello world)$"),
    re.compile(r"^(just\s+)?(?:talk|chat)\s+(?:to|with)\s+me(?:\s+(?:then|please))?$"),
    re.compile(r"^(?:let'?s|can we)\s+(?:talk|chat)$"),
]

BIOMEDICAL_HINTS = {
    "10x",
    "annotation",
    "antibody",
    "assay",
    "b cell",
    "cell",
    "cellmarker",
    "cellxgene",
    "census",
    "cl:",
    "cluster",
    "differentiation",
    "disease",
    "ensembl",
    "expression",
    "gene",
    "go:",
    "hgnc",
    "immune",
    "immunology",
    "marker",
    "markers",
    "ncbi",
    "ontology",
    "panglaodb",
    "protein",
    "scrna",
    "single-cell",
    "single cell",
    "t cell",
    "t-cell",
    "tissue",
    "transcriptomic",
    "treg",
    "uniprot",
    "uberon",
}

CONVERSATIONAL_RESPONSE_PATTERNS = [
    re.compile(r"^(hello|hi|hey)[.!]?(?: how can i (assist|help) you(?: today)?[.!]?)?$"),
    re.compile(r"^(hello|hi|hey)[.!]? ask me a single-cell biology question when ready[.!]?$"),
    re.compile(r"^i'?m here[.!]? what would you like to talk about[?]?$"),
    re.compile(r"^i can answer single-cell biology questions using the hosted rag knowledge base[.!]?$"),
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


def has_biomedical_intent(query: str) -> bool:
    """Return true when a query looks like it is asking for domain knowledge."""

    raw = str(query or "")
    normalized = normalize_query_for_guard(raw)
    if not normalized:
        return False
    if ONTOLOGY_ID_RE.search(raw):
        return True
    if any(hint in normalized for hint in BIOMEDICAL_HINTS):
        return True
    if GENE_SYMBOL_RE.search(raw) and not is_conversational_query(raw):
        return True
    return False


def conversational_answer(query: str) -> str:
    normalized = normalize_query_for_guard(query)
    if normalized in {"thanks", "thank you", "thx", "ty"}:
        return "You're welcome. Ask me a single-cell biology question when ready."
    if normalized in {"test", "testing", "ping", "are you there", "hello world"}:
        return "The hosted RAG API is reachable. Ask me a single-cell biology question when ready."
    if normalized in {"help", "what can you do", "what do you do", "can you help", "can you help me", "who are you", "what are you"}:
        return "I can answer single-cell biology questions using the hosted RAG knowledge base."
    if normalized in {"talk to me", "just talk to me", "just talk to me then", "chat with me", "just chat with me", "lets chat", "let's chat"}:
        return "I'm here. What would you like to talk about?"
    return "Hello. Ask me a single-cell biology question when ready."


def conversational_fallback_answer(query: str) -> str:
    """Return a citation-free response when a non-domain query has weak retrieval."""

    if is_conversational_query(query):
        return conversational_answer(query)
    return "I'm here. The RAG context did not find a relevant single-cell source for that, but we can still talk."


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


def strip_inline_citations(answer: str) -> str:
    return CITATION_RE.sub("", str(answer or "")).strip()


def is_conversational_response(answer: str) -> bool:
    """Detect short chat responses that should not receive RAG citations."""

    cleaned = strip_inline_citations(answer)
    normalized = normalize_query_for_guard(cleaned)
    if not normalized or "retrieved context is insufficient" in normalized:
        return False
    if any(pattern.fullmatch(normalized) for pattern in CONVERSATIONAL_RESPONSE_PATTERNS):
        return True
    if len(normalized.split()) <= 16 and (
        normalized.startswith(("hello", "hi", "hey", "i'm here", "im here"))
        and any(phrase in normalized for phrase in ("assist", "help", "ask me", "talk about"))
    ):
        return True
    return False
