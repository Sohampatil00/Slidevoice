import base64
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app import core, indic_server, providers
from app.core import WorkflowError


def test_reference_upload_requires_permission(client, project, reference_bytes):
    response = client.post(
        f"/api/projects/{project['id']}/reference", files={"file": ("voice.wav", reference_bytes)}
    )
    assert response.status_code == 400
    assert not core.read_project(project["id"]).get("voice_reference")


def test_sample_mode_does_not_silently_use_a_preset(client, project):
    client.post(
        f"/api/projects/{project['id']}/audio",
        json={
            "provider": "indic_mio",
            "consent": True,
            "use_reference": True,
            "voice_id": "some_preset",
        },
    )
    result = core.read_project(project["id"])
    assert result["job"]["status"] == "failed"
    assert "Upload a 3–20 second voice sample" in result["job"]["message"]


def test_reference_upload_duration_and_access(client, project, reference_bytes, wav_bytes):
    url = f"/api/projects/{project['id']}/reference"
    result = client.post(url, data={"consent": "true"}, files={"file": ("voice.wav", reference_bytes)})
    assert result.status_code == 200
    reference = result.json()["voice_reference"]
    assert reference["duration"] == pytest.approx(4)
    assert client.get(reference["audio_url"]).status_code == 200
    invalid = client.post(url, data={"consent": "true"}, files={"file": ("short.wav", wav_bytes)})
    assert invalid.status_code == 400
    assert core.read_project(project["id"])["voice_reference"]["file"] == reference["file"]
    assert client.get(reference["audio_url"]).status_code == 200


def test_reference_fingerprint_invalidates_cache(project, reference_bytes):
    folder = core.project_dir(project["id"])
    reference = folder / "reference.wav"
    reference.write_bytes(reference_bytes)
    original = providers.audio_signature("An explanation.", "indic_mio", "", 1, reference_audio=reference)
    reference.write_bytes(reference_bytes + b"changed")
    updated = providers.audio_signature("An explanation.", "indic_mio", "", 1, reference_audio=reference)
    assert original != updated


def test_provider_receives_reference_from_project(client, project, reference_bytes, wav_bytes, monkeypatch):
    client.post(
        f"/api/projects/{project['id']}/reference",
        data={"consent": "true"},
        files={"file": ("voice.wav", reference_bytes)},
    )
    references = []

    def synthesize(script, destination, provider, voice_id, speed, reference_audio=None):
        references.append(reference_audio)
        destination.write_bytes(wav_bytes)
        return 1.0

    monkeypatch.setattr(providers, "synthesize", synthesize)
    result = client.post(
        f"/api/projects/{project['id']}/audio", json={"provider": "indic_mio", "consent": True}
    )
    assert result.status_code == 200
    assert len(references) == 3
    assert all(reference.is_file() for reference in references)
    assert len(set(references)) == 1
    saved = core.read_project(project["id"])["voice_reference"]
    assert references[0].name == saved["file"]
    assert saved["duration"] == pytest.approx(4)


def test_narration_is_chunked_without_losing_words():
    text = "A slide explains one concept at a time. " * 50
    chunks = providers.split_narration(text)
    assert len(chunks) > 1
    assert all(len(chunk) <= 280 for chunk in chunks)
    assert " ".join(chunks) == text.strip()
    with pytest.raises(WorkflowError):
        providers.split_narration("x" * 281)


def test_reference_payload_and_multiple_chunks(project, reference_bytes, wav_bytes, monkeypatch):
    folder = core.project_dir(project["id"])
    reference = folder / "reference.wav"
    reference.write_bytes(reference_bytes)
    real_client = httpx.Client
    requests = []

    def respond(request):
        payload = json.loads(request.content)
        assert len(payload["text"]) <= 280
        assert payload["reference"]["type"] == "base64"
        assert base64.b64decode(payload["reference"]["data"]) == reference_bytes
        requests.append(payload)
        return httpx.Response(200, json={"audio": base64.b64encode(wav_bytes).decode(), "token_count": 25})

    monkeypatch.setattr(
        providers.httpx, "Client", lambda **kwargs: real_client(transport=httpx.MockTransport(respond))
    )
    destination = folder / "speech.wav"
    duration = providers.synthesize(
        "Every slide has an explanation. " * 20, destination, "indic_mio", "", 1, reference_audio=reference
    )
    assert len(requests) >= 3
    assert duration == pytest.approx(len(requests) + (len(requests) - 1) * 0.12, abs=0.002)


