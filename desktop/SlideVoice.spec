# Native OS build only. Both platforms bundle the same app and branding assets.
import sys
import tomllib
from pathlib import Path

root = Path(SPECPATH).parent
resources = root / '.desktop-build/resources'
version = tomllib.loads((root / 'pyproject.toml').read_text())['project']['version']
a = Analysis([str(root / 'desktop/entry.py')], pathex=[str(root)],
             binaries=[], datas=[(str(root / 'app/static'), 'app/static'),
                                  (str(resources), 'desktop_resources')],
             hiddenimports=['app.main', 'app.lux_bootstrap', 'uvicorn.logging',
                            'uvicorn.loops.auto', 'uvicorn.protocols.http.auto',
                            'uvicorn.protocols.websockets.auto', 'uvicorn.lifespan.on'],
             excludes=['torch', 'torchaudio', 'transformers', 'PyQt5', 'PyQt6', 'PySide6'],
             noarchive=False)
pyz = PYZ(a.pure)
windows = {'icon': str(root / 'desktop/assets/SlideVoice.ico'),
           'version': str(root / '.desktop-build/windows-version.txt')} if sys.platform == 'win32' else {}
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='SlideVoice',
          debug=False, strip=False, upx=False, console=False, **windows)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='SlideVoice')
if sys.platform == 'darwin':
    app = BUNDLE(coll, name='SlideVoice.app', bundle_identifier='org.slidevoice.desktop',
                 icon=str(root / 'desktop/assets/SlideVoice.icns'),
                 version=version,
                 info_plist={'CFBundleDisplayName': 'SlideVoice',
                             'CFBundleShortVersionString': version,
                             'CFBundleVersion': version,
                             'NSHighResolutionCapable': True,
                             'NSAppTransportSecurity': {'NSAllowsLocalNetworking': True}})
