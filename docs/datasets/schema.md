# Unified data schema

## CyberEntity

```json
{
  "id": "source:source_id",
  "entity_type": "CVE | CWE | CAPEC | ATTACK_TECHNIQUE | ATLAS_TECHNIQUE | ...",
  "name": "",
  "description": "",
  "source": "NVD",
  "source_id": "CVE-...",
  "version": "",
  "created_at": "",
  "updated_at": "",
  "references": [],
  "metadata": {},
  "source_file": "data/raw/..."
}
```

## Chunk

Each chunk retains `chunk_id`, `document_id`, text, page/section fields, character offsets, source, source ID, version, references, and source-file provenance.

## ML rows

Intent rows contain `text`, `intent`, `source_type`, `source`, `synthetic`, and `difficulty`. OOD rows contain explicit `IN_DOMAIN`/`OUT_OF_DOMAIN` labels. Claim verification rows contain `claim`, `evidence`, `label`, provenance fields, and `synthetic`. Reranker rows contain query/document/relevance and construction provenance.

The normalized JSONL and generated artifacts are append-free/replaced deterministically by source ID, so rerunning a source does not duplicate records.
