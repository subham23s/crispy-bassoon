"""Evidence-preserving Markdown/JSON/PDF/DOCX report export."""
from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from typing import Any

from app.models import Answer


@dataclass
class ExportedReport:
    filename: str
    media_type: str
    content: bytes

    def to_dict(self) -> dict[str, Any]:
        return {"filename": self.filename, "media_type": self.media_type, "content_base64": base64.b64encode(self.content).decode("ascii")}


def report_markdown(answer: Answer) -> str:
    data = answer.to_dict()
    lines = [f"# CyberSecRA-X Report: {answer.query}", "", "## Executive summary", answer.answer, "", "## Evidence reliability", json.dumps(answer.cers, indent=2), "", "## Claims and verification"]
    for claim in data["claims"]:
        lines += [f"- **{claim['status']}** ({claim['support_score']:.3f}) {claim['claim']}", f"  - Explanation: {claim['explanation']}", f"  - Citation IDs: {', '.join(claim['citation_ids']) or 'none'}"]
    lines += ["", "## Evidence and provenance"]
    for item in data["evidence"]:
        lines += [f"### {item['source']} — {item['title']}", f"- URL: {item['url'] or 'not provided'}", f"- Chunk: {item['chunk_id']}", f"- Authority: {item['authority_score']}", "", item["text"], ""]
    relationships = [edge for item in data["evidence"] for edge in item.get("provenance", {}).get("graph_relationships", [])]
    lines += ["## Contradictions", json.dumps(data["conflicts"], indent=2), "", "## Related query entities", json.dumps(data["related_entities"], indent=2), "", "## Knowledge graph relationships", json.dumps(relationships, indent=2), "", "## Timeline", json.dumps(data["timeline"], indent=2), "", "## Limitations"]
    lines += [f"- {item}" for item in data["limitations"]]
    references = []
    for item in data["evidence"]:
        url = item.get("url")
        if url and url not in references:
            references.append(url)
    lines += ["", "## References"] + [f"- {url}" for url in references]
    return "\n".join(lines) + "\n"


def export_answer(answer: Answer, fmt: str) -> ExportedReport:
    fmt = fmt.lower()
    if fmt == "json":
        return ExportedReport("cybersecra-report.json", "application/json", json.dumps(answer.to_dict(), indent=2, ensure_ascii=False).encode())
    markdown = report_markdown(answer)
    if fmt in {"md", "markdown"}:
        return ExportedReport("cybersecra-report.md", "text/markdown; charset=utf-8", markdown.encode())
    if fmt == "docx":
        try:
            from docx import Document  # type: ignore
        except ImportError as exc:
            raise ValueError("DOCX export requires python-docx; install backend/requirements-documents.txt") from exc
        document = Document()
        for line in markdown.splitlines():
            document.add_paragraph(line)
        import io
        buffer = io.BytesIO()
        document.save(buffer)
        return ExportedReport("cybersecra-report.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", buffer.getvalue())
    if fmt == "pdf":
        try:
            from reportlab.lib.pagesizes import letter
            from reportlab.lib.styles import getSampleStyleSheet
            from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
        except ImportError as exc:
            raise ValueError("PDF export requires reportlab; install backend/requirements-documents.txt") from exc
        import io
        from xml.sax.saxutils import escape
        buffer = io.BytesIO()
        styles = getSampleStyleSheet()
        flow = []
        for line in markdown.splitlines():
            if not line:
                flow.append(Spacer(1, 8))
            else:
                style = styles["Heading2"] if line.startswith("#") else styles["BodyText"]
                flow.append(Paragraph(escape(line.lstrip("# ")), style))
        SimpleDocTemplate(buffer, pagesize=letter, title=answer.query).build(flow)
        return ExportedReport("cybersecra-report.pdf", "application/pdf", buffer.getvalue())
    raise ValueError("format must be one of json, markdown, docx, pdf")
