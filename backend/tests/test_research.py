import unittest

from app.research import compare_papers, extract_paper
from app.research.metrics import ndcg, precision_recall_f1


class ResearchTests(unittest.TestCase):
    def test_extracts_structured_paper_sections(self):
        paper = extract_paper("A Secure Study\nAlice, Bob\n2024\n# Abstract\nWe study logs.\n# Dataset\nCIC-IDS\n# Results\nF1 0.8")
        self.assertEqual(paper.title, "A Secure Study")
        self.assertEqual(paper.year, "2024")
        self.assertIn("CIC-IDS", paper.dataset)
        self.assertIn("F1", paper.evaluation_metrics)

    def test_comparison_is_explicit_about_limitations(self):
        first = extract_paper("One\n# Dataset\nD")
        second = extract_paper("Two\n# Dataset\nD")
        result = compare_papers([first, second])
        self.assertEqual(result["repeated_datasets"][0]["paper_count"], 2)
        self.assertTrue(result["limitations"])

    def test_metrics_are_computed(self):
        self.assertEqual(precision_recall_f1(["a", "b"], ["b"])["recall"], 0.5)
        self.assertGreater(ndcg({"a"}, ["a"]), 0.0)


if __name__ == "__main__":
    unittest.main()
