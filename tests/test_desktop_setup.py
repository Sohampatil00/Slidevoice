import hashlib
import io
import json

import pytest

from app import core, desktop_setup


def test_corrupt_download_is_not_installed_and_retry_reuses_verified_cache(tmp_path, monkeypatch):
    class Response(io.BytesIO):
        headers = {}

    monkeypatch.setattr(desktop_setup, "urlopen", lambda *a, **k: Response(b"broken"))
    path = tmp_path / "office.msi"
    checksum = hashlib.sha256(b"valid").hexdigest()
    with pytest.raises(RuntimeError, match="checksum"):
        desktop_setup.verified_download("https://example.invalid/office", path, checksum)
    assert not path.exists()
    assert not path.with_suffix(".msi.part").exists()
    monkeypatch.setattr(desktop_setup, "urlopen", lambda *a, **k: Response(b"valid"))
    desktop_setup.verified_download("https://example.invalid/office", path, checksum)
    monkeypatch.setattr(desktop_setup, "urlopen", lambda *a, **k: pytest.fail("cached file redownloaded"))
    desktop_setup.verified_download("https://example.invalid/office", path, checksum)


def test_failed_model_setup_can_retry_without_losing_projects(monkeypatch):
    project = core.new_project("Keep this presentation")
    monkeypatch.setattr(desktop_setup.lux_bootstrap, "prepare_runtime", lambda: ("python", core.DATA))
    monkeypatch.setattr(desktop_setup, "prepare_office", lambda: None)
    monkeypatch.setattr(desktop_setup.media, "soffice", lambda: "soffice")

    def fail(*a, **k):
        raise RuntimeError("network unavailable")

    monkeypatch.setattr(desktop_setup, "run_child", fail)
    with pytest.raises(RuntimeError, match="network"):
        desktop_setup.prepare_all()
    assert desktop_setup.read_status()["status"] == "failed"
    monkeypatch.setattr(desktop_setup, "run_child", lambda *a, **k: None)
    desktop_setup.prepare_all()
    assert desktop_setup.read_status()["status"] == "complete"
    assert core.read_project(project["id"])["title"] == "Keep this presentation"


def test_completed_setup_is_not_repeated(monkeypatch):
    desktop_setup.report("complete", "Local components are ready.")
    monkeypatch.setattr(desktop_setup.lux_bootstrap, "prepare_runtime", lambda: pytest.fail("setup repeated"))
    desktop_setup.prepare_all()


def test_stale_setup_owner_is_replaced(monkeypatch):
    owner = core.DATA / "setup-owner.lock"
    owner.write_text("999999999", encoding="ascii")
    desktop_setup.report("complete", "Local components are ready.")
    monkeypatch.setattr(desktop_setup.lux_bootstrap, "prepare_runtime", lambda: pytest.fail("setup repeated"))
    desktop_setup.prepare_all()
    assert not owner.exists()


def test_interrupted_setup_is_retryable():
    desktop_setup.report("running", "Preparing")
    value = json.loads(desktop_setup.status_path().read_text())
    value["process_started"] = 0
    desktop_setup.status_path().write_text(json.dumps(value))
    assert desktop_setup.read_status()["status"] == "failed"


def test_setup_routes_require_desktop(client, monkeypatch):
    monkeypatch.delenv("SLIDEVOICE_DESKTOP", raising=False)
    assert client.get("/api/desktop/setup").status_code == 404
    assert client.post("/api/desktop/setup").status_code == 404
    monkeypatch.setenv("SLIDEVOICE_DESKTOP", "1")
    assert client.get("/api/desktop/setup").json()["status"] == "not_started"


def test_parallel_download_resumes_completed_chunks(tmp_path, monkeypatch):
    from urllib.error import URLError

    content = b"0123456789abcdef" * 8
    broken = True
    requests = []

    class Response(io.BytesIO):
        status = 206

        def __init__(self, first, last):
            super().__init__(content[first : last + 1])
            self.headers = {"Content-Range": f"bytes {first}-{last}/{len(content)}"}

    def fetch(request, **kwargs):
        first, last = map(int, request.get_header("Range").split("=")[1].split("-"))
        requests.append(first)
        if broken and first == 16:
            raise URLError("connection interrupted")
        return Response(first, last)

    monkeypatch.setattr(desktop_setup, "urlopen", fetch)
    monkeypatch.setattr(desktop_setup.time, "sleep", lambda _: None)
    target = tmp_path / "office.part"
    checksum = hashlib.sha256(content).hexdigest()
    with pytest.raises(URLError):
        desktop_setup.download_ranges(
            "https://example.invalid", target, len(content), checksum, chunk_size=16
        )
    broken = False
    requests.clear()
    desktop_setup.download_ranges("https://example.invalid", target, len(content), checksum, chunk_size=16)
    assert target.read_bytes() == content
    assert requests == [16]
