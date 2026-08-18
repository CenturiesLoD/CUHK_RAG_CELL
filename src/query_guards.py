#!/usr/bin/env python3
"""Lightweight guards for requests that should not enter RAG retrieval."""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any

SPACE_RE = re.compile(r"\s+")
EDGE_PUNCT_RE = re.compile(r"^[\s\"'`.,!?;:~()\[\]{}<>]+|[\s\"'`.,!?;:~()\[\]{}<>]+$")
CITATION_RE = re.compile(r"\s*\[[^\[\]\n]+\]")
GENE_SYMBOL_RE = re.compile(r"\b[A-Z][A-Z0-9-]{1,11}\b")
ONTOLOGY_ID_RE = re.compile(r"\b(?:CL|GO|HP|PATO|UBERON|HGNC|NCBIGene):[A-Za-z0-9_:-]+\b", re.IGNORECASE)
INTENT_CONVERSATIONAL = "conversational"
INTENT_BIOMEDICAL_RAG = "biomedical_rag"
INTENT_UNCLEAR = "unclear"

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
    "no",
    "nope",
    "nah",
    "no thanks",
    "not now",
    "stop",
    "cancel",
    "nevermind",
    "never mind",
    "i don't want to",
    "i dont want to",
    "i do not want to",
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
    re.compile(r"^(?:no|nope|nah)(?:\s+thanks?)?$"),
    re.compile(r"^(?:not\s+now|stop|cancel|never\s*mind)$"),
    re.compile(r"^i\s+(?:do\s+not|don'?t|dont)\s+want(?:\s+to)?(?:\s+(?:ask|chat|talk|do\s+that|right\s+now|now|today))?$"),
    re.compile(r"^(just\s+)?(?:talk|chat)\s+(?:to|with)\s+me(?:\s+(?:then|please))?$"),
    re.compile(r"^(?:let'?s|can we)\s+(?:talk|chat)$"),
    re.compile(r"^(?:really\??\s*)?is\s+this\s+(?:a\s+)?single[- ]cell biology question\??$"),
    re.compile(r"^(?:really\??\s*)?(?:is|was)\s+that\s+(?:a\s+)?single[- ]cell biology question\??$"),
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
    re.compile(r"^i\s+(?:do\s+not|don'?t|dont)\s+want(?:\s+to)?[.!]?$"),
    re.compile(r"^(?:that'?s|thats) okay[.!]? we can pause(?:,? or you can ask something else whenever you'?re ready)?[.!]?$"),
    re.compile(r"^i can answer single-cell biology questions using the hosted rag knowledge base[.!]?$"),
]

#IF YOURE READING THIS HIIII

CONVERSATIONAL_META_PATTERNS = [
    # Confirmation / rhetorical questions
    re.compile(
        r"^(?:really|seriously|wait)[,!]?\s+"
        r"(?:is|are|was|were|does|do|did|can|could|should|would)\b.+\?$"
    ),

    # "Is this ...?" / "Are you saying ...?"
    re.compile(
        r"^(?:is|are|was|were)\s+(?:this|that|it)\b.+\?$"
    ),
    re.compile(
        r"^(?:are|do)\s+you\s+(?:saying|mean|think|really\s+mean)\b.+\?$"
    ),

    # Explicit meta-conversation
    re.compile(
        r"^(?:what|why|how)\s+do\s+you\s+mean\b.+\??$"
    ),
    re.compile(
        r"^(?:are\s+you\s+sure|you'?re\s+sure)\b.+\??$"
    ),
]



def _clean_signal_values(values: Iterable[Any] | None, *, limit: int = 5) -> list[str]:
    if values is None:
        return []
    cleaned: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        cleaned.append(text)
        if len(cleaned) >= limit:
            break
    return cleaned


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


