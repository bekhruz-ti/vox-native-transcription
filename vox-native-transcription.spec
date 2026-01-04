# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file for Vox Native Transcription.

Build with: pyinstaller vox-native-transcription.spec
Output will be in dist/Vox/
"""

import os

# Read version from VERSION file
with open('VERSION', 'r') as f:
    version = f.read().strip()

block_cipher = None

# Data files to include
datas = [
    ('src/ui/resources/style.qss', 'src/ui/resources'),
]

# Hidden imports that PyInstaller might miss
hiddenimports = [
    # Audio libraries
    'webrtcvad',
    'sounddevice',
    '_sounddevice_data',
    
    # Keyboard/mouse hooks
    'keyboard',
    'pynput',
    'pynput.keyboard',
    'pynput.keyboard._win32',
    'pynput.mouse',
    'pynput.mouse._win32',
    
    # Windows automation
    'uiautomation',
    'comtypes',
    'comtypes.client',
    
    # PySide6 modules
    'PySide6.QtCore',
    'PySide6.QtGui',
    'PySide6.QtWidgets',
    
    # Network
    'websockets',
    'websockets.client',
    
    # OpenAI/ElevenLabs
    'openai',
    'elevenlabs',
    'httpx',
    
    # Standard library modules sometimes missed
    'json',
    'asyncio',
    'threading',
    'queue',
]

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Exclude unnecessary modules to reduce size
        'tkinter',
        'matplotlib',
        'PIL',
        'scipy',
    ],
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
    name='Vox',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # No console window (GUI app)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # icon='src/ui/resources/icons/app.ico',  # Uncomment when you add an icon
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='Vox',
)
