"""Assemble and verify a source-only, credential-free CyberSecRA-X release."""
from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
import re
import shutil
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXCLUDED_DIRS = {".git", ".runtime", "release", "__agent__", ".agent", ".opencode", "node_modules", ".next", ".dart_tool", "__pycache__", ".pytest_cache", ".venv", "venv", "build", ".gradle", "Pods", "DerivedData", "ephemeral", "coverage", ".idea", ".vscode"}
GENERATED_DATA = {"raw", "processed", "normalized", "chunks", "embeddings", "graph", "ml", "ingestion_jobs"}
EXCLUDED_FILES = (".env", ".env.*", "*.db", "*.db-*", "*.sqlite", "*.sqlite-*", "*.pyc", "*.pyo", "*.tsbuildinfo", "*.log", "*.pem", "*.key", "*.p12", "*.jks", "*.keystore", "local.properties", ".jwt_secret", ".flutter-plugins*", "Generated.xcconfig", "flutter_export_environment.sh", "GeneratedPluginRegistrant.*", "RELEASE_MANIFEST.json", ".DS_Store", "Thumbs.db")
REQUIRED = ("README.md", "LICENSE", ".env.example", "Makefile", "backend/app/main.py", "backend/requirements.txt", "frontend/package.json", "frontend/package-lock.json", "frontend/app/layout.tsx", "ml/models/inference.py", "scripts/product.py", "scripts/package_release.py", "docs/PRODUCT_RELEASE.md", "data/source_config.json", "data/evaluation/cybertrust_qa.json")


def included(path: Path) -> bool:
    parts = path.parts
    if path.as_posix() in {"scripts/generate_work_record.py", "docs/reports/work_record_source_manifest.json", "docs/reports/work_record_verification.json"} or path.name.startswith("CyberSecRA-X_Complete_Work_Record_"):
        return False  # Agent execution records are not product source/runtime inputs.
    if any(part in EXCLUDED_DIRS or part.startswith((".node_modules-", "pytest-cache-files-")) for part in parts):
        return False
    if path.name != ".env.example" and any(fnmatch.fnmatch(path.name, pattern) for pattern in EXCLUDED_FILES):
        return False
    if parts[0] == "data":
        if len(parts) > 1 and parts[1] in GENERATED_DATA:
            return path.name == ".gitkeep"
        if len(parts) == 2 and path.name not in {"source_config.json", ".gitkeep"}:
            return False  # Old acquisition manifests point to intentionally omitted artifacts.
    return True


def local_secrets() -> list[bytes]:
    secrets = []
    path = ROOT / ".env"
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.startswith("#"):
                key, value = line.split("=", 1)
                if any(word in key.upper() for word in ("SECRET", "PASSWORD", "API_KEY", "TOKEN")) and len(value.strip()) >= 16:
                    secrets.append(value.strip().strip('"').encode())
    secret_file = ROOT / "data/.jwt_secret"
    if secret_file.exists():
        secrets.append(secret_file.read_bytes().strip())
    return [value for value in secrets if value]


def check_content(name: str, payload: bytes, secrets: list[bytes]) -> None:
    if any(secret in payload for secret in secrets):
        raise RuntimeError(f"Local credential detected in packaged content: {name}")
    if re.search(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|\bsk-(?:proj-)?[A-Za-z0-9_-]{24,}\b", payload):
        raise RuntimeError(f"Credential signature detected: {name}")


def verify(archive: Path) -> dict:
    secrets = local_secrets()
    with zipfile.ZipFile(archive) as bundle:
        if bundle.testzip() is not None:
            raise RuntimeError("ZIP CRC integrity check failed")
        prefix = "CyberSecRA-X/"
        names = set(bundle.namelist())
        missing = [name for name in REQUIRED if prefix + name not in names]
        if missing:
            raise RuntimeError(f"Release files missing: {missing}")
        manifest = json.loads(bundle.read(prefix + "RELEASE_MANIFEST.json"))
        for item in manifest["files"]:
            path = Path(item["path"])
            if not included(path) or path.is_absolute() or ".." in path.parts:
                raise RuntimeError(f"Excluded or unsafe path in archive: {path}")
            payload = bundle.read(prefix + path.as_posix())
            if hashlib.sha256(payload).hexdigest() != item["sha256"]:
                raise RuntimeError(f"Release content hash failed: {path}")
            check_content(str(path), payload, secrets)
        if names != {prefix + item["path"] for item in manifest["files"]} | {prefix + "RELEASE_MANIFEST.json"}:
            raise RuntimeError("Archive contains unlisted content")
    return {"archive": str(archive), "files": len(manifest["files"]), "bytes": archive.stat().st_size, "sha256": hashlib.sha256(archive.read_bytes()).hexdigest(), "integrity": "passed", "required_files": "present", "secret_scan": "passed"}


def package(output: Path) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    destination = output / "CyberSecRA-X"
    # Only this script's prior generated output may be replaced.
    if destination.exists():
        if not (destination / "RELEASE_MANIFEST.json").exists():
            raise RuntimeError("Release directory already exists without a generated manifest; preserving it")
        shutil.rmtree(destination)
    destination.mkdir()
    files = []
    secrets = local_secrets()
    for directory, subdirectories, filenames in os.walk(ROOT, followlinks=False):
        base = Path(directory).relative_to(ROOT)
        subdirectories[:] = [name for name in subdirectories if name not in EXCLUDED_DIRS and not name.startswith((".node_modules-", "pytest-cache-files-")) and not (Path(directory) / name).is_symlink()]
        for name in sorted(filenames):
            relative = base / name
            source = ROOT / relative
            if not included(relative) or source.is_symlink():
                continue
            if source.stat().st_size > 10 * 1024 * 1024:
                raise RuntimeError(f"Unexpected large source artifact: {relative}")
            payload = source.read_bytes()
            check_content(relative.as_posix(), payload, secrets)
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(payload)
            files.append({"path": relative.as_posix(), "bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest()})
    for required in REQUIRED:
        if not (destination / required).is_file():
            raise RuntimeError(f"Source release is incomplete: {required}")
    manifest = {"product": "CyberSecRA-X", "version": "1.0.0", "assembled_at": datetime.now(timezone.utc).isoformat(), "kind": "source release; dependencies/models/data are reproduced by documented commands", "files": sorted(files, key=lambda item: item["path"])}
    (destination / "RELEASE_MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    archive = output / "CyberSecRA-X-final.zip"
    temporary = archive.with_suffix(".zip.tmp")
    with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as bundle:
        for item in [*manifest["files"], {"path": "RELEASE_MANIFEST.json"}]:
            relative = Path(item["path"])
            info = zipfile.ZipInfo("CyberSecRA-X/" + relative.as_posix())
            info.compress_type = zipfile.ZIP_DEFLATED
            executable = relative.suffix == ".sh" or relative.name == "gradlew"
            info.external_attr = (0o100755 if executable else 0o100644) << 16
            bundle.writestr(info, (destination / relative).read_bytes())
    temporary.replace(archive)
    result = verify(archive)
    (output / "CyberSecRA-X-final.zip.sha256").write_text(result["sha256"] + "  CyberSecRA-X-final.zip\n", encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "release")
    parser.add_argument("--verify", type=Path)
    args = parser.parse_args()
    print(json.dumps(verify(args.verify) if args.verify else package(args.output.resolve()), indent=2))


if __name__ == "__main__":
    main()