def conversational_intent_signals(query: str) -> list[str]:
    normalized = normalize_query_for_guard(query)
    if not normalized:
        return []
    if normalized in CONVERSATIONAL_EXACT:
        return [f"exact conversational phrase: {normalized}"]
    for pattern in CONVERSATIONAL_PATTERNS:
        if pattern.fullmatch(normalized):
            return [f"conversational pattern: {pattern.pattern}"]
    return []

def conversational_meta_signals(query: str) -> list[str]:
    normalized = normalize_query_for_guard(query)

    if not normalized:
        return []

    for pattern in CONVERSATIONAL_META_PATTERNS:
        if pattern.fullmatch(normalized):
            return [f"meta-conversational pattern: {pattern.pattern}"]

    return []


def biomedical_intent_signals(
    query: str,
    *,
    alias_target_ids: Iterable[Any] | None = None,
) -> list[str]:
    """Return deterministic signals that a query should enter RAG retrieval."""

    raw = str(query or "")
    normalized = normalize_query_for_guard(raw)
    signals: list[str] = []
    if not normalized:
        return signals

    ontology_matches = _clean_signal_values(match.group(0) for match in ONTOLOGY_ID_RE.finditer(raw))
    if ontology_matches:
        signals.append("ontology/gene identifier: " + ", ".join(ontology_matches))

    alias_ids = _clean_signal_values(alias_target_ids)
    if alias_ids:
        signals.append("exact corpus alias match: " + ", ".join(alias_ids))

    hint_matches = [hint for hint in sorted(BIOMEDICAL_HINTS, key=len, reverse=True) if hint in normalized]
    if hint_matches:
        signals.append("biomedical/domain term: " + ", ".join(hint_matches[:5]))

    gene_symbols = _clean_signal_values(match.group(0) for match in GENE_SYMBOL_RE.finditer(raw))
    if gene_symbols and not is_conversational_query(raw):
        signals.append("gene-symbol-like token: " + ", ".join(gene_symbols))

    return signals


def has_biomedical_intent(query: str) -> bool:
    """Return true when a query looks like it is asking for domain knowledge."""

    return bool(biomedical_intent_signals(query))


def retrieval_intent_signals(
    retrieval_quality: dict[str, Any] | None,
    results: list[dict[str, Any]] | None,
) -> list[str]:
    if not retrieval_quality or not results:
        return []

    top = results[0]
    reasons = [str(reason) for reason in top.get("reasons", [])]
    exact_match = any(reason.startswith("exact ") for reason in reasons)
    bm25_norm = float(top.get("bm25_norm") or 0.0)
    rerank_score = float(top.get("rerank_score") or 0.0)
    neural_rerank_norm = float(top.get("neural_rerank_norm") or 0.0)
    confidence = str(retrieval_quality.get("confidence") or "")

    signals: list[str] = []
    if exact_match:
        signals.append("retrieval exact alias/name/id match")
    if confidence in {"high", "medium"} and (bm25_norm >= 0.08 or rerank_score >= 0.45 or neural_rerank_norm >= 0.55):
        signals.append(
            "retrieval score support: "
            f"confidence={confidence}, bm25_norm={bm25_norm:.3f}, "
            f"rerank={rerank_score:.3f}, neural={neural_rerank_norm:.3f}"
        )
    return signals


def has_only_soft_domain_hints(signals: Iterable[Any]) -> bool:
    signal_text = [str(signal) for signal in signals]
    return bool(signal_text) and all(signal.startswith("biomedical/domain term") for signal in signal_text)


def intent_decision(
    *,
    intent: str,
    confidence: str,
    reason: str,
    stage: str,
    signals: Iterable[Any] | None = None,
    needs_retrieval: bool = False,
) -> dict[str, Any]:
    return {
        "intent": intent,
        "confidence": confidence,
        "reason": reason,
        "stage": stage,
        "signals": _clean_signal_values(signals, limit=10),
        "needs_retrieval": needs_retrieval,
    }


