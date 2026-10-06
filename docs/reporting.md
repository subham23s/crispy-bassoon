# Report export

`POST /reports/export` accepts an authenticated JSON body:

```json
{"query":"What does NIST CSF 2.0 provide?","mode":"RESEARCHER","format":"markdown"}
```

Formats:

- `json`: complete answer object;
- `markdown`: human-readable report with claims, citation IDs, evidence, provenance, contradictions, timeline, and limitations;
- `docx`: optional `python-docx` dependency;
- `pdf`: optional `reportlab` dependency.

Optional formats fail with an explicit dependency message instead of returning a fake file. The report exporter never invents references or evidence.
