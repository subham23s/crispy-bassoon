import unittest

from app.models import Evidence
from app.verification.verification_pipeline import VerificationPipeline


class VerificationPipelineTests(unittest.TestCase):
    def setUp(self):
        self.evidence = [Evidence("chunk-1", "doc-1", "Source", "The control is required for all systems.", "Source", "test", "https://example.test", None, "", .9, .9, .9, 0, .9)]

    def test_explicit_heuristic_fallback_is_labeled(self):
        output = VerificationPipeline(provider="heuristic").verify("The control is required for all systems.", self.evidence)
        self.assertEqual(output.claims[0].status, "SUPPORTED")
        self.assertIn("heuristic", output.claims[0].explanation.lower())

    def test_unknown_claim_is_not_verified(self):
        output = VerificationPipeline(provider="heuristic").verify("The moon controls CVE remediation.", self.evidence)
        self.assertIn(output.claims[0].status, {"UNKNOWN", "PARTIALLY_SUPPORTED"})
        self.assertFalse(output.claims[0].citation_ids)


if __name__ == "__main__":
    unittest.main()
