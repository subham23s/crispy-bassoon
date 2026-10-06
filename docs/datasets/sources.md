# Source and licensing register

| Source | Use in project | Access mode | License/terms action |
|---|---|---|---|
| NIST CSF 2.0 | curated framework evidence | official public page | verify NIST terms before redistribution |
| MITRE ATT&CK | technique evidence/graph mapping | official public page | review MITRE ATT&CK terms |
| CISA KEV | vulnerability catalog semantics | official catalog/API/download | follow CISA reuse and refresh guidance |
| NVD | CVE/API metadata semantics | official API documentation | follow NVD API rate/attribution requirements |
| OWASP LLM Top 10 | RAG security guidance | official project page | review OWASP project license |
| PyMuPDF, FastAPI, Flutter packages | runtime | package registries | preserve package licenses |

The repository's seed corpus contains concise attributed development notes, not a bulk redistribution of external datasets. Live ingestion must record URL, version, retrieval time, checksum, terms, and source license in document metadata.

Acquisition scripts:

- `scripts/data/ingest_mitre_attack.py` — official MITRE ATT&CK STIX bundle;
- `scripts/data/ingest_mitre_atlas.py` — official MITRE ATLAS YAML;
- `scripts/data/ingest_nvd.py` — bounded NVD API v2.0, CVE/date-range/incremental modes;
- `scripts/data/ingest_cisa_kev.py` — official CISA JSON catalog;
- `scripts/data/ingest_cwe.py` and `ingest_capec.py` — official MITRE XML archives;
- `scripts/data/ingest_nist.py` and `ingest_owasp.py` — explicit pages in `data/source_config.json`;
- `scripts/data/ingest_papers.py` — OpenAlex metadata with optional advertised open-access URLs.

A source is not represented as processed until the script successfully downloads/parses it. The manifest keeps failures and warnings instead of substituting demo data.
