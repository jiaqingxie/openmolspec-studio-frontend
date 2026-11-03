import os
import json
from pathlib import Path
import signal
import subprocess
import socket
import threading
import sys
import time

from scripts import dev
from scripts import setup
import pytest


def state(pid):
    return subprocess.run(["ps", "-p", str(pid), "-o", "stat="], text=True, capture_output=True).stdout.strip()


def test_cleanup_stops_descendants_even_when_npm_style_leader_has_exited():
    leader = subprocess.Popen([sys.executable, "-c", "import subprocess,sys; child=subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)']);print(child.pid,flush=True)"], stdout=subprocess.PIPE, text=True, start_new_session=True)
    child_pid = int(leader.stdout.readline())
    leader.wait(timeout=5)
    try:
        assert state(child_pid) and not state(child_pid).startswith("Z")
        dev.terminate_groups([leader], grace_seconds=0.2)
        deadline = time.monotonic() + 3
        while state(child_pid) and not state(child_pid).startswith("Z") and time.monotonic() < deadline:
            time.sleep(0.01)
        assert not state(child_pid) or state(child_pid).startswith("Z")
    finally:
        try:
            os.killpg(leader.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
        leader.stdout.close()


def test_setup_does_not_accept_python310_for_asyncio_timeout_and_typing_self(tmp_path):
    binary = tmp_path / "reported-python"
    for version, expected in [([3, 10], False), ([3, 11], True), ([3, 12], True), ([3, 13], False)]:
        binary.write_text(f"#!{sys.executable}\nprint({json.dumps(json.dumps(version))})\n")
        binary.chmod(0o700)
        assert setup.supported(binary) is expected


def test_start_wrapper_leaves_asset_root_unset_for_dotenv_to_supply(tmp_path):
    wrapper = Path(__file__).resolve().parents[2] / "start.sh"
    (tmp_path / "start.sh").write_text(wrapper.read_text())
    binary = tmp_path / ".venv/bin/python"
    binary.parent.mkdir(parents=True)
    binary.write_text(f"#!{sys.executable}\nimport os\nprint(os.environ.get('OPENMOLSPEC_ROOT','unset'))\n")
    binary.chmod(0o700)
    environment = {key: value for key, value in os.environ.items() if key != "OPENMOLSPEC_ROOT"}
    response = subprocess.run(["bash", str(tmp_path / "start.sh")], text=True, capture_output=True, env=environment, check=True)
    assert response.stdout.strip() == "unset"


def test_restart_port_check_accepts_closed_listener_with_recent_connections():
    listener = socket.socket()
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", 0))
    listener.listen()
    port = listener.getsockname()[1]
    with pytest.raises(RuntimeError):
        dev.available("127.0.0.1", port)

    def exchange():
        connection, _ = listener.accept()
        connection.recv(1)
        connection.sendall(b"ok")
        connection.close()

    worker = threading.Thread(target=exchange)
    worker.start()
    with socket.create_connection(("127.0.0.1", port)) as client:
        client.sendall(b"x")
        while client.recv(10):
            pass
    worker.join(timeout=3)
    listener.close()
    dev.available("127.0.0.1", port)
