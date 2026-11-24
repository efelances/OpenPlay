# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
from PyInstaller.utils.hooks import collect_all

ROOT = Path(SPECPATH).resolve().parent

mp_datas, mp_bins, mp_hidden = collect_all("mediapipe")
wv_datas, wv_bins, wv_hidden = collect_all("webview")

datas = [
    (str(ROOT / "openplay" / "web"), "openplay/web"),
    (str(ROOT / "openplay" / "locales"), "openplay/locales"),
    (str(ROOT / "openplay" / "models" / "face_landmarker.task"), "openplay/models"),
] + mp_datas + wv_datas

binaries = mp_bins + wv_bins
hiddenimports = ["win32com", "win32com.client", "pythoncom"] + mp_hidden + wv_hidden

a = Analysis(
    [str(ROOT / "scripts" / "pyi_entry.py")],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="OpenPlay Access",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    icon=str(ROOT / "assets" / "icon.ico"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="OpenPlay Access",
)
