# Methodology

## Baseline

The runnable baseline uses a curated, attributed development corpus covering NIST CSF, MITRE ATT&CK T1059, CISA KEV, NVD API guidance, and OWASP LLM application security. It is explicitly not a current feed.

## Retrieval

For every chunk, compute a BM25-style lexical signal and TF-IDF-lite cosine signal. Query variants are ranked separately and fused with reciprocal rank fusion. Authority and recency are metadata signals, not substitutes for entailment.

## Verification

Answers are split into sentences. Token overlap against attributed chunks produces a transparent support baseline. Conflicts are flagged when passages share substantive terms but differ in polarity. This is a heuristic baseline, not a validated NLI model.

## Experiments to run next

1. Annotate CyberTrust-QA with claim/chunk support labels.
2. Compare LLM-only, lexical RAG, hybrid RAG, reranked RAG, and verified RAG.
3. Measure retrieval, citation, abstention, contradiction, and OOD metrics.
4. Calibrate CERS against human labels and report confidence intervals.
