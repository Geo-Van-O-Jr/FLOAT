from __future__ import annotations

import importlib.metadata
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    storage_file = ROOT / '.storage-path'
    if storage_file.exists():
        storage = Path(storage_file.read_text(encoding='utf-8-sig').strip())
        os.environ['TEMP'] = os.environ['TMP'] = str(storage / 'tmp')
        os.environ['PYINSTALLER_CONFIG_DIR'] = str(storage / '.cache' / 'pyinstaller')
        os.environ['MPLCONFIGDIR'] = str(storage / '.cache' / 'matplotlib')
    for filename in ('hand_landmarker.task', 'vosk-model-small-pt-0.3/final.mdl', 'whisper-small/model.bin', 'whisper-small/tokenizer.json'):
        if not (ROOT / 'models' / filename).is_file():
            raise FileNotFoundError(f'Modelo ausente: {filename}. Execute scripts/prepare_models.py primeiro.')
    from PySide6.QtWidgets import QApplication
    from float_app.ui import app_icon
    app = QApplication([])
    (ROOT / 'build').mkdir(exist_ok=True)
    app_icon().pixmap(64, 64).save(str(ROOT / 'build' / 'float.ico'), 'ICO')
    subprocess.run([sys.executable, '-m', 'PyInstaller', '--noconfirm', str(ROOT / 'FLOAT.spec')], cwd=ROOT, check=True)
    destination = ROOT / 'dist' / 'FLOAT'
    shutil.copytree(ROOT / 'models', destination / 'models', dirs_exist_ok=True, ignore=shutil.ignore_patterns('.cache'))
    for name in ('README.md', 'THIRD_PARTY_NOTICES.md', 'VALIDATION.md'):
        shutil.copy2(ROOT / name, destination / name)
    licenses = destination / 'licenses'
    packages = []
    for distribution in importlib.metadata.distributions():
        name = distribution.metadata['Name']
        packages.append({'name': name, 'version': distribution.version})
        for file in distribution.files or []:
            if any(part.lower().startswith(('license', 'copying', 'notice')) for part in Path(str(file)).parts):
                original = Path(distribution.locate_file(file))
                if original.is_file():
                    target = licenses / name / str(file).replace('/', '_').replace('\\', '_')
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(original, target)
    (destination / 'dependencies.json').write_text(json.dumps(sorted(packages, key=lambda p: p['name']), indent=2), encoding='utf-8')
    print(f'Pronto: {destination / "FLOAT.exe"}', flush=True)


if __name__ == '__main__':
    main()

