from pathlib import Path
from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_dynamic_libs

root = Path(SPECPATH)
datas, binaries, hiddenimports = [], [], []
for package in ('mediapipe', 'vosk'):
    package_datas, package_binaries, package_hidden = collect_all(package)
    datas += package_datas
    binaries += package_binaries
    hiddenimports += package_hidden
datas += collect_data_files('faster_whisper')
binaries += collect_dynamic_libs('ctranslate2')

a = Analysis(
    [str(root / 'run_float.py')], pathex=[str(root / 'src')],
    binaries=binaries, datas=datas, hiddenimports=hiddenimports,
    hookspath=[str(root / 'hooks')],
    excludes=['tkinter', 'pytest', 'IPython', 'notebook', 'torch', 'tensorflow', 'jax', 'matplotlib.tests'],
    hooksconfig={'matplotlib': {'backends': ['Agg']}},
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='FLOAT', debug=False,
          bootloader_ignore_signals=False, strip=False, upx=False, console=False,
          icon=str(root / 'build' / 'float.ico'))
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='FLOAT')

