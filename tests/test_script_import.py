import json

import httpx
import pytest

from app import core, providers, script_import
from app.core import WorkflowError


def endpoint(project, action):
    return f"/api/projects/{project['id']}/scripts/{action}"


def labelled(texts):
    return "\n\n".join(f"Slide {number}\n{text}" for number, text in enumerate(texts, 1))


def test_labelled_preview_is_local_and_does_not_save(client, project, monkeypatch):
    def unexpected(*args):
        pytest.fail("Labelled scripts must not call Claude")

    monkeypatch.setattr(providers, "distribute_script", unexpected)
    source = "# Slide 1\r\nIntroduction.\r\n\r\n[Slide 2]\r\nSecond point.\r\n\r\n**Slide 3:**\r\nClosing."
    response = client.post(endpoint(project, "preview"), json={"script": source, "method": "claude"})
    assert response.status_code == 200, response.text
    preview = response.json()
    assert preview["method"] == "headings"
    assert [slide["script"] for slide in preview["slides"]] == ["Introduction.", "Second point.", "Closing."]
    assert core.read_project(project["id"])["updated_at"] == preview["revision"]
    assert core.read_project(project["id"])["slides"][0]["script"] == project["slides"][0]["script"]


@pytest.mark.parametrize(
    "script",
    [
        "Unassigned preamble\nSlide 1\nA\nSlide 2\nB\nSlide 3\nC",
        "Slide 1\nA\nSlide 3\nC",
        "Slide 1\nA\nSlide 1\nB\nSlide 3\nC",
        "Slide 2\nB\nSlide 1\nA\nSlide 3\nC",
        "Slide 1\nA\nSlide 2\nB\nSlide 4\nD",
        "   ",
    ],
)
def test_invalid_labelled_script_leaves_project_unchanged(client, project, script):
    response = client.post(endpoint(project, "preview"), json={"script": script})
    assert response.status_code == 400
    assert core.read_project(project["id"])["updated_at"] == project["updated_at"]


def test_unlabelled_script_requires_explicit_claude_method_and_key(client, project, monkeypatch):
    called = []
    with monkeypatch.context() as patch:
        patch.setattr(providers, "distribute_script", lambda *args: called.append(True))
        response = client.post(endpoint(project, "preview"), json={"script": "A. B. C."})
        assert response.status_code == 400
        assert not called
    response = client.post(endpoint(project, "preview"), json={"script": "A. B. C.", "method": "claude"})
    assert response.status_code == 400
    assert "ANTHROPIC_API_KEY" in response.json()["detail"]


def test_single_slide_needs_no_headings_or_ai(client):
    current = core.new_project("One slide")
    current["slides"] = [{"id": "slide-001", "number": 1, "title": "One", "script": ""}]
    core.save_project(current)
    response = client.post(endpoint(current, "preview"), json={"script": "The whole explanation."})
    assert response.status_code == 200
    assert response.json()["slides"][0]["script"] == "The whole explanation."


def test_claude_matching_preserves_source_and_includes_slide_context(client, project, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "mock-key")
    requests = []
    real_client = httpx.Client

    def respond(request):
        requests.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "stop_reason": "end_turn",
                "content": [
                    {"type": "text", "text": '```json\n{"boundaries": [1, 3, 4]}\n```'},
                ],
            },
        )

    monkeypatch.setattr(
        providers.httpx, "Client", lambda **kwargs: real_client(transport=httpx.MockTransport(respond))
    )
    source = "First sentence.\n\nNext part!  Still the second slide.\nThe conclusion."
    response = client.post(endpoint(project, "preview"), json={"script": source, "method": "claude"})
    assert response.status_code == 200, response.text
    assert response.json()["method"] == "claude"
    sections = [entry["script"] for entry in response.json()["slides"]]
    assert sections == ["First sentence.", "Next part!  Still the second slide.", "The conclusion."]
    assert source.split() == " ".join(sections).split()
    content = requests[0]["messages"][0]["content"]
    assert len([block for block in content if block["type"] == "image"]) == 3
    assert "speaker_notes" in content[0]["text"]
    assert "script_units" in content[-1]["text"]
    assert core.read_project(project["id"])["updated_at"] == project["updated_at"]