@pytest.mark.parametrize(
    "payload", [{"audio": "not-base64"}, {"error": "broken"}, {"audio": "", "token_count": 1400}, []]
)
def test_invalid_model_responses_leave_no_output(project, monkeypatch, payload):
    real_client = httpx.Client
    monkeypatch.setattr(
        providers.httpx,
        "Client",
        lambda **kwargs: real_client(
            transport=httpx.MockTransport(lambda request: httpx.Response(200, json=payload))
        ),
    )
    target = core.project_dir(project["id"]) / "output.wav"
    with pytest.raises(WorkflowError):
        providers.synthesize("An explanation.", target, "indic_mio", "own", 1)
    assert not target.exists()


def test_model_server_connection_error_is_actionable(project, monkeypatch):
    real_client = httpx.Client

    def disconnected(request):
        raise httpx.ConnectError("failed", request=request)

    monkeypatch.setattr(
        providers.httpx, "Client", lambda **kwargs: real_client(transport=httpx.MockTransport(disconnected))
    )
    with pytest.raises(WorkflowError, match="indic-mio.command"):
        providers.synthesize(
            "An explanation.", core.project_dir(project["id"]) / "output.wav", "indic_mio", "own", 1
        )


@pytest.mark.parametrize(
    "url",
    [
        "http://remote.example:8001",
        "https://user:secret@remote.example",
        "file:///private/audio",
        "https://server.example?token=secret",
    ],
)
def test_rejects_unsafe_server_configuration(monkeypatch, url):
    monkeypatch.setenv("INDIC_MIO_BASE_URL", url)
    with pytest.raises(WorkflowError):
        providers.indic_base_url()


def test_presets_follow_documented_api(monkeypatch):
    real_client = httpx.Client

    def respond(request):
        assert request.url.path == "/v1/presets"
        return httpx.Response(200, json={"presets": ["my_own_voice"]})

    monkeypatch.setattr(
        providers.httpx, "Client", lambda **kwargs: real_client(transport=httpx.MockTransport(respond))
    )
    assert providers.available_voices()[0]["id"] == "my_own_voice"


def test_bundled_server_protocol_without_loading_models(monkeypatch, reference_bytes, wav_bytes):
    calls = []

    class FakeEngine:
        def synthesize(self, text, audio, parameters):
            calls.append((text, audio, parameters))
            return wav_bytes, 48000, 25

    monkeypatch.setattr(indic_server, "IndicEngine", FakeEngine)
    body = {
        "text": "A clear explanation.",
        "reference": {"type": "base64", "data": base64.b64encode(reference_bytes).decode()},
    }
    with TestClient(
        indic_server.app, base_url="http://127.0.0.1", headers={"X-SlideVoice": "local"}
    ) as client:
        assert client.get("/health").json()["model"] == "SPRINGLab/Indic-Mio"
        assert client.get("/v1/presets").json() == {"presets": []}
        response = client.post("/v1/tts", json=body)
        assert response.status_code == 200
        assert base64.b64decode(response.json()["audio"]) == wav_bytes
        assert calls[0][1] == reference_bytes
        assert client.post("/v1/tts", json=body, headers={"Origin": "https://example.com"}).status_code == 403
        assert client.post("/v1/tts", json={**body, "text": "x" * 281}).status_code == 422
        assert client.post("/v1/tts", json={**body, "llm": {"model": "a-different-model"}}).status_code == 400


@pytest.mark.parametrize(
    "reason",
    [
        "Generation reached its token limit. Shorten the sentence.",
        "The model did not return valid speech tokens. Try a shorter sentence.",
        "The model produced empty or invalid audio. Try another reference recording.",
    ],
)
def test_model_generation_errors_retry_with_shorter_chunks(project, monkeypatch, wav_bytes, reason):
    requested = []
    succeeded = []
    real_client = httpx.Client

    def respond(request):
        text = json.loads(request.content)["text"]
        requested.append(text)
        if len(requested) == 1:
            return httpx.Response(422, json={"detail": reason})
        succeeded.append(text)
        return httpx.Response(200, json={"audio": base64.b64encode(wav_bytes).decode(), "token_count": 25})

    monkeypatch.setattr(
        providers.httpx, "Client", lambda **kwargs: real_client(transport=httpx.MockTransport(respond))
    )
    text = "A complete explanation stays in order. All original words must be spoken exactly once."
    target = core.project_dir(project["id"]) / "retried.wav"
    duration = providers.synthesize(text, target, "indic_mio", "own", 1)
    assert len(requested) >= 3
    assert all(len(piece) < len(text) for piece in requested[1:])
    assert " ".join(succeeded) == text
    assert duration == pytest.approx(len(succeeded) + (len(succeeded) - 1) * 0.12, abs=0.002)
    assert target.is_file()


