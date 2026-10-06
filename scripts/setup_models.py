"""Explicit optional model setup; never downloads models at API startup."""
from __future__ import annotations

import argparse
import os


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--nli", action="store_true", help="download/load the configured NLI model")
    parser.add_argument("--model", default=os.getenv("NLI_MODEL", "cross-encoder/nli-deberta-v3-base"))
    args = parser.parse_args()
    if not args.nli:
        parser.error("choose --nli; model downloads are explicit")
    from app.verification.nli_verifier import TransformerNLI
    verifier = TransformerNLI(args.model)
    verifier.load(allow_download=True)
    print({"status": "loaded", "model": args.model})


if __name__ == "__main__":
    main()
