import subprocess
import sys

import pytest
from fastapi.testclient import TestClient

from app import desktop_settings, lux_bootstrap, processes
from app.main import app
from app.platform_paths import desktop_directories, python_in_environment


def test_paths_keep_windows_data_outside_installation(tmp_path):
    paths = desktop_directories("win32", tmp_path, {"LOCALAPPDATA": str(tmp_path / "Local")})
    assert paths["data"] == tmp_path / "Local/SlideVoice/data"
    assert python_in_environment(paths["cache"], "win32").name == "python.exe"


def test_paths_keep_mac_data_outside_bundle(tmp_path):
    paths = desktop_directories("darwin", tmp_path, {})
    assert paths["data"] == tmp_path / "Library/Application Support/SlideVoice/data"
    assert paths["cache"] == tmp_path / "Library/Caches/SlideVoice"


def test_desktop_endpoints_are_disabled_in_browser_mode(monkeypatch):
    monkeypatch.delenv("SLIDEVOICE_DESKTOP", raising=False)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        assert client.get("/api/desktop/settings").status_code == 404
        assert client.get("/api/desktop/identity").status_code == 404


def test_keys_persist_without_being_returned(tmp_path, monkeypatch):
    config = tmp_path / ".env"
    monkeypatch.setenv("SLIDEVOICE_DESKTOP", "1")
    monkeypatch.setenv("GEMINI_API_KEY", "")
    monkeypatch.setattr(desktop_settings.core, "CONFIG_FILE", config)
    # Track restoration even though the handler writes os.environ directly.
    monkeypatch.setenv("SCRIPT_PROVIDER", "auto")
    with TestClient(app, base_url="http://127.0.0.1") as client:
        response = client.put(
            "/api/desktop/settings",
            headers={"X-SlideVoice": "local"},
            json={"gemini_key": "test-secret"},
        )
        assert response.status_code == 200
        assert response.json()["gemini_configured"]
        assert "test-secret" not in response.text
        assert "test-secret" in config.read_text()
        if sys.platform != "win32":
            assert config.stat().st_mode & 0o777 == 0o600
        assert client.put("/api/desktop/settings", json={}).status_code == 403
        response = client.put(
            "/api/desktop/settings", headers={"X-SlideVoice": "local"}, json={"gemini_key": "bad\nkey"}
        )
        assert response.status_code == 400


