# Reproducible data bootstrap

CyberSecRA-X does not assume a prepared cybersecurity dataset. It constructs a local data tree from explicit official endpoints and user-configured paper metadata sources.

## One command

```bash
# Evaluation/ML artifacts only; no internet required
PYTHONPATH=backend python scripts/bootstrap_data.py --evaluation

# Laptop profile: ATT&CK, CISA KEV, bounded recent NVD, configured NIST/OWASP pages
PYTHONPATH=backend python scripts/bootstrap_data.py --minimal

# Add ATLAS, CWE, CAPEC
PYTHONPATH=backend python scripts/bootstrap_data.py --full

# Add OpenAlex paper metadata; full text is opt-in and only uses advertised URLs
PYTHONPATH=backend python scripts/bootstrap_data.py --minimal --papers

# Incremental NVD last-modified window
PYTHONPATH=backend python scripts/bootstrap_data.py --minimal --update
```

The bootstrap prints a report and writes:

- `data/data_manifest.json`: source URL, version, checksum, terms/license note, counts, status, and errors;
- `data/data_version.json`: processing/embedding version and hardware profile;
- `data/processed/bootstrap_report.json`: complete run report;
- `data/normalized/`: unified entities and relationships;
- `data/chunks/`: sentence-aware chunks with provenance;
- `data/embeddings/`: explicit `tfidf-lite` CPU baseline embeddings;
- `data/processed/bm25_index.json`;
- `data/graph/cyber_graph.json`;
- `data/ml/`: labeled intent, OOD, verification, reranker, temporal, and contradiction artifacts.

## Source policy

The scripts use official structured feeds/APIs where available and a small explicit list of NIST/OWASP pages from `data/source_config.json`. They do not crawl. Requests use bounded retry/backoff, an identifying user agent, and cached raw files. NVD defaults to a seven-day bounded window and supports `--cve`, `--start-date`, `--end-date`, `--update`, `--limit`, and `--max-pages`.

A failed download is recorded as an error. The pipeline continues other stages, but the report exits non-zero when errors occurred. It never inserts an invented record for an unavailable source.

## Dataset categories

- **Authoritative knowledge:** downloaded source records with source URL/version/checksum and terms note.
- **Research-paper metadata:** OpenAlex metadata; individual paper rights remain with the publisher/author. Paywalls are not bypassed.
- **ML supervision:** manually curated bootstrap examples, explicitly labeled `manual_curated`; optional template augmentation is `synthetic=true`.
- **Evaluation:** CyberTrust-QA and generated validation artifacts.
- **Synthetic:** controlled contradiction/unknown examples and optional intent augmentation; never presented as intelligence.
- **Demo:** separate `data/demo/` namespace.

## Training

```bash
PYTHONPATH=backend python scripts/train_intent.py
PYTHONPATH=backend python scripts/train_ood.py
PYTHONPATH=backend python scripts/evaluate_models.py
PYTHONPATH=backend python scripts/validate_datasets.py
```

The default baseline is TF-IDF + Logistic Regression. It is trained only after the labeled dataset is built. The output stores configuration, timestamp, hardware profile, label mapping, metrics, and an explicit warning that the small bootstrap labels are not production ground truth.

## Scheduled/incremental refresh

Run the source refresh job manually or from an external scheduler:

```bash
PYTHONPATH=backend python scripts/update_sources.py --sources nvd cisa_kev mitre_attack
```

The job writes `data/processed/source_update_status.json`, preserves failure status, uses the ingestion scripts' retry/backoff logic, and supports incremental NVD updates. `backend/app/jobs/refresh.py` provides a bounded in-process scheduler wrapper; production deployments should run it through a durable worker/cron/Celery-style supervisor rather than relying on API process lifetime.

## Empty/offline environment behavior

If internet access is unavailable, run `--evaluation` to build ML/evaluation schemas and use `--minimal` later. Raw external data is only represented in the manifest after a real successful fetch. No placeholder CVEs, ATT&CK entities, advisories, papers, or metric results are created.
