# -*- mode: python ; coding: utf-8 -*-
import os
import sys
from PyInstaller.utils.hooks import collect_submodules, collect_data_files

block_cipher = None

# Collect all submodules and data for complex packages
hidden_imports = collect_submodules('src')
hidden_imports += ['PyQt5.QtCore', 'PyQt5.QtGui', 'PyQt5.QtWidgets', 'open3d', 'pythonnet', 'laspy', 'pyproj', 'numpy', 'scipy', 'ifcopenshell', 'pye57']

# Add src directory to path
sys.path.insert(0, os.path.abspath('src'))

a = Analysis(
    ['launch.py'],
    pathex=[os.getcwd()],
    binaries=[],
    datas=[('src', 'src')],
    hiddenimports=hidden_imports,
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
    name='AV_Snap',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
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
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='AV_Snap',
)
