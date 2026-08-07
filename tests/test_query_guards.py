from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.query_guards import (  # noqa: E402
    INTENT_BIOMEDICAL_RAG,
    INTENT_CONVERSATIONAL,
    INTENT_UNCLEAR,
    classify_query_intent,
    conversational_fallback_answer,
    conversational_answer,
    conversational_citation_check,
    conversational_retrieval_quality,
    has_biomedical_intent,
    is_conversational_query,
    is_conversational_response,
    strip_inline_citations,
)


class QueryGuardTests(unittest.TestCase):
    def test_greetings_bypass_retrieval(self) -> None:
        for query in ["hi", "hi??", "hiii~", "hello!", "Hey there", "good morning", "thanks", "test"]:
            with self.subTest(query=query):
                self.assertTrue(is_conversational_query(query))

    def test_direct_chat_requests_bypass_retrieval(self) -> None:
        for query in ["Just talk to me then", "talk to me", "chat with me", "let's chat"]:
            with self.subTest(query=query):
                self.assertTrue(is_conversational_query(query))

    def test_biomedical_short_queries_do_not_bypass_retrieval(self) -> None:
        for query in ["CD20", "FOXP3", "T cell", "What is Treg?", "HGNC:374", "CL:0000815"]:
            with self.subTest(query=query):
                self.assertFalse(is_conversational_query(query))
                self.assertTrue(has_biomedical_intent(query))

    def test_router_prefers_hard_biomedical_signals(self) -> None:
        for query in ["CD20", "FOXP3", "T cell", "What is Treg?", "HGNC:374", "CL:0000815"]:
            with self.subTest(query=query):
                decision = classify_query_intent(query)
                self.assertEqual(decision["intent"], INTENT_BIOMEDICAL_RAG)
                self.assertEqual(decision["stage"], "pre_retrieval")
                self.assertTrue(decision["needs_retrieval"])

    def test_router_uses_alias_hits_as_biomedical_signal(self) -> None:
        decision = classify_query_intent("regulatory t lymphocyte", alias_target_ids=["CL:0000815"])

        self.assertEqual(decision["intent"], INTENT_BIOMEDICAL_RAG)
        self.assertIn("exact corpus alias match", " ".join(decision["signals"]))

    def test_router_does_not_let_alias_noise_override_chat(self) -> None:
        decision = classify_query_intent("Just talk to me then", alias_target_ids=["NCBIGene:4321"])

        self.assertEqual(decision["intent"], INTENT_CONVERSATIONAL)
        self.assertFalse(decision["needs_retrieval"])

    def test_router_prefers_hard_conversational_signals(self) -> None:
        for query in ["hiii~", "Just talk to me then", "ok"]:
            with self.subTest(query=query):
                decision = classify_query_intent(query)
                self.assertEqual(decision["intent"], INTENT_CONVERSATIONAL)
                self.assertFalse(decision["needs_retrieval"])

    def test_router_uses_retrieval_for_ambiguous_queries(self) -> None:
        quality = {"confidence": "medium", "reason": "top result has partial retrieval support"}
        results = [{"bm25_norm": 0.12, "rerank_score": 0.1, "neural_rerank_norm": 0.0, "reasons": ["bm25 lexical match"]}]

        decision = classify_query_intent("regulatory suppressor population", retrieval_quality=quality, results=results)

        self.assertEqual(decision["intent"], INTENT_BIOMEDICAL_RAG)
        self.assertEqual(decision["stage"], "post_retrieval")

    def test_router_keeps_weak_ambiguous_queries_unclear(self) -> None:
        quality = {"confidence": "low", "reason": "top result has weak retrieval support"}
        results = [{"bm25_norm": 0.0, "rerank_score": 0.0, "neural_rerank_norm": 0.0, "reasons": ["qwen3 vector match"]}]

        decision = classify_query_intent("what is the weather", retrieval_quality=quality, results=results)

        self.assertEqual(decision["intent"], INTENT_UNCLEAR)
        self.assertEqual(decision["stage"], "post_retrieval")

    def test_conversational_response_has_no_citations_or_sources(self) -> None:
        answer = conversational_answer("hi")
        quality = conversational_retrieval_quality()
        citation_check = conversational_citation_check()

        self.assertIn("Hello", answer)
        self.assertNotIn("[", answer)
        self.assertEqual(quality["confidence"], "none")
        self.assertTrue(quality["bypassed_retrieval"])
        self.assertTrue(citation_check["passed"])
        self.assertEqual(citation_check["source_ids"], [])
        self.assertEqual(citation_check["citations"], [])
        self.assertEqual(citation_check["claim_count"], 0)

    def test_non_domain_fallback_has_no_citations(self) -> None:
        answer = conversational_fallback_answer("what is the weather")

        self.assertNotIn("[", answer)
        self.assertIn("we can still talk", answer)

    def test_conversational_model_output_is_not_citable(self) -> None:
        answer = "Hello! How can I assist you today [HGNC:374]?"

        self.assertTrue(is_conversational_response(answer))
        self.assertEqual(strip_inline_citations(answer), "Hello! How can I assist you today?")


if __name__ == "__main__":
    unittest.main()
