"""CyberSecRA-X API.

FastAPI is the preferred runtime. A dependency-free JSON HTTP fallback is kept
for constrained development environments where dependencies are unavailable;
it uses the exact same domain services and is clearly reported by /health.
"""
from __future__ import annotations

import base64
import json
import logging
import hashlib
import math
import re
import sys
import uuid
from datetime import date, datetime, timezone
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from app.auth import AuthService
from app.config import settings
from app.database import Infrastructure, AdminRecord, Experiment, IngestionJob, Note, ResearchItem, SavedEvidence, Workspace
from app.services import DocumentStore, ResearchPipeline
from app.services.corpus import scan_content
from app.services.document_jobs import DocumentJobManager
from app.services.extraction import ExtractionUnavailable
from app.research.gaps import analyze_gap_candidates
from app.services.rag_security import assess_text, assess_documents, evaluate as evaluate_rag_security
from app.services.graph import EvidenceGraph
from app.jobs.refresh import RefreshManager
from app.services.source_refresh import SOURCES
from app.reporting.exporter import export_answer
from app.models import Answer
from app.research.papers import extract_paper, compare_papers

logger = logging.getLogger(__name__)

try:  # Optional until the documented environment is installed.
    from fastapi import FastAPI, HTTPException, Request
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import JSONResponse, StreamingResponse
    import uvicorn

    HAS_FASTAPI = True
except ImportError:  # pragma: no cover - exercised in the constrained base image.
    FastAPI = Any  # type: ignore
    HAS_FASTAPI = False


class Runtime:
    def __init__(self) -> None:
        self.infrastructure = Infrastructure(settings)
        self.repository = self.infrastructure.repository
        self.auth = AuthService(self.repository, settings.jwt_secret, settings.access_token_minutes)
        self.store = DocumentStore(include_bootstrap=True)
        # Rehydrate owned documents before serving requests. Seed documents are
        # loaded by DocumentStore itself; persisted user documents remain tenant
        # tagged and are only visible to their owner.
        for record in self.repository.list_all_documents():
            owner_id = str(record.get("owner_id") or "")
            if owner_id:
                self.store.load_persisted(record, owner_id)
        self.pipeline = ResearchPipeline(self.store)
        self.graph = EvidenceGraph(settings.data_dir, self.infrastructure.neo4j)
        self.pipeline.retriever.graph = self.graph
        self.refresh_jobs = RefreshManager()
        spool = Path(self.repository.path).parent / "ingestion_jobs" if hasattr(self.repository, "path") else settings.data_dir / "ingestion_jobs" / hashlib.sha256(settings.database_url.encode()).hexdigest()[:12]
        self.document_jobs = DocumentJobManager(self._process_upload, spool_dir=spool, on_update=self._persist_document_job)
        self.runtime_mode = "fastapi" if HAS_FASTAPI else "stdlib-fallback"

    def _process_upload(self, filename: str, payload: bytes, *, source: str, source_type: str, owner_id: str) -> Any:
        document = self.store.ingest_bytes(filename, payload, source=source, source_type=source_type, owner_id=owner_id)
        status = "quarantined" if document.security_flags else "indexed"
        self.repository.save_document(document.document_id, owner_id, document.title, document.source, document.checksum, status, document.to_dict(), document.ingestion_timestamp)
        self.repository.save_chunks(document.document_id, owner_id, [chunk.to_dict() for chunk in self.store.get_chunks({document.document_id})])
        return document

    def _persist_document_job(self, record: dict[str, Any]) -> None:
        job = IngestionJob(str(record["job_id"]), str(record.get("owner_id") or ""), None, "document_upload", str(record.get("status", "QUEUED")).lower(), str(record.get("filename", "")), str(record.get("error") or ""), {"filename": record.get("filename", ""), "document_id": record.get("document_id"), "document_status": record.get("document_status")}, str(record.get("submitted_at") or _now()), record.get("started_at"), record.get("finished_at"))
        self.repository.save_ingestion_job(job)

    def close(self) -> None:
        self.document_jobs.close()
        self.refresh_jobs.executor.shutdown(wait=True)
        self.infrastructure.close()


runtime = Runtime()


def _user_from_request(headers: dict[str, str]) -> dict[str, Any] | None:
    authorization = headers.get("authorization", "")
    if not authorization.lower().startswith("bearer "):
        return None
    try:
        return runtime.auth.authenticate(authorization.split(" ", 1)[1].strip())
    except ValueError:
        return None


def _require_user(user: dict[str, Any] | None) -> dict[str, Any]:
    if user is None:
        raise PermissionError("Authentication required")
    return user


class ForbiddenError(PermissionError):
    pass


def _require_admin(user: dict[str, Any] | None) -> dict[str, Any]:
    actor = _require_user(user)
    if str(actor.get("role", "")).upper() not in {"ADMIN", "SUPERADMIN"}:
        raise ForbiddenError("Administrator role required")
    return actor


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _experiment_record(payload: dict[str, Any], owner_id: str, previous: dict[str, Any] | None = None) -> Experiment:
    values = {**(previous or {}), **payload}
    name = values.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ValueError("experiment name is required")
    parameters = values.get("hyperparameters", {})
    if not isinstance(parameters, dict):
        raise ValueError("hyperparameters must be a JSON object")
    try:
        json.dumps(parameters, allow_nan=False)
    except (ValueError, TypeError) as exc:
        raise ValueError("hyperparameters must contain finite JSON values") from exc
    status = values.get("status", "created")
    if not isinstance(status, str) or status not in {"created", "running", "completed", "failed", "cancelled"}:
        raise ValueError("status must be created, running, completed, failed, or cancelled")
    _validate_workspace(values, owner_id)
    return Experiment(previous["id"] if previous else str(uuid.uuid4()), owner_id, name.strip(), values.get("workspace_id") or None, str(values.get("dataset", "")), str(values.get("model", "")), parameters, str(values.get("notes", "")), status, previous["created_at"] if previous else _now(), _now())


def _document_summary(document: Any) -> dict[str, Any]:
    return {
        "document_id": document.document_id,
        "title": document.title,
        "source": document.source,
        "source_type": document.source_type,
        "url": document.url,
        "version": document.version,
        "language": document.language,
        "tags": [tag for tag in document.tags if not tag.startswith("owner:")],
        "checksum": document.checksum,
        "ingestion_timestamp": document.ingestion_timestamp,
        "status": "quarantined" if document.security_flags else "indexed",
        "security_flags": document.security_flags,
        "extraction": document.extraction,
        "chunk_count": runtime.store.chunk_count(document.document_id),
    }


def _refresh_status() -> dict[str, Any]:
    path = settings.data_dir / "processed" / "source_update_status.json"
    if not path.exists():
        return {"status": "never_run", "failures": [], "last_successful_update": []}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"status": "invalid_status_file", "failures": ["status file is not valid JSON"], "last_successful_update": []}


