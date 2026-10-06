"""Contract tests using explicit model-output fixtures, never model metrics."""
import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from ml.models.inference import ModelUnavailable, TransformerReranker, TransformerTextClassifier, reranker
from app.services.reranking import rerank
from app.services.pipeline import ResearchPipeline


class PipelineFixture:
    def __init__(self, rows, num_labels=2):
        self.model = SimpleNamespace(config=SimpleNamespace(num_labels=num_labels))
        self.rows = rows
        self.kwargs = {}

    def __call__(self, text, **kwargs):
        self.kwargs = kwargs
        return self.rows


class ModelInferenceTests(unittest.TestCase):
    def test_confident_negative_is_not_ranked_as_relevant(self):
        adapter = TransformerReranker("test-fixture")
        adapter._pipeline = PipelineFixture([{"label": "NOT_RELEVANT", "score": 0.99}, {"label": "RELEVANT", "score": 0.01}])
        self.assertEqual(adapter.score("question", "unrelated").score, 0.01)
        self.assertTrue(adapter._pipeline.kwargs["truncation"])

    def test_scalar_cross_encoder_requests_sigmoid(self):
        adapter = TransformerReranker("test-fixture")
        adapter._pipeline = PipelineFixture([{"label": "LABEL_0", "score": 0.2}], num_labels=1)
        self.assertEqual(adapter.score("question", "document").score, 0.2)
        self.assertEqual(adapter._pipeline.kwargs["function_to_apply"], "sigmoid")

    def test_ambiguous_binary_labels_require_configuration(self):
        adapter = TransformerReranker("test-fixture")
        adapter._pipeline = PipelineFixture([{"label": "LABEL_0", "score": 0.9}, {"label": "LABEL_1", "score": 0.1}])
        with self.assertRaises(ModelUnavailable):
            adapter.score("question", "document")
        with patch.dict(os.environ, {"RERANKER_RELEVANT_LABEL": "LABEL_1"}):
            self.assertEqual(adapter.score("question", "document").score, 0.1)

    def test_unknown_ood_labels_fail_instead_of_becoming_in_domain(self):
        adapter = TransformerTextClassifier("test-fixture", task="ood")
        adapter._pipeline = PipelineFixture([{"label": "LABEL_0", "score": 0.9}])
        with self.assertRaises(ModelUnavailable):
            adapter.predict("question")

    def test_checkpoint_cache_is_keyed_by_model_identity(self):
        self.assertIs(reranker("checkpoint-a"), reranker("checkpoint-a"))
        self.assertIsNot(reranker("checkpoint-a"), reranker("checkpoint-b"))

    def test_mid_batch_failure_preserves_original_ranking(self):
        evidence = ResearchPipeline().ask("What does NIST CSF provide?").evidence
        original = [item.to_dict() for item in evidence]
        with patch.dict(os.environ, {"RERANKER_PROVIDER": "transformer"}), patch("ml.models.inference.reranker") as factory:
            factory.return_value.score.side_effect = [SimpleNamespace(score=0.9, engine="fixture", model="fixture"), ModelUnavailable("interrupted")]
            ranked, status = rerank("query", evidence)
        self.assertEqual(status["status"], "unavailable")
        self.assertEqual([item.to_dict() for item in ranked], original)
