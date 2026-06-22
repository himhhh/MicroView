# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
block_cipher = None
PROJ = '.'
# On Windows the project folder is just the current directory
# (the script is run from the project root)

import sys, os
if getattr(sys, 'frozen', False):
    PROJECT_ROOT = Path(sys._MEIPASS)
else:
    PROJECT_ROOT = Path(__file__).resolve().parent
PROJ = str(PROJECT_ROOT)

added_files = [
    ('resources/style.qss', 'resources'),
    ('resources/style_dark.qss', 'resources'),
    (f'{PROJ}/ui/__init__.py', 'ui'),
    (f'{PROJ}/ui/controls.py', 'ui'),
    (f'{PROJ}/ui/main_window.py', 'ui'),
    (f'{PROJ}/ui/settings_dialog.py', 'ui'),
    (f'{PROJ}/ui/sidebar.py', 'ui'),
    (f'{PROJ}/ui/viewer.py', 'ui'),
    (f'{PROJ}/ui/lut_widget.py', 'ui'),
    (f'{PROJ}/core/__init__.py', 'core'),
    (f'{PROJ}/core/image_processor.py', 'core'),
    (f'{PROJ}/core/lif_reader.py', 'core'),
    (f'{PROJ}/core/nd2_reader.py', 'core'),
    (f'{PROJ}/core/scanner.py', 'core'),
]

icon_path = str(Path(PROJ) / 'resources' / 'app_icon.ico')
icon = icon_path if os.path.exists(icon_path) else None

a = Analysis(
    ['main.py'],
    pathex=[PROJ],
    binaries=[],
    datas=added_files,
    hiddenimports=[
        'nd2', 'numpy', 'cv2', 'PIL', 'PIL.Image',
        'dask', 'dask.array', 'pydantic', 'ome_types',
        'readlif', 'readlif.reader',
        'bs4', 'soupsieve',
        'ui', 'ui.main_window', 'ui.viewer', 'ui.sidebar', 'ui.controls',
        'ui.settings_dialog', 'ui.lut_widget',
        'core', 'core.scanner', 'core.nd2_reader', 'core.image_processor',
        'core.lif_reader',
        'PySide6.QtCore', 'PySide6.QtGui', 'PySide6.QtWidgets',
        'PySide6.QtNetwork',  # for QLocalServer (single-instance)
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'matplotlib', 'scipy', 'pandas', 'IPython', 'jupyter'],
    cipher=block_cipher,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name='MicroView',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon,
)

coll = COLLECT(
    exe, a.binaries, a.zipfiles, a.datas,
    strip=False, upx=True, upx_exclude=[],
    name='MicroView',
)
