# CyberSecRA-X

**Evidence-aware cybersecurity research intelligence — source release 1.0.0**

CyberSecRA-X combines a FastAPI backend, production Next.js/TypeScript dashboard, Flutter client, provenance-aware data pipeline, and reproducible research/evaluation tooling. Its answer workflow is:

**understand → retrieve → rank → correlate → verify → cite → detect conflicts → score → explain or abstain**.

The product works locally with SQLite, attributed source excerpts, CPU retrieval, and explicit heuristic verification. Approved LLMs, reviewed transformer checkpoints, PostgreSQL/pgvector, Redis, and Neo4j are environment-configured integrations. Unavailable services/models are reported honestly; no current CVE record, model accuracy, human label, or benchmark result is invented.

## Release status

The final pass executed **77 backend tests with no skips**, live PostgreSQL/pgvector/Redis/Neo4j checks, real OCR and PDF/DOCX/table round trips, **12 web tests**, TypeScript, a **21-page production Next.js build**, clean Dart analysis, and **six Flutter tests**. Live frontend/FastAPI integration exercised **18 routes**, auth, queries, SSE, uploads, workspaces, history, exports, and experiment lifecycle. Both npm audit and pip-audit reported no known vulnerabilities in the checked release dependencies.

See [docs/PRODUCT_RELEASE.md](docs/PRODUCT_RELEASE.md) for exact execution boundaries and [previous continuation records](docs/reports/CONTINUATION_2026-10-03_02.md) for history. Test results establish implementation behavior, not scientific superiority or CERS calibration.

## Features

- **Evidence research:** query intent/OOD handling; lexical/CPU-semantic hybrid retrieval; optional cross-encoder reranking; authority/recency ranking; graph and temporal signals; citations, claim statuses, possible contradictions, CERS, limitations, and abstention.
- **Backend:** FastAPI/OpenAPI, authenticated JSON/SSE APIs, PBKDF2 passwords, expiring HS256 tokens, single-use refresh rotation, owner-scoped document/research/experiment access, bounded request/upload handling, administrative views and source refresh controls.
- **Documents:** PDF, DOCX, TXT, Markdown, CSV, JSON, logs, and common image formats. Extraction retains page/section provenance, scans prompt-injection signals, quarantines flagged content, and supports bounded background processing. Scanned PDFs/images use OCR when Tesseract is installed. Ruled PDF/DOCX/CSV tables retain extracted cells.
- **Research:** persistent workspaces, notes, saved answers/evidence, paper extraction/comparison, candidate gaps, JSON/Markdown/PDF/DOCX reports, and measured experiment tracking/comparison.
- **Cybersecurity:** bounded MITRE ATT&CK/ATLAS, CISA KEV, NVD, CWE, CAPEC, NIST, OWASP, and OpenAlex adapters; provenance manifests, deduplication, chunks, embeddings/vector/BM25 indexes, graph generation, and resumable NVD updates. IOC/log tools report defensive heuristic leads rather than asserting incidents.
- **Clients:** responsive dashboard, auth, assistant, documents, research/history, graph/timeline, paper/gap analysis, experiments/evaluation, RAG security, settings/admin/health. Flutter shares the API and supports speech input, camera/files, citations, workspaces, history, and secure token storage.
- **ML:** preprocessing, CPU baseline and transformer training infrastructure, offline model loading, NLI adapter/fallback, CERS calibration framework, CyberTrust-QA, A–J ablations, and security regression evaluation.

## Architecture

```mermaid
flowchart LR
  Web[Next.js dashboard] --> API[FastAPI / local stdlib fallback]
  Mobile[Flutter] --> API
  API --> R[Understanding + hybrid retrieval + ranking]
  R --> V[Verification + citations + conflicts + CERS]
  V --> A[Evidence answer / abstention]
  API --> D[(SQLite or PostgreSQL/pgvector)]
  API -. configured .-> Cache[Redis]
  API -. configured .-> Graph[Neo4j]
  R -. configured .-> Models[Reviewed transformers / approved LLM]
  Worker[Source refresh worker] --> Corpus[Attributed corpus + indexes]
  Corpus --> R
```