def test_retries_are_bounded_and_leave_no_partial_audio(project, monkeypatch):
    requested = []
    real_client = httpx.Client

    def respond(request):
        requested.append(json.loads(request.content)["text"])
        return httpx.Response(
            422, json={"detail": "Generation reached its token limit. Shorten the sentence."}
        )

    monkeypatch.setattr(
        providers.httpx, "Client", lambda **kwargs: real_client(transport=httpx.MockTransport(respond))
    )
    target = core.project_dir(project["id"]) / "failed.wav"
    with pytest.raises(WorkflowError, match="Automatic retries also failed"):
        providers.synthesize(
            "This sentence keeps failing even when it is split into shorter requests.",
            target,
            "indic_mio",
            "own",
            1,
        )
    assert len(requested) == 3
    assert not target.exists()
    assert not list(target.parent.glob("indic-speech-*"))


def test_single_word_can_retry_without_splitting_word(project, monkeypatch, wav_bytes):
    requested = []
    real_client = httpx.Client

    def respond(request):
        requested.append(json.loads(request.content)["text"])
        if len(requested) == 1:
            return httpx.Response(
                422, json={"detail": "The model did not return valid speech tokens. Try a shorter sentence."}
            )
        return httpx.Response(200, json={"audio": base64.b64encode(wav_bytes).decode(), "token_count": 25})

    monkeypatch.setattr(
        providers.httpx, "Client", lambda **kwargs: real_client(transport=httpx.MockTransport(respond))
    )
    target = core.project_dir(project["id"]) / "one-word.wav"
    providers.synthesize("SQL", target, "indic_mio", "own", 1)
    assert requested == ["SQL", "SQL"]
    assert target.is_file()


@pytest.mark.parametrize("recover", [True, False])
def test_silent_success_responses_retry_without_overwriting_good_audio(
    project, monkeypatch, wav_bytes, silent_wav_bytes, recover
):
    requested = []
    succeeded = []
    real_client = httpx.Client

    def respond(request):
        text = json.loads(request.content)["text"]
        requested.append(text)
        audio = wav_bytes if recover and len(requested) > 1 else silent_wav_bytes
        if audio == wav_bytes:
            succeeded.append(text)
        return httpx.Response(200, json={"audio": base64.b64encode(audio).decode(), "token_count": 25})

    monkeypatch.setattr(
        providers.httpx, "Client", lambda **kwargs: real_client(transport=httpx.MockTransport(respond))
    )
    target = core.project_dir(project["id"]) / "existing.wav"
    target.write_bytes(wav_bytes)
    text = "Keep every word in this explanation. Silent output must be retried."
    if recover:
        providers.synthesize(text, target, "indic_mio", "own", 1)
        assert " ".join(succeeded) == text
        assert len(requested) >= 3
    else:
        with pytest.raises(WorkflowError, match="Automatic retries also failed"):
            providers.synthesize(text, target, "indic_mio", "own", 1)
        assert len(requested) == 3
        assert target.read_bytes() == wav_bytes
    assert not list(target.parent.glob("indic-speech-*"))


@pytest.mark.parametrize(
    "detail",
    [
        {"request": "secret-api-key"},
        [{"loc": ["body", "text"], "input": "secret-api-key"}],
        "secret-api-key",
        "Reference must contain 3–20 seconds of clean speech.",
    ],
)
def test_validation_errors_do_not_retry_or_expose_provider_input(project, monkeypatch, detail):
    requested = []
    real_client = httpx.Client

    def respond(request):
        requested.append(True)
        return httpx.Response(422, json={"detail": detail})

    monkeypatch.setattr(
        providers.httpx, "Client", lambda **kwargs: real_client(transport=httpx.MockTransport(respond))
    )
    with pytest.raises(WorkflowError) as error:
        providers.synthesize(
            "A narration.", core.project_dir(project["id"]) / "invalid.wav", "indic_mio", "own", 1
        )
    assert len(requested) == 1
    assert "secret-api-key" not in str(error.value)
    assert "voice" in str(error.value).lower()
