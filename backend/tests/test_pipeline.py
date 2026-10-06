import unittest

from app.services import DocumentStore, ResearchPipeline


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.pipeline = ResearchPipeline(DocumentStore())

    def test_answer_exposes_evidence_and_provenance(self):
        result = self.pipeline.ask("What does the NIST Cybersecurity Framework 2.0 provide?")
        self.assertTrue(result.evidence)
        self.assertIn("CERS", result.cers["name"])
        self.assertTrue(all(item.url for item in result.evidence))
        self.assertTrue(all(item.provenance["chunk_id"] == item.chunk_id for item in result.evidence))
        self.assertTrue(result.claims)

    def test_ood_abstains(self):
        result = self.pipeline.ask("Can you recommend a pizza recipe?")
        self.assertTrue(result.abstained)
        self.assertEqual(result.evidence, [])

    def test_unknown_identifier_abstains(self):
        result = self.pipeline.ask("Tell me about CVE-2099-99999")
        self.assertTrue(result.abstained)
        self.assertIn("identifier", result.limitations[0])

    def test_retrieval_is_scoped_to_owner_documents(self):
        self.pipeline.store.ingest_bytes(
            "alice.txt",
            b"Alice tenant security sentinel alpha-tenant-only.",
            owner_id="alice",
        )
        alice = self.pipeline.ask("What is the alpha-tenant-only security sentinel?", owner_id="alice")
        bob = self.pipeline.ask("What is the alpha-tenant-only security sentinel?", owner_id="bob")
        self.assertTrue(any("alpha-tenant-only" in item.text for item in alice.evidence))
        self.assertFalse(any("alpha-tenant-only" in item.text for item in bob.evidence))


if __name__ == "__main__":
    unittest.main()