Structure: `backend/`, `frontend/`, `mobile/`, `ml/`, `scripts/`, `data/`, `docker/`, and `docs/`. Database schema initialization is idempotent in `backend/app/database/`; Compose also includes `docker/postgres/init/`. Detailed [system](docs/architecture/system.md), [pipeline](docs/architecture/rag-pipeline.md), and [mobile](docs/architecture/mobile.md) documentation is preserved.

## Prerequisites

- Python **3.12 recommended** (3.11–3.13 accepted by setup), with `venv`/pip support.
- Node **22+** and npm; Internet access for initial dependency installation.
- Tesseract with English language data for OCR. On Debian/Ubuntu: `sudo apt-get install tesseract-ocr`.
- Flutter stable for mobile source analysis/tests; the included platform scaffolds were generated with **Flutter 3.47.6**. Android builds require Java/Android SDK; iOS builds require macOS/Xcode.
- Docker Engine/Compose only for the container startup alternative.

## Installation and one-command local startup

From the extracted `CyberSecRA-X/` directory:

```bash
python3 scripts/product.py setup --python python3.12
python3 scripts/product.py up
```

`setup` creates `.env` with unique local JWT/PostgreSQL/Neo4j credentials, installs backend/document dependencies into `.venv`, and runs `npm ci`. Provider keys remain empty. Existing `.env` files are preserved. `up` builds the production frontend when source/configuration changes, starts both services, waits for readiness, and stores only lifecycle state/logs under `.runtime/`.

- **Web:** <http://localhost:3000>
- **API:** <http://localhost:8000>
- **Health:** <http://localhost:8000/health>
- **Readiness:** <http://localhost:8000/ready>
- **API docs:** <http://localhost:8000/docs> and <http://localhost:8000/redoc>

Register through the web interface. No default user/admin password is shipped. The local application includes five concise, attributed official-source excerpts; real data bootstrap expands that corpus.

```bash
python3 scripts/product.py status
python3 scripts/product.py test
python3 scripts/product.py down
```

Equivalent Make targets are `make setup`, `make up`, `make test`, `make build`, and `make down`. If Make is unavailable, use the Python commands above. For development, run `.venv/bin/python backend/run.py` with `PYTHONPATH=backend` and `npm run dev --prefix frontend` in separate terminals.

## Configuration and database setup

Edit the generated `.env`; `.env.example` documents the integration variables. Keep real credentials out of source/releases.

| Variables | Purpose |
|---|---|
| `HOST`, `PORT`, `WEB_HOST`, `WEB_PORT` | Local listeners, default 127.0.0.1:8000/3000 |
| `NEXT_PUBLIC_API_URL`, `CORS_ORIGINS` | Browser API endpoint and allowed web origins; API URL changes trigger a rebuild |
| `DATABASE_URL`, `DATA_DIR` | SQLite/PostgreSQL repository and corpus/artifact directory |
| `JWT_SECRET`, `ACCESS_TOKEN_MINUTES` | Authentication signing/expiration; production requires a configured 32+ character secret |
| `REDIS_URL`, `NEO4J_URI`, `NEO4J_USERNAME`, `NEO4J_PASSWORD` | Optional local/external cache/graph services |
| `LLM_PROVIDER`, `LLM_BASE_URL`, `LLM_MODEL`, `LLM_API_KEY` | Approved provider configuration; `none` is the deterministic fallback |
| `NLI_PROVIDER`, `NLI_MODEL`, `RERANKER_PROVIDER`, `RERANKER_MODEL` | Reviewed transformer integration; absent checkpoints report unavailable/fallback |
| `INTENT_PROVIDER`, `OOD_PROVIDER`, `INTENT_MODEL`, `OOD_MODEL` | Classifier selection/model paths |
| `NVD_API_KEY`, `MAX_UPLOAD_BYTES`, `BACKGROUND_UPLOAD_BYTES` | Feed credentials and ingestion bounds |
| `CERS_WEIGHTS`, `CERS_ABSTENTION_THRESHOLD`, `CERS_CALIBRATION_STATUS` | Project-defined scoring/calibration configuration |

