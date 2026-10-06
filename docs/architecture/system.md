# CyberSecRA-X system architecture

```mermaid
flowchart LR
  Web[Web dashboard\nstatic Node client] --> API[FastAPI / fallback API]
  Mobile[Flutter mobile client] --> API
  API --> Auth[Auth service\nPBKDF2 + HS256]
  API --> Q[Query understanding\nintent / OOD / entities]
  Q --> R[Hybrid retrieval\nBM25-style + TF-IDF + RRF]
  R --> Rank[Authority + recency + graph-aware rank]
  Rank --> V[Claim verification\nprovenance / contradictions]
  V --> A[Evidence-aware answer\nCERS / abstention]
  API --> Ingest[Document ingestion\nchecksum / chunks / scan]
  Ingest --> Store[(SQLite local repository)]
  R --> Corpus[(Curated corpus + user documents)]
  API -. optional .-> LLM[OpenAI-compatible provider]
  API -. optional .-> Infra[(PostgreSQL / Redis / Neo4j)]
```

## Core trust boundary

Documents are data. They are never treated as system or developer instructions. Every answer carries a chain:

`claim -> chunk -> document -> source URL -> publication/update metadata -> retrieval timestamp`

## Current implementation versus adapters

The local increment implements the query-to-evidence path with standard-library algorithms. FastAPI, PyMuPDF, SQLAlchemy, PostgreSQL/pgvector, Redis, Neo4j, transformer embeddings, cross-encoder reranking, and an approved LLM provider are pinned as opt-in dependencies. `/health/detailed` reports the local degraded mode rather than implying those services are connected.
