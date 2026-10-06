# CyberSecRA-X presentation outline

1. **Problem:** Retrieved cybersecurity information is not automatically trustworthy.
2. **Existing limitation:** Fluent answers can hide stale, conflicting, or unsupported claims.
3. **Research question:** How can an assistant show why an answer should be trusted?
4. **Innovation boundary:** Evidence-aware orchestration with provenance, claim verification, contradictions, CERS, and abstention.
5. **Architecture:** Web + mobile → API → query understanding → hybrid retrieval → ranking → verification → answer.
6. **ML/RAG pipeline:** lexical + TF-IDF baseline now; transformer/reranker adapters next.
7. **Knowledge graph:** bounded relationship endpoint with evidence, not invented edges.
8. **Security:** retrieved documents remain data; prompt-injection signals are isolated.
9. **Mobile:** shared backend, secure token storage, voice, camera, file upload, evidence panels.
10. **Evaluation:** CyberTrust-QA schema and computed baseline runner; no fabricated metrics.
11. **Limitations:** small corpus, heuristic verifier, pending live adapters and Flutter verification.
12. **Future work:** labeled benchmark, NLI, calibrated CERS, full ablations, production infrastructure.
