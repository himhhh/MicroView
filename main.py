#!/usr/bin/env python3
"""
MicroView — Main entry point.

A clean, intuitive Nikon ND2 microscope image browser for macOS.
"""

import sys
import os
import traceback
from pathlib import Path
from datetime import datetime

# ── Early error logging (for debugging Finder-launch crashes) ──
LOG_DIR = Path.home() / "Library" / "Logs" / "MicroView"
LOG_FILE = LOG_DIR / "app.log"


def _setup_logging():
    """Ensure the log directory exists and write a startup marker."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(f"\n{'='*60}\n")
        f.write(f"Startup: {datetime.now().isoformat()}\n")
        f.write(f"Python: {sys.version}\n")
        f.write(f"Executable: {sys.executable}\n")
        f.write(f"argv: {sys.argv}\n")
        f.write(f"cwd: {os.getcwd()}\n")
        if getattr(sys, 'frozen', False):
            f.write(f"MEIPASS: {getattr(sys, '_MEIPASS', 'N/A')}\n")
        f.write(f"PATH: {os.environ.get('PATH', 'N/A')}\n")


def _log_error(msg: str):
    """Write an error message to the log file."""
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        with open(LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(f"ERROR [{datetime.now().isoformat()}]: {msg}\n")
    except Exception:
        pass  # can't even log — nothing we can do


def main():
    try:
        _setup_logging()
    except Exception:
        pass

    try:
        # Add project root to sys.path (dev: source dir, frozen: MEIPASS)
        if getattr(sys, 'frozen', False):
            PROJECT_ROOT = Path(sys._MEIPASS)
        else:
            PROJECT_ROOT = Path(__file__).resolve().parent
        if str(PROJECT_ROOT) not in sys.path:
            sys.path.insert(0, str(PROJECT_ROOT))

        # Pre-import heavy modules so they're available before Qt event loop starts
        _log_error('Pre-importing nd2/dask...')
        try:
            import nd2, dask, dask.array
            _log_error('nd2/dask imported OK')
        except Exception as _e:
            _log_error(f'nd2/dask import warning: {_e}')

        from PySide6.QtWidgets import QApplication
        from PySide6.QtGui import QFont
        from ui.main_window import MainWindow

        app = QApplication(sys.argv)
        app.setApplicationName("MicroView")
        app.setOrganizationName("MicroView")
        app.setApplicationVersion("1.0.0")
        # Window icon (for Windows title bar)
        from PySide6.QtGui import QIcon
        import os as _os
        icon_ok = False
        for ip in [
            _os.path.join(PROJECT_ROOT, 'resources', 'app_icon.ico'),
            _os.path.join(str(PROJECT_ROOT), 'resources', 'app_icon.ico'),
        ]:
            if _os.path.exists(ip):
                app.setWindowIcon(QIcon(ip)); icon_ok = True; break
        if getattr(sys, 'frozen', False):
            ip2 = _os.path.join(sys._MEIPASS, 'resources', 'app_icon.ico')
            if _os.path.exists(ip2):
                app.setWindowIcon(QIcon(ip2)); icon_ok = True

        # Set default font (cross-platform)
        font = QFont()
        if sys.platform == 'win32':
            font.setFamilies(["Segoe UI", "Microsoft YaHei", "sans-serif"])
            font.setPointSize(10)
        else:
            font.setFamilies(["-apple-system", "Helvetica Neue", "SF Pro Text", "sans-serif"])
            font.setPointSize(12)
        app.setFont(font)

        # macOS-specific settings
        try:
            app.setAttribute(
                sys.intern("AA_UseHighDpiPixmaps")
            )
        except Exception:
            pass

        # ── Windows single-instance lock ──
        # On Windows, double-clicking a file in Explorer launches a NEW process
        # each time. We use QLocalServer/QLocalSocket to forward the file path
        # to the already-running instance and exit the new process immediately.
        _win_server = None
        _win_is_first = True
        if sys.platform == 'win32':
            from PySide6.QtNetwork import QLocalServer, QLocalSocket

            _SERVER_NAME = "MicroView-SingleInstance-v1"
            _win_files = [a for a in sys.argv[1:]
                          if a.lower().endswith(('.nd2', '.lif'))]

            _sock = QLocalSocket()
            _sock.connectToServer(_SERVER_NAME)
            if _sock.waitForConnected(500):
                # Forward paths to the existing instance, then exit
                for fp in _win_files:
                    _sock.write((fp + '\n').encode('utf-8'))
                _sock.waitForBytesWritten(1000)
                _sock.disconnectFromServer()
                _log_error(f'IPC: forwarded {len(_win_files)} file(s) → exiting')
                sys.exit(0)

            # We are the first instance — start the server
            QLocalServer.removeServer(_SERVER_NAME)
            _win_server = QLocalServer()
            _win_server.listen(_SERVER_NAME)
            _win_is_first = True
            _log_error('IPC: first instance, server started')

        window = MainWindow()
        window.show()
        window.raise_()
        window.activateWindow()

        # ── Wire up Windows single-instance server ──
        if _win_server is not None:
            def _on_new_connection():
                client = _win_server.nextPendingConnection()
                if not client:
                    return
                buf = bytearray()

                def _on_data():
                    buf.extend(client.readAll().data())
                    while b'\n' in buf:
                        idx = buf.index(b'\n')
                        fp = bytes(buf[:idx]).decode('utf-8').strip()
                        del buf[:idx + 1]
                        if fp and os.path.exists(fp):
                            _log_error(f'IPC received: {fp}')
                            window.open_file_from_finder(fp)

                client.readyRead.connect(_on_data)

            _win_server.newConnection.connect(_on_new_connection)

        from PySide6.QtCore import QTimer

        # ── macOS file-open handler ──
        # PyInstaller's bootloader does NOT forward odoc events to argv,
        # so we register an NSApplication delegate that handles openFile:/openFiles:.
        if sys.platform == 'darwin':
            try:
                from Foundation import NSObject
                from AppKit import NSApplication

                # Track recently opened files to deduplicate (macOS fires both
                # application:openFile: and application:openFiles: for the same event).
                # Entries auto-expire after 10s so re-opening the same file works.
                _recently_opened = {}

                class _MicroViewDelegate(NSObject):
                    def _dedup_ok(self, fp):
                        """Return True if file should be opened (not recently deduped)."""
                        now = __import__('time').time()
                        if fp in _recently_opened:
                            if now - _recently_opened[fp] < 10:
                                return False
                        _recently_opened[fp] = now
                        return True

                    def application_openFile_(self, app, filename):
                        fp = str(filename) if filename else ''
                        if fp and self._dedup_ok(fp) and os.path.exists(fp):
                            _log_error(f'DELEGATE openFile: {fp}')
                            QTimer.singleShot(500, lambda f=fp: window.open_file_from_finder(f))
                            return True
                        return False

                    def application_openFiles_(self, app, filenames):
                        if filenames is None:
                            return
                        for fn in filenames:
                            fp = str(fn) if fn else ''
                            if fp and self._dedup_ok(fp) and os.path.exists(fp):
                                _log_error(f'DELEGATE openFiles: {fp}')
                                QTimer.singleShot(2000, lambda f=fp: window.open_file_from_finder(f))

                _delegate = _MicroViewDelegate.alloc().init()
                _delegate.retain()
                NSApplication.sharedApplication().setDelegate_(_delegate)
                _log_error('DELEGATE: registered via NSApplication.sharedApplication().setDelegate_')
            except Exception as e:
                _log_error(f'Failed to register delegate: {e}')
                import traceback as _tb
                _log_error(_tb.format_exc())

        # ── Check argv (launched from CLI) ──
        for arg in sys.argv[1:]:
            if arg.endswith(('.nd2','.ND2','.lif','.LIF')):
                QTimer.singleShot(500, lambda f=arg: window.open_file_from_finder(f))

        sys.exit(app.exec())

    except Exception as e:
        _log_error(f"Fatal startup error: {e}\n{traceback.format_exc()}")
        # Try to show a native macOS alert
        try:
            import subprocess
            subprocess.run([
                'osascript', '-e',
                f'display dialog "MicroView 启动失败:\\n\\n{e}" '
                'buttons {"OK"} default button "OK" with icon stop'
            ], timeout=5)
        except Exception:
            pass
        sys.exit(1)


if __name__ == "__main__":
    main()
