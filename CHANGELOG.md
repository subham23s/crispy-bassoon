# Changelog

## 1.0.0 — 2026-10-03 product source release

- Added tested configure/setup/build/up/status/test/down commands, source-aware production rebuilds, process ownership checks, readiness, request bounds, generated local signing credentials, and concurrency-safe refresh rotation.
- Repaired dependency advisories with executed FastAPI/Starlette/multipart/pytest and Next.js/Tailwind/PostCSS/sharp updates; npm audit and pip-audit report no known vulnerabilities for the checked release requirements.
- Verified 77 backend tests with live services/OCR, 12 web tests, TypeScript, 21-page production build, six Flutter tests/clean analysis, and 18 live web/API integration routes.
- Recomputed the seed-corpus evaluation and available B/C/E–J configurations; A/D and human calibration remain explicitly unavailable.
- Added source-only release packaging with required-file/content/CRC/credential verification, a per-file SHA-256 manifest, and final product documentation.
- Verified a fresh source-ZIP extraction with newly generated configuration/database, a native-filesystem production build, all 18 live web/API routes, and startup/status/shutdown.

## Unreleased — 2026-10-03 second continuation

- Completed live PostgreSQL answer/history/chunk contracts, psycopg URL selection, timestamp serialization, owner-preserving upserts, and database health reporting.
- Executed isolated PostgreSQL/pgvector, Redis, and Neo4j integration tests, including FastAPI query/history/export/upload with PostgreSQL.
- Added crash-released refresh locking, strict partial/failure accounting, configured data-directory propagation, fresh scheduled acquisition, stopped-worker status, and resumable bounded NVD updates.
- Fixed mobile tools compilation and preserved refreshed sessions on non-authentication retry failures; six Flutter tests and clean Dart analysis now execute through native-filesystem staging.
- Generated missing Android/iOS scaffolds without replacing existing files; fixed iOS root-level permission insertion and Android speech-service visibility. Environment checks now identify missing platform toolchains.
- Verified real image/scanned-PDF OCR and ruled-table extraction; retained camera-image page locators and explicit OCR failure semantics.
- Full installed backend suite: 75 passed, zero skips. Web: 12 passed; TypeScript and Python compilation passed. Fresh CISA worker: 1,733 actual records processed with zero failures.
- Expanded service/OCR CI and excluded runtime/local build artifacts. Details: `docs/reports/CONTINUATION_2026-10-03_02.md`.

## Unreleased — 2026-10-03 continuation

- Continued the existing filesystem implementation and retained the saved plan in `__agent__/plan.json`.
- Completed experiment create/edit/delete and measured-metric entry/comparison in the API and Next.js client; edits preserve metrics, values must be finite, and operations are owner-scoped.
- Added web answer-history access and research evidence bookmarking; repeated bookmarks update the existing snapshot in both SQLite and PostgreSQL adapters.
- Connected administrator source selection, refresh submission, job polling, and explicit partial/failure states. Authorization denials now return 403 rather than expiring valid sessions.
- Completed fallback SSE CORS, PATCH/DELETE preflight, timeline filters, and bounded malformed-request handling.
- Fixed reranker relevance scoring, checkpoint-keyed caches, offline model loading, atomic failure fallback, OOD label validation, and transformer training argument compatibility.
- Connected Flutter workspaces, notes, bookmarks, saved answer history, document deletion, quarantine display, and fuller citation/limitation views; added a widget-test fixture and Flutter CI job (SDK unavailable locally).
- Closed short-lived SQLite connections, corrected API-test runtime cleanup, added active Next.js-client tests and isolated live API smoke tooling, and verified PDF/DOCX export/extraction round trips.
- Verified 54 backend tests with one optional-service skip, 12 web tests, TypeScript, and Next.js production build. Added a build-only portable-copy command for the observed Windows-mount EPERM failure.
- Recomputed CyberTrust-QA and A–J artifacts from the real pipeline. B/C/E–J ran; unavailable A/D remain explicitly unmeasured.

## Unreleased — 2026-10-02

- Initialized the CyberSecRA-X monorepo with a local-first evidence pipeline.
- Added explainable query understanding, OOD abstention, hybrid lexical/TF-IDF retrieval, authority/recency ranking, provenance, claim verification, contradiction signals, CERS, and explicit limitations.
- Added PBKDF2 password hashing, HS256 access tokens, SQLite schema, owner-tagged document ingestion, prompt-injection scanning, log/IOC analysis, paper extraction, comparison helpers, and CyberTrust-QA evaluation.
- Added a responsive web dashboard and a Flutter mobile client using the same API paths.
- Added Docker/Compose, CI configuration, architecture/research/security documentation, and runnable tests.
- Added reproducible data bootstrap from an empty data directory: official ATT&CK/ATLAS/NVD/CISA/CWE/CAPEC/NIST/OWASP/OpenAlex acquisition, manifests, normalization, chunks, BM25, CPU embeddings, graph output, ML datasets, validation, and baseline training scripts.
- Tightened API auth, refresh-token rotation, user-document persistence/isolation/deletion, quarantining, and runtime loading of successful normalized bootstrap data.

## Scope note

The original October 2 increment was a dependency-light vertical slice. Subsequent work verifies local live-service adapters, OCR, Flutter analysis/tests, refresh cycles, and the extractable product lifecycle. Transformer/LLM-backed research, platform/device builds, production deployment, and human calibration retain explicit verification boundaries; see `docs/PRODUCT_RELEASE.md`.
