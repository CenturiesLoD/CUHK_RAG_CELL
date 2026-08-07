from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.cell_rag_cli import Style, format_answer, prompt_api_key, wrap_text  # noqa: E402


class RagChatCliTests(unittest.TestCase):
    def test_wrap_text_keeps_content_readable(self) -> None:
        text = "regulatory T cells suppress immune responses and express FOXP3"
        wrapped = wrap_text(text, width=32)
        self.assertIn("regulatory T cells", wrapped)
        self.assertLessEqual(max(len(line) for line in wrapped.splitlines()), 32)

    def test_format_answer_is_clean_user_output(self) -> None:
        response = {
            "answer": "Regulatory T cells are T cells involved in immune regulation [CL:0000815].",
            "retrieval_quality": {"confidence": "high"},
            "citation_check": {"passed": True},
            "sources": [
                {
                    "doc_id": "CL:0000815",
                    "title": "regulatory T cell",
                    "source_id": "cell_ontology_cl_obo",
                }
            ],
        }
        output = format_answer(response, style=Style(False), show_sources=True)
        self.assertIn("Answer", output)
        self.assertIn("Confidence: high", output)
        self.assertIn("Citation check: passed", output)
        self.assertIn("CL:0000815 | regulatory T cell | cell_ontology_cl_obo", output)
        self.assertNotIn("{", output)

    def test_prompt_api_key_uses_existing_value(self) -> None:
        self.assertEqual(prompt_api_key("existing-key"), "existing-key")


if __name__ == "__main__":
    unittest.main()
