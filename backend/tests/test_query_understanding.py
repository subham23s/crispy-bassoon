import unittest

from app.services.query_understanding import understand_query


class QueryUnderstandingTests(unittest.TestCase):
    def test_extracts_security_intent_and_identifier(self):
        result = understand_query("What is CVE-2024-12345 and which mitigation applies?")
        self.assertTrue(result.is_in_domain)
        self.assertEqual(result.intent, "vulnerability")
        self.assertEqual(result.entities[0], {"type": "cve", "value": "CVE-2024-12345"})
        self.assertTrue(result.requires_multihop_reasoning)

    def test_rejects_obvious_ood_query(self):
        result = understand_query("What is the capital of France?")
        self.assertFalse(result.is_in_domain)
        self.assertEqual(result.domain, "out_of_domain")

    def test_detects_hinglish(self):
        result = understand_query("CVE ko kaise patch karein aur iska impact kya hai?")
        self.assertEqual(result.language, "hinglish")
        self.assertTrue(result.is_in_domain)


if __name__ == "__main__":
    unittest.main()
