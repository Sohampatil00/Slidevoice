"""Run with the build virtualenv on the target OS; never packages checkout data/secrets."""

import json
import os
import shutil
import subprocess
import sys
import tomllib
from importlib import metadata
from pathlib import Path
from urllib.request import urlretrieve

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / ".desktop-build"
RESOURCES = BUILD / "resources"


def run(*command):
    subprocess.run(list(map(str, command)), cwd=ROOT, check=True)


def main():
    import imageio_ffmpeg

    run(sys.executable, ROOT / "scripts/build_icons.py")
    version = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
    version_tuple = tuple(int(part) for part in version.split(".")) + (0,)
    RESOURCES.mkdir(parents=True, exist_ok=True)
    (BUILD / "windows-version.txt").write_text(f"""VSVersionInfo(
      ffi=FixedFileInfo(filevers={version_tuple}, prodvers={version_tuple}, mask=0x3f,
                       flags=0, OS=0x40004, fileType=0x1, subtype=0, date=(0, 0)),
      kids=[StringFileInfo([StringTable('040904B0',[
        StringStruct('CompanyName','SlideVoice'),
        StringStruct('FileDescription','SlideVoice presentation studio'),
        StringStruct('FileVersion','{version}'),
        StringStruct('ProductName','SlideVoice'),
        StringStruct('ProductVersion','{version}'),
        StringStruct('OriginalFilename','SlideVoice.exe')])]),
        VarFileInfo([VarStruct('Translation',[1033,1200])])])""")
    (RESOURCES / "desktop-release.json").write_text(
        json.dumps(
            {
                "name": "SlideVoice",
                "version": version,
                "platform": sys.platform,
                "script_provider": "gemini",
                "narration_provider": "lux_tts",
                "presentation_mode": True,
            },
            indent=2,
        )
    )
    binary = RESOURCES / "bin"
    binary.mkdir(exist_ok=True)
    uv = shutil.which("uv", path=str(Path(sys.executable).parent) + os.pathsep + os.environ.get("PATH", ""))
    if not uv:
        raise RuntimeError("Install requirements-build.txt first")
    shutil.copy2(uv, binary / ("uv.exe" if sys.platform == "win32" else "uv"))
    shutil.copy2(
        imageio_ffmpeg.get_ffmpeg_exe(), binary / ("ffmpeg.exe" if sys.platform == "win32" else "ffmpeg")
    )
    worker = RESOURCES / "worker" / "app"
    worker.mkdir(parents=True, exist_ok=True)
    for filename in ("__init__.py", "core.py", "lux_server.py"):
        shutil.copy2(ROOT / "app" / filename, worker / filename)
    wheels = RESOURCES / "wheels"
    wheels.mkdir(exist_ok=True)
    source_manifest = wheels / "sources.json"
    sources = json.loads(source_manifest.read_text()) if source_manifest.exists() else {}
    lines = []
    for line in (ROOT / "requirements-lux.txt").read_text().splitlines():
        if " @ git+" in line:
            package = line.split(" @ ")[0]
            matches = list(wheels.glob(package + "-*.whl"))
            if not matches or sources.get(package) != line:
                for old in matches:
                    old.unlink()
                run(sys.executable, "-m", "pip", "wheel", "--no-deps", "--wheel-dir", wheels, line)
                matches = list(wheels.glob(package + "-*.whl"))
                sources[package] = line
            line = "./wheels/" + matches[0].name
        lines.append(line)
    source_manifest.write_text(json.dumps(sources, indent=2))
    (RESOURCES / "requirements-lux.txt").write_text("\n".join(lines) + "\n")
    compile_command = [
        uv,
        "pip",
        "compile",
        "requirements-lux.txt",
        "--python-version",
        "3.12",
        "--output-file",
        "requirements-lux.lock",
    ]
    if sys.platform == "win32":
        compile_command.extend(["--torch-backend", "cpu"])
        urlretrieve(
            "https://go.microsoft.com/fwlink/p/?LinkId=2124703", BUILD / "MicrosoftEdgeWebview2Setup.exe"
        )
    subprocess.run(compile_command, cwd=RESOURCES, check=True)
    (RESOURCES / "requirements-lux.txt").write_bytes((RESOURCES / "requirements-lux.lock").read_bytes())
    inventory = [
        {
            "name": dist.metadata["Name"],
            "version": dist.version,
            "license": dist.metadata.get("License-Expression")
            or dist.metadata.get("License", "See upstream"),
        }
        for dist in metadata.distributions()
    ]
    (RESOURCES / "dependency-inventory.json").write_text(json.dumps(inventory, indent=2))
    notices = RESOURCES / "licenses"
    notices.mkdir(exist_ok=True)
    for dist in metadata.distributions():
        for source in dist.files or []:
            if any(
                part.lower() in {"licenses", "license", "license.txt", "copying", "notice"}
                for part in source.parts
            ):
                original = Path(dist.locate_file(source))
                if original.is_file():
                    target = notices / dist.metadata["Name"] / str(source).replace("../", "")
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(original, target)
    run(sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", ROOT / "desktop/SlideVoice.spec")
    if sys.platform == "darwin":
        dmg = ROOT / "dist/SlideVoice-macOS-arm64.dmg"
        dmg.unlink(missing_ok=True)
        stage = BUILD / "dmg"
        stage.mkdir(exist_ok=True)
        target = stage / "SlideVoice.app"
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(ROOT / "dist/SlideVoice.app", target, symlinks=True)
        applications = stage / "Applications"
        if not applications.is_symlink():
            applications.symlink_to("/Applications")
        run("hdiutil", "create", "-volname", "SlideVoice", "-srcfolder", stage, "-ov", "-format", "UDZO", dmg)
    else:
        shutil.make_archive(str(ROOT / "dist/SlideVoice-Windows-x64"), "zip", ROOT / "dist", "SlideVoice")
        compiler = shutil.which("iscc")
        if not compiler:
            candidate = (
                Path(os.getenv("ProgramFiles(x86)", "C:/Program Files (x86)")) / "Inno Setup 6/ISCC.exe"
            )
            compiler = str(candidate) if candidate.is_file() else None
        if not compiler:
            raise RuntimeError("Install Inno Setup 6 to produce the Windows installer.")
        run(compiler, f"/DAppVersion={version}", ROOT / "desktop/windows.iss")


if __name__ == "__main__":
    main()
