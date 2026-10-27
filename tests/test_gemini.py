import base64
import json

import httpx
import pytest

from app import core, providers
from app.core import WorkflowError


def gemini_result(text="A clear explanation.", finish="STOP"):
    return {
        "candidates": [
            {
                "finishReason": finish,
                "content": {
                    "parts": [
                        {"thought": True, "text": "Internal reasoning is not narration."},
                        {"text": text},
                    ]
                },
            }
        ]
    }


def mock_gemini(monkeypatch, respond):
    real_client = httpx.Client
    monkeypatch.setattr(
        providers.httpx, "Client", lambda **kwargs: real_client(transport=httpx.MockTransport(respond))
    )
    monkeypatch.setenv("GEMINI_API_KEY", "private-test-key")


def test_gemini_script_includes_image_notes_outline_and_tts_rules(project, monkeypatch):
    requests = []

    def respond(request):
        requests.append(request)
        return httpx.Response(200, json=gemini_result())

    mock_gemini(monkeypatch, respond)
    slide = project["slides"][0]
    script = providers.generate_script(slide, core.project_dir(project["id"]), ["Overview"], "Be concise")
    assert script == "A clear explanation."
    request = requests[0]
    assert str(request.url) == (
        "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.5-flash-lite:generateContent"
    )
    assert request.headers["x-goog-api-key"] == "private-test-key"
    assert "private-test-key" not in str(request.url)
    payload = json.loads(request.content)
    parts = payload["contents"][0]["parts"]
    assert parts[0]["inlineData"]["mimeType"] == "image/jpeg"
    assert base64.b64decode(parts[0]["inlineData"]["data"]).startswith(b"\xff\xd8")
    assert "speaker_notes" in parts[1]["text"]
    assert "Overview" in parts[1]["text"]
    assert "Be concise" in parts[1]["text"]
    system = payload["systemInstruction"]["parts"][0]["text"]
    assert "10 to 18 words" in system
    assert "numbers, units, and symbols" in system


@pytest.mark.parametrize(
    "payload",
    [
        {},
        [],
        {"candidates": []},
        {"promptFeedback": {"blockReason": "SAFETY"}},
        gemini_result(finish="MAX_TOKENS"),
        gemini_result(finish="SAFETY"),
        gemini_result(""),
        gemini_result("x" * 12001),
        {"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": None}]}}]},
    ],
)
def test_unusable_gemini_responses_are_not_saved(project, monkeypatch, payload):
    mock_gemini(monkeypatch, lambda request: httpx.Response(200, json=payload))
    with pytest.raises(WorkflowError, match="Gemini"):
        providers.generate_script(project["slides"][0], core.project_dir(project["id"]), [], "")


@pytest.mark.parametrize("status", [400, 401, 403, 404, 429, 500])
def test_gemini_errors_do_not_expose_key_or_provider_body(project, monkeypatch, status):
    mock_gemini(monkeypatch, lambda request: httpx.Response(status, text="private-test-key"))
    with pytest.raises(WorkflowError) as caught:
        providers.generate_script(project["slides"][0], core.project_dir(project["id"]), [], "")
    assert "private-test-key" not in str(caught.value)
    assert "Gemini" in str(caught.value)


def test_provider_selection_and_missing_key(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-key")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "claude-key")
    assert providers.script_provider() == "gemini"
    monkeypatch.setenv("SCRIPT_PROVIDER", "claude")
    assert providers.script_api_key() == "claude-key"
    monkeypatch.setenv("SCRIPT_PROVIDER", "gemini")
    monkeypatch.delenv("GEMINI_API_KEY")
    with pytest.raises(WorkflowError, match="GEMINI_API_KEY"):
        providers.script_api_key()
    monkeypatch.setenv("SCRIPT_PROVIDER", "unknown")
    with pytest.raises(WorkflowError, match="SCRIPT_PROVIDER"):
        providers.script_provider()


def test_gemini_generation_route_and_health(client, project, monkeypatch):
    mock_gemini(monkeypatch, lambda request: httpx.Response(200, json=gemini_result()))
    monkeypatch.setattr(providers, "indic_status", lambda: False)
    health = client.get("/api/health").json()
    assert health["scripts"] is True
    assert health["script_provider_name"] == "Gemini"
    assert "private-test-key" not in json.dumps(health)
    selected = project["slides"][1]
    response = client.post(f"/api/projects/{project['id']}/scripts", json={"slide_ids": [selected["id"]]})
    assert response.status_code == 200
    saved = core.read_project(project["id"])
    assert saved["job"]["status"] == "complete", saved["job"]["message"]
    assert saved["slides"][1]["script"] == "A clear explanation."
    assert saved["slides"][0]["script"] == project["slides"][0]["script"]


def test_partial_gemini_failure_keeps_completed_slides(client, project, monkeypatch):
    requests = []

    def respond(request):
        requests.append(request)
        return httpx.Response(200, json=gemini_result()) if len(requests) == 1 else httpx.Response(429)

    mock_gemini(monkeypatch, respond)
    client.post(
        f"/api/projects/{project['id']}/scripts", json={"slide_ids": [s["id"] for s in project["slides"]]}
    )
    saved = core.read_project(project["id"])
    assert saved["job"]["status"] == "failed"
    assert saved["slides"][0]["script"] == "A clear explanation."
    assert saved["slides"][1]["script"] == project["slides"][1]["script"]


def test_whole_deck_generation_replaces_every_script_and_clears_old_audio(client, project, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "private-test-key")
    called = []

    def generate(slide, folder, titles, instructions):
        called.append((slide["number"], instructions))
        return f"A new explanation for slide {slide['number']}."

    monkeypatch.setattr(providers, "generate_script", generate)
    saved = core.read_project(project["id"])
    for slide in saved["slides"]:
        slide.update(audio="old.wav", duration=1, audio_signature="old", audio_source="indic_mio")
    saved["export"] = {"duration": 3, "version": "old"}
    core.save_project(saved)
    response = client.post(
        f"/api/projects/{project['id']}/scripts",
        json={"slide_ids": [slide["id"] for slide in saved["slides"]], "instructions": "Keep it simple."},
    )
    assert response.status_code == 200
    saved = core.read_project(project["id"])
    assert saved["job"]["status"] == "complete"
    assert called == [(1, "Keep it simple."), (2, "Keep it simple."), (3, "Keep it simple.")]
    assert not saved["export"]
    for slide in saved["slides"]:
        assert slide["script"] == f"A new explanation for slide {slide['number']}."
        assert slide["audio"] is None
        assert slide["duration"] is None
        assert slide["audio_signature"] is None
