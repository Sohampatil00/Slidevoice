import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from contextlib import nullcontext

import pytest

from app import local_runtime, providers
from app.core import WorkflowError


class Process:
    pid = 987654

    def __init__(self, returncode=None):
        self.returncode = returncode

    def poll(self):
        return self.returncode

    def wait(self, timeout):
        self.returncode = 0
        return 0


@pytest.fixture
def runtime(monkeypatch):
    monkeypatch.setenv("LUX_TTS_AUTOSTART", "1")
    monkeypatch.setattr(providers, "speech_status", lambda provider: False)

    def unavailable(*args, **kwargs):
        raise ConnectionRefusedError()

    monkeypatch.setattr(local_runtime.socket, "create_connection", unavailable)
    return local_runtime.LuxRuntime()


def test_manual_mode_never_probes_or_starts(runtime, monkeypatch):
    monkeypatch.setenv("LUX_TTS_AUTOSTART", "0")
    monkeypatch.setattr(providers, "speech_status", lambda provider: pytest.fail("Unexpected probe"))
    runtime.ensure_ready()
    assert runtime._process is None


def test_existing_server_is_reused_and_never_stopped(runtime, monkeypatch):
    monkeypatch.setattr(providers, "speech_status", lambda provider: True)
    monkeypatch.setattr(
        local_runtime.processes, "stop_process_tree", lambda *args: pytest.fail("External server was stopped")
    )
    runtime.ensure_ready()
    runtime.stop()
    assert runtime._process is None


@pytest.mark.parametrize(
    "url", ["https://speech.example", "https://127.0.0.1:8004", "http://localhost:8004/api"]
)
def test_nonlocal_or_custom_servers_are_not_launched(runtime, monkeypatch, url):
    monkeypatch.setenv("LUX_TTS_BASE_URL", url)
    assert not local_runtime.lux_can_autostart()
    with pytest.raises(WorkflowError, match="local HTTP"):
        runtime.ensure_ready()
    assert runtime._process is None


def test_busy_port_is_not_overwritten(runtime, monkeypatch):
    monkeypatch.setattr(local_runtime.socket, "create_connection", lambda *args, **kwargs: nullcontext())
    with pytest.raises(WorkflowError, match="port is occupied"):
        runtime.ensure_ready()
    assert runtime._process is None


def test_simultaneous_requests_start_once_and_use_configured_port(runtime, monkeypatch):
    launches, stops = [], []
    process = Process()

    def start(command, **kwargs):
        launches.append((command, kwargs))
        return process

    monkeypatch.setenv("LUX_TTS_BASE_URL", "http://127.0.0.1:8123")
    monkeypatch.setattr(local_runtime.subprocess, "Popen", start)
    monkeypatch.setattr(providers, "speech_status", lambda provider: bool(launches))
    monkeypatch.setattr(local_runtime.processes, "stop_process_tree", lambda *args: stops.append(args))
    with ThreadPoolExecutor(max_workers=2) as executor:
        list(executor.map(lambda _: runtime.ensure_ready(), range(2)))
    assert len(launches) == 1
    command, options = launches[0]
    assert command == [sys.executable, "-m", "app.lux_bootstrap"]
    assert options["env"]["LUX_TTS_PORT"] == "8123"
    assert all(options[key] == value for key, value in local_runtime.processes.background_options().items())
    runtime.stop()
    assert stops == [(process,)]
    assert runtime._process is None


def test_failed_launcher_reports_the_managed_log(runtime, monkeypatch):
    monkeypatch.setattr(local_runtime.subprocess, "Popen", lambda *args, **kwargs: Process(returncode=1))
    with pytest.raises(WorkflowError, match="data/logs/lux.log"):
        runtime.ensure_ready()


def test_startup_timeout_stops_owned_process(runtime, monkeypatch):
    process, stops = Process(), []
    monkeypatch.setattr(local_runtime.subprocess, "Popen", lambda *args, **kwargs: process)
    monkeypatch.setattr(local_runtime.processes, "stop_process_tree", lambda *args: stops.append(args))
    with pytest.raises(WorkflowError, match="timed out"):
        runtime.ensure_ready(timeout=0)
    assert len(stops) == 1 and runtime._process is None


def test_normal_shutdown_releases_a_real_child(runtime):
    process = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(30)"], **local_runtime.processes.background_options()
    )
    runtime._process = process
    try:
        runtime.stop()
        assert process.poll() is not None
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()


def test_invalid_port_is_reported_before_a_network_probe(runtime, monkeypatch):
    monkeypatch.setenv("LUX_TTS_BASE_URL", "http://127.0.0.1:invalid")
    monkeypatch.setattr(providers, "speech_status", lambda provider: pytest.fail("Invalid URL was probed"))
    with pytest.raises(WorkflowError, match="valid server port"):
        runtime.ensure_ready()


def test_studio_lifespan_stops_its_owned_worker(runtime, monkeypatch):
    from fastapi.testclient import TestClient

    from app.main import app

    process, signals = Process(), []
    runtime._process = process
    monkeypatch.setattr(local_runtime, "LuxRuntime", lambda: runtime)
    monkeypatch.setattr(local_runtime.processes, "stop_process_tree", lambda *args: signals.append(args))
    with TestClient(app, base_url="http://127.0.0.1"):
        assert runtime._process is process
    assert runtime._process is None
    assert signals == [(process,)]
