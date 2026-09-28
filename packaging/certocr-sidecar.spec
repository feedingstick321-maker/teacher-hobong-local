from pathlib import Path
from PyInstaller.utils.hooks import collect_all

ROOT = Path(SPECPATH).parent.parent
rapid_datas, rapid_binaries, rapid_hidden = collect_all("rapidocr")

analysis = Analysis(
    [str(ROOT / "scripts" / "certocr_sidecar.py")],
    pathex=[str(ROOT)],
    binaries=rapid_binaries,
    datas=rapid_datas + [
        (str(ROOT / "data" / "models"), "data/models"),
        (str(ROOT / "data" / "dicts"), "data/dicts"),
    ],
    hiddenimports=rapid_hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["fastapi", "uvicorn"],
    noarchive=False,
    optimize=1,
)

pyz = PYZ(analysis.pure)

exe = EXE(
    pyz,
    analysis.scripts,
    analysis.binaries,
    analysis.datas,
    [],
    name="certocr-sidecar",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
