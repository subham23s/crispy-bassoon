# Filesystem continuation, second increment — 2026-10-03

This increment continues the code and [earlier report](CONTINUATION_2026-10-03.md). The filesystem already contained Flutter 3.47.6/Dart 3.13.5, partial Android/iOS plugin-output folders, extracted service binaries, and the Python 3.12.15 environment. These were verified directly rather than relying on the earlier environment description. Missing platform scaffolds were subsequently generated with Flutter.

## Implemented and repaired

- **PostgreSQL:** added the missing `answers` migration and saved-answer/history/chunk repository methods; normalized bare PostgreSQL URLs to the installed psycopg 3 driver; serialized timestamps consistently; corrected the database health key; guarded owned upserts; preserved initialization errors during cleanup.
- **Live-service contracts:** isolated-schema PostgreSQL tests cover authentication/rotation, owner isolation, upload chunks, saved answers, metric-preserving experiment updates, pgvector distance execution, and FastAPI query/history/export/upload flows. Redis tests execute value/TTL operations. Neo4j tests execute attributed import twice and inspect graph traversal without duplicate edges. Fixtures are removed after each service test.
- **Refresh reliability:** added crash-released cross-process SQLite locking, strict source/processing-result handling, partial-page failures, unique atomic status writes, configured `DATA_DIR` propagation, and explicit worker stopped state. Scheduled refreshes request fresh downloads; `--cached` explicitly selects cached reprocessing. Health differentiates active, stale, stopped, and one-shot workers.
- **NVD recovery:** bounded updates retain their window and next page when truncated; checkpoints advance only after that window is complete. The NVD CLI is no longer passed an unsupported `--force` flag. Bootstrap failures reported as JSON are no longer converted into success because the subprocess exited with code zero.
- **Data processing:** acquisition/normalization/chunks/embeddings/vector/BM25/graph/paper/dataset processing honor `DATA_DIR`; external artifact paths remain explicit. Relationship resolution reuses a precomputed ID set.
- **Mobile:** fixed a syntax error in the defensive tools view; retained refreshed credentials on non-authentication retry failures; added injectable HTTP clients, a session-regression test, and a tools widget test that compiles `main.dart`. Added `scripts/check_mobile_portable.py` to execute source analysis and ordinary Flutter tests on a native filesystem when mounted Windows paths reject native compiler operations.
- **Mobile platforms:** generated missing Android/iOS scaffolds using the new preserving `--fill-missing` mode. Platform permission validation exposed an iOS nested-plist insertion error; the helper now writes root-level usage keys structurally. Added Android speech-service visibility and product labels. Android XML/iOS plist parsing and required-permission checks passed. The environment checker now reports the actual missing Android SDK/Java and macOS/Xcode toolchains.
- **OCR:** verified the actual OCR engine, retained image page locators in chunks, bounded scanned-page rendering before allocating pixels, and converted OCR engine/timeout failures into explicit extraction-unavailable results. Added real camera-image/scanned-PDF/table round trips.
- **Automation:** CI now provisions PostgreSQL/pgvector, Redis, Neo4j, and OCR for backend integration tests. Runtime directories, Gradle/local configuration, and generated Flutter crash logs are excluded from Git/build contexts. CI changes are configured, not remotely executed results.

## Executed verification

| Check | Observed result |
|---|---|
| Full Python 3.12 backend suite with all service/OCR variables set | **75 passed, zero skips**, 64.87 seconds |
| Real PostgreSQL/Redis/Neo4j contract suite | **6 passed** |
| Real image OCR, scanned-PDF OCR, explicit timeout, and ruled-table extraction | **4 passed** |
| Staged Flutter dependency resolution, Dart analysis, and standard Flutter tests | **No analyzer issues; 6 tests passed** |
| Flutter platform generation, repeat fill-missing run, shell syntax, Android XML/iOS plist/root permissions | Passed |
| `npm test --prefix frontend` | **12 passed** |
| `npm run typecheck --prefix frontend` | Passed |
| Python compilation of `backend`, `ml`, and `scripts` | Passed |
| `scripts/smoke_api.py` against live Uvicorn/isolated SQLite | Passed |
| `scripts/check_docker_config.py` | Passed configuration checks; Docker executable absent |
| Host Python 3.14 dependency-free suite, before the final OCR/worker-status additions | **68 discovered, 53 passed, 15 explicit skips** |

The previous production Next.js build result is retained in the earlier report; it was not rerun in this increment. The new service adapters were exercised with PostgreSQL **18.6/pgvector**, Redis **8.0.5**, and Neo4j **5.26.0**. The Compose/CI service versions differ and their container execution has not run locally.

