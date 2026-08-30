# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for PDFSearchViewer (Windows GUI exe)."""

from pathlib import Path

from PyInstaller.utils.hooks import collect_all

ROOT = Path(SPECPATH).resolve()
SRC = ROOT / "src"

datas = []
binaries = []
hiddenimports = [
    "pymupdf",
    "fitz",
]

# PyMuPDF ships native libs + resources; collect them once (do not also collect fitz).
_pymupdf = collect_all("pymupdf")
datas += _pymupdf[0]
binaries += _pymupdf[1]
hiddenimports += _pymupdf[2]

a = Analysis(
    [str(SRC / "pdfsearchviewer" / "__main__.py")],
    pathex=[str(SRC)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "pytest",
        "tkinter",
        "matplotlib",
        "numpy",
        "scipy",
        "pandas",
    ],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="PDFSearchViewer",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # GUI app: no console window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
