# Evidence-aware RAG pipeline

1. **Understand:** deterministic intent, domain, language, complexity, entities, temporal and multi-hop requirements.
2. **Expand:** produce security-oriented query variants and safe subqueries.
3. **Retrieve:** lexical scoring, TF-IDF-lite semantic scoring, metadata, and graph-term signals.
4. **Fuse:** reciprocal rank fusion keeps lexical and semantic evidence visible rather than replacing one with the other.
5. **Rank:** authority, recency, relevance, graph relevance, and provenance contribute to an explainable final score.
6. **Generate:** the local provider composes from retrieved attributed passages. An external provider is optional and cannot change system policy.
7. **Verify:** split into claims, match to chunks, assign `SUPPORTED`, `PARTIALLY_SUPPORTED`, or `UNSUPPORTED`, and attach chunk identifiers.
8. **Cross-check:** opposing-polarity passages are surfaced as possible contradictions.
9. **Score:** CERS combines six components with configurable weights and states that it is project-defined.
10. **Abstain:** out-of-domain, unknown identifiers, low evidence, or excessive unsupported content produce explicit abstention.

The current local generator intentionally quotes/summarizes retrieved text rather than inventing a fluent answer. This is a safer baseline while model-backed generation and NLI validation are evaluated against CyberTrust-QA.
