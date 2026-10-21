import io
import wave

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app import core
from app.main import app


@pytest.fixture(autouse=True)
def isolated_data(tmp_path, monkeypatch):
    monkeypatch.setattr(core, "DATA", tmp_path / "data")
    core.DATA.mkdir()
    core.locks.clear()
    for key in (
        "ANTHROPIC_API_KEY",
        "INDIC_MIO_API_KEY",
        "INDIC_MIO_PRESET_ID",
        "INDIC_MIO_BASE_URL",
        "INDIC_MIO_MODEL",
        "INDIC_MIO_CODEC_MODEL",
    ):
        monkeypatch.delenv(key, raising=False)


@pytest.fixture
def client():
    with TestClient(app, base_url="http://127.0.0.1", headers={"X-SlideVoice": "local"}) as session:
        yield session


@pytest.fixture
def project(client):
    response = client.post("/api/demo")
    assert response.status_code == 200
    return response.json()


@pytest.fixture
def wav_bytes():
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(48000)
        audio.writeframes(b"\x00\x00" * 48000)
    return buffer.getvalue()


@pytest.fixture
def png_bytes():
    buffer = io.BytesIO()
    Image.new("RGB", (640, 360), "#b5c5a0").save(buffer, format="PNG")
    return buffer.getvalue()


@pytest.fixture
def reference_bytes():
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(48000)
        audio.writeframes(b"\x00\x00" * 48000 * 4)
    return buffer.getvalue()
