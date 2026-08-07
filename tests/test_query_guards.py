from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.query_guards import (  # noqa: E402
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
