# Build on Windows: pyinstaller --clean --noconfirm acc_telemetry.spec
# The build is only successful if the actual frozen exe opens and closes its UI.
from pathlib import Path
import json
import os
import subprocess
import tempfile

root = Path(SPECPATH)
a = Analysis([str(root / 'launcher.py')], pathex=[str(root)],
             binaries=[], datas=[(str(root / 'tracks'), 'tracks'),
                                 (str(root / 'THIRD_PARTY_NOTICES.md'), '.')],
             hiddenimports=['acc_telemetry.app'], hookspath=[], hooksconfig={}, runtime_hooks=[], excludes=[], noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name='acc_telemetry',
          debug=False, bootloader_ignore_signals=False, strip=False, upx=False,
          console=False, disable_windowed_traceback=False)

if os.name == 'nt':
    with tempfile.TemporaryDirectory(prefix='acc-frozen-test-') as folder:
        test_dir = Path(folder)
        config = test_dir / 'broadcasting.json'
        config.write_text(json.dumps({'updListenerPort': 9000, 'connectionPassword': ''}), encoding='utf-8')
        env = dict(os.environ, LOCALAPPDATA=str(test_dir))
        # Neither test runs from the source directory: imports/resources must be bundled.
        default_dir = test_dir / 'Documents' / 'Assetto Corsa Competizione' / 'Config'
        default_dir.mkdir(parents=True)
        (default_dir / 'broadcasting.json').write_text('{"updListenerPort":0}', encoding='utf-8')
        env['USERPROFILE'] = env['HOME'] = str(test_dir)
        for mode in ('demo', 'live', 'disabled-default-config'):
            report = test_dir / (mode + '.json')
            command = [str(Path(DISTPATH) / 'acc_telemetry.exe'), '--smoke-test',
                       '--smoke-report', str(report)]
            if mode != 'disabled-default-config':
                command += ['--config', str(config)]
            if mode == 'demo':
                command.append('--demo')
            process = subprocess.Popen(command, cwd=test_dir, env=env)
            try:
                code = process.wait(timeout=45)
            except subprocess.TimeoutExpired:
                subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], check=False)
                raise RuntimeError('Frozen ' + mode + ' smoke test timed out')
            result = json.loads(report.read_text(encoding='utf-8')) if report.is_file() else {}
            if code != 0 or result.get('ok') is not True:
                log = test_dir / 'ACCTelemetry' / 'logs' / 'startup.log'
                if log.is_file():
                    print(log.read_text(encoding='utf-8')[-6000:])
                raise RuntimeError(f'Frozen {mode} smoke test failed: exit={code}, report={result}')
            print('FROZEN UI SMOKE TEST PASSED:', mode, json.dumps(result))