def _refresh_worker_status() -> dict[str, Any]:
    path = settings.data_dir / "processed/refresh_worker_status.json"
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
        last_run = datetime.fromisoformat(state["last_run"]).astimezone(timezone.utc)
        age = (datetime.now(timezone.utc) - last_run).total_seconds()
        # --once is a verification command, not an active scheduled process.
        state["active"] = not state.get("once", False) and state["status"] in {"ready", "degraded", "busy"} and 0 <= age <= max(60, int(state["interval_seconds"])) * 2
        return state
    except (OSError, ValueError, KeyError, TypeError):
        return {"status": "unavailable", "active": False}


def _ioc_result(text: str) -> dict[str, Any]:
    indicators = []
    for value in sorted(set(re.findall(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", text))):
        indicators.append({"type": "ipv4", "value": value, "match": "local regex", "status": "not_enriched", "explanation": "No external intelligence lookup is configured."})
    for value in sorted(set(re.findall(r"\b(?:[0-9a-f]{32}|[0-9a-f]{40}|[0-9a-f]{64})\b", text, re.IGNORECASE))):
        indicators.append({"type": "hash", "value": value, "match": "local regex", "status": "not_enriched", "explanation": "No external intelligence lookup is configured."})
    for value in sorted(set(re.findall(r"\b[A-Za-z0-9.-]+\.(?:com|org|net|io|gov|in|edu)\b", text, re.IGNORECASE))):
        indicators.append({"type": "domain", "value": value, "match": "local regex", "status": "not_enriched", "explanation": "No external intelligence lookup is configured."})
    return {"indicators": indicators, "count": len(indicators), "analysis_basis": "local regex classification only", "limitations": ["IOC enrichment is not performed without an approved provider and API key.", "A classified IOC is not evidence of maliciousness."]}


def _log_result(text: str) -> dict[str, Any]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    suspicious_terms = ("failed", "denied", "invalid", "powershell", "cmd.exe", "suspicious", "malware", "brute force")
    events = []
    for number, line in enumerate(lines, start=1):
        matches = [term for term in suspicious_terms if term in line.lower()]
        if matches:
            events.append({"line": number, "text": line[:1000], "signals": matches, "assessment": "Potentially suspicious activity; corroboration is required."})
    return {"line_count": len(lines), "potentially_suspicious": events, "attack_mappings": [{"technique": "T1059", "reason": "Command interpreter terms were observed; this is a lead, not proof."}] if any("powershell" in line.lower() or "cmd.exe" in line.lower() for line in lines) else [], "analysis_basis": "local keyword heuristic; not an incident determination", "limitations": ["Heuristic local parser only; no incident is asserted from weak evidence."]}


def _security_scan(text: str) -> dict[str, Any]:
    result = assess_text(text)
    result["matches"] = result.pop("signals", [])
    result["action"] = "isolate_document_content_and_do_not_execute_instructions" if result["prompt_injection_detected"] else "no_known_pattern_detected"
    result["limitations"] = ["Pattern detection is a defense-in-depth signal, not a proof of intent."]
    return result


def _workspace_owned(workspace_id: str, owner_id: str) -> bool:
    return any(str(item.get("id")) == workspace_id for item in runtime.repository.list_workspaces(owner_id))


def _query_response(payload: dict[str, Any], user_id: str) -> dict[str, Any]:
    query = str(payload.get("query", "")).strip()
    if not query:
        raise ValueError("query is required")
    mode = str(payload.get("mode", "RESEARCHER")).upper()
    _validate_workspace(payload, user_id)
    answer = runtime.pipeline.ask(query, mode=mode, owner_id=user_id)
    _save_answer(answer, payload, user_id)
    return answer.to_dict()


def _validate_workspace(payload: dict[str, Any], user_id: str) -> None:
    workspace_id = str(payload.get("workspace_id") or "").strip()
    if workspace_id and not _workspace_owned(workspace_id, user_id):
        raise ValueError("Workspace not found")


def _save_answer(answer: Answer, payload: dict[str, Any], user_id: str) -> None:
    runtime.repository.save_answer(user_id, answer.to_dict())
    workspace_id = str(payload.get("workspace_id", "")).strip()
    if workspace_id:
        runtime.repository.save_research_item(ResearchItem(str(uuid.uuid4()), workspace_id, user_id, "answer", answer.query, "active", None, {"answer": answer.to_dict()}, _now(), _now()))


def _upload_response(payload: dict[str, Any], user_id: str) -> dict[str, Any]:
    filename = str(payload.get("filename", "upload.txt"))
    encoded = payload.get("content_base64")
    if encoded:
        try:
            content = base64.b64decode(encoded, validate=True)
        except Exception as exc:
            raise ValueError("content_base64 is invalid") from exc
    else:
        raw = payload.get("content", "")
        content = str(raw).encode("utf-8")
    if len(content) > settings.max_upload_bytes:
        raise ValueError("uploaded file exceeds the configured size limit")
    source_type = "paper" if payload.get("source_type") == "paper" else "user_document"
    if bool(payload.get("background")) or len(content) >= settings.background_upload_bytes:
        job = runtime.document_jobs.submit(filename=filename, payload=content, owner_id=user_id, source_type=source_type)
        return {"status": "QUEUED", "job": job, "processing_states": sorted(DocumentJobManager.STATES)}
    document = runtime._process_upload(filename, content, source="user_upload", source_type=source_type, owner_id=user_id)
    status = "quarantined" if document.security_flags else "indexed"
    return {"status": status, "document": _document_summary(document), "chunks": runtime.store.chunk_count(document.document_id), "security_scan": _security_scan(document.content), "processing_state": "COMPLETED"}


def _route(method: str, path: str, payload: dict[str, Any], headers: dict[str, str]) -> tuple[int, dict[str, Any]]:
    parsed = urlparse(path)
    params = parse_qs(parsed.query)
    path = parsed.path
    user = _user_from_request(headers)
    try:
        if method == "GET" and path == "/ready":
            infrastructure = runtime.infrastructure.health()
            database = infrastructure["services"]["database"]
            ready = database["available"]
            if not ready and getattr(runtime.repository, "backend_name", "") == "sqlite":
                try:
                    with runtime.repository.connect() as connection:
                        connection.execute("SELECT 1")
                    ready = True
                except Exception:
                    ready = False
            return (200 if ready else 503), {"status": "ready" if ready else "not_ready", "repository": infrastructure["repository_backend"], "degraded": infrastructure["degraded"]}
        if method == "GET" and path == "/health":
            infrastructure = runtime.infrastructure.health()
            return 200, {
                "status": "degraded" if infrastructure["degraded"] else "ok",
                "service": settings.app_name,
                "runtime": runtime.runtime_mode,
                "mode": infrastructure["mode"],
                "degraded": infrastructure["degraded"],
                "evidence_mode": "curated-local-corpus",
            }
        if method == "GET" and path == "/health/detailed":
            infrastructure = runtime.infrastructure.health()
            services = infrastructure["services"]
            return 200, {
                "status": "degraded" if infrastructure["degraded"] else "ok",
                "runtime": runtime.runtime_mode,
                "database": infrastructure["repository_backend"],
                "redis": "ready" if services["redis"]["available"] else services["redis"]["state"],
                "graph": "neo4j" if services["neo4j"]["available"] else "in-process-provenance",
                "degraded": infrastructure["degraded"],
                "degraded_mode": infrastructure["degraded"],
                "degraded_reasons": infrastructure["reasons"],
                "infrastructure": infrastructure,
                "llm_provider": settings.llm_provider,
                "external_current_data": False,
                "source_refresh_status": _refresh_status(),
                "refresh_worker": _refresh_worker_status(),
                "capabilities": {
                    "query_understanding": True,
                    "hybrid_retrieval": True,
                    "claim_verification": True,
                    "document_ingestion": True,
                    "vision_interpretation": False,
                    "source_refresh_jobs": True,
                    "scheduled_refresh_worker": _refresh_worker_status()["active"],
                    "live_source_refresh": True,
                    "nli_transformer": __import__("importlib.util").util.find_spec("transformers") is not None,
                    "production_postgres": services["database"]["available"] and infrastructure["repository_backend"] == "postgresql-pgvector",
                    "redis_cache": services["redis"]["available"],
                    "neo4j_graph": services["neo4j"]["available"],
                },
            }
        if method == "POST" and path == "/auth/register":
            return 201, runtime.auth.register(str(payload.get("email", "")), str(payload.get("password", "")), str(payload.get("role", "USER")))
        if method == "POST" and path == "/auth/login":
            return 200, runtime.auth.login(str(payload.get("email", "")), str(payload.get("password", "")))
        if method == "POST" and path == "/auth/refresh":
            return 200, runtime.auth.refresh(str(payload.get("refresh_token", "")))
        if method == "POST" and path == "/auth/logout":
            _require_user(user)
            runtime.auth.logout(str(payload.get("refresh_token", "")))
            return 200, {"status": "logged_out"}
        if method == "GET" and path == "/auth/me":
            actor = _require_user(user)
            return 200, {"user": actor}
        if method == "POST" and path == "/chat/query":
            actor = _require_user(user)
            return 200, _query_response(payload, actor["sub"])
        if method == "GET" and path == "/chat/history":
            actor = _require_user(user)
            return 200, {"answers": runtime.repository.list_answers(actor["sub"])}
        answer_match = re.fullmatch(r"/chat/answers/([^/]+)", path)
        if method == "GET" and answer_match:
            actor = _require_user(user)
            answer = runtime.repository.get_answer(answer_match.group(1), actor["sub"])
            return (200, {"answer": answer}) if answer else (404, {"detail": "Answer not found"})
        if method == "POST" and path == "/documents/upload":
            actor = _require_user(user)
            return 201, _upload_response(payload, actor["sub"])
        if method == "GET" and path == "/documents":
            actor = _require_user(user)
            return 200, {"documents": [_document_summary(item) for item in runtime.store.list_documents(actor["sub"], include_shared=False)], "jobs": runtime.document_jobs.list(actor["sub"]), "persisted_jobs": runtime.repository.list_ingestion_jobs(actor["sub"])}
        job_match = re.fullmatch(r"/documents/jobs/([^/]+)", path)
        if method == "GET" and job_match:
            actor = _require_user(user)
            job = runtime.document_jobs.get(job_match.group(1), actor["sub"])
            if job is None:
                saved = runtime.repository.get_ingestion_job(job_match.group(1), actor["sub"])
                if saved:
                    job = {**saved, "job_id": saved["id"], "status": saved["status"].upper(), **saved.get("metadata", {})}
            return (200, {"job": job}) if job else (404, {"detail": "Processing job not found"})
        chunks_match = re.fullmatch(r"/documents/([^/]+)/chunks", path)
        if method == "GET" and chunks_match:
            actor = _require_user(user)
            document = runtime.store.get_document(chunks_match.group(1), owner_id=actor["sub"])
            if document is None:
                return 404, {"detail": "Document not found"}
            return 200, {"chunks": [chunk.to_dict() for chunk in runtime.store.get_chunks({document.document_id})]}
        document_match = re.fullmatch(r"/documents/([^/]+)", path)
        if document_match and method in {"GET", "DELETE"}:
            actor = _require_user(user)
            document_id = document_match.group(1)
            if method == "GET":
                document = runtime.store.get_document(document_id, owner_id=actor["sub"])
                if document is None:
                    return 404, {"detail": "Document not found"}
                return 200, {"document": _document_summary(document)}
            if runtime.store.get_document(document_id, owner_id=actor["sub"]) is None:
                return 404, {"detail": "Document not found or cannot be deleted"}
            if not runtime.repository.delete_document(document_id, actor["sub"]):
                return 404, {"detail": "Document persistence record not found"}
            runtime.store.delete_document(document_id, actor["sub"])
            return 200, {"status": "deleted", "document_id": document_id}
        if method == "POST" and path == "/logs/analyze":
            _require_user(user)
            return 200, _log_result(str(payload.get("content", "")))
        if method == "POST" and path == "/ioc/analyze":
            _require_user(user)
            return 200, _ioc_result(str(payload.get("content", "")))
        if method == "POST" and path == "/rag-security/scan":
            _require_user(user)
            return 200, _security_scan(str(payload.get("content", "")))
        if method == "GET" and path == "/rag-security/evaluate":
            _require_user(user)
            return 200, evaluate_rag_security()
        if method == "GET" and path == "/rag-security/documents":
            actor = _require_user(user)
            return 200, assess_documents(runtime.store.list_documents(actor["sub"], include_shared=False))
        if method == "POST" and path == "/research/gap-analysis":
            actor = _require_user(user)
            docs = [doc for doc in runtime.store.list_documents(actor["sub"], include_shared=False) if doc.source_type in {"user_document", "paper"} and not doc.security_flags]
            result = analyze_gap_candidates(docs)
            result.update({"evidence_document_count": len(docs), "label": "Candidate research gap"})
            return 200, result
        if method == "GET" and path == "/research/workspaces":
            actor = _require_user(user)
            return 200, {"workspaces": runtime.repository.list_workspaces(actor["sub"])}
        if method == "POST" and path == "/research/workspaces":
            actor = _require_user(user)
            name = str(payload.get("name", "")).strip()
            if not name:
                raise ValueError("workspace name is required")
            record = Workspace(str(uuid.uuid4()), actor["sub"], name, _now(), dict(payload.get("settings") or {}))
            return 201, {"workspace": runtime.repository.save_workspace(record)}
        workspace_items = re.fullmatch(r"/research/workspaces/([^/]+)/items", path)
        if workspace_items:
            actor = _require_user(user)
            workspace_id = workspace_items.group(1)
            if not _workspace_owned(workspace_id, actor["sub"]):
                return 404, {"detail": "Workspace not found"}
            if method == "GET":
                return 200, {"items": runtime.repository.list_research_items(workspace_id, actor["sub"])}
            if method == "POST":
                title = str(payload.get("title", "")).strip()
                if not title:
                    raise ValueError("research item title is required")
                source_id = payload.get("source_document_id")
                if source_id and runtime.repository.get_document(str(source_id), actor["sub"]) is None:
                    return 404, {"detail": "Owned source document not found"}
                record = ResearchItem(str(uuid.uuid4()), workspace_id, actor["sub"], str(payload.get("item_type", "question")), title, str(payload.get("status", "active")), source_id, dict(payload.get("data") or {}), _now(), _now())
                return 201, {"item": runtime.repository.save_research_item(record)}
        workspace_notes = re.fullmatch(r"/research/workspaces/([^/]+)/notes", path)
        if workspace_notes:
            actor = _require_user(user)
            workspace_id = workspace_notes.group(1)
            if not _workspace_owned(workspace_id, actor["sub"]):
                return 404, {"detail": "Workspace not found"}
            if method == "GET":
                return 200, {"notes": runtime.repository.list_notes(workspace_id, actor["sub"])}
            if method == "POST":
                body = str(payload.get("body", "")).strip()
                if not body:
                    raise ValueError("note body is required")
                item_id = payload.get("research_item_id")
                if item_id and not any(item["id"] == item_id for item in runtime.repository.list_research_items(workspace_id, actor["sub"])):
                    return 404, {"detail": "Research item not found in this workspace"}
                record = Note(str(uuid.uuid4()), workspace_id, actor["sub"], body, str(payload.get("title", "")), item_id, _now(), _now())
                return 201, {"note": runtime.repository.save_note(record)}
        workspace_evidence = re.fullmatch(r"/research/workspaces/([^/]+)/evidence", path)
        if workspace_evidence:
            actor = _require_user(user)
            workspace_id = workspace_evidence.group(1)
            if not _workspace_owned(workspace_id, actor["sub"]):
                return 404, {"detail": "Workspace not found"}
            if method == "GET":
                return 200, {"evidence": runtime.repository.list_saved_evidence(workspace_id, actor["sub"])}
            if method == "POST":
                evidence_id = str(payload.get("evidence_id", "")).strip()
                if not evidence_id:
                    raise ValueError("evidence_id is required")
                chunk = next((item for item in runtime.store.get_chunks(runtime.store.visible_document_ids(actor["sub"])) if item.chunk_id == evidence_id), None)
                if chunk is None:
                    return 404, {"detail": "Visible evidence chunk not found"}
                record = SavedEvidence(str(uuid.uuid4()), workspace_id, actor["sub"], evidence_id, chunk.to_dict(), str(payload.get("note", "")), _now())
                return 201, {"evidence": runtime.repository.save_evidence(record)}
        if method == "POST" and path in {"/papers/analyze", "/papers/compare"}:
            actor = _require_user(user)
            ids = payload.get("document_ids", [payload.get("document_id")])
            if not isinstance(ids, list) or not 1 <= len(ids) <= 20 or any(not isinstance(item, str) or not item for item in ids):
                raise ValueError("Provide between 1 and 20 document IDs")
            if path == "/papers/compare" and len(set(ids)) < 2:
                raise ValueError("Select at least two different papers to compare")
            records = []
            for document_id in ids:
                document = runtime.store.get_document(document_id, owner_id=actor["sub"])
                if document is None or document.security_flags:
                    return 404, {"detail": "Readable paper not found"}
                record = extract_paper(document.content, document.title)
                for spans in record.field_provenance.values():
                    for span in spans:
                        span.update({"document_id": document.document_id, "url": document.url})
                records.append(record)
            return 200, compare_papers(records) if path.endswith("compare") else {"paper": records[0].to_dict()}
        if method == "GET" and path == "/papers":
            actor = _require_user(user)
            papers = [item for item in runtime.store.list_documents(actor["sub"], include_shared=True) if item.source_type == "paper" and not item.security_flags]
            return 200, {"papers": [{**_document_summary(item), "content_available": bool(item.content), "analysis": extract_paper(item.content, item.title).to_dict()} for item in papers]}
        if method == "GET" and path == "/threats":
            actor = _require_user(user)
            threats = [item for item in runtime.store.list_documents(actor["sub"], include_shared=True) if not item.security_flags and any(term in (item.tags or []) for term in ("threat_actor", "malware", "campaign"))]
            return 200, {"threats": [_document_summary(item) for item in threats]}
        if method == "GET" and path == "/vulnerabilities":
            actor = _require_user(user)
            vulnerabilities = [item for item in runtime.store.list_documents(actor["sub"], include_shared=True) if not item.security_flags and (item.source in {"NVD", "CISA", "CISA KEV"} or "cve" in item.tags)]
            return 200, {"vulnerabilities": [_document_summary(item) for item in vulnerabilities]}
        if method == "GET" and path == "/experiments":
            actor = _require_user(user)
            return 200, {"experiments": runtime.repository.list_experiments(actor["sub"])}
        if method == "POST" and path == "/experiments":
            actor = _require_user(user)
            record = _experiment_record(payload, actor["sub"])
            return 201, {"experiment": runtime.repository.save_experiment(record)}
        experiment_match = re.fullmatch(r"/experiments/([^/]+)", path)
        if experiment_match and experiment_match.group(1) != "compare" and method in {"GET", "PATCH", "DELETE"}:
            actor = _require_user(user)
            experiment_id = experiment_match.group(1)
            previous = next((row for row in runtime.repository.list_experiments(actor["sub"]) if row["id"] == experiment_id), None)
            if previous is None:
                return 404, {"detail": "Experiment not found"}
            if method == "DELETE":
                runtime.repository.delete_experiment(experiment_id, actor["sub"])
                return 200, {"status": "deleted", "experiment_id": experiment_id}
            if method == "PATCH":
                record = _experiment_record(payload, actor["sub"], previous)
                runtime.repository.save_experiment(record)
                previous = asdict(record)
            return 200, {"experiment": {**previous, "metrics": runtime.repository.list_experiment_metrics(experiment_id)}}
        experiment_metrics = re.fullmatch(r"/experiments/([^/]+)/metrics", path)
        if method == "POST" and experiment_metrics:
            actor = _require_user(user)
            experiment_id = experiment_metrics.group(1)
            experiment = next((item for item in runtime.repository.list_experiments(actor["sub"]) if str(item.get("id")) == experiment_id), None)
            if experiment is None:
                return 404, {"detail": "Experiment not found"}
            name = str(payload.get("name", "")).strip()
            if not name or len(name) > 120:
                raise ValueError("metric name must contain 1 to 120 characters")
            raw_value = payload.get("value")
            if isinstance(raw_value, bool) or not isinstance(raw_value, (int, float)) or not math.isfinite(raw_value):
                raise ValueError("metric value must be a finite JSON number")
            value = float(raw_value)
            runtime.repository.save_experiment_metric(str(uuid.uuid4()), experiment_id, name, value)
            return 201, {"metrics": runtime.repository.list_experiment_metrics(experiment_id)}
        if method == "GET" and path == "/experiments/compare":
            actor = _require_user(user)
            experiments = runtime.repository.list_experiments(actor["sub"])
            return 200, {"experiments": [{**item, "metrics": runtime.repository.list_experiment_metrics(str(item["id"]))} for item in experiments], "comparison_basis": "persisted experiment metrics"}
        if method == "GET" and path == "/admin/overview":
            _require_admin(user)
            manifest_path = settings.data_dir / "data_manifest.json"
            manifest: dict[str, Any] = {}
            if manifest_path.exists():
                try: manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                except json.JSONDecodeError: manifest = {"errors": ["data_manifest.json is invalid JSON"]}
            from app.services.llm import provider_status
            return 200, {"users": runtime.repository.list_users(), "documents": runtime.repository.list_all_documents(), "ingestion_jobs": runtime.repository.list_ingestion_jobs(), "health": runtime.infrastructure.health(), "model_usage": {"llm": provider_status().__dict__, "nli_provider": __import__("os").getenv("NLI_PROVIDER", "auto"), "reranker_provider": __import__("os").getenv("RERANKER_PROVIDER", "none")}, "errors": manifest.get("errors", []), "data_sources": manifest.get("sources", []), "evaluation": evaluate_rag_security()}
        if method == "GET" and path == "/timeline":
            actor = _require_user(user)
            return 200, _timeline_result(actor["sub"], params.get("start", [None])[0], params.get("end", [None])[0])
        match = re.fullmatch(r"/vulnerabilities/(CVE-\d{4}-\d{4,7})", path, flags=re.IGNORECASE)
        if method == "GET" and match:
            actor = _require_user(user)
            return 200, _query_response({"query": match.group(1).upper(), "mode": "SOC_ANALYST"}, actor["sub"])
        match = re.fullmatch(r"/graph/entity/(.+)", path)
        if method == "GET" and match:
            _require_user(user)
            return 200, runtime.graph.search(unquote(match.group(1)), depth=1)
        if method == "GET" and path.startswith("/graph/search/"):
            _require_user(user)
            return 200, runtime.graph.search(unquote(path.removeprefix("/graph/search/")), depth=1)
        if method == "GET" and path == "/data/refresh/sources":
            _require_admin(user)
            return 200, {"sources": list(SOURCES)}
        if method == "GET" and path == "/data/refresh/status":
            _require_user(user)
            status = _refresh_status()
            status["jobs"] = runtime.refresh_jobs.list()
            return 200, status
        if method == "POST" and path == "/data/refresh":
            _require_admin(user)
            sources = payload.get("sources")
            if sources is not None and (not isinstance(sources, list) or not sources or any(not isinstance(item, str) or item not in SOURCES for item in sources)):
                raise ValueError("sources must be a non-empty list of configured source names")
            return 202, {"job": runtime.refresh_jobs.start(sources, bool(payload.get("force")))}
        refresh_job_match = re.fullmatch(r"/data/refresh/jobs/([^/]+)", path)
        if method == "GET" and refresh_job_match:
            _require_admin(user)
            job = runtime.refresh_jobs.get(refresh_job_match.group(1))
            return (200, {"job": job}) if job else (404, {"detail": "Refresh job not found"})
        if method == "POST" and path == "/reports/export":
            actor = _require_user(user)
            if payload.get("answer_id"):
                saved = runtime.repository.get_answer(str(payload["answer_id"]), actor["sub"])
                if saved is None:
                    return 404, {"detail": "Answer not found"}
                return 200, export_answer(Answer.from_dict(saved), str(payload.get("format", "markdown"))).to_dict()
            query = str(payload.get("query", "")).strip()
            if not query:
                raise ValueError("query is required")
            answer = runtime.pipeline.ask(query, mode=str(payload.get("mode", "RESEARCHER")), owner_id=actor["sub"])
            return 200, export_answer(answer, str(payload.get("format", "markdown"))).to_dict()
        if method == "GET" and path == "/evaluation":
            _require_user(user)
            result: dict[str, Any] = {"available": True, "benchmarks": ["CyberTrust-QA"], "metrics": "computed by scripts/evaluation; no metrics are hard-coded"}
            for name in ("cybertrust_results.json", "ablation_results.json", "cers_calibration.json"):
                file = settings.data_dir / "evaluation" / name
                if file.exists():
                    try: result[name.removesuffix(".json")] = json.loads(file.read_text(encoding="utf-8"))
                    except json.JSONDecodeError: result[name.removesuffix(".json")] = {"status": "invalid_artifact"}
            return 200, result
        return 404, {"detail": "Route not found"}
    except ForbiddenError as exc:
        return 403, {"detail": str(exc)}
    except PermissionError as exc:
        return 401, {"detail": str(exc)}
    except (ValueError, ExtractionUnavailable) as exc:
        return 400, {"detail": str(exc), "processing_state": "FAILED"}
    except Exception:
        logger.exception("Request failed: %s %s", method, path)
        return 500, {"detail": "The request could not be completed. See server logs for the internal error."}


def _timeline_result(owner_id: str, start: str | None = None, end: str | None = None) -> dict[str, Any]:
    for value in (start, end):
        if value and (len(value) != 10 or date.fromisoformat(value).isoformat() != value):
            raise ValueError("Timeline bounds must be ISO dates (YYYY-MM-DD)")
    if start and end and start > end:
        raise ValueError("Timeline start must not be after end")
    events: list[dict[str, Any]] = []
    for document in runtime.store.list_documents(owner_id, include_shared=True):
        if document.security_flags:
            continue
        if document.publication_date:
            events.append({"date": document.publication_date, "event_type": "publication", "document_id": document.document_id, "title": document.title, "source": document.source, "url": document.url, "version": document.version, "provenance": "document.publication_date"})
        if document.update_date and document.update_date != document.publication_date:
            events.append({"date": document.update_date, "event_type": "modified", "document_id": document.document_id, "title": document.title, "source": document.source, "url": document.url, "version": document.version, "provenance": "document.update_date"})
    status_path = settings.data_dir / "processed" / "source_update_status.json"
    if status_path.exists():
        try:
            status = json.loads(status_path.read_text(encoding="utf-8"))
            for key in ("started_at", "finished_at"):
                if status.get(key):
                    events.append({"date": status[key], "event_type": "source_refresh", "title": "Official source refresh", "source": "CyberSecRA-X refresh job", "provenance": "source_update_status.json"})
        except json.JSONDecodeError:
            pass
    ordered = sorted(events, key=lambda item: item.get("date", ""))
    if start:
        ordered = [event for event in ordered if str(event.get("date", "")) >= start]
    if end:
        ordered = [event for event in ordered if str(event.get("date", ""))[:10] <= end]
    return {"events": ordered, "filters": {"available": True, "start": start, "end": end}, "limitations": ["Version and supersession events are shown only when present in ingested source metadata."]}


def _candidate_gaps(documents: list[Any]) -> list[dict[str, Any]]:
    if len(documents) < 2:
        return [{"title": "Insufficient corpus for a comparison", "observation": "Provide at least two research papers or attributed documents before generating a candidate gap.", "evidence": []}]
    tags = {}
    for doc in documents:
        for tag in doc.tags:
            tags.setdefault(tag, []).append(doc.document_id)
    repeated = [{"topic": tag, "documents": ids} for tag, ids in tags.items() if len(ids) >= 2]
    return [{"title": "Candidate research gap: under-compared evidence", "observation": "The supplied corpus has repeated topics but no validated comparison of methods or evaluation settings.", "evidence": [doc.document_id for doc in documents], "repeated_topics": repeated}]


def _graph_relationships(entity: str) -> list[dict[str, Any]]:
    return runtime.graph.search(entity, depth=1).get("edges", [])


def _sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _stream_query_events(payload: dict[str, Any], actor: dict[str, Any]):
    query = str(payload.get("query", "")).strip()
    if not query:
        yield _sse("error", {"detail": "query is required"})
        return
    _validate_workspace(payload, actor["sub"])
    for event in runtime.pipeline.stream(query, mode=str(payload.get("mode", "RESEARCHER")), owner_id=actor["sub"]):
        if event.get("reset"):
            yield _sse("answer_reset", {})
        elif "text" in event:
            yield _sse("answer_delta", {"text": event["text"], "generation_mode": event.get("generation_mode", "unknown")})
        elif event.get("stage") == "COMPLETE":
            answer = event.get("answer")
            if answer is not None:
                _save_answer(answer, payload, actor["sub"])
            yield _sse("complete", {"answer": answer.to_dict() if answer is not None else {}, "streaming": True})
        else:
            stage = event.get("stage", "STATUS")
            yield _sse("status", {key: value for key, value in event.items() if key != "stage"} | {"stage": stage})


def _stream_query(payload: dict[str, Any], actor: dict[str, Any]):
    try:
        yield from _stream_query_events(payload, actor)
    except ValueError as exc:
        yield _sse("error", {"detail": str(exc)})
    except Exception:
        logger.exception("Streaming query failed")
        yield _sse("error", {"detail": "The query could not be completed. Retry or inspect server logs."})


def create_app() -> Any:
    if not HAS_FASTAPI:
        return None
    app = FastAPI(title=settings.app_name, version="1.0.0", description="Evidence-aware cybersecurity research intelligence API")
    app.add_middleware(CORSMiddleware, allow_origins=list(settings.cors_origins), allow_credentials=True, allow_methods=["GET", "POST", "PATCH", "DELETE"], allow_headers=["*"])

    @app.middleware("http")
    async def request_context(request: Request, call_next: Any) -> Any:
        limit = settings.max_upload_bytes * 4 // 3 + 65536
        try:
            length = int(request.headers.get("content-length", "0"))
        except ValueError:
            return JSONResponse(status_code=400, content={"detail": "Invalid Content-Length"})
        if length < 0 or length > limit:
            return JSONResponse(status_code=413 if length > limit else 400, content={"detail": "Request body exceeds the configured limit" if length > limit else "Invalid Content-Length"})
        chunks, size = [], 0
        async for chunk in request.stream():
            size += len(chunk)
            if size > limit:
                return JSONResponse(status_code=413, content={"detail": "Request body exceeds the configured limit"})
            chunks.append(chunk)
        request._body = b"".join(chunks)
        request_id = request.headers.get("x-request-id", str(uuid.uuid4()))
        response = await call_next(request)
        response.headers["x-request-id"] = request_id
        response.headers["x-content-type-options"] = "nosniff"
        return response

    @app.get("/health")
    async def health() -> dict[str, Any]:
        return _route("GET", "/health", {}, {})[1]

    @app.get("/ready")
    async def readiness() -> Any:
        status, body = _route("GET", "/ready", {}, {})
        return JSONResponse(status_code=status, content=body)

    @app.get("/health/detailed")
    async def detailed_health() -> dict[str, Any]:
        return _route("GET", "/health/detailed", {}, {})[1]

    @app.post("/auth/register")
    async def register(payload: dict[str, Any]) -> Any:
        status, result = _route("POST", "/auth/register", payload, {})
        if status >= 400:
            raise HTTPException(status_code=status, detail=result["detail"])
        return JSONResponse(status_code=status, content=result)

    @app.post("/auth/login")
    async def login(payload: dict[str, Any]) -> Any:
        status, result = _route("POST", "/auth/login", payload, {})
        if status >= 400:
            raise HTTPException(status_code=status, detail=result["detail"])
        return JSONResponse(status_code=status, content=result)

    @app.post("/auth/refresh")
    async def refresh(payload: dict[str, Any]) -> Any:
        status, result = _route("POST", "/auth/refresh", payload, {})
        if status >= 400:
            raise HTTPException(status_code=status, detail=result["detail"])
        return result

    @app.post("/auth/logout")
    async def logout(payload: dict[str, Any], request: Request) -> Any:
        status, result = _route("POST", "/auth/logout", payload, dict(request.headers))
        if status >= 400:
            raise HTTPException(status_code=status, detail=result["detail"])
        return result

    @app.get("/auth/me")
    async def me(request: Request) -> Any:
        status, result = _route("GET", "/auth/me", {}, dict(request.headers))
        if status >= 400:
            raise HTTPException(status_code=status, detail=result["detail"])
        return result

    @app.post("/chat/query")
    def chat_query(payload: dict[str, Any], request: Request) -> Any:
        status, result = _route("POST", "/chat/query", payload, dict(request.headers))
        if status >= 400:
            raise HTTPException(status_code=status, detail=result["detail"])
        return result

    @app.post("/chat/stream")
    async def chat_stream(payload: dict[str, Any], request: Request) -> Any:
        actor = _user_from_request(dict(request.headers))
        if actor is None:
            raise HTTPException(status_code=401, detail="Authentication required")
        return StreamingResponse(_stream_query(payload, actor), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    @app.post("/documents/upload")
    def upload(payload: dict[str, Any], request: Request) -> Any:
        status, result = _route("POST", "/documents/upload", payload, dict(request.headers))
        if status >= 400:
            raise HTTPException(status_code=status, detail=result["detail"])
        return JSONResponse(status_code=status, content=result)

    @app.get("/documents")
    async def documents(request: Request) -> Any:
        status, result = _route("GET", "/documents", {}, dict(request.headers))
        if status >= 400:
            raise HTTPException(status_code=status, detail=result["detail"])
        return result

    @app.get("/documents/jobs/{job_id}")
    async def document_job(job_id: str, request: Request) -> Any:
        status, result = _route("GET", f"/documents/jobs/{job_id}", {}, dict(request.headers))
        if status >= 400:
            raise HTTPException(status_code=status, detail=result["detail"])
        return result

    @app.get("/documents/{document_id}")
    async def document(document_id: str, request: Request) -> Any:
        status, result = _route("GET", f"/documents/{document_id}", {}, dict(request.headers))
        if status >= 400:
            raise HTTPException(status_code=status, detail=result["detail"])
        return result

    @app.delete("/documents/{document_id}")
    async def delete_document(document_id: str, request: Request) -> Any:
        status, result = _route("DELETE", f"/documents/{document_id}", {}, dict(request.headers))
        if status >= 400:
            raise HTTPException(status_code=status, detail=result["detail"])
        return result

    @app.post("/logs/analyze")
    async def logs(payload: dict[str, Any], request: Request) -> Any:
        status, result = _route("POST", "/logs/analyze", payload, dict(request.headers))
        if status >= 400:
            raise HTTPException(status_code=status, detail=result["detail"])
        return result

    @app.post("/ioc/analyze")
    async def ioc(payload: dict[str, Any], request: Request) -> Any:
        status, result = _route("POST", "/ioc/analyze", payload, dict(request.headers))
        if status >= 400:
            raise HTTPException(status_code=status, detail=result["detail"])
        return result

    @app.post("/rag-security/scan")
    async def rag_scan(payload: dict[str, Any], request: Request) -> Any:
        status, result = _route("POST", "/rag-security/scan", payload, dict(request.headers))
        if status >= 400:
            raise HTTPException(status_code=status, detail=result["detail"])
        return result

    @app.get("/rag-security/evaluate")
    async def rag_evaluate(request: Request) -> Any:
        status, result = _route("GET", "/rag-security/evaluate", {}, dict(request.headers))
        if status >= 400:
            raise HTTPException(status_code=status, detail=result["detail"])
        return result

    @app.get("/rag-security/documents")
    async def rag_documents(request: Request) -> Any:
        status, result = _route("GET", "/rag-security/documents", {}, dict(request.headers))
        if status >= 400:
            raise HTTPException(status_code=status, detail=result["detail"])
        return result

    @app.post("/research/gap-analysis")
    async def gap(payload: dict[str, Any], request: Request) -> Any:
        status, result = _route("POST", "/research/gap-analysis", payload, dict(request.headers))
        if status >= 400:
            raise HTTPException(status_code=status, detail=result["detail"])
        return result

    @app.get("/vulnerabilities/{cve_id}")
    async def vulnerability(cve_id: str, request: Request) -> Any:
        status, result = _route("GET", f"/vulnerabilities/{cve_id}", {}, dict(request.headers))
        if status >= 400:
            raise HTTPException(status_code=status, detail=result["detail"])
        return result

    @app.get("/graph/entity/{entity_id}")
    async def graph(entity_id: str, request: Request) -> Any:
        status, result = _route("GET", f"/graph/entity/{entity_id}", {}, dict(request.headers))
        if status >= 400:
            raise HTTPException(status_code=status, detail=result["detail"])
        return result

    @app.get("/graph/search/{query}")
    async def graph_search(query: str, request: Request) -> Any:
        status, result = _route("GET", f"/graph/search/{query}", {}, dict(request.headers))
        if status >= 400:
            raise HTTPException(status_code=status, detail=result["detail"])
        return result

    @app.get("/papers")
    async def papers(request: Request) -> Any:
        status, result = _route("GET", "/papers", {}, dict(request.headers))
        if status >= 400:
            raise HTTPException(status_code=status, detail=result["detail"])
        return result

    @app.get("/threats")
    async def threats(request: Request) -> Any:
        status, result = _route("GET", "/threats", {}, dict(request.headers))
        if status >= 400:
            raise HTTPException(status_code=status, detail=result["detail"])
        return result

    @app.get("/vulnerabilities")
    async def vulnerabilities(request: Request) -> Any:
        status, result = _route("GET", "/vulnerabilities", {}, dict(request.headers))
        if status >= 400:
            raise HTTPException(status_code=status, detail=result["detail"])
        return result

    @app.get("/timeline")
    async def timeline(request: Request) -> Any:
        status, result = _route("GET", f"/timeline?{request.url.query}", {}, dict(request.headers))
        return JSONResponse(status_code=status, content=result)

    @app.get("/research/workspaces")
    async def workspaces(request: Request) -> Any:
        status, result = _route("GET", "/research/workspaces", {}, dict(request.headers))
        if status >= 400:
            raise HTTPException(status_code=status, detail=result["detail"])
        return result

    @app.post("/research/workspaces")
    async def workspace_create(payload: dict[str, Any], request: Request) -> Any:
        status, result = _route("POST", "/research/workspaces", payload, dict(request.headers))
        if status >= 400:
            raise HTTPException(status_code=status, detail=result["detail"])
        return JSONResponse(status_code=status, content=result)

    @app.get("/experiments")
    async def experiments(request: Request) -> Any:
        status, result = _route("GET", "/experiments", {}, dict(request.headers))
        if status >= 400:
            raise HTTPException(status_code=status, detail=result["detail"])
        return result

    @app.post("/experiments")
    async def experiment_create(payload: dict[str, Any], request: Request) -> Any:
        status, result = _route("POST", "/experiments", payload, dict(request.headers))
        if status >= 400:
            raise HTTPException(status_code=status, detail=result["detail"])
        return JSONResponse(status_code=status, content=result)

    @app.get("/experiments/compare")
    async def experiment_compare(request: Request) -> Any:
        status, result = _route("GET", "/experiments/compare", {}, dict(request.headers))
        if status >= 400:
            raise HTTPException(status_code=status, detail=result["detail"])
        return result

    @app.api_route("/research/workspaces/{workspace_id}/items", methods=["GET", "POST"])
    async def workspace_items(workspace_id: str, request: Request, payload: dict[str, Any] | None = None) -> Any:
        method = request.method.upper()
        status, result = _route(method, f"/research/workspaces/{workspace_id}/items", payload or {}, dict(request.headers))
        if status >= 400:
            raise HTTPException(status_code=status, detail=result["detail"])
        return JSONResponse(status_code=status, content=result) if method == "POST" else result

    @app.api_route("/research/workspaces/{workspace_id}/notes", methods=["GET", "POST"])
    async def workspace_notes(workspace_id: str, request: Request, payload: dict[str, Any] | None = None) -> Any:
        method = request.method.upper()
        status, result = _route(method, f"/research/workspaces/{workspace_id}/notes", payload or {}, dict(request.headers))
        if status >= 400:
            raise HTTPException(status_code=status, detail=result["detail"])
        return JSONResponse(status_code=status, content=result) if method == "POST" else result

    @app.api_route("/research/workspaces/{workspace_id}/evidence", methods=["GET", "POST"])
    async def workspace_evidence(workspace_id: str, request: Request, payload: dict[str, Any] | None = None) -> Any:
        method = request.method.upper()
        status, result = _route(method, f"/research/workspaces/{workspace_id}/evidence", payload or {}, dict(request.headers))
        if status >= 400:
            raise HTTPException(status_code=status, detail=result["detail"])
        return JSONResponse(status_code=status, content=result) if method == "POST" else result

    @app.post("/experiments/{experiment_id}/metrics")
    async def experiment_metric(experiment_id: str, payload: dict[str, Any], request: Request) -> Any:
        status, result = _route("POST", f"/experiments/{experiment_id}/metrics", payload, dict(request.headers))
        if status >= 400:
            raise HTTPException(status_code=status, detail=result["detail"])
        return JSONResponse(status_code=status, content=result)

    @app.api_route("/experiments/{experiment_id}", methods=["GET", "PATCH", "DELETE"])
    def experiment_detail(experiment_id: str, request: Request, payload: dict[str, Any] | None = None) -> Any:
        status, result = _route(request.method, f"/experiments/{experiment_id}", payload or {}, dict(request.headers))
        return JSONResponse(status_code=status, content=result)

    @app.get("/admin/overview")
    async def admin_overview(request: Request) -> Any:
        status, result = _route("GET", "/admin/overview", {}, dict(request.headers))
        if status >= 400:
            raise HTTPException(status_code=status, detail=result["detail"])
        return result

    @app.post("/reports/export")
    def reports_export(payload: dict[str, Any], request: Request) -> Any:
        status, result = _route("POST", "/reports/export", payload, dict(request.headers))
        if status >= 400:
            raise HTTPException(status_code=status, detail=result["detail"])
        return result

    @app.get("/data/refresh/status")
    async def refresh_status(request: Request) -> Any:
        status, result = _route("GET", "/data/refresh/status", {}, dict(request.headers))
        if status >= 400:
            raise HTTPException(status_code=status, detail=result["detail"])
        return result

    @app.get("/data/refresh/sources")
    def refresh_sources(request: Request) -> Any:
        status, result = _route("GET", "/data/refresh/sources", {}, dict(request.headers))
        return JSONResponse(status_code=status, content=result)

    @app.post("/data/refresh")
    async def refresh_start(payload: dict[str, Any], request: Request) -> Any:
        status, result = _route("POST", "/data/refresh", payload, dict(request.headers))
        if status >= 400:
            raise HTTPException(status_code=status, detail=result["detail"])
        return JSONResponse(status_code=status, content=result)

    @app.get("/data/refresh/jobs/{job_id}")
    async def refresh_job(job_id: str, request: Request) -> Any:
        status, result = _route("GET", f"/data/refresh/jobs/{job_id}", {}, dict(request.headers))
        if status >= 400:
            raise HTTPException(status_code=status, detail=result["detail"])
        return result

    @app.get("/evaluation")
    async def evaluation(request: Request) -> Any:
        status, result = _route("GET", "/evaluation", {}, dict(request.headers))
        if status >= 400:
            raise HTTPException(status_code=status, detail=result["detail"])
        return result

    @app.get("/chat/history")
    @app.get("/chat/answers/{answer_id}")
    @app.get("/documents/{document_id}/chunks")
    def persisted_resource(request: Request) -> Any:
        status, result = _route("GET", request.url.path, {}, dict(request.headers))
        return JSONResponse(status_code=status, content=result)

    @app.post("/papers/analyze")
    @app.post("/papers/compare")
    def paper_intelligence(payload: dict[str, Any], request: Request) -> Any:
        status, result = _route("POST", request.url.path, payload, dict(request.headers))
        return JSONResponse(status_code=status, content=result)

    return app


app = create_app()


class FallbackHandler(BaseHTTPRequestHandler):
    def _cors_headers(self) -> None:
        origin = self.headers.get("Origin", "")
        if origin in settings.cors_origins:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Access-Control-Allow-Credentials", "true")
            self.send_header("Vary", "Origin")
        self.send_header("X-Content-Type-Options", "nosniff")

    def _send(self, status: int, body: dict[str, Any]) -> None:
        encoded = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self._cors_headers()
        self.end_headers()
        self.wfile.write(encoded)

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(204)
        self._cors_headers()
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Request-ID")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PATCH, DELETE, OPTIONS")
        self.end_headers()

    def _handle(self, method: str) -> None:
        parsed = urlparse(self.path)
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length < 0:
                raise ValueError()
        except ValueError:
            self._send(400, {"detail": "Invalid Content-Length"})
            return
        if length > ((settings.max_upload_bytes + 2) // 3) * 4 + 1024 * 1024:
            self._send(413, {"detail": "Request body exceeds the configured size limit"})
            return
        raw = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(raw.decode("utf-8")) if raw else {}
            if not isinstance(payload, dict):
                raise ValueError()
        except (ValueError, UnicodeDecodeError):
            self._send(400, {"detail": "Request body must be a UTF-8 JSON object"})
            return
        headers = {key.lower(): value for key, value in self.headers.items()}
        if method == "POST" and parsed.path == "/chat/stream":
            actor = _user_from_request(headers)
            if actor is None:
                self._send(401, {"detail": "Authentication required"})
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "close")
            self._cors_headers()
            self.end_headers()
            for event in _stream_query(payload, actor):
                self.wfile.write(event.encode("utf-8"))
                self.wfile.flush()
            return
        status, body = _route(method, self.path, payload, headers)
        self._send(status, body)

    def do_GET(self) -> None:  # noqa: N802
        self._handle("GET")

    def do_POST(self) -> None:  # noqa: N802
        self._handle("POST")

    def do_DELETE(self) -> None:  # noqa: N802
        self._handle("DELETE")

    def do_PATCH(self) -> None:  # noqa: N802
        self._handle("PATCH")

    def log_message(self, format: str, *args: Any) -> None:
        sys.stderr.write(f"[cybersecra-x] {self.address_string()} {format % args}\n")


def run() -> None:
    if HAS_FASTAPI:
        uvicorn.run("app.main:app", host=settings.host, port=settings.port, reload=False)
    else:
        server = ThreadingHTTPServer((settings.host, settings.port), FallbackHandler)
        print(f"CyberSecRA-X stdlib fallback listening on http://{settings.host}:{settings.port}")
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()


if __name__ == "__main__":
    run()
