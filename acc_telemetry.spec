# Build on Windows: pyinstaller --clean --noconfirm acc_telemetry.spec
from pathlib import Path
root = Path(SPECPATH)
a = Analysis([str(root / 'acc_telemetry' / 'app.py')], pathex=[str(root)],
             binaries=[], datas=[(str(root / 'tracks'), 'tracks')],
             hiddenimports=[], hookspath=[], hooksconfig={}, runtime_hooks=[], excludes=[], noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name='acc_telemetry',
          debug=False, bootloader_ignore_signals=False, strip=False, upx=False,
          console=False, disable_windowed_traceback=False)
