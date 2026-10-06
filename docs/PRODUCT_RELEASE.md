# CyberSecRA-X product release 1.0.0

**Release date:** 2026-10-03. **Product type:** extractable source product with tested local setup/lifecycle, production web build, FastAPI, Flutter source/platform scaffolds, research/data/ML infrastructure, and environment-configured integrations.

## Implemented product

All existing functionality was retained. This final pass added:

- `scripts/product.py` and Make setup/configure/build/up/status/test/down targets. Setup creates unique local credentials, installs dependencies, and records the chosen Python environment. Startup waits for the API/repository and production web server; source/configuration fingerprints control rebuilds. Shutdown accounts for Next.js changing its process title and guards against PID reuse.
- `/ready`, FastAPI body-size bounds, stable generated local JWT secrets, production signing-secret requirements, and single-use refresh-token rotation under concurrent requests.
- Updated dependency pins and PostCSS/sharp overrides based on actual advisory checks. Next.js **15.5.27**, Tailwind **4.3.3**, FastAPI **0.142.2**, Starlette **1.3.1**, python-multipart **0.0.31**, and pytest **9.0.3** were installed and exercised. Document dependencies are pinned to the executed versions.
- Container health/readiness, environment-based service credentials, independent Docker-internal URLs, and optional infra/worker profiles. Removed the runtime web dependency on externally hosted fonts.
- A live production-web/FastAPI smoke command that executes the active TypeScript client and all navigation routes.
- A source-only packager with required-file checks, per-file hashes, ZIP CRC validation, credential scanning, and comprehensive cache/private-data/agent-internal exclusions.

Backend RAG, hybrid retrieval, reranking/NLI adapters, authority/temporal reasoning, citations, contradictions, CERS, source pipelines, graph integration, ingestion/OCR/tables, PDF/DOCX reports, SSE, research/history, admin controls, web views, mobile flows, and ML/evaluation infrastructure are included.

## Actual verification

| Executed check | Observed result |
|---|---|
| Full installed backend suite, with isolated development corpus and configured service/OCR variables | **77 passed, zero skips**, 48.54 seconds |
| Follow-up API/auth regressions after readiness fallback adjustment | **9 passed** |
| Follow-up data-job regressions after environment-loading adjustment | **3 passed** |
| PostgreSQL/pgvector, Redis, and Neo4j integration contracts | Executed in the full suite; all passed |
| OCR images/scanned PDFs, explicit failure semantics, ruled tables | Real Tesseract/PyMuPDF engines executed; all passed |
| PDF/DOCX extraction/export | Round-trip tests executed in the full suite; all passed |
| Web tests | **12 passed** |
| TypeScript | Passed |
| Next.js production build | Passed; **21 generated pages**, standalone tracing completed |
| Dart analysis | **No issues** |
| Flutter tests | **6 passed**, ordinary shader-enabled tests on staged native filesystem |
| Live Uvicorn smoke (`scripts/smoke_api.py`) | Passed with isolated SQLite |
| Live production web + FastAPI (`frontend/scripts/smoke-product.mjs`) | **18 routes passed**; auth, CORS, query, history, workspace, report export, upload/delete, experiment lifecycle, SSE, admin isolation, logout passed |
| Local lifecycle | Configure/setup/build/up/status/down executed; shutdown failure caused by Next.js process-title rewriting was fixed and retested |
| Fresh ZIP extraction | Native-filesystem production build, startup/readiness, all **18 live routes/client flows**, status, and shutdown passed |
| Python compilation | Backend, ML, scripts passed through the product test command |
| npm audit, including development dependencies | **0 reported vulnerabilities** after dependency repair |
| pip-audit of backend/document requirements | **No known vulnerabilities found** |
| Docker configuration checker | Parsed configuration and service/volume/health checks passed; Docker engine absent |
| A–J framework | B/C/E/F/G/H/I/J measured; A/D explicitly `not_run` |
| RAG security regression evaluation | All **3 controlled cases correct**; not a complete red-team evaluation |
| CERS calibration framework | Executed; `CALIBRATION_PENDING`, zero human labels, no invented metrics |