@pytest.mark.parametrize(
    "boundaries", [[1, 2], [1, 2, 2], [2, 1, 3], [1, 2, 4], [True, 2, 3], [1, "2", 3], None]
)
def test_ai_cannot_drop_duplicate_or_reorder_source(boundaries):
    with pytest.raises(WorkflowError):
        script_import.sections_from_boundaries(["A. ", "B. ", "C."], boundaries, 3)


@pytest.mark.parametrize(
    "source",
    [
        "A.  B!\nC?\n\nD",
        "An unpunctuated\n\nparagraph\n\nanother one",
        "No sentence boundary",
        "First.\n\n\n\nSecond.\n\nThird.",
        "Hello! नमस्कार. And a last sentence.",
    ],
)
def test_unit_splitting_keeps_every_character(source):
    assert "".join(script_import.script_units(source)) == source


@pytest.mark.parametrize(
    "payload",
    [
        {"content": [{"type": "text", "text": "Not JSON"}]},
        {"content": [{"type": "text", "text": "[]"}]},
        {"stop_reason": "max_tokens", "content": []},
        {"content": [{"type": "text", "text": '{"boundaries":[1,2,2]}'}]},
    ],
)
def test_bad_claude_response_is_actionable(client, project, monkeypatch, payload):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "mock-key")
    real_client = httpx.Client
    monkeypatch.setattr(
        providers.httpx,
        "Client",
        lambda **kwargs: real_client(
            transport=httpx.MockTransport(lambda request: httpx.Response(200, json=payload))
        ),
    )
    response = client.post(endpoint(project, "preview"), json={"script": "A. B. C.", "method": "claude"})
    assert response.status_code == 400
    assert core.read_project(project["id"])["updated_at"] == project["updated_at"]


def test_apply_is_atomic_and_only_invalidates_changed_audio(client, project, wav_bytes):
    current = core.read_project(project["id"])
    folder = core.project_dir(project["id"])
    for slide in current["slides"]:
        filename = f"{slide['id']}.wav"
        (folder / filename).write_bytes(wav_bytes)
        slide.update(audio=filename, duration=1, audio_source="uploaded", audio_signature="cached")
    current["export"] = {"version": "old", "duration": 3}
    (folder / "video.mp4").write_bytes(b"old video")
    (folder / "timings.json").write_text("{}")
    core.save_project(current)
    scripts = [current["slides"][0]["script"], "New second slide.", "New ending."]
    preview = client.post(endpoint(project, "preview"), json={"script": labelled(scripts)}).json()
    response = client.post(
        endpoint(project, "apply"), json={"revision": preview["revision"], "slides": preview["slides"]}
    )
    assert response.status_code == 200, response.text
    result = response.json()
    assert [slide["script"] for slide in result["slides"]] == scripts
    assert result["slides"][0]["audio_ready"] is True
    assert all(slide["audio"] is None for slide in result["slides"][1:])
    assert result["export"] is None
    assert not (folder / "video.mp4").exists()
    assert not (folder / "timings.json").exists()


def test_unchanged_import_keeps_export_and_revision(client, project):
    current = core.read_project(project["id"])
    current["export"] = {"version": "saved", "duration": 1}
    core.save_project(current)
    preview = client.post(
        endpoint(project, "preview"), json={"script": labelled([s["script"] for s in current["slides"]])}
    ).json()
    response = client.post(endpoint(project, "apply"), json=preview)
    assert response.status_code == 200
    assert response.json()["export"]["version"] == "saved"
    assert response.json()["updated_at"] == current["updated_at"]


