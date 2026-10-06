# Architecture decision log

## D-001 — Build a local-first vertical slice first

- **Decision:** Ship a deterministic evidence pipeline with a curated corpus and explicit adapters before requiring external credentials or large model downloads.
- **Reason:** The core trust question can be tested without pretending a live provider or downloaded model is available. It also keeps local development reproducible on CPU-only machines.
- **Alternatives:** Require an LLM/vector database at startup; use a chatbot mock.
- **Trade-offs:** Local retrieval is lightweight rather than state-of-the-art; a later deployment must configure stronger embedding/reranking providers and refresh feeds.

## D-002 — FastAPI with a standard-library fallback

- **Decision:** FastAPI/Uvicorn is the documented production API, while the same route/service layer can run on Python's `http.server` when dependencies are absent.
- **Reason:** The base WSL-mounted project folder cannot create a venv because chmod is restricted, and system pip/FastAPI were initially absent. A project-local-compatible `/tmp/cybersecra-venv` enabled FastAPI verification without modifying system Python; the fallback still keeps the repo runnable on constrained hosts.
- **Trade-offs:** The fallback is not a replacement for hardened production serving. It is labeled in `/health` and should sit behind Uvicorn/reverse proxy in deployment.

## D-003 — SQLite repository boundary

- **Decision:** Use a normalized SQLite schema for the local increment and keep repository methods separate from domain services.
- **Reason:** It requires no external daemon and preserves user, workspace, document, conversation, claim, and audit concepts. PostgreSQL/pgvector/Redis/Neo4j configuration points are documented.
- **Trade-offs:** The current backend does not yet claim to persist vectors in pgvector or relationships in Neo4j; those are integration milestones, not fake local results.

## D-004 — CERS is a project-defined metric

- **Decision:** Expose authority, relevance, entailment, agreement, recency, and retrieval-confidence components under the Cyber Evidence Reliability Score.
- **Reason:** Users need an inspectable signal, but it must not be presented as calibrated truth probability.
- **Trade-offs:** Scores require validation against annotated benchmark data before they can support research claims.

## D-005 — Retrieved text cannot become instructions

- **Decision:** Scan content for injection signals, isolate it as evidence, and never pass it as system policy.
- **Reason:** This is a primary RAG trust boundary and supports controlled security evaluation without offensive automation.
- **Trade-offs:** Pattern scanning has false positives/negatives and must be supplemented by model and deployment controls.
