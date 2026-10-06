"""Extract structured paper fields from openly downloaded PDFs when available."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from common import DATA_DIR, artifact_path, ensure_data_dirs, record_artifact, record_error, write_jsonl


def process() -> dict[str, Any]:
    ensure_data_dirs()
    pdf_dir = DATA_DIR / "raw/papers/pdf"
    output = DATA_DIR / "normalized/paper_sections.jsonl"
    pdfs = sorted(pdf_dir.glob("*.pdf")) if pdf_dir.exists() else []
    if not pdfs:
        result = {"status": "not_downloaded", "pdfs": 0, "records": 0, "reason": "No openly advertised PDFs were downloaded; metadata-only mode is valid."}
        output.write_text("", encoding="utf-8")
        record_artifact("paper_sections", output, records=0, status="not_downloaded")
        return result
    try:
        import fitz  # type: ignore
    except ImportError:
        result = {"status": "blocked", "pdfs": len(pdfs), "records": 0, "reason": "PyMuPDF is required for page-preserving PDF extraction."}
        record_error("paper_sections", result["reason"])
        return result
    try:
        from app.research.papers import extract_paper
    except ImportError as exc:
        raise RuntimeError("backend must be on PYTHONPATH for structured paper extraction") from exc
    rows = []
    failures = []
    for pdf in pdfs:
        try:
            pages = []
            with fitz.open(pdf) as document:
                for number, page in enumerate(document, start=1):
                    pages.append(f"[Page {number}]\n{page.get_text('text')}")
            text = "\n\n".join(pages)
            parsed = extract_paper(text, pdf.name)
            rows.append({"id": pdf.stem, "entity_type": "RESEARCH_PAPER_SECTION", "name": parsed.title, "description": parsed.abstract, "source": "open_access_paper_pdf", "source_file": artifact_path(pdf), "record": parsed.to_dict(), "page_text_available": True})
        except Exception as exc:
            failures.append({"file": str(pdf), "error": str(exc)})
    count = write_jsonl(output, rows)
    record_artifact("paper_sections", output, records=count, metadata={"pdfs": len(pdfs), "failures": len(failures), "provenance": "page markers and extracted field section spans"})
    return {"status": "processed" if rows else "error", "pdfs": len(pdfs), "records": count, "failures": failures}


def main() -> None:
    argparse.ArgumentParser().parse_args()
    print(json.dumps(process(), indent=2))


if __name__ == "__main__":
    main()