### Reproduction commands used

The service test endpoints were `127.0.0.1:15432` (PostgreSQL), `127.0.0.1:16379` (Redis), and `127.0.0.1:17687` (isolated Neo4j). The existing Neo4j instance on 7687 was retained. The isolated Neo4j fixture used loopback-only, authentication-disabled configuration; its tests establish graph behavior, **not authentication/deployment hardening**.

The three test-service processes were shut down gracefully after verification. Their local runtime artifacts remain available; the pre-existing Neo4j process was not stopped.

```bash
PATH=/tmp/omnirush/services/usr/bin:$PATH \
LD_LIBRARY_PATH=/tmp/omnirush/services/usr/lib/x86_64-linux-gnu \
TESSDATA_PREFIX=/tmp/omnirush/services/usr/share/tesseract-ocr/5/tessdata \
TMPDIR=/tmp/omnirush PYTHONPATH=backend \
TEST_POSTGRES_URL=postgresql://cybersecra@127.0.0.1:15432/cybersecra \
TEST_REDIS_URL=redis://127.0.0.1:16379/15 \
TEST_NEO4J_URI=bolt://127.0.0.1:17687 \
TEST_NEO4J_PASSWORD=isolated-fixture \
/tmp/omnirush/cybersecra-py312/bin/python -m pytest \
  -p no:cacheprovider --tb=short -q backend/tests

GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=safe.directory \
GIT_CONFIG_VALUE_0=/mnt/c/Users/Lenovo/flutter TMPDIR=/tmp/omnirush \
python3 scripts/check_mobile_portable.py \
  --flutter /mnt/c/Users/Lenovo/flutter/bin/flutter \
  --temp-dir /tmp/omnirush --offline
```

The Python environment additionally installed `pytesseract==0.3.13`. Tesseract **5.5.0** and its English/OSD data were extracted from Ubuntu packages into `/tmp/omnirush/services`. Temporary environments and extracted binaries are not a portable installation; the documented Python/Flutter/system-package setup remains the supported reproduction path.

Executed platform generation with `PATH=/mnt/c/Users/Lenovo/flutter/bin:$PATH`, the same per-command Git safe-directory environment, and `TMPDIR=/tmp/omnirush`:

```bash
bash mobile/tool/generate_platforms.sh --fill-missing
```

The helper copies missing platform files and metadata, preserves existing files, and leaves Dart application source intact. A second execution also completed. Native platform compilation has not run.

## Fresh-source worker execution

Executed, with a separate artifact directory:

```bash
DATA_DIR=/mnt/c/Users/Lenovo/MLPA/.runtime/refresh-live-data \
TMPDIR=/tmp/omnirush PYTHONPATH=backend \
/tmp/omnirush/cybersecra-py312/bin/python \
  scripts/refresh_worker.py --once --sources cisa_kev
```

The actual CISA feed identified catalog **2026.10.02**. The run downloaded and processed **1,733 records**, then produced **1,733 normalized entities/chunks/256-dimensional vectors**, BM25 with **4,165 terms**, and a **1,733-node/zero-edge graph**. All six processing stages returned successful JSON results; the status artifact recorded **zero failures** at `2026-10-03T17:31:40.472725+00:00`.

Artifacts are under `.runtime/refresh-live-data/`, including the raw official response, provenance manifest, and `processed/source_update_status.json`. This run did not replace the existing application corpus. Separately, automated isolated-fixture tests ran the persistent worker's initial cycle and verified graceful SIGTERM shutdown and a `stopped` status. No continuously deployed production scheduler is claimed.

## Remaining prerequisites

1. **Model-backed research:** provision reviewed transformer checkpoints and an approved LLM/provider. PyTorch/Transformers are absent in the verified API environment; A/D ablations and model accuracy remain unmeasured.
2. **Human evidence:** supply reviewed reranker examples, broader CyberTrust-QA annotations, and CERS calibration labels. Existing development measurements are not scientific validation.
3. **Platform builds:** Android SDK/toolchain and a device/emulator are absent; iOS compilation requires macOS/Xcode. Android/iOS source projects exist and Dart/widget checks now execute.
4. **Deployment:** Docker container startup, authenticated production Neo4j, deployment secrets, and an always-on refresh service still require a target environment. Live local service operation and worker cycles have now been verified.
5. **Extraction breadth:** controlled OCR and a ruled table pass; arbitrary layout/complex-table fidelity and vision inference are not established by those tests.

No model predictions, human labels, external benchmark scores, device builds, or production deployment results were fabricated.
