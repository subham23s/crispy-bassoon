# Claim verification

The verification architecture is in `backend/app/verification/`:

- `claim_extractor.py` — deterministic atomic claim extraction;
- `nli_verifier.py` — lazy Hugging Face transformer-NLI adapter plus explicit heuristic fallback;
- `citation_verifier.py` — claim/evidence entailment and citation IDs;
- `contradiction_detector.py` — cross-source contradiction classification;
- `verification_pipeline.py` — composable end-to-end pipeline.

Configure:

```bash
NLI_PROVIDER=auto
NLI_MODEL=cross-encoder/nli-deberta-v3-base
```

`auto` attempts the transformer only when the optional ML environment is installed and the model can load. Otherwise results clearly say `used_fallback: true`. `NLI_PROVIDER=transformer` fails closed if the model is unavailable; it does not silently claim a transformer result.

Explicit setup:

```bash
python -m pip install -r backend/requirements-ml.txt
PYTHONPATH=backend python scripts/setup_models.py --nli
```

No NLI accuracy is reported without a labeled evaluation run.
