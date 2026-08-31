# PyInstaller spec — one-folder bundle for macOS.
# Run: pyinstaller nextchapter-core.spec --noconfirm

import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_submodules

block_cipher = None
root = Path(SPECPATH)
is_windows = sys.platform.startswith("win")
use_strip = not is_windows

# 显式收集子模块 + uvicorn 关键模块（避免 bootloader 找不到）
hiddenimports = collect_submodules("nextchapter_core")
hiddenimports += [
    "uvicorn",
    "uvicorn.logging",
    "uvicorn.loops",
    "uvicorn.loops.auto",
    "uvicorn.protocols",
    "uvicorn.protocols.http",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.http.h11_impl",
    "uvicorn.lifespan",
    "uvicorn.lifespan.on",
    "uvicorn.lifespan.off",
    "starlette",
    "fastapi",
    "pydantic",
    "httpx",
    "multipart",
    "multipart.multipart",
    "anyio",
    "sniffio",
    "h11",
    "uvloop",
    "email",
    "encodings.utf_8",
    "encodings.utf_8_sig",
    "encodings.gb18030",
    "encodings.gbk",
    "encodings.cp936",
    "encodings.latin_1",
]

a = Analysis(
    [str(root / "nextchapter_core" / "__main__.py")],
    pathex=[str(root)],
    binaries=[],
    datas=[],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="nextchapter-core",
    debug=False,
    bootloader_ignore_signals=False,
    strip=use_strip,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=use_strip,
    upx=False,
    upx_exclude=[],
    name="nextchapter-core",
)
