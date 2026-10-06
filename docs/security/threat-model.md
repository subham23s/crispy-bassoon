# Security and threat model

## Assets

- user credentials and refresh/access tokens;
- uploaded papers, logs, screenshots, and workspace metadata;
- source provenance and claim verification records;
- model/provider credentials.

## Threats and controls

| Threat | Control in this increment | Remaining work |
|---|---|---|
| Password disclosure | PBKDF2-SHA256 salted hashes; no plaintext persistence | Deploy a secrets manager and password reset/email workflow |
| Token tampering | HS256 signed tokens with expiry; secure mobile storage | Key rotation and refresh-token family/revocation store |
| Prompt injection | pre-index pattern scan; retrieved content remains data | classifier/red-team suite and provider-level tool isolation |
| Cross-tenant documents | owner tags and owner-scoped metadata persistence | enforce owner filters in every production repository query and integration test |
| Malicious uploads | size limits, extension-aware parsing, checksum, no execution | antivirus/sandbox, MIME sniffing, object storage isolation |
| Hallucinated CVEs/citations | exact-identifier abstention, provenance, claim status | live source adapters and NLI/citation entailment |
| DoS/rate abuse | request validation and bounded file size | Redis rate limiting behind a reverse proxy |
| Data leakage in logs | structured internal errors avoid raw stacks in API | audit log redaction review and retention/deletion jobs |

This is a defensive research system. It does not scan targets, exploit vulnerabilities, deploy malware, or perform credential actions.