@pytest.mark.parametrize("invalid", ["duplicate", "missing", "unknown", "blank", "oversize"])
def test_invalid_apply_cannot_partially_save(client, project, invalid):
    preview = client.post(endpoint(project, "preview"), json={"script": labelled(["A", "B", "C"])}).json()
    if invalid == "duplicate":
        preview["slides"][1]["id"] = preview["slides"][0]["id"]
    elif invalid == "missing":
        preview["slides"].pop()
    elif invalid == "unknown":
        preview["slides"][2]["id"] = "nonexistent"
    elif invalid == "blank":
        preview["slides"][2]["script"] = "   "
    else:
        preview["slides"][2]["script"] = "x" * 12001
    response = client.post(endpoint(project, "apply"), json=preview)
    assert response.status_code in {400, 422}
    assert core.read_project(project["id"])["updated_at"] == project["updated_at"]


@pytest.mark.parametrize("clock_offset", [0, -60], ids=["same-clock-tick", "clock-moved-back"])
def test_stale_preview_rejected(client, project, monkeypatch, clock_offset):
    from datetime import datetime, timedelta

    fixed = (datetime.fromisoformat(project["updated_at"]) + timedelta(seconds=clock_offset)).isoformat()
    monkeypatch.setattr(core, "now", lambda: fixed)
    preview = client.post(endpoint(project, "preview"), json={"script": labelled(["A", "B", "C"])}).json()
    client.patch(
        f"/api/projects/{project['id']}/slides/slide-001",
        json={"title": "New title", "script": "Latest edit"},
    )
    response = client.post(endpoint(project, "apply"), json=preview)
    assert response.status_code == 409
    assert core.read_project(project["id"])["slides"][0]["script"] == "Latest edit"


def test_import_obeys_job_lock(client, project):
    lock = core.project_lock(project["id"])
    lock.acquire()
    try:
        for action in ["preview", "apply"]:
            body = (
                {"script": labelled(["A", "B", "C"])}
                if action == "preview"
                else {
                    "revision": project["updated_at"],
                    "slides": [{"id": slide["id"], "script": "X"} for slide in project["slides"]],
                }
            )
            assert client.post(endpoint(project, action), json=body).status_code == 409
    finally:
        lock.release()


def test_blank_matches_require_editing_before_apply(client, project, monkeypatch):
    monkeypatch.setattr(providers, "distribute_script", lambda *args: ["A", "", "C"])
    response = client.post(endpoint(project, "preview"), json={"script": "A. C.", "method": "claude"})
    assert response.status_code == 200
    assert response.json()["slides"][1]["script"] == ""
    assert client.post(endpoint(project, "apply"), json=response.json()).status_code == 422


@pytest.mark.parametrize(
    "script",
    ["x" * 120001, labelled(["x" * 12001, "B", "C"])],
    ids=["oversized-full-script", "oversized-slide-script"],
)
def test_import_size_limits(client, project, script):
    assert client.post(endpoint(project, "preview"), json={"script": script}).status_code in {400, 422}


def test_imported_sections_feed_bulk_narration(client, project, monkeypatch, wav_bytes):
    scripts = ["This is the opening.", "This explains the next slide.", "These are the closing words."]
    preview = client.post(endpoint(project, "preview"), json={"script": labelled(scripts)}).json()
    assert client.post(endpoint(project, "apply"), json=preview).status_code == 200
    spoken = []

    def synthesize(script, destination, provider, voice_id, speed, reference_audio=None):
        spoken.append(script)
        destination.write_bytes(wav_bytes)
        return 1.0

    monkeypatch.setattr(providers, "synthesize", synthesize)
    response = client.post(
        f"/api/projects/{project['id']}/audio",
        json={
            "provider": "indic_mio",
            "voice_id": "test",
            "consent": True,
            "use_reference": False,
        },
    )
    assert response.status_code == 200
    assert spoken == scripts
    current = client.get(f"/api/projects/{project['id']}").json()
    assert current["job"]["status"] == "complete"
    assert all(slide["audio_ready"] for slide in current["slides"])
