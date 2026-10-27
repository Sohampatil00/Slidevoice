import base64
import json
from contextlib import asynccontextmanager

import httpx
import pytest
from fastapi.testclient import TestClient

from app import core, lux_server, providers
from app.core import WorkflowError
from app.main import app


@pytest.fixture
def lux_client(monkeypatch, wav_bytes):
    class Engine:
        def synthesize(self, text, audio):
            assert text.strip() and audio
            return wav_bytes, 48000

    @asynccontextmanager
    async def lifespan(app):
        app.state.engine = Engine()
        yield

    monkeypatch.setattr(lux_server.app.router, "lifespan_context", lifespan)
    with TestClient(lux_server.app, base_url="http://127.0.0.1", headers={"X-SlideVoice": "local"}) as client:
        yield client


def body(reference_bytes):
    return {
        "text": "Welcome to this presentation.",
        "reference": {"type": "base64", "data": base64.b64encode(reference_bytes).decode()},
    }


def test_lux_server_contract_and_wav(lux_client, reference_bytes, wav_bytes):
    health = lux_client.get("/health").json()
    assert health["provider"] == "lux_tts"
    assert health["model"] == "YatharthS/LuxTTS"
    result = lux_client.post("/v1/tts", json=body(reference_bytes))
    assert result.status_code == 200
    assert base64.b64decode(result.json()["audio"]) == wav_bytes
    result = lux_client.post("/v1/tts", json={**body(reference_bytes), "output": {"format": "wav"}})
    assert result.headers["content-type"] == "audio/wav"
    assert result.content == wav_bytes


def test_lux_model_reference_limits_and_origin(lux_client, reference_bytes):
    request = body(reference_bytes)
    assert (
        lux_client.post("/v1/tts", json=request, headers={"Origin": "http://example.com"}).status_code == 403
    )
    for invalid in [
        {"model": "other"},
        {"text": "x" * 1201},
        {"text": "   "},
        {"reference": {"type": "preset", "data": "a"}},
    ]:
        assert lux_client.post("/v1/tts", json={**request, **invalid}).status_code == 422
    assert (
        lux_client.post("/v1/tts", json={**request, "reference": {"type": "base64", "data": "!"}}).status_code
        == 400
    )


def test_lux_auth_and_busy(lux_client, monkeypatch, reference_bytes):
    monkeypatch.setenv("LUX_TTS_API_KEY", "test-token")
    assert lux_client.get("/health").status_code == 401
    assert lux_server.inference_lock.acquire(blocking=False)
    try:
        assert (
            lux_client.post(
                "/v1/tts", json=body(reference_bytes), headers={"Authorization": "Bearer test-token"}
            ).status_code
            == 429
        )
    finally:
        lux_server.inference_lock.release()


def test_lux_requires_permission_and_reference(client, project):
    url = f"/api/projects/{project['id']}/audio"
    assert client.post(url, json={"provider": "lux_tts"}).status_code == 400
    client.post(url, json={"provider": "lux_tts", "consent": True})
    result = core.read_project(project["id"])
    assert result["job"]["status"] == "failed"
    assert "3–20 second voice sample" in result["job"]["message"]


def test_lux_uses_project_reference_and_saves_source(
    client, project, reference_bytes, wav_bytes, monkeypatch
):
    url = f"/api/projects/{project['id']}"
    client.post(url + "/reference", data={"consent": "true"}, files={"file": ("voice.wav", reference_bytes)})
    saved_reference = core.read_project(project["id"])["voice_reference"]["file"]
    expected_reference = core.project_dir(project["id"]) / saved_reference
    startup_calls = []
    monkeypatch.setattr(app.state.lux_runtime, "ensure_ready", lambda progress: startup_calls.append(True))
    calls = []

    def synthesize(script, destination, provider, voice_id, speed, reference_audio=None):
        assert provider == "lux_tts" and reference_audio == expected_reference
        assert reference_audio.is_file()
        destination.write_bytes(wav_bytes)
        calls.append(True)
        return 1

    monkeypatch.setattr(providers, "synthesize", synthesize)
    client.post(url + "/audio", json={"provider": "lux_tts", "consent": True})
    saved = core.read_project(project["id"])
    assert len(calls) == 3
    assert saved["job"]["status"] != "failed"
    assert all(s["audio_source"] == "lux_tts" for s in saved["slides"])
    assert len(startup_calls) == 1
    client.post(url + "/audio", json={"provider": "lux_tts", "consent": True})
    assert len(calls) == 3  # Cache hits do not start or contact the model.
    assert len(startup_calls) == 1


@pytest.mark.parametrize("silent_first", [False, True])
def test_lux_large_chunks_and_silent_retry(
    project, reference_bytes, wav_bytes, silent_wav_bytes, monkeypatch, silent_first
):
    folder = core.project_dir(project["id"])
    reference = folder / "reference.wav"
    reference.write_bytes(reference_bytes)
    calls, successes = [], []
    real_client = httpx.Client

    def respond(request):
        payload = json.loads(request.content)
        assert request.url.port == 8004
        assert payload["model"] == "YatharthS/LuxTTS" and "llm" not in payload
        assert len(payload["text"]) <= 1200
        assert base64.b64decode(payload["reference"]["data"]) == reference_bytes
        calls.append(payload["text"])
        silent = silent_first and len(calls) == 1
        if not silent:
            successes.append(payload["text"])
        return httpx.Response(
            200, json={"audio": base64.b64encode(silent_wav_bytes if silent else wav_bytes).decode()}
        )

    monkeypatch.setattr(
        providers.httpx, "Client", lambda **kwargs: real_client(transport=httpx.MockTransport(respond))
    )
    text = "Each slide explains one useful concept clearly. " * 15
    providers.synthesize(text, folder / "lux.wav", "lux_tts", "", 1, reference)
    assert " ".join(successes) == text.strip()
    if not silent_first:
        assert len(calls) == 1  # A whole typical slide avoids Indic's 280-character limit.


def test_lux_cache_and_health_are_engine_specific(project, reference_bytes, monkeypatch):
    reference = core.project_dir(project["id"]) / "ref.wav"
    reference.write_bytes(reference_bytes)
    signature = providers.audio_signature("Welcome.", "lux_tts", "", 1, reference)
    assert signature != providers.audio_signature("Welcome.", "chatterbox_turbo", "", 1, reference)
    reference.write_bytes(reference_bytes + b"changed")
    assert signature != providers.audio_signature("Welcome.", "lux_tts", "", 1, reference)
    real_client = httpx.Client
    monkeypatch.setattr(
        providers.httpx,
        "Client",
        lambda **kwargs: real_client(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(200, json={"status": "ok", "provider": "chatterbox_turbo"})
            )
        ),
    )
    assert not providers.speech_status("lux_tts")
    monkeypatch.setenv("LUX_TTS_BASE_URL", "http://remote.example:8004")
    with pytest.raises(WorkflowError, match="loopback"):
        providers.speech_base_url("lux_tts")
