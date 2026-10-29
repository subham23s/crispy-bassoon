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
import webbrowser
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


def resolve_command(command: list[str]) -> list[str]:
    if os.name == "nt" and command:
        resolved = shutil.which(command[0])
        if resolved:
            return [resolved, *command[1:]]
    return command


def run(command: list[str], env=None) -> None:
    resolved = resolve_command(command)
    # Invoke npm.cmd with an explicitly quoted cmd.exe command line on Windows.
    # Its path can contain shell metacharacters (for example, "VITE&REACT").
    if os.name == "nt" and resolved and Path(resolved[0]).name.lower() == "npm.cmd":
        arguments = subprocess.list2cmdline(resolved[1:])
        command_line = f'cmd.exe /d /s /c ""{resolved[0]}" {arguments}"'
        subprocess.run(command_line, cwd=ROOT, env=env or environment(), check=True)
        return
    subprocess.run(resolved, cwd=ROOT, env=env or environment(), check=True)


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
    standalone = ROOT / "frontend/.next/standalone"
    if standalone.exists():
        static_src = ROOT / "frontend/.next/static"
        static_dst = standalone / ".next/static"
        if static_src.exists():
            shutil.copytree(static_src, static_dst, dirs_exist_ok=True)
        public_src = ROOT / "frontend/public"
        public_dst = standalone / "public"
        if public_src.exists():
            shutil.copytree(public_src, public_dst, dirs_exist_ok=True)
    save(STATE / "web-build.json", web_stamp(env))


def free_port(port: int) -> None:
    with socket.socket() as probe:
        try:
            probe.bind(("127.0.0.1", port))
            return
        except OSError as exc:
            raise RuntimeError(f"Port {port} is already in use; refusing to stop its owner automatically") from exc


def url_ready(url: str) -> bool:
    try:
        with urlopen(url, timeout=1) as response:
            return 200 <= response.status < 500
    except (URLError, TimeoutError, OSError):
        return False