The installed clean Python environment was created by `product.py setup` using Python **3.12.15**. Web dependencies were installed with `npm ci` on a native temporary filesystem and Node **24.21.0**. The initial parallel provisioning attempt exceeded memory and a later installation exhausted `/tmp`; after preserving/relocating old caches and running heavyweight checks sequentially, setup/build/tests completed. No failed/interrupted invocation is counted as passed.

The archive extraction check generated new local credentials and a new SQLite repository, rebuilt all 21 pages, and ran the production client smoke against ports 13000/18000. It reused the installed dependency trees, not the original project's configuration, database, build, or lifecycle state. A first extraction build on the Windows mount timed out; the native-filesystem retry passed with `NODE_OPTIONS=--max-old-space-size=384` after stopping the original application.

Local service checks used PostgreSQL **18.6/pgvector**, Redis **8.0.5**, and Neo4j **5.26.0**. The isolated Neo4j graph fixture bound loopback with authentication disabled; graph behavior was verified, not production authentication hardening. Compose/CI specify their own service versions and were not remotely executed.

## Evaluation integrity

The final packaged evaluation uses the **five attributed source excerpts** and **three existing CyberTrust-QA questions**, with deterministic classifiers and heuristic verification. The executed CyberTrust artifact records generation time, corpus/dataset hashes, mean CERS **0.4699**, and abstention on **1/3** of the questions. J's mean CERS is also **0.4699** in this release run. A has no configured approved LLM; D has no configured reviewed cross-encoder. Their result cells remain unmeasured.

These are tiny development measurements, not calibrated truth probabilities, model accuracy, component-effectiveness proof, or scientific superiority. The intentionally unknown CVE in the abstention benchmark is a question/control, not an invented vulnerability record. Generated private corpus/training snapshots and old runtime caches are excluded from the ZIP; source/configuration and actual small evaluation artifacts are retained.

## Reproduction

After extraction, from `CyberSecRA-X/`:

```bash
python3 scripts/product.py setup --python python3.12
python3 scripts/product.py up
python3 scripts/product.py test
node frontend/scripts/smoke-product.mjs
python3 scripts/product.py down
```

On mounted filesystems, use a native `--venv`/`TMPDIR` if necessary. The executed setup used `--venv /tmp/omnirush/product-venv --skip-web-install` after an independent clean `npm ci`; neither temporary dependency tree is shipped. For complete optional checks, set `TEST_POSTGRES_URL`, `TEST_REDIS_URL`, `TEST_NEO4J_URI`, `TEST_NEO4J_PASSWORD`, and put Tesseract/data on the process environment. A separate `DATA_DIR` keeps verification isolated from existing user/corpus state.

Docker alternative: run `python3 scripts/product.py configure`, then `docker compose up --build`. Web is <http://localhost:3000>, API <http://localhost:8000>, health `/health`, readiness `/ready`, OpenAPI `/docs`. See the root README for exact feed/model/mobile/configuration commands and troubleshooting.

## External prerequisites only

- Approved LLM/provider access and credentials, and reviewed transformer checkpoints for real model-backed inference/A/D measurements.
- Human-reviewed reranker examples, broader benchmark annotations, and CERS calibration labels.
- Android SDK/Java/device tooling for Android compilation/device runs; macOS/Xcode for iOS compilation. No Android release/device build is claimed.
- Docker Engine/Compose if using containers, and a target environment/service credentials for production hosting, authenticated service deployment, and continuously scheduled workers.

The deterministic local product does not require cloud infrastructure or an LLM. Controlled OCR/table execution passed; arbitrary complex-layout fidelity is not asserted.

## Release package

The packager creates **`release/CyberSecRA-X/`** and **`release/CyberSecRA-X-final.zip`**, plus a SHA-256 sidecar. `RELEASE_MANIFEST.json` contains every included file's content hash. Verification checks required backend/frontend/ML/mobile/Docker/scripts/documentation files, all manifest hashes, ZIP CRC integrity, unsafe/excluded paths, and absence of generated local secrets/private-key/API-key signatures.

Excluded: Git, node_modules, virtual environments, Flutter/Next/Python/test/build caches, credentials, user databases/uploads, large downloaded/trained datasets/models, runtime binaries/logs, agent internals, and generated agent work records. Existing source and live filesystem data are preserved outside the release directory. Dependency/source acquisition remains reproducible through the shipped commands.