def classify_query_intent(
    query: str,
    *,
    alias_target_ids: Iterable[Any] | None = None,
    retrieval_quality: dict[str, Any] | None = None,
    results: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Route a query before RAG, then optionally refine after retrieval."""

    normalized = normalize_query_for_guard(query)
    if not normalized:
        return intent_decision(
            intent=INTENT_UNCLEAR,
            confidence="low",
            reason="empty query",
            stage="pre_retrieval",
            needs_retrieval=False,
        )

    biomedical_signals = biomedical_intent_signals(query, alias_target_ids=alias_target_ids)
    conversational_signals = conversational_intent_signals(query)
    meta_conversational_signals = conversational_meta_signals(query)

    alias_only_biomedical = bool(biomedical_signals) and all(
        signal.startswith("exact corpus alias match") for signal in biomedical_signals
    )

    if conversational_signals and (
        not biomedical_signals
        or alias_only_biomedical
        or has_only_soft_domain_hints(biomedical_signals)
    ):
        return intent_decision(
            intent=INTENT_CONVERSATIONAL,
            confidence="high",
            reason="hard conversational signal",
            stage="pre_retrieval",
            signals=conversational_signals,
            needs_retrieval=False,
        )

    if meta_conversational_signals:
        return intent_decision(
            intent=INTENT_CONVERSATIONAL,
            confidence="high",
            reason="meta-conversational question",
            stage="pre_retrieval",
            signals=meta_conversational_signals,
            needs_retrieval=False,
        )

    if biomedical_signals:
        return intent_decision(
            intent=INTENT_BIOMEDICAL_RAG,
            confidence="high",
            reason="hard biomedical signal",
            stage="pre_retrieval",
            signals=biomedical_signals,
            needs_retrieval=True,
        )
    if conversational_signals:
        return intent_decision(
            intent=INTENT_CONVERSATIONAL,
            confidence="high",
            reason="hard conversational signal",
            stage="pre_retrieval",
            signals=conversational_signals,
            needs_retrieval=False,
        )

    retrieval_signals = retrieval_intent_signals(retrieval_quality, results)
    if retrieval_quality is not None:
        if retrieval_signals:
            return intent_decision(
                intent=INTENT_BIOMEDICAL_RAG,
                confidence="medium",
                reason="ambiguous query gained retrieval support",
                stage="post_retrieval",
                signals=retrieval_signals,
                needs_retrieval=True,
            )
        return intent_decision(
            intent=INTENT_UNCLEAR,
            confidence="low",
            reason="ambiguous query lacked reliable biomedical retrieval support",
            stage="post_retrieval",
            signals=[str(retrieval_quality.get("reason") or "weak retrieval support")],
            needs_retrieval=False,
        )

    return intent_decision(
        intent=INTENT_UNCLEAR,
        confidence="low",
        reason="no hard biomedical or conversational signal",
        stage="pre_retrieval",
        needs_retrieval=True,
    )


def conversational_answer(query: str) -> str:
    normalized = normalize_query_for_guard(query)
    if normalized in {"thanks", "thank you", "thx", "ty"}:
        return "You're welcome. Ask me a single-cell biology question when ready."
    if normalized in {"test", "testing", "ping", "are you there", "hello world"}:
        return "The hosted RAG API is reachable. Ask me a single-cell biology question when ready."
    if normalized in {"help", "what can you do", "what do you do", "can you help", "can you help me", "who are you", "what are you"}:
        return "I can answer single-cell biology questions using the hosted RAG knowledge base."
    if "single cell biology question" in normalized or "single-cell biology question" in normalized:
        return "Not as written. Ask me about a cell type, marker, gene, tissue, ontology term, or dataset when ready."
    if normalized in {
        "no",
        "nope",
        "nah",
        "no thanks",
        "not now",
        "stop",
        "cancel",
        "nevermind",
        "never mind",
        "i don't want to",
        "i dont want to",
        "i do not want to",
    }:
        return "That's okay. We can pause, or you can ask something else whenever you're ready."
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
