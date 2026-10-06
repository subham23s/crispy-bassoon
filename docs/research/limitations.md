# Limitations

- The bundled seed corpus is intentionally small. The live bootstrap/update pipeline and standalone scheduler execute, including a fresh CISA refresh; continuously scheduled production deployment remains pending.
- TF-IDF-lite and token-overlap are still the active local baselines. A configurable transformer-NLI adapter is implemented, but model dependencies/weights are optional and were not downloaded in this environment.
- Contradiction detection is a polarity heuristic and can miss nuanced disagreements.
- PDF/DOCX parsing/export, real image/scanned-PDF OCR, and a ruled PDF table passed controlled round trips on October 3. Complex layouts/table fidelity and vision inference remain unverified. Image uploads extract text rather than making visual claims.
- PostgreSQL/pgvector, Redis, and Neo4j passed live local adapter tests. Docker startup and authenticated production Neo4j remain unverified; the local graph integration fixture used an isolated loopback-only server with authentication disabled.
- Flutter analysis and six tests pass with the available SDK. Android SDK/device builds and macOS/Xcode iOS builds remain pending.
- CERS has configurable weights/thresholds and a calibration evaluator, but no human-labeled calibration set exists; calibration remains explicitly pending.
- The latest A–J run executed B/C/E–J; A/D require unavailable LLM/cross-encoder configuration. Only three development questions exist, and graph/temporal effects are not established by equal retrieval scores. J abstained on all three items in this run; the artifact records this directly.
- No system should be used as the sole basis for patching, incident response, or risk acceptance.