def alive(pid: int) -> bool:
    if os.name == "nt":
        import ctypes
        ctypes.windll.kernel32.OpenProcess.restype = ctypes.c_void_p
        handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
        if not handle:
            return False
        exit_code = ctypes.c_ulong()
        ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code))
        ctypes.windll.kernel32.CloseHandle(handle)
        return exit_code.value == 259
    try:
        os.kill(pid, 0)
        proc = Path(f"/proc/{pid}/stat")
        return not (proc.exists() and proc.read_text().rsplit(")", 1)[1].split()[0] == "Z")
    except (ProcessLookupError, PermissionError, OSError):
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
        if os.name == "nt":
            import ctypes
            handle = ctypes.windll.kernel32.OpenProcess(1, False, pid)
            if handle:
                ctypes.windll.kernel32.TerminateProcess(handle, 0)
                ctypes.windll.kernel32.CloseHandle(handle)
        else:
            try:
                os.kill(pid, signal.SIGTERM)
            except OSError:
                pass
            for _ in range(100):
                if not alive(pid):
                    break
                time.sleep(0.1)
            if alive(pid):
                kill_sig = getattr(signal, "SIGKILL", signal.SIGTERM)
                try:
                    os.kill(pid, kill_sig)
                except OSError:
                    pass


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
    previous = json.loads(state_path.read_text()) if state_path.exists() else {}
    env = environment()
    api_port, web_port = int(env.get("PORT", "8000")), int(env.get("WEB_PORT", "3000"))
    api_url = f"http://127.0.0.1:{api_port}"
    web_url = f"http://127.0.0.1:{web_port}"
    api_ready, web_ready = url_ready(api_url + "/ready"), url_ready(web_url)
    if api_ready and web_ready:
        print(f"Product is already running at http://localhost:{web_port}")
        if not getattr(args, "no_open", False):
            print(f"[*] Opening dashboard in browser: http://localhost:{web_port}")
            webbrowser.open(f"http://localhost:{web_port}")
        return
    if not api_ready:
        free_port(api_port)
    if not web_ready:
        free_port(web_port)
    stamp_path = STATE / "web-build.json"
    expected = web_stamp(env)
    stamp = json.loads(stamp_path.read_text()) if stamp_path.exists() else None
    if not args.no_build and (stamp != expected or not (ROOT / "frontend/.next/BUILD_ID").exists()):
        build()
    elif not stamp_path.exists() and (ROOT / "frontend/.next/BUILD_ID").exists():
        save(stamp_path, expected)
    if not (ROOT / "frontend/.next/BUILD_ID").exists():
        raise RuntimeError("Production web build is missing; run product.py build")
    executable = python_executable(args)
    run([executable, "-c", "import fastapi,uvicorn"])
    if args.data_dir:
        data = Path(args.data_dir).resolve()
        env.update(DATA_DIR=str(data), DATABASE_URL=f"sqlite:///{data / 'cybersecra.db'}")
    STATE.mkdir(exist_ok=True)
    previous_services = {item.get("name"): item for item in previous.get("services", [])}
    state = {"api": f"http://localhost:{api_port}", "web": f"http://localhost:{web_port}", "services": []}
    if api_ready and "backend" in previous_services:
        state["services"].append(previous_services["backend"])
    if web_ready and "frontend" in previous_services:
        state["services"].append(previous_services["frontend"])
    standalone = ROOT / "frontend/.next/standalone/server.js"
    if standalone.exists():
        frontend_cmd = ["node", str(standalone)]
    else:
        frontend_cmd = ["node", str(ROOT / "frontend/node_modules/next/dist/bin/next"), "start", str(ROOT / "frontend"), "--hostname", env.get("WEB_HOST", "127.0.0.1"), "--port", str(web_port)]
    commands = []
    if not api_ready:
        commands.append(("backend", [executable, str(ROOT / "backend/run.py")], env, f"http://127.0.0.1:{api_port}/ready"))
    if not web_ready:
        commands.append(("frontend", frontend_cmd, {**env, "PORT": str(web_port), "HOSTNAME": env.get("WEB_HOST", "127.0.0.1")}, f"http://127.0.0.1:{web_port}"))
    creation_flags = (subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS) if os.name == "nt" else 0
    started_services = []
    try:
        for name, command, service_env, url in commands:
            log = STATE / f"{name}.log"
            with log.open("ab") as output:
                try:
                    process = subprocess.Popen(
                        resolve_command(command),
                        cwd=ROOT,
                        env=service_env,
                        stdout=output,
                        stderr=output,
                        start_new_session=os.name != "nt",
                        creationflags=(creation_flags | 0x01000000) if os.name == "nt" else 0,
                    )
                except OSError:
                    process = subprocess.Popen(
                        resolve_command(command),
                        cwd=ROOT,
                        env=service_env,
                        stdout=output,
                        stderr=output,
                        start_new_session=os.name != "nt",
                        creationflags=creation_flags,
                    )
            record = {"name": name, "pid": process.pid}
            proc = Path(f"/proc/{process.pid}/stat")
            if proc.exists():
                record["start_ticks"] = proc.read_text().rsplit(")", 1)[1].split()[19]
            state["services"].append(record)
            started_services.append(record)
            save(state_path, state)
            wait_url(url, process, log)
    except BaseException:
        stop_services({"services": started_services})
        if state["services"]:
            save(state_path, state)
        else:
            state_path.unlink(missing_ok=True)
        raise
    info = {"status": "running", "web": state["web"], "api": state["api"], "health": state["api"] + "/health", "readiness": state["api"] + "/ready"}
    print(json.dumps(info, indent=2))
    if not getattr(args, "no_open", False):
        print("\n[*] Opening dashboard in browser: " + state["web"])
        webbrowser.open(state["web"])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("configure", "setup", "build", "up", "down", "status", "test"))
    parser.add_argument("--python")
    parser.add_argument("--venv", default=str(ROOT / ".venv"))
    parser.add_argument("--skip-web-install", action="store_true")
    parser.add_argument("--no-build", action="store_true")
    parser.add_argument("--no-open", action="store_true", help="Do not auto-open the dashboard in the browser")
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
