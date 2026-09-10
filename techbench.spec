# -*- mode: python ; coding: utf-8 -*-
"""One-folder portable build for a USB stick. Run scripts/build_portable.ps1."""

from PyInstaller.utils.hooks import collect_all

datas = [
    ("config/app_config.json", "config"),
    ("config/recommendation_rules.json", "config"),
    ("assets/styles/theme.qss", "assets/styles"),
]
binaries = []
hiddenimports = [
    "wmi",
    "pythoncom",
    "pywintypes",
    "win32api",
    "win32com",
    "win32com.client",
    "pythoncom",
    "cv2",
    "numpy",
    "psutil",
    "reportlab",
    "reportlab.platypus",
    "reportlab.lib.pagesizes",
    "reportlab.pdfbase",
]

for package in ("PySide6", "reportlab", "cv2"):
    pkg_datas, pkg_binaries, pkg_hidden = collect_all(package)
    datas += pkg_datas
    binaries += pkg_binaries
    hiddenimports += pkg_hidden

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtQuickWidgets"],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="TechBench",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="GIT-TechBench-Portable",
)