SQLite initializes automatically. For PostgreSQL use, for example, `DATABASE_URL=postgresql+psycopg://user:password@localhost:5432/cybersecra`; the account needs schema/pgvector initialization privileges. Optional service failures retain the local fallback and appear in detailed health. Readiness checks the serving repository.

Provision an administrator without exposing credentials in command-line arguments:

```bash
ADMIN_EMAIL=admin@example.org ADMIN_PASSWORD='your-own-strong-password' \
  PYTHONPATH=backend .venv/bin/python scripts/create_admin.py
```

## Docker startup

```bash
python3 scripts/product.py configure
docker compose up --build
```

The default containers run the same local-first product with document/OCR dependencies. URLs remain 3000/8000. Docker itself was unavailable during this release pass; configuration was checked, but container startup is not claimed.

For the optional infrastructure profile, set these `.env` values using the generated credentials:

```text
DOCKER_DATABASE_URL=postgresql+psycopg://cybersecra:<POSTGRES_PASSWORD>@postgres:5432/cybersecra
DOCKER_REDIS_URL=redis://redis:6379/0
DOCKER_NEO4J_URI=bolt://neo4j:7687
```

Then run `docker compose --profile infra up --build`. Add `--profile workers` for scheduled source refresh. Stop containers with `docker compose --profile infra --profile workers down`. Local application URLs and Docker-internal service URLs are independently configurable.

## Real data bootstrap and refresh

```bash
PYTHONPATH=backend .venv/bin/python scripts/bootstrap_data.py --minimal
PYTHONPATH=backend .venv/bin/python scripts/bootstrap_data.py --full
PYTHONPATH=backend .venv/bin/python scripts/update_sources.py --sources cisa_kev --force
PYTHONPATH=backend .venv/bin/python scripts/refresh_worker.py --sources cisa_kev --interval 86400
```

Use `--once` for one worker cycle and `--cached` only for intentional cached reprocessing. `DATA_DIR` isolates acquisition/processing output. Cross-process locking prevents overlapping publications; status artifacts record failures/partial runs and graceful stopped state. Truncated NVD updates resume the same window/page cursor. Raw and normalized source snapshots, manifests, indexes, and trained models are regenerated rather than distributed in the clean source ZIP. Source licensing remains with each publisher. See [bootstrapping](docs/datasets/bootstrapping.md) and [sources](docs/datasets/sources.md).

## Model and calibration setup

The deterministic retrieval/verification fallback runs without model downloads or provider credentials. Full model-backed inference requires explicit provisioning:

```bash
.venv/bin/python -m pip install -r backend/requirements-ml.txt
PYTHONPATH=backend .venv/bin/python scripts/setup_models.py --nli --model <reviewed-checkpoint>
PYTHONPATH=backend .venv/bin/python scripts/bootstrap_data.py --evaluation
PYTHONPATH=backend .venv/bin/python scripts/train_intent.py
PYTHONPATH=backend .venv/bin/python scripts/train_ood.py
PYTHONPATH=backend .venv/bin/python scripts/evaluate_models.py
PYTHONPATH=. .venv/bin/python scripts/train_transformer.py --task intent
PYTHONPATH=. .venv/bin/python scripts/train_reranker.py
```

Set provider/model environment variables after installing reviewed checkpoints. `NLI_PROVIDER=transformer` fails closed when unavailable; `auto` reports a heuristic fallback. Reranker training needs reviewed positive/negative pairs. Generated synthetic controls are explicitly labeled and never represented as authoritative cybersecurity intelligence. Human CERS calibration labels remain externally required; no calibration accuracy is computed from absent labels.

## Mobile

