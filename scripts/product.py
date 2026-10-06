"""Portable local product lifecycle: configure, setup, build, up, test, down."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import shutil
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / ".runtime"


def environment() -> dict[str, str]:
    values = {}
    path = ROOT / ".env"
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip() and not line.lstrip().startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                values[key.strip()] = value.strip().strip('"').strip("'")
    return {**values, **os.environ, "PYTHONPATH": str(ROOT / "backend") + os.pathsep + str(ROOT)}


def save(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, indent=2), encoding="utf-8")
    temporary.replace(path)


def configure() -> None:
    path = ROOT / ".env"
    if path.exists():
        print("Existing .env preserved.")
        return
    text = (ROOT / ".env.example").read_text(encoding="utf-8")
    for key in ("JWT_SECRET", "POSTGRES_PASSWORD", "NEO4J_PASSWORD"):
        text = text.replace(f"{key}=\n", f"{key}={secrets.token_urlsafe(48)}\n")
    with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w", encoding="utf-8") as handle:
        handle.write(text)
    print("Created .env with unique local credentials; provider keys remain empty.")


def python_executable(args) -> str:
    if args.python:
        return args.python
    setup = STATE / "setup.json"
    if setup.exists():
        executable = json.loads(setup.read_text())["python"]
        if Path(executable).exists():
            return executable
    for name in (ROOT / ".venv/Scripts/python.exe", ROOT / ".venv/bin/python"):
        if name.exists():
            return str(name)
    return shutil.which("python3.12") or shutil.which("python3.11") or sys.executable


def run(command: list[str], env=None) -> None:
    subprocess.run(command, cwd=ROOT, env=env or environment(), check=True)


def setup(args) -> None:
    configure()
    base = python_executable(args)
    run([base, "-c", "import sys; assert (3,11) <= sys.version_info[:2] < (3,14), 'Use Python 3.11, 3.12, or 3.13 for the pinned stack'"])
    venv = Path(args.venv).resolve()
    if not (venv / "pyvenv.cfg").exists():
        run([base, "-m", "venv", str(venv)])
    executable = str(venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python"))
    run([executable, "-m", "pip", "install", "-r", "backend/requirements.txt", "-r", "backend/requirements-documents.txt"])
    if not args.skip_web_install:
        run(["npm", "ci", "--prefix", "frontend"])
    save(STATE / "setup.json", {"python": executable})
    print("Setup complete. Start with: python3 scripts/product.py up")


def web_stamp(env: dict[str, str]) -> dict:
    frontend = ROOT / "frontend"
    paths = [frontend / name for name in ("package-lock.json", "next.config.mjs", "postcss.config.mjs", "tailwind.config.ts", "tsconfig.json")]
    for name in ("app", "components", "hooks", "lib", "types", "public"):
        if (frontend / name).exists():
            paths.extend(path for path in (frontend / name).rglob("*") if path.is_file())
    digest = hashlib.sha256()
    for path in sorted(paths):
        digest.update(path.relative_to(frontend).as_posix().encode())
        digest.update(path.read_bytes())
    return {"api_url": env.get("NEXT_PUBLIC_API_URL", "http://localhost:8000"), "source_sha256": digest.hexdigest()}


def build() -> None:
    env = environment()
    run(["npm", "run", "build:portable" if str(ROOT).startswith("/mnt/") else "build", "--prefix", "frontend"], env)
    save(STATE / "web-build.json", web_stamp(env))


def alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        proc = Path(f"/proc/{pid}/stat")
        return not (proc.exists() and proc.read_text().rsplit(")", 1)[1].split()[0] == "Z")
    except (ProcessLookupError, PermissionError):
        return False


def stop_services(state: dict) -> None:
    for service in state.get("services", []):
        pid = service["pid"]
        if not alive(pid):
            continue
        proc = Path(f"/proc/{pid}")
        if proc.exists():
            # Next.js rewrites its process title, so cmdline is not a reliable
            # ownership marker. Check working directory and process start time.
            cwd = (proc / "cwd").resolve()
            started = (proc / "stat").read_text().rsplit(")", 1)[1].split()[19]
            if not cwd.is_relative_to(ROOT) or (service.get("start_ticks") and service["start_ticks"] != started):
                raise RuntimeError(f"PID {pid} no longer belongs to this product; refusing to stop it")
        os.kill(pid, signal.SIGTERM)
        for _ in range(100):
            if not alive(pid):
                break
            time.sleep(0.1)
        if alive(pid):
            os.kill(pid, signal.SIGKILL)


def wait_url(url: str, process: subprocess.Popen, log: Path) -> None:
    for _ in range(180):
        if process.poll() is not None:
            raise RuntimeError(f"Service exited during startup. Inspect {log}")
        try:
            with urlopen(url, timeout=2) as response:
                if response.status == 200:
                    return
        except (URLError, TimeoutError, OSError):
            pass
        time.sleep(0.5)
    raise RuntimeError(f"Startup timed out for {url}. Inspect {log}")


def up(args) -> None:
    configure()
    state_path = STATE / "product.json"
    if state_path.exists():
        previous = json.loads(state_path.read_text())
        if any(alive(item["pid"]) for item in previous["services"]):
            raise RuntimeError("Product is already running; use status or down first")
    env = environment()
    api_port, web_port = int(env.get("PORT", "8000")), int(env.get("WEB_PORT", "3000"))
    for port in (api_port, web_port):
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", port))
    stamp_path = STATE / "web-build.json"
    expected = web_stamp(env)
    stamp = json.loads(stamp_path.read_text()) if stamp_path.exists() else None
    if not args.no_build and (stamp != expected or not (ROOT / "frontend/.next/BUILD_ID").exists()):
        build()
    if not (ROOT / "frontend/.next/BUILD_ID").exists():
        raise RuntimeError("Production web build is missing; run product.py build")
    executable = python_executable(args)
    run([executable, "-c", "import fastapi,uvicorn"])
    if args.data_dir:
        data = Path(args.data_dir).resolve()
        env.update(DATA_DIR=str(data), DATABASE_URL=f"sqlite:///{data / 'cybersecra.db'}")
    STATE.mkdir(exist_ok=True)
    state = {"api": f"http://localhost:{api_port}", "web": f"http://localhost:{web_port}", "services": []}
    commands = [
        ("backend", [executable, str(ROOT / "backend/run.py")], env, f"http://127.0.0.1:{api_port}/ready"),
        ("frontend", ["node", str(ROOT / "frontend/node_modules/next/dist/bin/next"), "start", str(ROOT / "frontend"), "--hostname", env.get("WEB_HOST", "127.0.0.1"), "--port", str(web_port)], {**env, "PORT": str(web_port)}, f"http://127.0.0.1:{web_port}"),
    ]
    try:
        for name, command, service_env, url in commands:
            log = STATE / f"{name}.log"
            with log.open("ab") as output:
                process = subprocess.Popen(command, cwd=ROOT, env=service_env, stdout=output, stderr=output, start_new_session=os.name != "nt")
            record = {"name": name, "pid": process.pid}
            proc = Path(f"/proc/{process.pid}/stat")
            if proc.exists():
                record["start_ticks"] = proc.read_text().rsplit(")", 1)[1].split()[19]
            state["services"].append(record)
            save(state_path, state)
            wait_url(url, process, log)
    except BaseException:
        stop_services(state)
        state_path.unlink(missing_ok=True)
        raise
    print(json.dumps({"status": "running", "web": state["web"], "api": state["api"], "health": state["api"] + "/health", "readiness": state["api"] + "/ready"}, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("configure", "setup", "build", "up", "down", "status", "test"))
    parser.add_argument("--python")
    parser.add_argument("--venv", default=str(ROOT / ".venv"))
    parser.add_argument("--skip-web-install", action="store_true")
    parser.add_argument("--no-build", action="store_true")
    parser.add_argument("--data-dir")
    args = parser.parse_args()
    if args.action == "configure": configure()
    elif args.action == "setup": setup(args)
    elif args.action == "build": build()
    elif args.action == "up": up(args)
    elif args.action == "test":
        executable = python_executable(args)
        run([executable, "-m", "pytest", "-p", "no:cacheprovider", "-q", "backend/tests"])
        run([executable, "-m", "compileall", "-q", "backend", "ml", "scripts"])
        run(["npm", "test", "--prefix", "frontend"])
        run(["npm", "run", "typecheck", "--prefix", "frontend"])
    else:
        path = STATE / "product.json"
        state = json.loads(path.read_text()) if path.exists() else {"services": []}
        if args.action == "down":
            stop_services(state)
            path.unlink(missing_ok=True)
            print("Product stopped.")
        else:
            print(json.dumps({**state, "running": bool(state["services"]) and all(alive(item["pid"]) for item in state["services"])}, indent=2))


if __name__ == "__main__":
    main()
