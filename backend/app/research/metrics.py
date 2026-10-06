"""Dependency-light evaluation metrics for reproducible benchmark scripts."""
from __future__ import annotations

import math
from collections import Counter
from typing import Iterable


def precision_recall_f1(expected: Iterable[str], predicted: Iterable[str]) -> dict[str, float]:
    expected_set, predicted_set = set(expected), set(predicted)
    true_positive = len(expected_set & predicted_set)
    precision = true_positive / len(predicted_set) if predicted_set else 0.0
    recall = true_positive / len(expected_set) if expected_set else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"precision": precision, "recall": recall, "f1": f1}


def reciprocal_rank(relevant_ids: set[str], ranked_ids: list[str]) -> float:
    for index, item in enumerate(ranked_ids, start=1):
        if item in relevant_ids:
            return 1 / index
    return 0.0


def ndcg(relevant_ids: set[str], ranked_ids: list[str], k: int = 10) -> float:
    # A document can contribute only once; retrieval returns multiple chunks
    # from one document and counting duplicates would produce an impossible
    # NDCG greater than one.
    unique_ranked = list(dict.fromkeys(ranked_ids))[:k]

    def dcg(items: list[str]) -> float:
        return sum((1 / math.log2(index + 2)) for index, item in enumerate(items) if item in relevant_ids)

    observed = dcg(unique_ranked)
    ideal = dcg(list(relevant_ids)[:k])
    return observed / ideal if ideal else 0.0


def exact_match(expected: str, predicted: str) -> float:
    return float(expected.strip().casefold() == predicted.strip().casefold())


def token_f1(expected: str, predicted: str) -> float:
    left, right = Counter(expected.casefold().split()), Counter(predicted.casefold().split())
    overlap = sum((left & right).values())
    if not overlap:
        return 0.0
    precision = overlap / max(1, sum(right.values()))
    recall = overlap / max(1, sum(left.values()))
    return 2 * precision * recall / (precision + recall)
