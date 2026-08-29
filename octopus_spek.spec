# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置：章鱼频谱查看器 单文件 exe。"""
from PyInstaller.utils.hooks import collect_all

# PyAV 携带 FFmpeg DLL，需要全部收集
av_datas, av_binaries, av_hiddenimports = collect_all("av")

a = Analysis(
    ["run.py"],
    pathex=[],
    binaries=av_binaries,
    datas=[("icon/HMSicon.png", "icon")] + av_datas,
    hiddenimports=av_hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["PyQt5", "PyQt6", "PySide2", "tkinter", "matplotlib"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="章鱼频谱查看器",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    icon="icon/HMSicon.ico",
)
