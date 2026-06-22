# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
block_cipher = None
PROJ = '/Users/jimmy/Downloads/Jimmy/files/vibe coding/nd2-browser'

added_files = [
    ('resources/style.qss', 'resources'),
    ('resources/style_dark.qss', 'resources'),
    # ui/ package — each file explicitly
    (f'{PROJ}/ui/__init__.py', 'ui'),
    (f'{PROJ}/ui/controls.py', 'ui'),
    (f'{PROJ}/ui/main_window.py', 'ui'),
    (f'{PROJ}/ui/settings_dialog.py', 'ui'),
    (f'{PROJ}/ui/sidebar.py', 'ui'),
    (f'{PROJ}/ui/viewer.py', 'ui'),
    (f'{PROJ}/ui/lut_widget.py', 'ui'),
    # core/ package — each file explicitly
    (f'{PROJ}/core/__init__.py', 'core'),
    (f'{PROJ}/core/image_processor.py', 'core'),
    (f'{PROJ}/core/lif_reader.py', 'core'),
    (f'{PROJ}/core/nd2_reader.py', 'core'),
    (f'{PROJ}/core/scanner.py', 'core'),
]

icon = str(Path(PROJ) / 'resources' / 'app_icon.icns')

a = Analysis(
    ['main.py'],
    pathex=[PROJ],
    binaries=[],
    datas=added_files,
    hiddenimports=[
        'nd2', 'numpy', 'cv2', 'PIL', 'PIL.Image',
        'dask', 'dask.array', 'pydantic', 'ome_types',
        'readlif', 'readlif.reader', 
        'bs4', 'soupsieve', 'Foundation', 'AppKit', 'pyobjc-core', 'pyobjc_framework_Cocoa',
        'ui', 'ui.main_window', 'ui.viewer', 'ui.sidebar', 'ui.controls', 'ui.settings_dialog', 'ui.lut_widget',
        'core', 'core.scanner', 'core.nd2_reader', 'core.image_processor', 'core.lif_reader',
        'PySide6.QtCore', 'PySide6.QtGui', 'PySide6.QtWidgets',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'matplotlib', 'scipy', 'pandas', 'IPython', 'jupyter'],
    cipher=block_cipher,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(pyz, a.scripts, [], exclude_binaries=True,
    name='MicroView', debug=False,
    bootloader_ignore_signals=False, strip=False, upx=True,
    console=False, disable_windowed_traceback=False,
    target_arch=None, codesign_identity=None, entitlements_file=None,
    icon=icon)

coll = COLLECT(exe, a.binaries, a.zipfiles, a.datas,
    strip=False, upx=True, upx_exclude=[], name='MicroView')

app = BUNDLE(coll, name='MicroView.app', icon=icon,
    bundle_identifier='com.microview.app',
    info_plist={
        'CFBundleShortVersionString': '1.0.0', 'CFBundleVersion': '1.0.0',
        'NSHighResolutionCapable': True, 'LSMinimumSystemVersion': '11.0',
        'CFBundleDocumentTypes': [{
            'CFBundleTypeExtensions': ['nd2', 'ND2', 'lif', 'LIF'],
            'CFBundleTypeName': 'Microscope Image',
            'CFBundleTypeRole': 'Viewer', 'LSHandlerRank': 'Default',
        }],
    })
