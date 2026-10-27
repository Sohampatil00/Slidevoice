"""Export native icons from the checked-in 1024px SlideVoice master image."""

from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
MASTER = ROOT / "app/static/branding/slidevoice.png"
ASSETS = ROOT / "desktop/assets"


def main():
    with Image.open(MASTER) as source:
        master = source.convert("RGBA")
    if master.size != (1024, 1024):
        raise ValueError("The SlideVoice master icon must be 1024 × 1024")
    ASSETS.mkdir(parents=True, exist_ok=True)
    master.save(ASSETS / "SlideVoice.icns", format="ICNS")
    master.save(
        ASSETS / "SlideVoice.ico",
        format="ICO",
        sizes=[(size, size) for size in (16, 24, 32, 48, 64, 128, 256)],
    )
    (ROOT / "app/static/branding/slidevoice.ico").write_bytes((ASSETS / "SlideVoice.ico").read_bytes())
    master.resize((32, 32), Image.Resampling.LANCZOS).save(ROOT / "app/static/branding/favicon.png")
    print("Exported macOS ICNS, Windows ICO, and website favicon from the shared master.")


if __name__ == "__main__":
    main()
