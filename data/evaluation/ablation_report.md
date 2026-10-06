# CyberSecRA-X A-J ablation report

B is lexical; C is the hybrid baseline; D-I each add exactly one component to C (not cumulative). J enables all configured components. B-J use the same deterministic evidence generator to isolate retrieval/verification changes. NOT_RUN rows contain no metrics. Unlabeled claim support is not ground-truth accuracy.

| Configuration | Status | Key metrics | Reason |
|---|---|---|---|
| A LLM only | not_run |  | LLM_PROVIDER and LLM_API_KEY are not configured |
| B Basic RAG | measured | mean_recall_at_10=1.0, mean_reciprocal_rank=1.0, abstention_rate=0.3333333333333333 |  |
| C Hybrid RAG | measured | mean_recall_at_10=1.0, mean_reciprocal_rank=1.0, abstention_rate=0.3333333333333333 |  |
| D Hybrid RAG + reranker | not_run |  | Cross-encoder unavailable: {'provider': 'none', 'status': 'not_configured', 'model': 'cross-encoder/ms-marco-MiniLM-L-6-v2'} |
| E Hybrid + source priority | measured | mean_recall_at_10=1.0, mean_reciprocal_rank=1.0, abstention_rate=0.3333333333333333 |  |
| F Hybrid + temporal ranking | measured | mean_recall_at_10=1.0, mean_reciprocal_rank=1.0, abstention_rate=0.3333333333333333 |  |
| G Hybrid + knowledge graph | measured | mean_recall_at_10=1.0, mean_reciprocal_rank=1.0, abstention_rate=0.3333333333333333 |  |
| H Hybrid + citation verification | measured | mean_recall_at_10=1.0, mean_reciprocal_rank=1.0, abstention_rate=0.3333333333333333 |  |
| I Hybrid + contradiction detection | measured | mean_recall_at_10=1.0, mean_reciprocal_rank=1.0, abstention_rate=0.3333333333333333 |  |
| J Complete configured CyberSecRA-X | measured | mean_recall_at_10=1.0, mean_reciprocal_rank=1.0, abstention_rate=0.3333333333333333, mean_cers=0.4699 |  |
