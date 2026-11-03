"""Install the requested web stack using an isolated supported Python interpreter."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def supported(binary: str | Path) -> bool:
    try:
        version = json.loads(subprocess.check_output([str(binary), "-c", "import sys,json; print(json.dumps(list(sys.version_info[:2])))"], text=True, stderr=subprocess.DEVNULL))
        return (3, 11) <= tuple(version) < (3, 13)
    except (OSError, subprocess.SubprocessError, ValueError):
        return False


def run(command, **kwargs):
    subprocess.run([str(value) for value in command], cwd=ROOT, check=True, **kwargs)


def main():
    node, npm = shutil.which("node"), shutil.which("npm")
    if not node or not npm:
        raise SystemExit("请先安装 Node.js 24.14.1 或更新版本（包含 npm）。")
    version = tuple(map(int, subprocess.check_output([node, "--version"], text=True).strip().lstrip("v").split(".")[:3]))
    if version < (24, 14, 1):
        raise SystemExit("Ketcher 需要 Node.js >=24.14.1，请升级 Node.js 后重试。")
    python = ROOT / ".venv/bin/python"
    if not supported(python):
        candidate = os.getenv("OPENMOLSPEC_PYTHON")
        candidates = [candidate] if candidate else [shutil.which(f"python3.{minor}") for minor in (12, 11)]
        interpreter = next((value for value in candidates if value and supported(value)), None)
        if interpreter:
            run([interpreter, "-m", "venv", ROOT / ".venv"])
        else:
            # uv itself is installed in a disposable directory, never into system Python.
            with tempfile.TemporaryDirectory(prefix="openmolspec-setup-") as temporary:
                uv = shutil.which("uv")
                if not uv:
                    run([sys.executable, "-m", "pip", "install", "--target", temporary, "uv"])
                    uv = str(Path(temporary) / "bin/uv")
                if (ROOT / ".venv").exists():
                    raise SystemExit("现有 .venv 的 Python 版本不兼容。请先将该目录改名，再运行 ./setup.sh；推荐 Python 3.12。")
                run([uv, "venv", "--python", "3.12", "--seed", ROOT / ".venv"])
    run([python, "-m", "pip", "install", "-e", ROOT, "-r", ROOT / "requirements.txt", "-r", ROOT / "requirements-services.txt"])
    subprocess.run([npm, "ci", "--no-audit", "--no-fund"], cwd=ROOT / "web", check=True)
    print("\n依赖已安装。运行 ./start.sh 启动 Next.js、应用 API 和独立化学服务。")


if __name__ == "__main__":
    main()
