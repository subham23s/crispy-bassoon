# Filesystem continuation — 2026-10-03

**Historical increment:** the [second continuation](CONTINUATION_2026-10-03_02.md) resolves local service, Flutter analysis/tests, OCR, and worker checks listed below and records the latest implementation/results.

## Starting point

The existing repository, documentation, source, tests, evaluation artifacts, and `__agent__/plan.json` were used as the specification. `.agent/plan.json` was absent. Existing acquisition, corpus, authentication, retrieval, verification, streaming, research, clients, and deployment adapters were retained.

## Implemented

- **Experiments:** owner-scoped GET/PATCH/DELETE, create/edit/delete web controls, measured numeric metric entry, per-metric comparison, validated metadata, and SQLite updates that preserve attached metrics. Metric-name updates now behave consistently across SQLite and PostgreSQL adapters.
- **Research:** web answer history, workspace evidence bookmarking/display, idempotent bookmark updates, and mobile workspaces/notes/bookmarks/history.
- **Administration:** source selection, refresh submission/polling, duplicate-job prevention, partial/failed states, and HTTP 403 for authenticated users lacking the administrator role.
- **Fallback API:** configured-origin SSE CORS, PATCH/DELETE preflight, date-filter parity, malformed/oversized JSON boundaries, and PATCH dispatch.
- **Models:** positive-class relevance scoring, scalar cross-encoder sigmoid handling, explicit legacy label mapping, checkpoint-keyed caches, offline inference loading, unknown OOD-label rejection, and atomic reranking fallback. Training uses `eval_strategy`, seeds before model-head initialization, and explicitly labels binary reranker outputs.
- **Tooling:** SQLite connection cleanup, isolated API-test teardown, active Next.js-client/SSE regressions, PDF/DOCX round trips, live Uvicorn smoke tooling, a Windows-mount build workaround, and expanded CI including Flutter analysis/tests.

## Executed checks

Python 3.12.15 and `backend/requirements.txt` plus `python-docx`, `reportlab`, and `Pillow` were installed at `/tmp/omnirush/cybersecra-py312`. Packages are symlinked to the installer cache because `/tmp` capacity and Windows-mounted native copy behavior prevented conventional installation. This environment is temporary; recreate it using the documented Python 3.11/3.12 setup when needed.

| Command | Observed result |
|---|---|
| `PYTHONPATH=backend /tmp/omnirush/cybersecra-py312/bin/python -m pytest -p no:cacheprovider -q backend/tests` | **54 passed, 1 skipped**; skip requires `TEST_POSTGRES_URL` |
| `PYTHONPATH=backend python3 -m unittest discover -s backend/tests -q` | 55 discovered: **46 passed, 9 dependency/service skips** on host Python 3.14 |
| `npm test --prefix frontend` | **12 passed**, including the actual Next.js TypeScript client |
| `npm run typecheck --prefix frontend` | Passed |
| `npm run build:portable --prefix frontend` | Passed; 21 static pages generated, production traces completed |
| `/tmp/omnirush/cybersecra-py312/bin/python scripts/smoke_api.py` | Passed against live FastAPI/Uvicorn and a temporary database |
| `PYTHONPATH=backend /tmp/omnirush/cybersecra-py312/bin/python -m compileall -q backend ml scripts` | Passed |
| `PYTHONPATH=backend /tmp/omnirush/cybersecra-py312/bin/python scripts/check_docker_config.py` | Configuration checks passed; Docker unavailable |
| `python3 scripts/check_mobile.py --json` | Flutter/Dart and generated platforms absent; commands blocked |

Normal Next.js compilation succeeded but native `copyfile` failed with `EPERM` on `/mnt/c`. `build:portable` adds an optional build-process-only stream-copy fallback and completed successfully. Ordinary Linux CI uses the normal build command.

Flutter tests and the newly configured CI jobs have **not** executed here. Model-output fixtures verify adapter behavior, not downloaded-model accuracy.

## Recomputed evaluation

Executed:

```bash
PYTHONPATH=backend /tmp/omnirush/cybersecra-py312/bin/python scripts/evaluation/evaluate_cybertrust.py
PYTHONPATH=backend /tmp/omnirush/cybersecra-py312/bin/python scripts/evaluation/run_ablation.py --summary
```

Artifacts: `data/evaluation/cybertrust_results.json`, `ablation_results.json`, `ablation_results.csv`, and `ablation_report.md`.

- CyberTrust-QA used **three existing questions** and the **five-document seed corpus**. Computed mean CERS: **0.4699**; abstention rate: **1/3**. Dataset/corpus hashes and generation time are recorded.
- Ablations used the existing **8,936-document runtime corpus**. **B/C/E/F/G/H/I/J** executed. **A** had no configured LLM; **D** had no configured cross-encoder and remains `not_run`.
- J's mean CERS was **0.41109999999999997**, with abstention on **all three questions**. This outcome is retained directly in the artifact.
- Equal retrieval scores on these few questions do not validate component effectiveness, CERS, or superiority. Human labels and broader evaluation remain necessary.

The existing raw/normalized corpus was reused. No missing source records, annotations, or evaluation outputs were invented.

## Remaining external work

1. Provision PostgreSQL/pgvector, Redis, and Neo4j and run live integration checks.
2. Install Flutter/Dart, generate platform projects, and run analysis, tests, and device builds.
3. Provision reviewed transformer checkpoints and an approved LLM; run model-backed inference and A/D configurations.
4. Supply human-reviewed reranker pairs, expanded CyberTrust-QA labels, and CERS calibration data.
5. Verify OCR binaries/complex tables and deploy the scheduled refresh worker.

The local-first application is runnable and substantially implemented. Production integration and research validity remain bounded by these prerequisites.