def test_bootstrap_retries_failed_setup_and_reuses_success(tmp_path, monkeypatch):
    resources = tmp_path / "resources"
    resources.mkdir()
    requirements = resources / "requirements-lux.txt"
    requirements.write_text("example==1\n")
    environment = tmp_path / "runtime"
    python = python_in_environment(environment)
    monkeypatch.setenv("SLIDEVOICE_RESOURCE_DIR", str(resources))
    monkeypatch.setattr(lux_bootstrap, "runtime_inputs", lambda: (requirements, resources, environment))
    monkeypatch.setattr(lux_bootstrap, "find_uv", lambda: "uv")
    calls = []

    def failed(command, **kwargs):
        if "venv" in command:
            python.parent.mkdir(parents=True)
            python.touch()
        else:
            raise subprocess.CalledProcessError(1, command)

    with pytest.raises(subprocess.CalledProcessError):
        lux_bootstrap.prepare_runtime(run=failed)
    assert not (environment / ".slidevoice-runtime").exists()

    def success(command, **kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(command, 0)

    lux_bootstrap.prepare_runtime(run=success)
    lux_bootstrap.prepare_runtime(run=success)
    assert len(calls) == 1
    requirements.write_text("example==2\n")
    lux_bootstrap.prepare_runtime(run=success)
    assert len(calls) == 2


def test_cleanup_terminates_descendant_in_separate_session(tmp_path):
    pid_file = tmp_path / "child.pid"
    child_script = "import time; time.sleep(60)"
    script = (
        "import subprocess,sys,time; "
        f"p=subprocess.Popen([sys.executable,'-c',{child_script!r}], **{processes.background_options()!r}); "
        f"open({str(pid_file)!r},'w').write(str(p.pid)); time.sleep(60)"
    )
    process = subprocess.Popen([sys.executable, "-c", script], **processes.background_options())
    import time

    import psutil

    try:
        deadline = time.monotonic() + 10
        while not pid_file.exists() and time.monotonic() < deadline:
            time.sleep(0.05)
        child = psutil.Process(int(pid_file.read_text()))
        processes.stop_process_tree(process, timeout=2)
        assert process.poll() is not None
        assert not child.is_running() or child.status() == psutil.STATUS_ZOMBIE
    finally:
        processes.stop_process_tree(process, timeout=1)


def test_windows_process_options_hide_console():
    assert processes.background_options("win32") == {"creationflags": 0x200 | 0x08000000}


def test_window_opens_ready_url_without_splash_navigation(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from app import desktop

    paths = {"application": tmp_path, "data": tmp_path / "data", "cache": tmp_path / "cache"}
    events = []
    process = object()
    monkeypatch.setattr(desktop, "configure_desktop_environment", lambda: paths)
    monkeypatch.setattr(desktop, "start_backend", lambda paths: (process, "http://127.0.0.1:1234", "nonce"))
    monkeypatch.setattr(desktop, "wait_backend", lambda *args: events.append("ready"))
    monkeypatch.setattr(desktop, "stop_process_tree", lambda child: events.append("stopped"))

    class Closing:
        callback = None

        def __iadd__(self, callback):
            self.callback = callback
            return self

    closing = Closing()

    def create_window(title, **options):
        assert events == ["ready"]
        assert options["url"] == "http://127.0.0.1:1234"
        assert "html" not in options
        events.append("window")
        return SimpleNamespace(events=SimpleNamespace(closing=closing))

    webview = SimpleNamespace(
        settings={}, create_window=create_window, start=lambda **kwargs: events.append("shown")
    )
    monkeypatch.setitem(sys.modules, "webview", webview)
    assert desktop.main() == 0
    assert closing.callback is not None
    closing.callback()
    assert events.pop() == "stopped"
    assert webview.settings["ALLOW_DOWNLOADS"]
    assert events == ["ready", "window", "shown", "stopped"]


def test_desktop_settings_reject_legacy_provider_controls(client, monkeypatch):
    monkeypatch.setenv("SLIDEVOICE_DESKTOP", "1")
    monkeypatch.setenv("SCRIPT_PROVIDER", "claude")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "legacy-key")
    from app import providers

    assert providers.script_provider() == "gemini"
    settings = client.get("/api/desktop/settings").json()
    assert settings["script_provider"] == "gemini"
    assert "anthropic_configured" not in settings
    for payload in ({"anthropic_key": "legacy-key"}, {"script_provider": "claude"}):
        assert client.put("/api/desktop/settings", json=payload).status_code == 422


def test_desktop_fullscreen_control_only_toggles_its_own_window():
    from types import SimpleNamespace

    from app.desktop import DesktopControls

    controls = DesktopControls()
    toggles = []
    controls._window = SimpleNamespace(toggle_fullscreen=lambda: toggles.append(True))
    assert controls.toggle_fullscreen() is True
    assert controls.toggle_fullscreen() is False
    assert len(toggles) == 2


def test_native_bridge_policy_is_desktop_only(client, monkeypatch):
    monkeypatch.delenv("SLIDEVOICE_DESKTOP", raising=False)
    assert "unsafe-eval" not in client.get("/").headers["content-security-policy"]
    monkeypatch.setenv("SLIDEVOICE_DESKTOP", "1")
    policy = client.get("/").headers["content-security-policy"]
    assert "script-src 'self' 'unsafe-eval'" in policy
    assert "unsafe-inline" not in policy
    assert "frame-ancestors 'none'" in policy
