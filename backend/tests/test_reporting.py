import unittest
import io
import importlib.util

from app.reporting.exporter import export_answer
from app.services import DocumentStore, ResearchPipeline


class ReportingTests(unittest.TestCase):
    @unittest.skipUnless(importlib.util.find_spec("docx"), "python-docx is optional")
    def test_docx_export_and_ingestion_preserve_evidence(self):
        from docx import Document
        from app.services.extraction import extract
        answer = ResearchPipeline(DocumentStore()).ask("What does NIST CSF 2.0 provide?")
        report = export_answer(answer, "docx")
        document = Document(io.BytesIO(report.content))
        text = "\n".join(paragraph.text for paragraph in document.paragraphs)
        self.assertIn(answer.evidence[0].chunk_id, text)
        self.assertIn("Claims and verification", extract(report.filename, report.content).text)

    @unittest.skipUnless(importlib.util.find_spec("reportlab") and importlib.util.find_spec("fitz"), "PDF report dependencies are optional")
    def test_pdf_export_and_ingestion_preserve_provenance(self):
        import fitz
        from app.services.extraction import extract
        answer = ResearchPipeline(DocumentStore()).ask("What does NIST CSF 2.0 provide?")
        report = export_answer(answer, "pdf")
        with fitz.open(stream=report.content, filetype="pdf") as document:
            self.assertGreater(len(document), 0)
            self.assertIn("Evidence reliability", "".join(page.get_text() for page in document))
        extracted = extract(report.filename, report.content)
        self.assertTrue(extracted.spans)
        self.assertIn("https://www.nist.gov/cyberframework", extracted.text)

    def test_markdown_and_json_exports_preserve_claims_and_provenance(self):
        answer = ResearchPipeline(DocumentStore()).ask("What does NIST CSF 2.0 provide?")
        markdown = export_answer(answer, "markdown")
        payload = export_answer(answer, "json")
        self.assertIn(b"Evidence reliability", markdown.content)
        self.assertIn(b"claims", payload.content)
        self.assertIn(answer.evidence[0].chunk_id.encode(), markdown.content)

    def test_unknown_format_is_rejected(self):
        answer = ResearchPipeline(DocumentStore()).ask("What does NIST CSF 2.0 provide?")
        with self.assertRaises(ValueError):
            export_answer(answer, "html")


if __name__ == "__main__":
    unittest.main()
