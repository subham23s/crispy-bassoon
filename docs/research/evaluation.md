# Evaluation plan

The benchmark schema is in `data/evaluation/cybertrust_qa.json`; the runner is `scripts/evaluation/evaluate_cybertrust.py`.

Required metrics:

- retrieval: Recall@K, Precision@K, MRR, NDCG;
- classification/OOD: accuracy, precision, recall, F1, AUROC when scores exist;
- QA: exact match, token F1, semantic similarity;
- citations: citation precision, citation recall, claim support rate;
- reliability: abstention accuracy, unsupported-claim rate, hallucination rate, contradiction detection performance;
- security: prompt-injection detection precision/recall over labeled test cases.

The current runner computes per-item CERS, abstention, claim support rate, exact match, token F1, and evidence count from an actual local run. The generated JSON must be treated as a baseline measurement, not a published result.
