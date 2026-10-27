from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]


def test_master_icon_is_high_resolution_with_transparent_padding():
    with Image.open(ROOT / "app/static/branding/slidevoice.png") as icon:
        assert icon.size == (1024, 1024)
        assert icon.mode == "RGBA"
        assert icon.getpixel((0, 0))[3] == 0
        assert icon.getpixel((512, 512))[3] == 255


def test_windows_icon_contains_shell_and_high_dpi_sizes():
    path = ROOT / "desktop/assets/SlideVoice.ico"
    with Image.open(path) as icon:
        assert icon.format == "ICO"
        assert {(16, 16), (32, 32), (48, 48), (256, 256)} <= icon.ico.sizes()
    assert path.read_bytes() == (ROOT / "app/static/branding/slidevoice.ico").read_bytes()


def test_macos_icon_contains_retina_size_and_matches_master():
    with Image.open(ROOT / "desktop/assets/SlideVoice.icns") as icon:
        assert icon.format == "ICNS"
        assert icon.size == (1024, 1024)
        with Image.open(ROOT / "app/static/branding/slidevoice.png") as master:
            assert icon.convert("RGBA").tobytes() == master.convert("RGBA").tobytes()
