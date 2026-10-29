"""Report required/optional runtimes, libraries, services, and GPU status."""
from __future__ import annotations

import importlib.util
import json
import os
import shutil
import socket
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def command_info(name: str, *, required: bool = False) -> dict[str, Any]:
    path = shutil.which(name)
    result: dict[str, Any] = {"status": "AVAILABLE" if path else ("REQUIRED" if required else "OPTIONAL"), "available": bool(path), "path": path}
    if path:
        try:
            completed = subprocess.run([name, "--version"], capture_output=True, text=True, timeout=10, check=False)
            result["version"] = (completed.stdout or completed.stderr).strip().splitlines()[0] if completed.returncode == 0 else "version command failed"
        except Exception as exc:
            result["error"] = str(exc)
    return result


def module_info(name: str, *, required: bool = False) -> dict[str, Any]:
    available = bool(importlib.util.find_spec(name))
    return {"status": "AVAILABLE" if available else ("REQUIRED" if required else "OPTIONAL"), "available": available}


def tcp_service(name: str, host: str, port: int) -> dict[str, Any]:
    try:
        with socket.create_connection((host, port), timeout=1.5):
            return {"status": "AVAILABLE", "host": host, "port": port, "available": True}
    except OSError as exc:
        return {"status": "OPTIONAL", "host": host, "port": port, "available": False, "reason": str(exc)}


def gpu_info() -> dict[str, Any]:
    result: dict[str, Any] = {"cuda": False, "gpu": None, "status": "OPTIONAL"}
    try:
        import torch  # type: ignore
        result.update({"torch_cuda_available": bool(torch.cuda.is_available()), "torch_version": getattr(torch, "__version__", "unknown")})
        if torch.cuda.is_available():
            result.update({"cuda": True, "gpu": torch.cuda.get_device_name(0), "status": "AVAILABLE"})
    except ImportError:
        result["reason"] = "PyTorch is not installed"
    try:
        nvidia = shutil.which("nvidia-smi")
        if nvidia:
            completed = subprocess.run([nvidia, "--query-gpu=name,driver_version", "--format=csv,noheader"], capture_output=True, text=True, timeout=5, check=False)
            if completed.returncode == 0 and completed.stdout.strip():
                result["nvidia_smi"] = completed.stdout.strip()
    except Exception as exc:
        result["nvidia_smi_error"] = str(exc)
    return result


def main() -> None:
    commands = {
        "python": command_info("python3", required=True),
        "node": command_info("node", required=True),
        "npm": command_info("npm", required=True),
        "docker": command_info("docker"),
        "docker_compose": command_info("docker-compose"),
        "flutter": command_info("flutter"),
        "dart": command_info("dart"),
        "tesseract": command_info("tesseract"),
        "libreoffice": command_info("libreoffice"),
        "pandoc": command_info("pandoc"),
    }
    if commands["docker"]["available"]:
        try:
            completed = subprocess.run(["docker", "compose", "version"], capture_output=True, text=True, timeout=10, check=False)
            commands["docker_compose"] = {"status": "AVAILABLE" if completed.returncode == 0 else "OPTIONAL", "available": completed.returncode == 0, "version": (completed.stdout or completed.stderr).strip()}
        except Exception as exc:
            commands["docker_compose"] = {"status": "OPTIONAL", "available": False, "error": str(exc)}
    modules = {name: module_info(name, required=name in {"fastapi", "uvicorn"}) for name in ("fastapi", "uvicorn", "fitz", "yaml", "transformers", "torch", "PIL", "pytesseract", "docx", "reportlab", "sklearn", "redis", "neo4j", "psycopg", "sqlalchemy")}
    services = {
        "postgresql": tcp_service("PostgreSQL", os.getenv("POSTGRES_HOST", "localhost"), int(os.getenv("POSTGRES_PORT", "5432"))),
        "redis": tcp_service("Redis", os.getenv("REDIS_HOST", "localhost"), int(os.getenv("REDIS_PORT", "6379"))),
        "neo4j": tcp_service("Neo4j", os.getenv("NEO4J_HOST", "localhost"), int(os.getenv("NEO4J_PORT", "7687"))),
    }
    result = {
        "root": str(ROOT),
        "python": sys.version,
        "commands": commands,
        "python_modules": modules,
        "services": services,
        "gpu_cuda": gpu_info(),
        "files": {
            "env_example": (ROOT / ".env.example").is_file(),
            "data_manifest": (ROOT / "data/data_manifest.json").is_file(),
        },
        "verification_guidance": {
            "backend": "PYTHONPATH=backend python -m pytest -q backend/tests",
            "data": "PYTHONPATH=backend python scripts/bootstrap_data.py --minimal --papers",
            "frontend": "npm test --prefix frontend",
            "nli": "pip install -r backend/requirements-ml.txt && PYTHONPATH=backend python scripts/setup_models.py --nli",
            "transformer_training": "PYTHONPATH=. python scripts/train_transformer.py --task intent",
        },
    }
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
