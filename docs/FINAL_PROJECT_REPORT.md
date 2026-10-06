# CyberSecRA-X final project report — source release 1.0.0

Updated for the 2026-10-03 product release. The authoritative current execution record is [PRODUCT_RELEASE.md](PRODUCT_RELEASE.md). The [second continuation](reports/CONTINUATION_2026-10-03_02.md) records earlier implementation and corpus checks.

## Abstract

CyberSecRA-X is an evidence-aware defensive cybersecurity research platform. This increment implements a reproducible local pipeline that understands cybersecurity queries, retrieves attributed chunks through hybrid lexical/semantic ranking, exposes provenance, verifies claims, flags potential contradictions, calculates a project-defined CERS signal, and abstains when evidence is not sufficient.

## Introduction and problem statement

Cybersecurity information changes quickly and authoritative sources can disagree. A fluent answer without a traceable source is not sufficient for research or defensive decisions. The system is built around: `retrieve → rank → correlate → verify → cross-check → score → explain → cite → abstain`.

## Existing systems and research boundary

The project does not claim that prior systems omit evidence verification, nor that CERS is scientifically validated. It provides an implementation baseline and a benchmark schema for testing those claims responsibly.

## Proposed system

- deterministic query understanding and OOD classification;
- checksum-aware document ingestion and chunk provenance;
- BM25-style lexical + TF-IDF-lite semantic retrieval with reciprocal rank fusion;
- authority, recency, graph-term, and relevance ranking;
- claim statuses and citation chunk IDs;
- possible contradiction detection;
- explicit abstention and limitations;
- PBKDF2/HS256 authentication and SQLite schema;
- paper extraction/comparison helpers;
- defensive log and IOC analysis;
- RAG prompt-injection signal scanner;
- web and mobile clients using the same API;
- CyberTrust-QA computed evaluation runner.

## Architecture

See [system architecture](architecture/system.md) and [RAG pipeline](architecture/rag-pipeline.md). FastAPI/Uvicorn is the verified API runtime in the project-local environment; the standard-library fallback remains available when dependencies are absent.

## Data and sources

The repository contains a reproducible bootstrap pipeline from an empty data directory. A historical live `--full` run fetched and normalized MITRE ATT&CK, MITRE ATLAS, CISA KEV, NVD API data, NIST/OWASP configured pages, CWE, and CAPEC; a `--minimal --papers` run also acquired 25 OpenAlex metadata records. That run produced 8,931 normalized entities, 21,262 relationship records, 9,455 sentence-aware chunks, BM25/CPU feature-hash artifacts, and a provenance manifest. Those generated snapshots and manifests are preserved locally and excluded from the source ZIP. The extractable release starts with five attributed excerpts and provides the acquisition commands to expand them. Source register: [datasets/sources.md](datasets/sources.md), bootstrap guide: [datasets/bootstrapping.md](datasets/bootstrapping.md).

## Models and retrieval

The verified retrieval baseline uses CPU `tfidf-lite` feature-hash embeddings, BM25, and token-overlap claim verification. The data bootstrap trains explicit TF-IDF + Logistic Regression intent and OOD baselines from a tiny manually curated dataset. A historical baseline run exposed a 0.0 intent test accuracy on 14 one-example-per-class test items; that development dataset is not production-quality ground truth. Trained snapshots are not shipped. Optional OpenAI-compatible providers and transformer/reranker checkpoints remain configurable. Installed document adapters and local PostgreSQL/pgvector, Redis, and Neo4j integrations were exercised for this release.

## Agents and graph

The current implementation keeps responsibilities in bounded services instead of unrestricted cyber agents. The graph endpoint returns provenance-backed local relationships and explicitly reports when a record-specific relationship needs a live source. No automated exploitation is present.

## Security

See [threat model](security/threat-model.md). The system isolates retrieved content from instructions, limits upload size, hashes passwords, signs expiring tokens, avoids raw API stack traces, and labels heuristic signals as potential rather than confirmed incidents.

## Mobile application

The Flutter client implements auth, bottom navigation, streaming queries with speech input, evidence/CERS/claim views, file picker, camera upload, document deletion/quarantine status, log/IOC tools, secure token storage, saved answer history, and persistent workspace notes/evidence bookmarks. Android/iOS platform projects exist. Flutter 3.47.6/Dart 3.13.5 passed clean analysis and six tests, including workspace/tools widgets and session-refresh regression coverage. Native platform builds require Android tooling or macOS/Xcode.

