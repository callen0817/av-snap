# Build on the target OS: python -m PyInstaller --noconfirm AV_Snap.spec
import os
from PyInstaller.utils.hooks import collect_all, collect_submodules

datas=[('logos','logos')]
binaries=[]
hiddenimports=collect_submodules('src')
for package in ['open3d','ifcopenshell','pye57','pyqtgraph','OpenGL']:
    data, binary, hidden = collect_all(package, filter_submodules=lambda name: not any(part in name.split(".") for part in ["examples", "tests", "ml"]))
    datas += data
    binaries += binary
    hiddenimports += hidden

a=Analysis(['launch.py'],pathex=['.'],binaries=binaries,datas=datas,hiddenimports=hiddenimports,
    excludes=['torch','tensorflow','tensorboard','bpy','PySide6','PyQt6','pytest','IPython','jupyterlab','notebook'],noarchive=False)
pyz=PYZ(a.pure)
exe=EXE(pyz,a.scripts,[],exclude_binaries=True,name='AV_Snap',debug=False,icon='logos/av_snap-01.png',
    bootloader_ignore_signals=False,strip=False,upx=False,console=True,disable_windowed_traceback=False)
coll=COLLECT(exe,a.binaries,a.datas,strip=False,upx=False,name='AV_Snap')
