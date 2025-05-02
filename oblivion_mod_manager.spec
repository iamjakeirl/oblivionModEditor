# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['oblivion_mod_manager/main.py'],
    pathex=[],
    binaries=[],
    datas=[('oblivion_mod_manager/data', 'oblivion_mod_manager/data')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'unittest', 'test', 'pydoc', 'doctest'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='OblivionModManager',
    debug=False,
    bootloader_ignore_signals=False,
    strip=True,  # Reduce size
    upx=False,   # Disable UPX for AV-friendliness
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # No console window for GUI
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)