# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path; block_cipher = None
added_files = [
    ('resources/style_dark.qss', 'resources'),
    ('resources/app_icon.ico', 'resources'),
    ('ui/__init__.py', 'ui'), ('ui/controls.py', 'ui'), ('ui/main_window.py', 'ui'),
    ('ui/settings_dialog.py', 'ui'), ('ui/sidebar.py', 'ui'), ('ui/viewer.py', 'ui'),
    ('ui/lut_widget.py', 'ui'),
    ('core/__init__.py', 'core'), ('core/image_processor.py', 'core'),
    ('core/lif_reader.py', 'core'), ('core/nd2_reader.py', 'core'), ('core/scanner.py', 'core'),
]
icon = str(Path('resources') / 'app_icon.ico')
a = Analysis(['main.py'], pathex=['.'], binaries=[], datas=added_files,
    hiddenimports=['nd2','numpy','cv2','PIL','PIL.Image','dask','dask.array','pydantic','ome_types',
    'readlif','readlif.reader','bs4','soupsieve','ui','ui.main_window','ui.viewer','ui.sidebar',
    'ui.controls','ui.settings_dialog','ui.lut_widget','core','core.scanner','core.nd2_reader',
    'core.image_processor','core.lif_reader','PySide6.QtCore','PySide6.QtGui','PySide6.QtWidgets',
    'PySide6.QtNetwork'],
    hookspath=[],hooksconfig={},runtime_hooks=[],
    excludes=['tkinter','matplotlib','scipy','pandas','IPython','jupyter',
    'Foundation','AppKit','pyobjc-core','pyobjc_framework_Cocoa','objc'],cipher=block_cipher)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe = EXE(pyz,a.scripts,[],exclude_binaries=True,name='MicroView',debug=False,
    bootloader_ignore_signals=False,strip=False,upx=True,console=False,icon=icon)
coll = COLLECT(exe,a.binaries,a.zipfiles,a.datas,strip=False,upx=True,upx_exclude=[],name='MicroView')
