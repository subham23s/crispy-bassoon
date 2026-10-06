# API endpoints

All request/response schemas are JSON in fallback mode and are also exposed through FastAPI OpenAPI when FastAPI is installed.

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | runtime health and mode |
| GET | `/health/detailed` | dependency/degraded-mode report |
| POST | `/auth/register` | create account; password is hashed |
| POST | `/auth/login` | issue expiring bearer + refresh tokens |
| POST | `/auth/refresh` | rotate a refresh token and issue a new access token |
| POST | `/auth/logout` | revoke the supplied refresh token |
| GET | `/auth/me` | inspect authenticated identity |
| POST | `/chat/query` | understand, retrieve, verify, score, and answer |
| POST | `/chat/stream` | SSE status, provisional deltas/reset, verified completion, and errors in both runtimes |
| GET | `/chat/history` | authenticated user's saved answers |
| GET | `/chat/answers/{id}` | reopen an owned saved answer |
| POST | `/documents/upload` | base64/text upload, checksum, scan, chunk, index |
| GET | `/documents` | list owned documents and processing jobs |
| GET | `/documents/{id}/chunks` | inspect visible indexed chunks |
| GET | `/documents/jobs/{id}` | inspect owned upload processing state |
| GET | `/documents/{id}` | inspect owned/curated document metadata |
| DELETE | `/documents/{id}` | delete an owned user document and index chunks |
| POST | `/research/gap-analysis` | label candidate gap observations |
| GET/POST | `/research/workspaces` | list/create owned workspaces |
| GET/POST | `/research/workspaces/{id}/items` | list/create research items |
| GET/POST | `/research/workspaces/{id}/notes` | list/create notes |
| GET/POST | `/research/workspaces/{id}/evidence` | save/list snapshots; repeated chunk IDs update a bookmark |
| GET/POST | `/experiments` | list/create experiments with dataset, model, parameters, notes, and status |
| GET/PATCH/DELETE | `/experiments/{id}` | inspect/update/delete an owned experiment; edits preserve metrics |
| POST | `/experiments/{id}/metrics` | record a finite JSON number under a nonempty metric name |
| GET | `/experiments/compare` | compare persisted owner-scoped metrics |
| GET | `/timeline?start=YYYY-MM-DD&end=YYYY-MM-DD` | inclusive dates; invalid/reversed bounds return 400 |
| GET | `/papers` | visible paper records |
| POST | `/papers/analyze`, `/papers/compare` | source-backed paper analysis/comparison |
| GET | `/vulnerabilities/{cve_id}` | exact identifier evidence lookup with abstention |
| POST | `/logs/analyze` | defensive heuristic log triage |
| POST | `/ioc/analyze` | local IOC classification without enrichment |
| GET | `/graph/entity/{entity_id}` | provenance-backed relationship adapter |
| POST | `/rag-security/scan` | controlled prompt-injection signal scan |
| POST | `/reports/export` | export a verified query report as JSON, Markdown, DOCX, or PDF (optional exporters require ML/report dependencies) |
| GET | `/data/refresh/status` | authenticated source-update status |
| GET | `/data/refresh/sources` | administrator's configured source choices |
| POST | `/data/refresh` | administrator starts a bounded refresh with `sources` and optional `force` |
| GET | `/data/refresh/jobs/{id}` | administrator inspects QUEUED/PROCESSING/COMPLETED/PARTIAL/FAILED state |
| GET | `/admin/overview` | administrator's persisted users/documents/jobs and service overview |
| GET | `/evaluation` | benchmark availability and non-hard-coded metric policy |

Private routes require a bearer token (401 when absent/invalid); administrator role denials return 403. Experiment status is one of `created`, `running`, `completed`, `failed`, or `cancelled`. Hyperparameters must be a JSON object. Metric values are user-supplied measurements, not server-validated research findings.

External source credentials are optional. When they are not configured, the API says so rather than generating current values. Transformer NLI is configured through `NLI_PROVIDER`/`NLI_MODEL`; `auto` falls back explicitly to labeled heuristic verification when optional ML dependencies/model weights are unavailable.
