"""Run an isolated live Uvicorn smoke test without changing the user's database."""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="cybersecra-smoke-") as directory:
        with socket.socket() as socket_probe:
            socket_probe.bind(("127.0.0.1", 0))
            port = socket_probe.getsockname()[1]
        env = {**os.environ, "HOST": "127.0.0.1", "PORT": str(port), "DATABASE_URL": f"sqlite:///{directory}/smoke.db", "LLM_PROVIDER": "none", "NLI_PROVIDER": "heuristic", "INTENT_PROVIDER": "deterministic", "OOD_PROVIDER": "deterministic", "REDIS_URL": "", "NEO4J_URI": "", "PYTHONPATH": str(ROOT / "backend")}
        process = subprocess.Popen([sys.executable, str(ROOT / "backend/run.py")], cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        base = f"http://127.0.0.1:{port}"
        token = ""

        def request(path, payload=None, method=None):
            headers = {"Content-Type": "application/json"}
            if token:
                headers["Authorization"] = f"Bearer {token}"
            data = json.dumps(payload).encode() if payload is not None else None
            with urlopen(Request(base + path, data=data, headers=headers, method=method), timeout=60) as response:
                return response.status, response.headers, response.read()

        def decoded(path, payload=None, method=None):
            return json.loads(request(path, payload, method)[2])

        try:
            for _ in range(180):
                if process.poll() is not None:
                    raise RuntimeError("API exited before becoming healthy")
                try:
                    health = decoded("/health")
                    break
                except (URLError, TimeoutError):
                    time.sleep(0.5)
            else:
                raise RuntimeError("API did not become healthy")
            assert health["runtime"] == "fastapi", health
            session = decoded("/auth/register", {"email": "live-smoke@example.test", "password": "isolated smoke fixture password"})
            token = session["access_token"]
            workspace = decoded("/research/workspaces", {"name": "Isolated smoke workspace"})["workspace"]
            response = request("/chat/stream", {"query": "What does NIST CSF 2.0 provide?", "workspace_id": workspace["id"]})
            assert "text/event-stream" in response[1]["Content-Type"]
            complete = next(frame for frame in response[2].decode().split("\n\n") if frame.startswith("event: complete"))
            answer = json.loads(complete.split("data: ", 1)[1])["answer"]
            assert answer["evidence"] and answer["claims"]
            assert decoded(f"/chat/answers/{answer['answer_id']}")["answer"]["answer_id"] == answer["answer_id"]
            report = decoded("/reports/export", {"answer_id": answer["answer_id"], "format": "json"})
            assert report["content_base64"]
            experiment = decoded("/experiments", {"name": "Isolated smoke fixture"})["experiment"]
            updated = decoded(f"/experiments/{experiment['id']}", {"notes": "Live API smoke; no evaluation metrics"}, "PATCH")
            assert updated["experiment"]["notes"].startswith("Live API")
            assert decoded(f"/experiments/{experiment['id']}", method="DELETE")["status"] == "deleted"
            try:
                decoded("/admin/overview")
                raise AssertionError("Regular user reached admin route")
            except HTTPError as error:
                assert error.code == 403
            print(json.dumps({"status": "passed", "runtime": health["runtime"], "checks": ["health", "authentication", "workspace", "SSE completion", "saved answer", "report export", "experiment create/update/delete", "admin authorization"], "database": "isolated temporary database"}, indent=2))
        finally:
            process.terminate()
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


if __name__ == "__main__":
    main()
