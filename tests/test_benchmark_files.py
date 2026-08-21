from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class BenchmarkFileTests(unittest.TestCase):
    def test_single_cell_benchmark_jsonl_is_valid(self) -> None:
        path = ROOT / "eval" / "single_cell_benchmark.jsonl"
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        self.assertGreaterEqual(len(rows), 40)
        ids = [row["id"] for row in rows]
        self.assertEqual(len(ids), len(set(ids)))
        for row in rows:
            with self.subTest(row=row["id"]):
                self.assertIsInstance(row.get("query"), str)
                self.assertTrue(row["query"].strip())
                self.assertIsInstance(row.get("category"), str)
                self.assertIn(row.get("expected_route"), {"biomedical_rag", "conversational"})
                self.assertIsInstance(row.get("top_k", 0), int)
                self.assertIsInstance(row.get("max_tokens", 0), int)

    def test_benchmark_has_expected_coverage(self) -> None:
        rows = [
            json.loads(line)
            for line in (ROOT / "eval" / "single_cell_benchmark.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        categories = {row["category"] for row in rows}
        expected = {
            "guardrail_chat",
            "cell_type_definition",
            "ontology_id_lookup",
            "gene_normalization",
            "gene_reference",
            "protein_function",
            "cell_marker_question",
            "cellxgene_summary",
            "cross_source_synthesis",
            "hard_negative",
        }
        self.assertTrue(expected <= categories)

    def test_online_baseline_template_has_scoring_columns(self) -> None:
        header = (
            ROOT / "eval" / "online_baseline_scores_template.csv"
        ).read_text(encoding="utf-8").splitlines()[0].split(",")
        for column in [
            "case_id",
            "system",
            "correctness_0_3",
            "citation_support_0_3",
            "source_specificity_0_3",
            "scope_handling_0_3",
            "hallucination_penalty_0_3",
        ]:
            self.assertIn(column, header)


if __name__ == "__main__":
    unittest.main()
