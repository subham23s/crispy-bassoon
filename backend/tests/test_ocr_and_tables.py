"""Round trips through real OCR/table engines, with clearly controlled fixtures."""
import importlib.util
import io
import shutil
import unittest
from unittest.mock import patch

from app.services.corpus import DocumentStore
from app.services.extraction import extract, ExtractionUnavailable

HAS_PDF = bool(importlib.util.find_spec("fitz"))
HAS_OCR = HAS_PDF and bool(importlib.util.find_spec("pytesseract")) and bool(importlib.util.find_spec("PIL")) and bool(shutil.which("tesseract"))


@unittest.skipUnless(HAS_OCR, "Real image/PDF OCR requires Tesseract, pytesseract, Pillow, and PyMuPDF")
class OcrRoundTripTests(unittest.TestCase):
    @staticmethod
    def image_fixture():
        import fitz
        with fitz.open() as document:
            page = document.new_page(width=600, height=150)
            page.insert_text((30, 70), "CYBERSECURITY EVIDENCE", fontsize=28)
            return page.get_pixmap(matrix=fitz.Matrix(3, 3), alpha=False).tobytes("png")

    def test_camera_image_ocr_is_searchable_and_retains_page_locator(self):
        store = DocumentStore()
        document = store.ingest_bytes("camera.png", self.image_fixture(), owner_id="fixture-owner")
        self.assertIn("CYBERSECURITY EVIDENCE", document.content)
        self.assertEqual(document.extraction["engine"], "tesseract")
        chunks = list(store.get_chunks({document.document_id}))
        self.assertEqual(chunks[0].page_number, 1)

    def test_scanned_pdf_uses_real_ocr_and_preserves_engine_and_page(self):
        import fitz
        with fitz.open() as document:
            page = document.new_page(width=600, height=150)
            page.insert_image(page.rect, stream=self.image_fixture())
            self.assertFalse(page.get_text().strip())
            payload = document.tobytes()
        result = extract("scanned.pdf", payload)
        self.assertIn("CYBERSECURITY EVIDENCE", result.text)
        self.assertEqual(result.spans[0], {"page": 1, "section": "body", "engine": "tesseract"})

    def test_ocr_timeout_is_explicit_and_does_not_index_a_document(self):
        store = DocumentStore()
        before = len(store.documents)
        with patch("pytesseract.image_to_string", side_effect=RuntimeError("Tesseract timeout")):
            with self.assertRaises(ExtractionUnavailable):
                store.ingest_bytes("camera.png", self.image_fixture(), owner_id="fixture-owner")
        self.assertEqual(len(store.documents), before)


@unittest.skipUnless(HAS_PDF, "PyMuPDF is optional")
class PdfTableTests(unittest.TestCase):
    def test_ruled_table_retains_cells_page_and_bounding_box(self):
        import fitz
        with fitz.open() as document:
            page = document.new_page(width=400, height=200)
            for x in (30, 190, 350):
                page.draw_line((x, 30), (x, 130))
            for y in (30, 80, 130):
                page.draw_line((30, y), (350, y))
            for x, y, text in ((40, 60, "Control"), (200, 60, "Status"), (40, 110, "Monitoring"), (200, 110, "Required")):
                page.insert_text((x, y), text, fontsize=12)
            payload = document.tobytes()
        result = extract("table.pdf", payload)
        self.assertIn("Monitoring | Required", result.text)
        table = next(span for span in result.spans if span["section"] == "table 1")
        self.assertEqual(table["page"], 1)
        self.assertEqual(len(table["bbox"]), 4)
