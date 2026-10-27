import base64
import json
from contextlib import asynccontextmanager

import httpx
import pytest
from fastapi.testclient import TestClient

from app import core, providers, turbo_server
from app.core import WorkflowError


@pytest.fixture
def turbo_client(monkeypatch, wav_bytes):
    class Engine:
        def synthesize(self, text, audio):
            assert text.strip()
            assert audio
            return wav_bytes, 48000

    @asynccontextmanager
    async def lifespan(app):
        app.state.engine = Engine()
        yield

    monkeypatch.setattr(turbo_server.app.router, "lifespan_context", lifespan)
    with TestClient(
        turbo_server.app, base_url="http://127.0.0.1", headers={"X-SlideVoice": "local"}
    ) as client:
        yield client


def test_turbo_server_contract_and_identity(turbo_client, reference_bytes):
    health = turbo_client.get("/health").json()
    assert health["provider"] == "chatterbox_turbo"
    assert health["model"] == "ResembleAI/chatterbox-turbo"
    response = turbo_client.post(
        "/v1/tts",
        json={
            "text": "Welcome to the presentation.",
            "reference": {"type": "base64", "data": base64.b64encode(reference_bytes).decode()},
        },
    )
    assert response.status_code == 200
    assert base64.b64decode(response.json()["audio"]).startswith(b"RIFF")
    assert response.json()["generation_seconds"] >= 0


def test_turbo_server_validates_requests_and_origin(turbo_client, reference_bytes):
    body = {
        "text": "Welcome.",
        "reference": {"type": "base64", "data": base64.b64encode(reference_bytes).decode()},
    }
    assert (
        turbo_client.post("/v1/tts", json=body, headers={"Origin": "http://evil.example"}).status_code == 403
    )
    assert turbo_client.post("/v1/tts", json={**body, "model": "another-model"}).status_code == 422
    assert turbo_client.post("/v1/tts", json={**body, "text": "x" * 281}).status_code == 422
    assert (
        turbo_client.post("/v1/tts", json={**body, "reference": {"type": "base64", "data": "!"}}).status_code
        == 400
    )


def test_turbo_auth_and_busy(turbo_client, monkeypatch, reference_bytes):
    monkeypatch.setenv("CHATTERBOX_TURBO_API_KEY", "test-token")
    assert turbo_client.get("/health").status_code == 401
    body = {
        "text": "Welcome.",
        "reference": {"type": "base64", "data": base64.b64encode(reference_bytes).decode()},
    }
    assert turbo_server.inference_lock.acquire(blocking=False)
    try:
        response = turbo_client.post("/v1/tts", json=body, headers={"Authorization": "Bearer test-token"})
        assert response.status_code == 429
    finally:
        turbo_server.inference_lock.release()


def test_turbo_requires_consent_and_longer_reference(client, project, reference_bytes):
    url = f"/api/projects/{project['id']}"
    assert client.post(url + "/audio", json={"provider": "chatterbox_turbo"}).status_code == 400
    client.post(url + "/reference", data={"consent": "true"}, files={"file": ("voice.wav", reference_bytes)})
    client.post(url + "/audio", json={"provider": "chatterbox_turbo", "consent": True})
    result = core.read_project(project["id"])
    assert result["job"]["status"] == "failed"
    assert "6–20 second" in result["job"]["message"]


@pytest.mark.parametrize("silent_first", [False, True])
def test_turbo_synthesis_protocol_and_silence_retry(
    project, reference_bytes, wav_bytes, silent_wav_bytes, monkeypatch, silent_first
):
    reference = core.project_dir(project["id"]) / "reference.wav"
    reference.write_bytes(reference_bytes)
    calls, succeeded = [], []
    real_client = httpx.Client

    def respond(request):
        body = json.loads(request.content)
        assert request.url.port == 8002
        assert body["model"] == "ResembleAI/chatterbox-turbo"
        assert "llm" not in body
        assert base64.b64decode(body["reference"]["data"]) == reference_bytes
        calls.append(body["text"])
        silent = silent_first and len(calls) == 1
        if not silent:
            succeeded.append(body["text"])
        return httpx.Response(
            200, json={"audio": base64.b64encode(silent_wav_bytes if silent else wav_bytes).decode()}
        )

    monkeypatch.setattr(
        providers.httpx, "Client", lambda **kwargs: real_client(transport=httpx.MockTransport(respond))
    )
    text = "Solar panels produce energy during the day. Batteries store extra energy for later use."
    target = reference.parent / "turbo.wav"
    assert providers.synthesize(text, target, "chatterbox_turbo", "", 1, reference) > 0
    assert " ".join(succeeded) == text
    assert target.exists()
    assert len(calls) > 1 if silent_first else len(calls) == 1


def test_turbo_cache_is_separate_and_references_are_hashed(project, reference_bytes):
    reference = core.project_dir(project["id"]) / "reference.wav"
    reference.write_bytes(reference_bytes)
    signature = providers.audio_signature("Welcome.", "chatterbox_turbo", "", 1, reference)
    assert signature != providers.audio_signature("Welcome.", "indic_mio", "", 1, reference)
    reference.write_bytes(reference_bytes + b"changed")
    assert signature != providers.audio_signature("Welcome.", "chatterbox_turbo", "", 1, reference)


def test_turbo_health_requires_correct_model_service(monkeypatch):
    real_client = httpx.Client
    monkeypatch.setattr(
        providers.httpx,
        "Client",
        lambda **kwargs: real_client(
            transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"status": "ok"}))
        ),
    )
    assert not providers.speech_status("chatterbox_turbo")
    assert providers.indic_status()
    monkeypatch.setenv("CHATTERBOX_TURBO_BASE_URL", "http://remote.example:8002")
    with pytest.raises(WorkflowError, match="loopback"):
        providers.speech_base_url("chatterbox_turbo")
