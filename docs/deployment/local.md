# Local deployment

## Dependency-light path (works in the current repository)

The host Python 3.14 supports the standard-library API fallback. A separate Python 3.12 environment and Flutter SDK were used for the latest full-stack checks; see the [execution record](../reports/CONTINUATION_2026-10-03_02.md). Docker and Android/iOS platform toolchains remain unavailable locally.

```bash
cp .env.example .env
make backend-test
make web-test
make run-backend       # http://127.0.0.1:8000
make run-web           # second terminal, http://localhost:3000
```

If GNU Make is not installed, run `bash scripts/checks.sh` for the backend checks and start with `PYTHONPATH=backend python3 backend/run.py` plus `npm run dev --prefix frontend` (or `npm run build && npm start --prefix frontend` for a production check). The Next.js client reads `NEXT_PUBLIC_API_URL`, defaulting to `http://localhost:8000`.

The web client expects the API at `http://localhost:8000`. Test it directly:

```bash
curl http://localhost:8000/health
TOKEN=$(curl -fsS -X POST http://localhost:8000/auth/register \
  -H 'content-type: application/json' \
  -d '{"email":"analyst@example.test","password":"correct horse battery"}' | python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')
curl -X POST http://localhost:8000/chat/query \
  -H 'content-type: application/json' \
  -H "authorization: Bearer $TOKEN" \
  -d '{"query":"What does NIST CSF 2.0 provide?","mode":"RESEARCHER"}'
```

## Full API mode

On Python 3.11+ with package installation available:

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -r backend/requirements.txt
PYTHONPATH=backend python backend/run.py
```

FastAPI/Swagger is then available at `/docs` and `/redoc`.

## Docker

```bash
cp .env.example .env
# Requires Docker and Compose
 docker compose up --build
```

The `infra` profile starts PostgreSQL/pgvector, Redis, and Neo4j with persistent volumes, PostgreSQL extension initialization, and service healthchecks:

```bash
docker compose config
docker compose --profile infra up --build
```

`python scripts/check_docker_config.py` validates Compose structure without Docker. The current API still reports SQLite/in-process mode unless a tested production repository adapter is selected; containers are not falsely counted as active integrations.

## Service integration checks

Install backend requirements, start real services, and select their test endpoints:

```bash
export TEST_POSTGRES_URL=postgresql+psycopg://user:password@localhost:5432/test_database
export TEST_REDIS_URL=redis://localhost:6379/15
export TEST_NEO4J_URI=bolt://localhost:7687
export TEST_NEO4J_USERNAME=neo4j
export TEST_NEO4J_PASSWORD=your-local-test-password
PYTHONPATH=backend python -m pytest -q backend/tests/test_live_services.py
```

Use a dedicated test database/service. PostgreSQL tests create/drop their own schema and require schema/pgvector privileges; Redis uses expiring unique keys; Neo4j creates/removes uniquely named fixture nodes. The latest local checks exercised PostgreSQL 18.6, Redis 8.0.5, and Neo4j 5.26.0. CI provisions the Compose-style versions separately.

## Scheduled source refresh

```bash
# Optional Compose worker (uses the mounted data directory)
docker compose --profile workers up --build -d refresh-worker

# Standalone scheduler; one cycle immediately, then daily
PYTHONPATH=backend python scripts/refresh_worker.py --sources cisa_kev --interval 86400

# One fresh cycle into an isolated existing location
DATA_DIR=/absolute/path/to/test-data PYTHONPATH=backend \
  python scripts/refresh_worker.py --once --sources cisa_kev
```

Source/processing errors are persisted rather than counted as successful refreshes. `--once` returns nonzero for degraded/failed/busy cycles. Add `--cached` only when intentionally reprocessing cached downloads. SIGTERM/SIGINT stop the worker between bounded acquisition/processing cycles and persist a stopped status. API health includes worker state and distinguishes one-shot checks from an active scheduler.

OCR requires system Tesseract plus `Pillow`/`pytesseract`; `backend/requirements-ml.txt` includes those Python dependencies. Controlled OCR/table checks are in `backend/tests/test_ocr_and_tables.py`.