## Experimental setup and actual checks

Current executed checks used a clean Python 3.12.15 product environment and Node 24.21.0:

- Python compilation of backend, ML, and scripts passed.
- Latest installed backend pytest: **77 passed, zero skips**, including live PostgreSQL/pgvector, Redis, Neo4j, and OCR. Follow-up readiness/auth and data-job checks also passed.
- Web tests: **12 passed**, including the active Next.js client, SSE, refresh coalescing, and experiment requests.
- TypeScript and a **21-page production Next.js build** passed. `build:portable` handles the observed Windows-mount native-copy EPERM.
- Live production web/API smoke passed all **18 routes** and active-client authentication, CORS, query/history/workspace/export/upload/experiment/SSE/admin-isolation/logout flows.
- A fresh ZIP extraction generated new credentials/database, rebuilt the production web on a native filesystem, and passed the same live smoke plus startup/status/shutdown. Installed dependencies were reused; original project runtime state was not.
- `scripts/smoke_api.py` passed against live Uvicorn with an isolated database: health, authentication, workspace, SSE completion, saved answer, report export, experiment lifecycle, and admin authorization.
- Installed PyMuPDF/python-docx/reportlab adapters passed PDF/DOCX round trips. Tesseract 5.5.0 passed real image/scanned-PDF OCR and a ruled PDF table; OCR timeout failures remain unindexed.
- Docker configuration checks passed; Docker runtime was unavailable. Flutter analysis/six tests ran through native-filesystem staging with ordinary shader-enabled tests.
- A fresh standalone CISA worker processed the official 2026.10.02 catalog into 1,733 normalized entities/chunks/vectors with zero reported failures in an isolated directory. Persistent-worker cycle/SIGTERM tests verify stopped status; production scheduling remains separate deployment work.
- CyberTrust-QA and the isolated available A–J configurations were rerun against the five-source release corpus; unavailable A/D configurations remained unmeasured.
- npm audit reported zero vulnerabilities; pip-audit found no known vulnerabilities in backend/document requirements.
- The source ZIP passed required-file, per-file SHA-256, CRC integrity, excluded-path, and local-credential checks.

The latest seed-corpus CyberTrust-QA run reported mean CERS **0.4699** and abstention rate **1/3** on three development items. The artifacts include corpus/dataset hashes and generation time. These are implementation measurements, not validated research results.

## Ablation and results

The release run measured **B/C/E/F/G/H/I/J** using five attributed source excerpts, three development questions, and deterministic generation/heuristic verification. **A/D** remain `not_run` because their approved LLM/reviewed cross-encoder configurations are unavailable. J abstained on **1/3** of the questions, with mean CERS **0.4699**. Earlier larger-corpus measurements are historical and use a different corpus. Equal retrieval scores on this tiny benchmark do not establish component effectiveness. Release artifacts are under `data/evaluation/`; missing result cells remain empty.

## Limitations

Transformer NLI/model-backed reranking, human calibration, production worker deployment, native Flutter builds, and A/D ablations remain prerequisite work. Local services, controlled OCR, and Flutter analysis/tests now execute. The Neo4j fixture used isolated loopback-only, authentication-disabled configuration; it does not establish authenticated production deployment. See [limitations.md](research/limitations.md).

## Remaining external verification

Docker startup, Android/iOS platform builds, transformer download/inference, authenticated production service deployment, always-on worker deployment, and human calibration remain unverified. Local service/worker execution, Flutter analysis/tests, OCR/PDF/DOCX/table checks, product lifecycle, and fresh-extraction integration are recorded in [PRODUCT_RELEASE.md](PRODUCT_RELEASE.md) and its linked historical records.

## Future work

1. Deploy the locally verified PostgreSQL/pgvector, Redis, and Neo4j integrations with target-environment authentication and configuration.
2. Deploy the verified source refresh scheduler and measure long-running freshness/failure recovery.
3. Provision model-backed inference, evaluate the corrected reranker, and extend beyond TF-IDF-lite retrieval.
4. Expand and human-label CyberTrust-QA and calibration/reranker datasets.
5. Run unavailable model-backed ablations and broader contradiction/red-team evaluations.
6. Execute Android/iOS device builds and expand OCR/complex-layout/table validation beyond controlled fixtures.
