# Ranking and authority methodology

For each chunk, the current baseline computes:

- `lexical`: BM25-style term-frequency score;
- `semantic`: TF-IDF-lite cosine score;
- `rrf`: reciprocal rank fusion of lexical, semantic, and graph-term orderings;
- `authority`: source metadata score from the curated record;
- `recency`: bounded age decay from update/publication date;
- `relevance`: normalized lexical/semantic combination;
- `graph`: overlap with security relationship vocabulary.

The local final score is:

```text
0.25 * normalized_rrf
+ 0.25 * dense_similarity
+ 0.25 * normalized_lexical
+ 0.15 * authority
+ 0.07 * recency
+ 0.03 * graph
```

When a query contains an exact CVE/CWE/CAPEC/ATT&CK identifier, exact-identifier chunks are preferred. When it names an authority such as NIST or CISA, source matching is restricted to that authority before scoring. This prevents generic expanded-query terms from turning unrelated passages into citations.

These coefficients are configurable by changing the retriever and are a project baseline, not a scientific authority estimator. The UI exposes component values and the ranking explanation so a researcher can inspect why a source outranked another. Authority does not override claim entailment or conflict evidence.