```bash
cd mobile
flutter pub get
dart analyze
flutter test
flutter run --dart-define=API_BASE_URL=http://10.0.2.2:8000
# With an installed Android SDK/Java toolchain:
flutter build apk --debug --dart-define=API_BASE_URL=http://10.0.2.2:8000
```

Use a host-reachable HTTPS URL on a physical device. Android/iOS projects and capture/speech permissions are included. No Android release/device build or iOS compilation was verified. On Windows-mounted filesystems, run from the repository root:

```bash
python3 scripts/check_mobile_portable.py --flutter /path/to/flutter/bin/flutter --temp-dir /native/temp/directory
```

This stages source, resolves dependencies, runs Dart analysis and ordinary shader-enabled Flutter tests. For incomplete platform folders, `bash mobile/tool/generate_platforms.sh --fill-missing` preserves existing files while adding missing scaffolds. See [mobile/README.md](mobile/README.md).

## Verification and evaluation

```bash
python3 scripts/product.py test
python3 scripts/product.py build
.venv/bin/python scripts/smoke_api.py
node frontend/scripts/smoke-product.mjs  # requires the running product
PYTHONPATH=backend .venv/bin/python scripts/check_docker_config.py
PYTHONPATH=backend .venv/bin/python scripts/evaluation/evaluate_cybertrust.py
PYTHONPATH=backend .venv/bin/python scripts/evaluation/run_ablation.py --summary
PYTHONPATH=backend .venv/bin/python scripts/evaluation/evaluate_rag_security.py
PYTHONPATH=backend .venv/bin/python scripts/evaluation/calibrate_cers.py
```

Set `TEST_POSTGRES_URL`, `TEST_REDIS_URL`, `TEST_NEO4J_URI`, `TEST_NEO4J_USERNAME`, and `TEST_NEO4J_PASSWORD` to run live integration contracts. Without configured services/tools, optional checks skip explicitly. The latest release ablations measured B/C/E/F/G/H/I/J against the packaged five-source development corpus and three benchmark questions. A/D are `not_run`; absent LLM/reranker results are not fabricated. These few development cases do not validate scientific effectiveness.

## Troubleshooting

- **Host Python 3.14 / missing pip:** install a supported Python and supply `setup --python /path/to/python3.12`. The stdlib API remains available for constrained development.
- **WSL/Windows mount permissions:** use a native virtual environment via `setup --venv /native/path/.venv`; `build:portable` handles the observed native-copy EPERM. Prefer a native project checkout/dependency directory if npm file operations fail.
- **Small `/tmp` / memory limits:** choose a sufficiently large native `TMPDIR`; run builds/tests sequentially. These were real constraints in the release environment.
- **Ports occupied:** inspect `product.py status`, stop managed services with `down`, or adjust ports/API URL/CORS before `up`.
- **OCR unavailable:** install Tesseract and document requirements; unreadable/failed OCR remains unindexed with an explicit error.
- **Graph/current vulnerability data absent:** execute the real bootstrap; absence is not replaced with invented records.
- **Provider/model unavailable:** inspect detailed health and answer limitations; configure credentials/checkpoints explicitly.

## Packaging and external prerequisites

```bash
python3 scripts/package_release.py
python3 scripts/package_release.py --verify release/CyberSecRA-X-final.zip
```

The packager creates `release/CyberSecRA-X/`, a per-file SHA-256 manifest, `release/CyberSecRA-X-final.zip`, and a checksum sidecar. It excludes credentials, private/user data, runtime/model caches, dependencies, Git/agent internals, and build outputs; validates required source files, every content hash, ZIP CRCs, and credential exclusions.

Externally required: approved model/provider access and credentials where applicable; reviewed human research/calibration datasets; Android SDK/device tooling or macOS/Xcode; Docker/service runtimes for container deployment; and target-environment infrastructure for production hosting. Core local product operation does not require an LLM or cloud service.

## License

MIT source code. External datasets, models, and APIs retain their own licenses/terms. [Research limitations](docs/research/limitations.md), [methodology](docs/research/methodology.md), and [threat model](docs/security/threat-model.md) remain available.
