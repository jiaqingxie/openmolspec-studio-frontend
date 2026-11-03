"""Own and supervise the three local processes; never take over an occupied port."""
from __future__ import annotations

import argparse
import json
import os
import secrets
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / ".openmolspec"
REGISTRY = STATE / "run.json"


def fingerprint(pid: int) -> str:
    result = subprocess.run(["ps", "-p", str(pid), "-o", "lstart="], text=True, capture_output=True)
    return result.stdout.strip()


def stop_registered():
    if not REGISTRY.is_file():
        print("没有由启动器管理的运行实例。")
        return
    registry = json.loads(REGISTRY.read_text())
    owner = registry["launcher"]
    if owner.get("fingerprint") and fingerprint(owner["pid"]) == owner["fingerprint"]:
        os.kill(owner["pid"], signal.SIGTERM)
        print("正在停止 OpenMolSpec 服务。")
        return
    for process in registry.get("services", []):
        if process.get("fingerprint") and fingerprint(process["pid"]) == process["fingerprint"]:
            try:
                os.killpg(process["pid"], signal.SIGTERM)
            except ProcessLookupError:
                pass
    REGISTRY.unlink(missing_ok=True)
    print("已清理本启动器记录的服务。")


def available(host: str, port: int):
    with socket.socket() as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((host, port))
        except OSError as exc:
            raise RuntimeError(f"端口 {port} 已被占用，请停止原服务或使用 --web-port / --api-port / --chemistry-port 指定其他端口。") from exc


def ready(url: str, process: subprocess.Popen, log: Path, timeout: float = 90):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"服务提前退出，日志：{log}\n{log.read_text(errors='replace')[-4000:]}")
        try:
            with urllib.request.urlopen(url, timeout=1) as response:
                if response.status == 200:
                    return
        except (urllib.error.URLError, TimeoutError, OSError):
            pass
        time.sleep(0.2)
    raise RuntimeError(f"服务启动超时：{url}；日志：{log}")


def terminate_groups(processes: list[subprocess.Popen], grace_seconds: float = 10):
    # A session can still contain Next.js children after its npm leader exits.
    remaining = set()
    for process in reversed(processes):
        try:
            os.killpg(process.pid, signal.SIGTERM)
            remaining.add(process.pid)
        except ProcessLookupError:
            pass
        except PermissionError:
            if process.poll() is None:
                raise
    deadline = time.monotonic() + grace_seconds
    while remaining and time.monotonic() < deadline:
        for process in processes:
            process.poll()
        for group in list(remaining):
            try:
                os.killpg(group, 0)
            except (ProcessLookupError, PermissionError):
                remaining.discard(group)
        if remaining:
            time.sleep(0.05)
    for group in remaining:
        try:
            os.killpg(group, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
    for process in processes:
        process.wait(timeout=5)


def main():
    load_dotenv(ROOT / ".env", override=False)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--web-port", type=int, default=3000)
    parser.add_argument("--api-port", type=int, default=8000)
    parser.add_argument("--chemistry-port", type=int, default=8001)
    parser.add_argument("--production", action="store_true", help="Use a previously built Next.js application")
    parser.add_argument("--stop", action="store_true")
    args = parser.parse_args()
    if args.stop:
        stop_registered()
        return
    if not os.environ.get("OPENMOLSPEC_DATABASE_URL"):
        raise RuntimeError("请先启动 PostgreSQL，并在 .env 设置 OPENMOLSPEC_DATABASE_URL。")
    available("127.0.0.1", args.chemistry_port)
    available("127.0.0.1", args.api_port)
    available(args.host, args.web_port)
    if not (ROOT / "web/node_modules/next").exists():
        raise RuntimeError("前端依赖未安装，请先运行 ./setup.sh。")
    if args.production and not (ROOT / "web/.next/BUILD_ID").exists():
        raise RuntimeError("请先在 web/ 运行 npm run build，再使用 --production。")
    (STATE / "logs").mkdir(parents=True, exist_ok=True)
    environment = os.environ.copy()
    local_host = "127.0.0.1" if args.host in {"0.0.0.0", "::"} else args.host
    environment.setdefault("OPENMOLSPEC_ROOT", str(ROOT))
    environment["OPENMOLSPEC_CHEMISTRY_URL"] = f"http://127.0.0.1:{args.chemistry_port}"
    environment["OPENMOLSPEC_API_URL"] = f"http://127.0.0.1:{args.api_port}"
    environment.setdefault("OPENMOLSPEC_ENV", "production" if args.production else "development")
    if not environment.get("OPENMOLSPEC_INTERNAL_KEY"):
        environment["OPENMOLSPEC_INTERNAL_KEY"] = secrets.token_urlsafe(32)
    if not environment.get("OPENMOLSPEC_MCP_LOCAL_URL"):
        environment["OPENMOLSPEC_MCP_LOCAL_URL"] = f"http://{local_host}:{args.web_port}/api/mcp"
    registry = {"launcher": {"pid": os.getpid(), "fingerprint": fingerprint(os.getpid())}, "services": []}
    processes = []
    handles = []

    def shutdown(signum, frame):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)

    def start(name, command, cwd, health, env=None):
        log_path = STATE / "logs" / f"{name}.log"
        handle = log_path.open("w")
        handles.append(handle)
        process = subprocess.Popen(command, cwd=cwd, env=env or environment, stdin=subprocess.DEVNULL, stdout=handle, stderr=subprocess.STDOUT, start_new_session=True)
        processes.append(process)
        registry["services"].append({"name": name, "pid": process.pid, "fingerprint": fingerprint(process.pid), "log": str(log_path)})
        temporary = REGISTRY.with_suffix(".tmp")
        temporary.write_text(json.dumps(registry))
        temporary.replace(REGISTRY)
        print(f"启动 {name}…", flush=True)
        ready(health, process, log_path)

    try:
        python = str(ROOT / ".venv/bin/python")
        start("chemistry", [python, "-m", "uvicorn", "services.chemistry.app:app", "--host", "127.0.0.1", "--port", str(args.chemistry_port)], ROOT, environment["OPENMOLSPEC_CHEMISTRY_URL"] + "/health")
        start("api", [python, "-m", "uvicorn", "services.api.app:app", "--host", "127.0.0.1", "--port", str(args.api_port)], ROOT, environment["OPENMOLSPEC_API_URL"] + "/api/health")
        frontend_env = {key: value for key, value in environment.items() if key not in {
            "OPENAI_API_KEY", "OPENAI_BASE_URL", "OPENMOLSPEC_LLM_MODEL",
            "OPENMOLSPEC_DATABASE_URL", "OPENMOLSPEC_INTERNAL_KEY",
        }}
        start("web", ["npm", "run", "start" if args.production else "dev", "--", "--hostname", args.host, "--port", str(args.web_port)], ROOT / "web", f"http://{local_host}:{args.web_port}", frontend_env)
        print(f"\nOpenMolSpec Studio: http://{local_host}:{args.web_port}\nMCP: {environment['OPENMOLSPEC_MCP_LOCAL_URL']}\n日志：{STATE / 'logs'}\n按 Ctrl+C 或运行 ./stop.sh 停止。", flush=True)
        while True:
            for process in processes:
                if process.poll() is not None:
                    raise RuntimeError("服务已退出，请查看 .openmolspec/logs/ 下的日志。")
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\n正在停止服务…", flush=True)
    finally:
        terminate_groups(processes)
        for handle in handles:
            handle.close()
        REGISTRY.unlink(missing_ok=True)


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from exc
