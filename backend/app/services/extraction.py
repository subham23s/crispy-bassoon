"""Validated document extraction; failures never become searchable evidence."""
from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


class ExtractionUnavailable(RuntimeError):
    pass


@dataclass
class Extraction:
    text: str
    spans: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    engine: str = "text"


def _ocr(image: Any) -> str:
    import shutil
    if not shutil.which("tesseract"):
        raise ExtractionUnavailable("OCR requires the Tesseract binary; document is not indexed")
    try:
        import pytesseract
    except ImportError as exc:
        raise ExtractionUnavailable("OCR requires pytesseract and Pillow") from exc
    try:
        return pytesseract.image_to_string(image, timeout=60).strip()
    except (RuntimeError, OSError) as exc:
        raise ExtractionUnavailable(f"OCR failed ({type(exc).__name__}); document is not indexed") from exc


def extract(filename: str, payload: bytes) -> Extraction:
    suffix = Path(filename).suffix.lower()
    spans: list[dict[str, Any]] = []
    warnings: list[str] = []
    parts: list[str] = []
    if not payload:
        raise ValueError("Document is empty")
    if suffix == ".pdf":
        try:
            import fitz
        except ImportError as exc:
            raise ExtractionUnavailable("PDF extraction requires PyMuPDF") from exc
        try:
            pdf = fitz.open(stream=payload, filetype="pdf")
        except Exception as exc:
            raise ValueError("Invalid or unreadable PDF") from exc
        with pdf:
            if pdf.needs_pass:
                raise ValueError("Encrypted PDF requires an unencrypted copy")
            if len(pdf) > 1000:
                raise ValueError("PDF exceeds the 1000-page processing limit")
            for number, page in enumerate(pdf, 1):
                text = page.get_text("text").strip()
                engine = "pymupdf"
                if not text:
                    try:
                        from PIL import Image
                        if page.rect.width * page.rect.height * 1.5 ** 2 > 40_000_000:
                            raise ValueError("Scanned PDF page exceeds OCR pixel limit")
                        pixmap = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5), alpha=False)
                        if pixmap.width * pixmap.height > 40_000_000:
                            raise ValueError("Scanned PDF page exceeds OCR pixel limit")
                        text = _ocr(Image.frombytes("RGB", [pixmap.width, pixmap.height], pixmap.samples))
                        engine = "tesseract"
                    except (ImportError, ExtractionUnavailable) as exc:
                        warnings.append(f"Page {number}: OCR unavailable ({type(exc).__name__})")
                        continue
                if text:
                    parts.append(f"[Page {number}]\n{text}")
                    spans.append({"page": number, "section": "body", "engine": engine})
                try:
                    for index, table in enumerate(page.find_tables().tables, 1):
                        cells = table.extract()
                        if cells:
                            parts.append(f"[Page {number}]\n[Table {index}]\n" + "\n".join(" | ".join(str(cell or "") for cell in row) for row in cells))
                            spans.append({"page": number, "section": f"table {index}", "engine": "pymupdf", "bbox": list(table.bbox)})
                except Exception as exc:
                    warnings.append(f"Page {number}: table extraction unavailable ({type(exc).__name__})")
        engine = "pdf_text_and_ocr"
    elif suffix == ".docx":
        try:
            from docx import Document
            from docx.table import Table
        except ImportError as exc:
            raise ExtractionUnavailable("DOCX extraction requires python-docx") from exc
        try:
            doc = Document(io.BytesIO(payload))
            for ordinal, item in enumerate(doc.iter_inner_content()):
                if isinstance(item, Table):
                    parts.append("[Table]\n" + "\n".join(" | ".join(cell.text for cell in row.cells) for row in item.rows))
                    spans.append({"page": None, "section": "table", "block": ordinal, "engine": "python-docx"})
                elif item.text.strip():
                    prefix = "# " if item.style and item.style.name.startswith("Heading") else ""
                    parts.append(prefix + item.text.strip())
                    spans.append({"page": None, "section": item.style.name if item.style else "paragraph", "block": ordinal, "engine": "python-docx"})
        except Exception as exc:
            raise ValueError("Invalid or unreadable DOCX") from exc
        warnings.append("DOCX has no reliable page boundaries before layout; page numbers are not inferred")
        engine = "python-docx"
    elif suffix in {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tiff", ".tif"}:
        try:
            from PIL import Image, UnidentifiedImageError
        except ImportError as exc:
            raise ExtractionUnavailable("Image OCR requires Pillow, pytesseract and Tesseract") from exc
        try:
            with Image.open(io.BytesIO(payload)) as image:
                if image.width * image.height > 40_000_000:
                    raise ValueError("Image exceeds OCR pixel limit")
                image.load()
                text = _ocr(image)
                if text:
                    parts.append(f"[Page 1]\n{text}")
        except UnidentifiedImageError as exc:
            raise ValueError("Invalid image; no evidence was indexed") from exc
        spans.append({"page": 1, "section": "image OCR", "engine": "tesseract"})
        engine = "tesseract"
    elif suffix in {".json", ".csv", ".txt", ".md", ".log", ""}:
        try:
            text = payload.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise ValueError("Text input must be UTF-8") from exc
        if suffix == ".json":
            try:
                text = json.dumps(json.loads(text), indent=2, ensure_ascii=False)
            except json.JSONDecodeError as exc:
                raise ValueError("Invalid JSON document") from exc
        elif suffix == ".csv":
            rows = list(csv.reader(io.StringIO(text)))
            text = "[Table]\n" + "\n".join(" | ".join(row) for row in rows)
        parts = [text]
        engine = suffix.lstrip(".") or "text"
        spans.append({"page": None, "section": "table" if suffix == ".csv" else "body", "engine": engine})
    else:
        raise ValueError(f"Unsupported file format: {suffix}")
    text = "\n\n".join(part for part in parts if part.strip())
    if not text.strip():
        if warnings:
            raise ExtractionUnavailable("No searchable text extracted. " + "; ".join(warnings))
        raise ValueError("No searchable text was found in the document")
    return Extraction(text, spans, warnings, engine)
