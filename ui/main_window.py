"""
Main window — holds the sidebar, viewer, and control panels.
"""

import os
from pathlib import Path

# Debug logging (writes to same log as main.py)
def _log(msg: str):
    try:
        from pathlib import Path as _P
        from datetime import datetime as _DT
        d = _P.home() / "Library" / "Logs" / "MicroView"
        d.mkdir(parents=True, exist_ok=True)
        with open(d / "app.log", "a", encoding="utf-8") as f:
            f.write(f"DEBUG [{_DT.now().isoformat()}]: {msg}\n")
    except Exception:
        pass

from PySide6.QtCore import Qt, QSettings, QThread, Signal, QTimer
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QDialog, QDialogButtonBox,
    QFileDialog, QHBoxLayout, QLabel, QListWidget,
    QMainWindow, QMenuBar, QMessageBox, QSplitter,
    QStatusBar, QVBoxLayout, QWidget,
)

from .sidebar import SidebarWidget
from .viewer import ViewerWidget
from .controls import ControlsWidget
from core.scanner import scan_folder, build_folder_tree


class ScanWorker(QThread):
    """Background worker for scanning ND2 files."""
    progress = Signal(int, int, str)   # current, total, filename
    finished = Signal(dict)            # file_index
    error = Signal(str)                # error message

    def __init__(self, root_path: str, use_cache: bool = True):
        super().__init__()
        self.root_path = root_path
        self.use_cache = use_cache

    def run(self):
        try:
            result = scan_folder(
                self.root_path,
                progress_callback=lambda c, t, f: self.progress.emit(c, t, f),
                use_cache=self.use_cache,
            )
            self.finished.emit(result)
        except Exception as e:
            self.error.emit(str(e))


class MainWindow(QMainWindow):
    """Top-level window for the ND2 Browser."""

    def __init__(self):
        super().__init__()

        # State
        self.file_index: dict = {}
        self.folder_tree: dict = {}
        self.current_filepath: str | None = None
        self._file_settings: dict = {}
        self._global_display_settings = None
        self._loading_file_settings = False
        self._export_channel_selection = None
        self._export_merge_selection = None
        self._export_merge_enabled = True
        self._pending_open_file: str | None = None
        self._active_workers: list = []
        self.current_raw_data = None   # numpy array of current file
        self._cached_norm: list = []       # cached normalized channel data
        self._render_timer = QTimer()      # debounce timer
        self._render_timer.setSingleShot(True)
        self._render_timer.setInterval(30)  # 30ms debounce
        self._render_timer.timeout.connect(self._do_render)
        self.settings = QSettings("MicroView", "MicroView")
        self.scan_worker: ScanWorker | None = None

        # Window properties
        self.setWindowTitle("MicroView")
        self.setMinimumSize(1100, 700)
        self.resize(1440, 900)

        # Apply white theme stylesheet
        self._load_stylesheet()

        # Build UI
        self._setup_menu_bar()
        self._setup_central_widget()
        self._setup_status_bar()

        # Viewer and controls default to dark mode

        # No auto-scan on startup — user opens folder manually
        self._update_status("就绪 — 请打开包含 ND2 或 LIF 文件的文件夹")

    # ── stylesheet ──────────────────────────────────────────────

    def _load_stylesheet(self):
        """Load and apply the dark QSS stylesheet."""
        possible_paths = [
            Path(__file__).parent.parent / "resources" / "style_dark.qss",
            Path(os.path.dirname(os.path.abspath(__file__))).parent / "resources" / "style_dark.qss",
        ]
        if getattr(sys, 'frozen', False):
            possible_paths.insert(0, Path(sys._MEIPASS) / "resources" / "style_dark.qss")

        for qss_path in possible_paths:
            if qss_path.exists():
                with open(qss_path, 'r', encoding='utf-8') as f:
                    self.setStyleSheet(f.read())
                return

        self.setStyleSheet("QMainWindow{background:#1e1e1e;} QMenuBar{background:#2d2d2d;} QStatusBar{background:#252525;}")

    def _on_settings(self):
        """Open channel color settings dialog."""
        from .settings_dialog import ColorSettingsDialog
        dlg = ColorSettingsDialog(self._dlg_colors, self)
        # Show current file's pixel size — always read directly from file
        # (scanner cache may contain stale/incorrect values)
        px = None
        if self.current_filepath:
            try:
                entry = self.file_index.get(self.current_filepath, {})
                lif_idx = entry.get('lif_image_index', -1)
                if lif_idx >= 0:
                    from core.lif_reader import read_lif_metadata
                    real_fp = entry.get('filepath', self.current_filepath)
                    metas = read_lif_metadata(real_fp)
                    if lif_idx < len(metas):
                        px = metas[lif_idx].pixel_size_um
                else:
                    from core.nd2_reader import read_metadata
                    fp = entry.get('filepath', self.current_filepath)
                    meta = read_metadata(fp)
                    if meta:
                        px = meta.pixel_size_um
            except Exception:
                pass
        dlg.set_pixel_size_info(px)
        if dlg.exec() == QDialog.Accepted:
            if self.current_raw_data is not None:
                self._display_all()
                # Refresh control button colours after settings change
                self.controls.set_dark_mode(True)

    def _dlg_colors(self):
        """Return (bg, text, btn_bg, btn_text, tree_bg, header_bg, input_bg)."""
        return ("#2d2d2d", "#CCC", "#3c3c3c", "#CCC",
                "#1e1e1e", "#2d2d2d", "#3c3c3c")

    @staticmethod
    def _merge_color_priority(hex_color: str) -> int:
        """Use the same blue → green → red priority as the preview Merge title."""
        try:
            r, g, b = int(hex_color[1:3], 16), int(hex_color[3:5], 16), int(hex_color[5:7], 16)
        except (ValueError, IndexError):
            return 6
        if b > r and b > g:
            return 0
        if g > r and g > b:
            return 1
        if r > g and r > b:
            return 2
        if b > r and g > r:
            return 3
        if r > g and b > g:
            return 4
        return 5

    def _merge_selection_html(self, selections: list[tuple[str, str]]) -> str:
        """Build the Merge title using the exact preview title color convention."""
        colors = [color for _, color in selections]
        top = sorted(colors, key=self._merge_color_priority)[:3]
        if not top:
            return "<span style='color:#FFF'>Merge</span>"
        if len(top) == 1:
            return f"<span style='color:{top[0]}'>Merge</span>"
        if len(top) == 2:
            return (f"<span style='color:{top[0]}'>Mer</span>"
                    f"<span style='color:{top[1]}'>ge</span>")
        return (f"<span style='color:{top[0]}'>M</span>"
                f"<span style='color:{top[1]}'>er</span>"
                f"<span style='color:{top[2]}'>ge</span>")

    @staticmethod
    def _merge_settings_button_style() -> str:
        return (
            "QToolButton { color:#F2F2F2; background:#3C3C3C; border:1px solid #666; "
            "border-radius:4px; font-size:15px; font-weight:600; }"
            "QToolButton:hover { background:#555; border-color:#888; }"
            "QToolButton:pressed { background:#007AFF; border-color:#007AFF; }"
        )

    def _setup_menu_bar(self):
        menu_bar = self.menuBar()

        # File menu
        file_menu = menu_bar.addMenu("文件(&F)")

        open_action = QAction("打开文件夹...", self)
        open_action.setShortcut(QKeySequence("Ctrl+O"))
        open_action.triggered.connect(self._on_open_folder)
        file_menu.addAction(open_action)

        refresh_action = QAction("刷新扫描", self)
        refresh_action.setShortcut(QKeySequence("Ctrl+R"))
        refresh_action.triggered.connect(self._on_refresh)
        file_menu.addAction(refresh_action)

        file_menu.addSeparator()

        quit_action = QAction("退出", self)
        quit_action.setShortcut(QKeySequence("Ctrl+Q"))
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

        # Settings menu
        settings_menu = menu_bar.addMenu("设置(&S)")
        settings_action = QAction("偏好设置...", self)
        settings_action.setShortcut(QKeySequence("Ctrl+,"))
        settings_action.triggered.connect(self._on_settings)
        settings_menu.addAction(settings_action)

        # Help menu
        help_menu = menu_bar.addMenu("帮助(&H)")
        about_action = QAction("关于...", self)
        about_action.triggered.connect(self._on_about)
        help_menu.addAction(about_action)

    # ── central widget ──────────────────────────────────────────

    def _setup_central_widget(self):
        """Create sidebar | (viewer + controls) split layout."""
        central = QWidget()
        self.setCentralWidget(central)

        # Sidebar (left)
        self.sidebar = SidebarWidget()
        self.sidebar.file_selected.connect(self._on_file_selected)

        # Right panel: viewer + controls
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)

        self.viewer = ViewerWidget()
        right_layout.addWidget(self.viewer, 1)  # stretch factor 1

        self.controls = ControlsWidget()
        self.controls.channel_changed.connect(self._on_channel_changed)
        self.controls.levels_changed.connect(self._on_adjustment_changed)
        self.controls.brightness_changed.connect(self._on_adjustment_changed)
        self.controls.contrast_changed.connect(self._on_adjustment_changed)
        self.controls.per_channel_changed.connect(self._on_per_channel_changed)
        self.controls.channel_toggle_changed.connect(self._on_channel_toggle)
        self.controls.global_apply_changed.connect(self._on_global_apply_changed)
        self.controls.export_requested.connect(self._on_export)
        self.controls.export_channels_requested.connect(self._on_export_channels)
        self.controls.batch_export_requested.connect(self._on_batch_export)
        self.controls.imagej_requested.connect(self._on_open_in_imagej)
        right_layout.addWidget(self.controls)

        # Splitter
        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self.sidebar)
        splitter.addWidget(right_panel)
        splitter.setStretchFactor(0, 0)  # sidebar: fixed
        splitter.setStretchFactor(1, 1)  # viewer: stretchy
        splitter.setSizes([280, 1000])

        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(splitter)

    # ── status bar ──────────────────────────────────────────────

    def _setup_status_bar(self):
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_label = QLabel("就绪 — 请打开包含 ND2 或 LIF 文件的文件夹")
        self.status_bar.addWidget(self.status_label)

    def _update_status(self, message: str):
        self.status_label.setText(message)

    # ── scanning ────────────────────────────────────────────────

    def _on_open_folder(self):
        folder = QFileDialog.getExistingDirectory(
            self, "选择包含 ND2 文件的文件夹", os.path.expanduser("~")
        )
        if folder:
            self.settings.setValue("last_folder", folder)
            self._start_scan(folder)

    def _on_refresh(self):
        last = self.settings.value("last_folder", "")
        if last and os.path.isdir(last):
            self._start_scan(last, use_cache=False)
        else:
            self._on_open_folder()

    def _cleanup_workers(self):
        for w in self._active_workers[:]:
            if w.isRunning():
                w.quit()
                w.wait(2000)
            w.deleteLater()
        self._active_workers.clear()

    def _start_scan(self, root_path: str, use_cache: bool = True):
        self._update_status("正在扫描文件夹...")
        # Don't clear if we're adding to existing tree
        if not self.file_index:
            self.sidebar.clear()
        self.sidebar.show_scanning_indicator(True)
        worker = ScanWorker(root_path, use_cache)
        self._active_workers.append(worker)
        # Use scan_id to distinguish initial scan from add-folder scan
        worker.finished.connect(self._on_scan_finished)
        worker.error.connect(self._on_scan_error)
        worker.start()
        self.scan_worker = worker

    def _on_scan_progress(self, current: int, total: int, filename: str):
        self._update_status(f"正在扫描 ({current}/{total}): {filename}")

    def _on_scan_finished(self, file_index: dict):
        tree = build_folder_tree(file_index, self.scan_worker.root_path)
        if self.file_index:
            # Already have folders open — add instead of replace
            self.file_index.update(file_index)
            self.sidebar.add_folder(tree, file_index)
        else:
            self.file_index = file_index
            self.folder_tree = tree
            self.sidebar.populate(tree, file_index)
        self.sidebar.show_scanning_indicator(False)

        pending = getattr(self, '_pending_open_file', None)
        if pending:
            self._pending_open_file = None
            import os as _os
            p_real = _os.path.realpath(pending)
            p_base = _os.path.basename(pending)
            found = None
            for key, entry in file_index.items():
                ep = entry.get('filepath', '')
                if ep == pending or _os.path.realpath(ep) == p_real:
                    found = key; break
            if not found:
                for key, entry in file_index.items():
                    fn = entry.get('filename', '')
                    if fn == p_base or p_base in fn:
                        found = key; break
            if found:
                self._on_file_selected(found)
                from PySide6.QtCore import QTimer
                QTimer.singleShot(300, lambda k=found: self.sidebar.select_file(k))

        total = len(file_index)
        nd2_n = sum(1 for e in file_index.values() if e.get('lif_image_index', -1) < 0)
        lif_n = sum(1 for e in file_index.values() if e.get('lif_image_index', -1) >= 0)
        parts = []
        if nd2_n: parts.append(f"{nd2_n} ND2")
        if lif_n: parts.append(f"{lif_n} LIF")
        self._update_status(f"共 {total} 个文件" + (f" ({', '.join(parts)})" if parts else ""))

    def _on_scan_error(self, error_msg: str):
        self.sidebar.show_scanning_indicator(False)
        self._update_status(f"扫描出错: {error_msg}")
        QMessageBox.warning(self, "扫描错误", f"扫描文件夹时出错：\n{error_msg}")

    # ── file loading ────────────────────────────────────────────

    def _on_file_selected(self, filepath: str):
        """Called when user clicks a file in the sidebar."""
        # Save current file's settings + zoom before switching
        if self.current_filepath and self.current_raw_data is not None:
            self._file_settings[self.current_filepath] = (
                self.controls.all_black_points(), self.controls.all_white_points(),
                self.controls.all_brightness(), self.controls.all_contrast(),
                self.controls.all_enabled(),
                self.viewer.get_zoom_state()
            )
        self.current_filepath = filepath
        try:
            from core.nd2_reader import read_pixels

            # Get metadata from file index
            entry = self.file_index.get(filepath, {})
            channel_count = entry.get('channel_count', 1)
            channel_names = entry.get('channel_names', [f"Ch{i+1}" for i in range(channel_count)])

            # Read full pixel data
            lif_idx = entry.get('lif_image_index', -1)
            if lif_idx >= 0:
                from core.lif_reader import read_lif_pixels
                real_fp = entry.get("filepath", filepath)
                raw_data = read_lif_pixels(real_fp, image_index=lif_idx)
            else:
                pass
                raw_data = read_pixels(filepath)
            self.current_raw_data = raw_data

            # Pre-normalize all channels (cache for fast slider response)
            from core.image_processor import _detect_nch, _get_ch, normalize_to_8bit
            nch = _detect_nch(raw_data)
            self._cached_norm = []
            for ch in range(nch):
                ch2d = _get_ch(raw_data, ch, 0)
                self._cached_norm.append(normalize_to_8bit(ch2d))

            # Compute per-channel histograms for the LUT widget
            import numpy as np
            histograms = []
            for ch_data in self._cached_norm:
                h, _ = np.histogram(ch_data, bins=256, range=(0, 255))
                histograms.append(h.astype(np.int32))
            self.controls.set_histograms(histograms)

            # Rebuilding controls emits default-state signals; do not let those
            # overwrite the global snapshot before it is applied.
            self._loading_file_settings = True

            # Set up per-channel controls
            self.controls.set_channels(channel_names)

            # Apply global settings lazily only when this file is opened.
            # Otherwise restore this file/Series' own in-session settings.
            if self.controls.global_apply_enabled() and self._global_display_settings:
                self.controls.restore_settings(*self._global_display_settings)
            elif filepath in self._file_settings:
                saved = self._file_settings[filepath]
                if len(saved) >= 6:
                    # Format: (black, white, brightness, contrast, enabled, zoom)
                    self.controls.restore_settings(saved[0], saved[1], saved[4],
                                                   saved[2], saved[3])
                    from PySide6.QtCore import QTimer
                    QTimer.singleShot(100, lambda s=saved: self.viewer.set_zoom_state(*s[5]))
                elif len(saved) >= 4:
                    # Format: (black_points, white_points, enabled, zoom) — old LUT-only
                    self.controls.restore_settings(saved[0], saved[1], saved[2])
                    from PySide6.QtCore import QTimer
                    QTimer.singleShot(100, lambda s=saved: self.viewer.set_zoom_state(*s[3]))
                else:
                    # Old format: (brightness, contrast, zoom)
                    self.controls.restore_settings(saved[0], saved[1])
                    if len(saved) > 2:
                        from PySide6.QtCore import QTimer
                        QTimer.singleShot(100, lambda s=saved: self.viewer.set_zoom_state(*s[2]))
            else:
                pass
                self.controls.reset_to_defaults()

            self._loading_file_settings = False

            # Display merge + all single channels
            self._display_all()

            # Update status
            w = entry.get('width', raw_data.shape[-1])
            h = entry.get('height', raw_data.shape[-2])
            name = entry.get('filename', os.path.basename(filepath))
            self._update_status(
                f"当前: {name}  |  {w}×{h}  |  {channel_count} 通道  |  "
                f"{entry.get('z_slices', 1)} Z-slice(s)"
            )

        except Exception as e:
            import traceback
            self._update_status(f"无法打开文件: {e}")
            QMessageBox.warning(self, "打开文件错误",
                f"无法打开文件：\n{filepath}\n\n错误信息：{e}\n\n{traceback.format_exc()}")

    # ── display ─────────────────────────────────────────────────

    def _display_all(self, preserve_view: bool = False):
        """Request a render (debounced — actual render happens via QTimer)."""
        if self.current_raw_data is None:
            return
        self._preserve_view_on_render = preserve_view
        # Debounce: restart the timer on every call
        self._render_timer.start()

    def _do_render(self):
        """Actual render using cached normalized data (fast!)."""
        if self.current_raw_data is None or not self._cached_norm:
            return

        blk = self.controls.all_black_points()
        wht = self.controls.all_white_points()
        brightness_vals = self.controls.all_brightness()
        contrast_vals = self.controls.all_contrast()
        enabled = self.controls.all_enabled()
        entry = self.file_index.get(self.current_filepath, {})
        nch = len(self._cached_norm)
        channel_names = entry.get('channel_names', [f"Ch{i+1}" for i in range(nch)])

        from core.image_processor import apply_levels, apply_lut, _guess_color, get_channel_hex
        import numpy as np

        def _adjust(ch_data, ch_idx):
            result = apply_levels(
                ch_data,
                blk[ch_idx] if ch_idx < len(blk) else 0.0,
                wht[ch_idx] if ch_idx < len(wht) else 255.0,
            )
            # Chain BC fine-tune after LUT
            from core.image_processor import apply_bc as _apply_bc
            b_val = brightness_vals[ch_idx] if ch_idx < len(brightness_vals) else 0.0
            c_val = contrast_vals[ch_idx] if ch_idx < len(contrast_vals) else 1.0
            return _apply_bc(result, b_val, c_val)

        # Build channel displays only for enabled channels
        adj_channels = []
        filtered_names = []
        filtered_colors = []
        for i in range(nch):
            if not enabled[i]:
                continue
            gray = _adjust(self._cached_norm[i], i)
            ch_name = channel_names[i] if i < len(channel_names) else ""
            color = _guess_color(ch_name, i)
            adj_channels.append(apply_lut(gray, color))
            display_label = ch_name
            filtered_names.append(display_label)
            filtered_colors.append(get_channel_hex(ch_name, i))

        # ── Store per-channel color map for export dialogs ──
        self._channel_colors = {}
        for i in range(nch):
            cn = channel_names[i] if i < len(channel_names) else f"Ch{i+1}"
            self._channel_colors[cn] = get_channel_hex(cn, i)

        # Build merge from enabled channels only
        h, w = self._cached_norm[0].shape
        if nch == 1:
            if enabled[0]:
                ch_name = channel_names[0] if channel_names else ""
                g = _adjust(self._cached_norm[0], 0)
                color = _guess_color(ch_name, 0)
                merge = apply_lut(g, color)
            else:
                merge = np.zeros((h, w, 3), dtype=np.uint8)
        else:
            rgb = np.zeros((h, w, 3), dtype=np.float64)
            for i in range(nch):
                if not enabled[i]:
                    continue
                ch_name = channel_names[i] if i < len(channel_names) else ""
                color = _guess_color(ch_name, i)
                ci = _adjust(self._cached_norm[i], i).astype(np.float64)
                for comp in range(3):
                    if color[comp] > 0:
                        rgb[:, :, comp] = np.maximum(rgb[:, :, comp],
                            ci * (color[comp] / 255.0))
            merge = np.clip(rgb, 0, 255).astype(np.uint8)

        # ── Scale bar (preview) ──
        _s = QSettings("MicroView", "MicroView")
        px_um = _s.value("scalebar_pixel_size_override", 0.0, type=float)
        if not px_um or px_um <= 0:
            px_um = self._get_pixel_size_um(entry)
        _sp = _s.value("scalebar_preview", False, type=bool)
        if _sp and px_um and px_um > 0:
            from core.image_processor import draw_scale_bar as _dsb
            _kw = self._scale_bar_kwargs()
            merge = _dsb(merge, px_um, **_kw)
            for ci in range(len(adj_channels)):
                adj_channels[ci] = _dsb(adj_channels[ci], px_um, **_kw)

        self.viewer.display_image(
            merge, adj_channels, filtered_names, filtered_colors,
            preserve_view=getattr(self, '_preserve_view_on_render', False),
        )

    def _on_channel_changed(self, channel: str | int):
        pass  # unused; kept for backward compat with controls signal

    def _on_open_in_imagej(self):
        """Open the current file in ImageJ/Fiji."""
        if self.current_raw_data is None:
            QMessageBox.information(self, "提示", "请先打开一个文件。")
            return

        s = QSettings("MicroView", "MicroView")
        raw_path = s.value("imagej_path", "").rstrip('/')
        open_mode = s.value("imagej_lif_mode", "完整文件")
        apply_adj = s.value("imagej_apply_adjustments", True, type=bool)

        if not raw_path:
            QMessageBox.information(
                self, "未配置 ImageJ",
                "请先在 视图 → 设置 中配置 Fiji/ImageJ 路径。"
            )
            return

        # Find .app bundle root (needed for 'open -a' on macOS)
        app_bundle = raw_path
        if '/Contents/MacOS/' in raw_path:
            app_bundle = raw_path.split('/Contents/MacOS/')[0]

        if not os.path.exists(app_bundle if app_bundle.endswith('.app') else raw_path):
            QMessageBox.information(
                self, "ImageJ 路径不存在",
                f"找不到 ImageJ/Fiji，请检查设置中的路径：\n{raw_path}"
            )
            return

        import sys as _sys
        is_mac = _sys.platform == 'darwin'

        entry = self.file_index.get(self.current_filepath, {})
        real_fp = entry.get('filepath', self.current_filepath)
        lif_idx = entry.get('lif_image_index', -1)

        # ── Build base name (same pattern as batch export) ──
        if lif_idx >= 0:
            # LIF: {lif_stem}-{img_name}
            lif_stem = os.path.splitext(os.path.basename(real_fp))[0]
            fn = entry.get('filename', '')
            if ' [' in fn:
                img_name = fn.split(' [')[-1].rstrip(']')
            elif '::' in (self.current_filepath or ''):
                img_name = self.current_filepath.split('::')[-1]
            else:
                img_name = f"Image{lif_idx}"
            base = f"{lif_stem}-{img_name}"
        else:
            # ND2: {stem}
            base = os.path.splitext(os.path.basename(real_fp))[0]

        files_to_open = []

        # "完整文件" mode: pass the raw file directly (both ND2 and LIF)
        if open_mode == "完整文件":
            files_to_open.append(real_fp)
        else:
            import tempfile, numpy as np
            from PIL import Image as PILImage
            from core.image_processor import (
                get_merge_display, get_channel_display, _detect_nch, normalize_to_8bit,
            )
            nch = _detect_nch(self.current_raw_data)
            ch_names = entry.get('channel_names', [f"Ch{i+1}" for i in range(nch)])
            enabled = self.controls.all_enabled()
            blk = self.controls.all_black_points()
            wht = self.controls.all_white_points()
            br = self.controls.all_brightness()
            ct = self.controls.all_contrast()

            tmp_dir = tempfile.mkdtemp(prefix="microview_")

            if open_mode in ("当前 Merge", "Merge + 所有通道"):
                tp = os.path.join(tmp_dir, f"{base}_Merge.tif")
                if apply_adj:
                    merge = get_merge_display(
                        self.current_raw_data,
                        ch_black=blk, ch_white=wht,
                        ch_brightness=br, ch_contrast=ct,
                        channel_names=ch_names,
                        enabled_channels=enabled,
                    )
                else:
                    merge = get_merge_display(
                        self.current_raw_data, channel_names=ch_names,
                        enabled_channels=enabled,
                    )
                PILImage.fromarray(merge).save(tp)
                files_to_open.append(tp)

            if open_mode in ("所有通道", "Merge + 所有通道"):
                for ch in range(nch):
                    if not enabled[ch]:
                        continue
                    cn = ch_names[ch] if ch < len(ch_names) else f"Ch{ch+1}"
                    tp = os.path.join(tmp_dir, f"{base}_{cn}.tif")
                    if apply_adj:
                        img = get_channel_display(
                            self.current_raw_data, channel=ch, colored=True,
                            channel_name=cn,
                            black_point=blk[ch] if ch < len(blk) else 0.0,
                            white_point=wht[ch] if ch < len(wht) else 255.0,
                            brightness=br[ch] if ch < len(br) else 0.0,
                            contrast=ct[ch] if ch < len(ct) else 1.0,
                        )
                    else:
                        ch2d = normalize_to_8bit(
                            self._cached_norm[ch] if ch < len(self._cached_norm)
                            else np.zeros((1, 1), dtype=np.uint8)
                        )
                        from core.image_processor import apply_lut, _guess_color
                        img = apply_lut(ch2d, _guess_color(cn, ch))
                    PILImage.fromarray(img).save(tp)
                    files_to_open.append(tp)

        if not files_to_open:
            return

        try:
            import subprocess
            if is_mac:
                subprocess.Popen(['open', '-a', app_bundle] + files_to_open)
            else:
                # Windows: ImageJ.exe launcher uses ANSI API, garbles non-
                # ASCII paths.  For raw files with Chinese paths, create a
                # hardlink in the temp dir (ASCII path) and open that instead.
                import tempfile as _tf, subprocess, shutil
                _md = _tf.mkdtemp(prefix="microview_")
                _to_open = []
                for f in files_to_open:
                    if f == real_fp:
                        # Raw file with potentially Chinese path → hardlink
                        ext = os.path.splitext(f)[1]
                        _link = os.path.join(_md, f"_original{ext}")
                        try:
                            os.link(f, _link)
                        except OSError:
                            shutil.copy2(f, _link)
                        _to_open.append(_link)
                    else:
                        _to_open.append(f)
                subprocess.Popen([raw_path] + _to_open)
            self._update_status(f"已在 ImageJ 中打开: {real_fp}")
        except Exception as e:
            QMessageBox.warning(self, "打开失败", f"无法启动 ImageJ:\n{e}")

    def _on_adjustment_changed(self):
        self._update_global_display_settings()
        self._display_all(preserve_view=True)

    def _on_per_channel_changed(self, cb, cc):
        self._update_global_display_settings()
        self._display_all(preserve_view=True)

    def _on_channel_toggle(self):
        self._update_global_display_settings()
        self._display_all(preserve_view=True)

    def _on_global_apply_changed(self, enabled: bool):
        """Capture settings once; actual application is deferred until file switching."""
        if enabled:
            self._update_global_display_settings(force=True)
        else:
            self._global_display_settings = None

    def _update_global_display_settings(self, force: bool = False):
        if self._loading_file_settings:
            return
        if not force and not self.controls.global_apply_enabled():
            return
        self._global_display_settings = (
            self.controls.all_black_points(), self.controls.all_white_points(),
            self.controls.all_enabled(), self.controls.all_brightness(),
            self.controls.all_contrast(),
        )

    def _export_file(self, filepath: str, lif_idx: int, out_folder: str, base_name: str = ""):
        """Export merge + channels for a single file to a folder."""
        from core.nd2_reader import read_pixels
        from core.lif_reader import read_lif_pixels
        from core.image_processor import get_merge_display, get_channel_display, _detect_nch
        from PIL import Image

        if lif_idx >= 0:
            raw = read_lif_pixels(filepath, image_index=lif_idx)
        else:
            raw = read_pixels(filepath)

        entry = self.file_index.get(filepath, {})
        ch_names = entry.get('channel_names', [])
        nch = _detect_nch(raw)
        base = base_name or os.path.splitext(os.path.basename(filepath))[0]

        merge = get_merge_display(raw)
        Image.fromarray(merge).save(os.path.join(out_folder, f"{base}_Merge.png"))

        for ch in range(nch):
            cn = ch_names[ch] if ch < len(ch_names) else f"Ch{ch+1}"
            img = get_channel_display(raw, channel=ch, colored=True, channel_name=cn)
            Image.fromarray(img).save(os.path.join(out_folder, f"{base}_{cn}.png"))


    def _on_export(self):
        """Export current Merge view with filename-based naming."""
        if self.current_raw_data is None:
            QMessageBox.information(self, "提示", "请先打开一个文件。")
            return

        entry = self.file_index.get(self.current_filepath, {})
        real_fp = entry.get('filepath', self.current_filepath or 'image')
        lif_idx = entry.get('lif_image_index', -1)
        if lif_idx >= 0:
            lif_stem = os.path.splitext(os.path.basename(real_fp))[0]
            fn = entry.get('filename', '')
            if ' [' in fn:
                img_name = fn.split(' [')[-1].rstrip(']')
            elif '::' in (self.current_filepath or ''):
                img_name = (self.current_filepath or '').split('::')[-1]
            else:
                img_name = f"Image{lif_idx}"
            base = f"{lif_stem}-{img_name}"
        else:
            base = os.path.splitext(os.path.basename(real_fp))[0]
        default_name = f"{base}_Merge.png"
        default_path = os.path.join(os.path.expanduser("~/Desktop"), default_name)

        filepath, selected_filter = QFileDialog.getSaveFileName(
            self, "导出 Merge", default_path,
            "PNG (*.png);;TIFF (*.tif)"
        )
        if not filepath:
            return
        self._save_merge(filepath)

    def _get_pixel_size_um(self, entry):
        """Read pixel_size_um directly from file (bypass stale cache)."""
        from core.nd2_reader import read_metadata
        from core.lif_reader import read_lif_metadata
        try:
            lif_idx = entry.get('lif_image_index', -1)
            if lif_idx >= 0:
                real_fp = entry.get('filepath', '')
                metas = read_lif_metadata(real_fp)
                if lif_idx < len(metas):
                    return metas[lif_idx].pixel_size_um
            else:
                fp = entry.get('filepath', '')
                meta = read_metadata(fp)
                if meta:
                    return meta.pixel_size_um
        except Exception:
            pass
        return entry.get('pixel_size_um')  # fallback to cache

    def _scale_bar_kwargs(self):
        """Return kwargs dict for draw_scale_bar from current QSettings."""
        s = QSettings("MicroView", "MicroView")
        return dict(
            color=s.value("scalebar_color", "white"),
            position=s.value("scalebar_position", "br"),
            style=s.value("scalebar_style", "line_text"),
            bar_um=s.value("scalebar_length_um", 0, type=int),
            thickness=s.value("scalebar_thickness", 5, type=int),
            font_size=s.value("scalebar_font_size", 30, type=int),
            show_label=s.value("scalebar_show_label", True, type=bool),
            font_family=s.value("scalebar_font_family", "Times New Roman"),
        )

    def _apply_scale_bar(self, img, entry, silent=False):
        """Apply scale bar to an export image if enabled in settings."""
        s = QSettings("MicroView", "MicroView")
        if not s.value("scalebar_export", True, type=bool):
            return img
        px_um = s.value("scalebar_pixel_size_override", 0.0, type=float)
        if not px_um or px_um <= 0:
            px_um = self._get_pixel_size_um(entry)
        if not px_um or px_um <= 0:
            if not silent:
                self._update_status("未找到像素标定数据，无法添加比例尺")
            return img
        from core.image_processor import draw_scale_bar as _dsb
        return _dsb(img, px_um, **self._scale_bar_kwargs())

    def _save_merge(self, filepath: str):
        """Save merge image to filepath."""
        blk = self.controls.all_black_points()
        wht = self.controls.all_white_points()
        cb = self.controls.all_brightness()
        cc = self.controls.all_contrast()
        enabled = self.controls.all_enabled()
        entry = self.file_index.get(self.current_filepath, {})
        ch_names = entry.get('channel_names', [])
        from core.image_processor import get_merge_display
        img = get_merge_display(self.current_raw_data,
                                ch_black=blk, ch_white=wht,
                                ch_brightness=cb, ch_contrast=cc,
                                channel_names=ch_names,
                                enabled_channels=enabled)
        img = self._apply_scale_bar(img, entry)
        from PIL import Image
        os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)
        Image.fromarray(img).save(filepath)
        self._update_status(f"已导出: {os.path.basename(filepath)}")

    def _on_export_channels(self):
        """Export selected channels of current file as individual images."""
        if self.current_raw_data is None:
            QMessageBox.information(self, "提示", "请先打开一个文件。")
            return

        entry = self.file_index.get(self.current_filepath, {})
        channel_names = entry.get('channel_names', [])
        nch = len(channel_names)
        if nch == 0:
            QMessageBox.information(self, "提示", "当前文件没有通道信息。")
            return

        from core.image_processor import _detect_nch
        nch = _detect_nch(self.current_raw_data)

        # ── Channel + format selection dialog ──
        from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout,
                                        QCheckBox, QComboBox, QLabel, QPushButton,
                                        QGroupBox, QToolButton)
        ch_dlg = QDialog(self)
        ch_dlg.setWindowTitle("选择导出通道")
        ch_dlg.setMinimumWidth(300)
        ch_lay = QVBoxLayout(ch_dlg)

        ch_lay.addWidget(QLabel(f"当前文件: {entry.get('filename', '?')}"))
        ch_lay.addWidget(QLabel(f"通道数: {nch}"))

        # Merge channels are configured independently from single-channel exports.
        merge_cb = QCheckBox()
        merge_cb.setChecked(self._export_merge_enabled)
        merge_channel_indices = list(self._export_merge_selection or [])
        if self._export_merge_selection is None:
            merge_channel_indices = [
                i for i, enabled in enumerate(self.controls.all_enabled()) if enabled
            ]
        if not merge_channel_indices:
            merge_channel_indices = list(range(nch))

        merge_row = QHBoxLayout()
        merge_row.setContentsMargins(0, 0, 0, 0)
        merge_row.setSpacing(6)
        merge_toggle = QWidget()
        merge_toggle_layout = QHBoxLayout(merge_toggle)
        merge_toggle_layout.setContentsMargins(0, 0, 0, 0)
        merge_toggle_layout.setSpacing(8)
        # macOS uses a larger native checkbox indicator; keep its real width
        # so the adjacent Merge title never overlaps the indicator.
        merge_cb.setFixedWidth(merge_cb.sizeHint().width())
        merge_toggle_layout.addWidget(merge_cb)
        merge_label = QLabel()
        merge_label.setTextFormat(Qt.RichText)
        merge_toggle_layout.addWidget(merge_label)
        merge_row.addWidget(merge_toggle)
        merge_settings_btn = QToolButton()
        merge_settings_btn.setText("⚙")
        merge_settings_btn.setToolTip("选择参与 Merge 合成的通道")
        merge_settings_btn.setFixedSize(24, 24)
        merge_settings_btn.setStyleSheet(self._merge_settings_button_style())
        merge_row.addWidget(merge_settings_btn)
        merge_row.addStretch()
        ch_lay.addLayout(merge_row)

        def _update_merge_settings_tip():
            count = len(merge_channel_indices)
            merge_settings_btn.setToolTip(f"选择参与 Merge 合成的通道（已选 {count} 个）")
            selections = []
            for i in merge_channel_indices:
                name = channel_names[i] if i < len(channel_names) else f"Ch{i+1}"
                color = getattr(self, '_channel_colors', {}).get(name, "#3498DB")
                selections.append((name, color))
            merge_label.setText(self._merge_selection_html(selections))

        def _choose_merge_channels():
            merge_dlg = QDialog(ch_dlg)
            merge_dlg.setWindowTitle("选择 Merge 通道")
            merge_lay = QVBoxLayout(merge_dlg)
            merge_lay.addWidget(QLabel("仅勾选需要参与 Merge 合成的通道："))
            merge_boxes = []
            for i, name in enumerate(channel_names):
                box = QCheckBox(name)
                box.setChecked(i in merge_channel_indices)
                hex_c = getattr(self, '_channel_colors', {}).get(name, "#3498DB")
                box.setStyleSheet(f"color: {hex_c}; font-weight: 600;")
                merge_boxes.append(box)
                merge_lay.addWidget(box)

            merge_btns = QDialogButtonBox(QDialogButtonBox.Cancel | QDialogButtonBox.Ok)
            merge_btns.rejected.connect(merge_dlg.reject)
            merge_btns.accepted.connect(merge_dlg.accept)
            merge_lay.addWidget(merge_btns)

            if merge_dlg.exec() == QDialog.Accepted:
                merge_channel_indices[:] = [
                    i for i, box in enumerate(merge_boxes) if box.isChecked()
                ]
                _update_merge_settings_tip()

        merge_settings_btn.clicked.connect(_choose_merge_channels)
        _update_merge_settings_tip()

        # Channel checkboxes — colors from main viewer (_channel_colors)
        ch_lay.addWidget(QLabel("— 单独通道 —"))
        ch_boxes = []
        for i, name in enumerate(channel_names):
            cb = QCheckBox(f"{name}")
            cb.setChecked(self._export_channel_selection is None or i in self._export_channel_selection)
            hex_c = getattr(self, '_channel_colors', {}).get(name, "#3498DB")
            cb.setStyleSheet(f"color: {hex_c}; font-weight: 600;")
            ch_boxes.append(cb)
            ch_lay.addWidget(cb)

        # Format selection
        C = self._dlg_colors()
        fmt_row = QHBoxLayout()
        fmt_row.addWidget(QLabel("导出格式:"))
        fmt_combo = QComboBox()
        fmt_combo.addItems(["PNG", "TIFF"])
        fmt_combo.setFixedWidth(90)
        fmt_combo.setStyleSheet(f"QComboBox{{background:{C[6]};color:{C[1]};border:1px solid #999;border-radius:3px;padding:4px 10px;font-size:13px;}} QComboBox:hover{{background:{C[2]};}} QComboBox QAbstractItemView{{background:{C[0]};color:{C[1]};selection-background-color:#007AFF;padding:4px;}}")
        fmt_row.addWidget(fmt_combo)
        fmt_row.addStretch()
        ch_lay.addLayout(fmt_row)

        # Scale bar checkbox (synced with settings)
        sb_cb = QCheckBox("添加比例尺")
        sb_cb.setChecked(QSettings("MicroView", "MicroView").value("scalebar_export", True, type=bool))
        sb_cb.toggled.connect(lambda v: QSettings("MicroView", "MicroView").setValue("scalebar_export", v))
        sb_cb.setStyleSheet(f"color:{C[1]};")
        ch_lay.addWidget(sb_cb)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel_btn = QPushButton("取消")
        cancel_btn.setStyleSheet(f"QPushButton{{background:{C[2]};color:{C[3]};border:1px solid #999;border-radius:4px;padding:6px 16px;}} QPushButton:hover{{background:{C[5]};}}")
        ok_btn = QPushButton("选择文件夹...")
        ok_btn.setStyleSheet(f"QPushButton{{background:#007AFF;color:#FFF;border:none;border-radius:4px;padding:6px 16px;font-weight:600;}} QPushButton:hover{{background:#0066D6;}}")
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(ok_btn)
        ch_lay.addLayout(btn_row)

        cancel_btn.clicked.connect(ch_dlg.reject)
        ok_btn.clicked.connect(ch_dlg.accept)

        if ch_dlg.exec() != QDialog.Accepted:
            return

        # Get selections
        export_merge = merge_cb.isChecked()
        selected_indices = [i for i, cb in enumerate(ch_boxes) if cb.isChecked()]
        selected_merge_indices = list(merge_channel_indices)
        export_fmt = fmt_combo.currentText()  # "PNG" or "TIFF"

        # Keep the most recent dialog choices for this app session only.
        self._export_merge_enabled = export_merge
        self._export_channel_selection = list(selected_indices)
        self._export_merge_selection = list(selected_merge_indices)

        if not export_merge and not selected_indices:
            QMessageBox.information(self, "提示", "请至少选择一个通道或 Merge。")
            return
        if export_merge and not selected_merge_indices:
            QMessageBox.information(self, "提示", "请在 Merge 设置中至少选择一个通道。")
            return

        # ── Choose output folder ──
        folder = QFileDialog.getExistingDirectory(
            self, "选择导出文件夹", os.path.expanduser("~/Desktop")
        )
        if not folder:
            return

        # ── Export ──
        try:
            lif_idx = entry.get('lif_image_index', -1)
            if lif_idx >= 0:
                fp = entry.get('filepath', self.current_filepath or 'image')
                lif_stem = os.path.splitext(os.path.basename(fp))[0]
                # Extract image name from filename or key
                fn = entry.get('filename', '')
                if ' [' in fn:
                    img_name = fn.split(' [')[-1].rstrip(']')
                elif '::' in (self.current_filepath or ''):
                    img_name = (self.current_filepath or '').split('::')[-1]
                else:
                    img_name = f"Image{lif_idx}"
                base = f"{lif_stem}-{img_name}"
            else:
                base = os.path.splitext(os.path.basename(self.current_filepath or "image"))[0]
            blk_vals = self.controls.all_black_points()
            wht_vals = self.controls.all_white_points()
            br_vals = self.controls.all_brightness()
            ct_vals = self.controls.all_contrast()

            from core.image_processor import get_merge_display, get_channel_display
            from PIL import Image

            ext = ".png" if export_fmt == "PNG" else ".tif"
            fmt = export_fmt
            count = 0

            if export_merge:
                merge_path = os.path.join(folder, f"{base}_Merge{ext}")
                merge_enabled = [i in selected_merge_indices for i in range(nch)]
                merge = get_merge_display(self.current_raw_data,
                                          ch_black=blk_vals, ch_white=wht_vals,
                                          ch_brightness=br_vals, ch_contrast=ct_vals,
                                          channel_names=channel_names,
                                          enabled_channels=merge_enabled)
                merge = self._apply_scale_bar(merge, entry)
                Image.fromarray(merge).save(merge_path, format=fmt)
                count += 1

            for ch in selected_indices:
                ch_name = channel_names[ch] if ch < len(channel_names) else f"Ch{ch+1}"
                ch_img = get_channel_display(self.current_raw_data, channel=ch, colored=True,
                                             channel_name=ch_name,
                                             black_point=blk_vals[ch] if ch < len(blk_vals) else 0.0,
                                             white_point=wht_vals[ch] if ch < len(wht_vals) else 255.0,
                                             brightness=br_vals[ch] if ch < len(br_vals) else 0.0,
                                             contrast=ct_vals[ch] if ch < len(ct_vals) else 1.0)
                ch_img = self._apply_scale_bar(ch_img, entry)
                ch_path = os.path.join(folder, f"{base}_{ch_name}{ext}")
                Image.fromarray(ch_img).save(ch_path, format=fmt)
                count += 1

            self._update_status(f"已导出 {count} 张图片到 {folder}")
        except Exception as e:
            import traceback
            QMessageBox.warning(self, "导出错误", f"{e}\n{traceback.format_exc()}")

    def _on_batch_export(self):
        """Batch export with sidebar-mirrored tree, dynamic channel filter + format."""
        if not self.file_index:
            QMessageBox.information(self, "提示", "请先扫描一个文件夹。")
            return

        try:
            self._do_batch_export()
        except Exception as e:
            import traceback as _tb
            _log(f"[_on_batch_export] FATAL: {e}\n{_tb.format_exc()}")
            QMessageBox.warning(self, "批量导出错误", f"{e}")

    def _do_batch_export(self):
        from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout,
                                        QCheckBox, QTreeWidget, QTreeWidgetItem, QPushButton,
                                        QComboBox, QLabel, QGroupBox, QWidget, QToolButton)
        from PySide6.QtCore import Qt as Qt2

        dlg = QDialog(self)
        dlg.setWindowTitle("批量导出")
        dlg.setMinimumSize(680, 560)
        layout = QVBoxLayout(dlg)
        layout.setSpacing(6)

        # ── Row 0: Select all + Format ──
        top_row = QHBoxLayout()
        select_all = QCheckBox("全选 / 取消全选")
        top_row.addWidget(select_all)
        top_row.addStretch()
        C = self._dlg_colors()
        top_row.addWidget(QLabel("格式:"))
        fmt_combo = QComboBox()
        fmt_combo.addItems(["PNG", "TIFF"])
        fmt_combo.setFixedWidth(90)
        fmt_combo.setStyleSheet(f"QComboBox{{background:{C[6]};color:{C[1]};border:1px solid #999;border-radius:3px;padding:4px 10px;font-size:13px;}} QComboBox:hover{{background:{C[2]};}} QComboBox QAbstractItemView{{background:{C[0]};color:{C[1]};selection-background-color:#007AFF;padding:4px;}}")
        top_row.addWidget(fmt_combo)
        layout.addLayout(top_row)

        # Scale bar toggle
        sb_cb = QCheckBox("添加比例尺")
        sb_cb.setChecked(QSettings("MicroView", "MicroView").value("scalebar_export", True, type=bool))
        sb_cb.toggled.connect(lambda v: QSettings("MicroView", "MicroView").setValue("scalebar_export", v))
        sb_cb.setStyleSheet(f"color:{C[1]};")
        layout.addWidget(sb_cb)

        # ── Row 1: Dynamic channel filter ──
        ch_filter_group = QGroupBox("通道导出与 Merge 设置")
        ch_filter_group.setStyleSheet(f"QGroupBox{{font-weight:600;color:{C[1]};}}")
        ch_filter_layout = QHBoxLayout(ch_filter_group)
        ch_filter_layout.setContentsMargins(6, 4, 6, 4)
        ch_filter_layout.setSpacing(4)

        # Merge selection is independent from the individual-channel filter.
        merge_filter_cb = QCheckBox()
        merge_filter_cb.setChecked(True)
        merge_channel_names = set()
        merge_selection_customized = False
        _batch_ch_color_map = {}

        merge_label = QLabel()
        merge_label.setTextFormat(Qt.RichText)
        merge_toggle = QWidget()
        merge_toggle_layout = QHBoxLayout(merge_toggle)
        merge_toggle_layout.setContentsMargins(0, 0, 0, 0)
        merge_toggle_layout.setSpacing(8)
        merge_filter_cb.setFixedWidth(merge_filter_cb.sizeHint().width())
        merge_toggle_layout.addWidget(merge_filter_cb)
        merge_toggle_layout.addWidget(merge_label)
        merge_settings_btn = QToolButton()
        merge_settings_btn.setText("⚙")
        merge_settings_btn.setToolTip("选择参与 Merge 合成的通道")
        merge_settings_btn.setFixedSize(24, 24)
        merge_settings_btn.setStyleSheet(self._merge_settings_button_style())

        def _update_batch_merge_label():
            selections = [
                (name, _batch_ch_color_map.get(name, "#3498DB"))
                for name in merge_channel_names
            ]
            merge_label.setText(self._merge_selection_html(selections))
            merge_settings_btn.setToolTip(f"选择参与 Merge 合成的通道（已选 {len(selections)} 个）")

        def _choose_batch_merge_channels():
            if not _ch_filter_state:
                QMessageBox.information(dlg, "提示", "请先勾选至少一个文件，再设置 Merge 通道。")
                return
            merge_dlg = QDialog(dlg)
            merge_dlg.setWindowTitle("选择 Merge 通道")
            merge_lay = QVBoxLayout(merge_dlg)
            merge_lay.addWidget(QLabel("仅勾选需要参与所有 Merge 合成的通道："))
            merge_boxes = []
            for name in sorted(_ch_filter_state):
                box = QCheckBox(name)
                box.setChecked(name in merge_channel_names)
                box.setStyleSheet(
                    f"color:{_batch_ch_color_map.get(name, '#3498DB')};font-weight:600;"
                )
                merge_boxes.append((name, box))
                merge_lay.addWidget(box)
            merge_btns = QDialogButtonBox(QDialogButtonBox.Cancel | QDialogButtonBox.Ok)
            merge_btns.rejected.connect(merge_dlg.reject)
            merge_btns.accepted.connect(merge_dlg.accept)
            merge_lay.addWidget(merge_btns)
            if merge_dlg.exec() == QDialog.Accepted:
                merge_channel_names.clear()
                merge_channel_names.update(name for name, box in merge_boxes if box.isChecked())
                nonlocal merge_selection_customized
                merge_selection_customized = True
                _update_batch_merge_label()

        merge_settings_btn.clicked.connect(_choose_batch_merge_channels)
        ch_filter_layout.addWidget(merge_toggle)
        ch_filter_layout.addWidget(merge_settings_btn)

        ch_filter_layout.addWidget(QLabel("│"))  # visual separator
        ch_filter_container = QWidget()
        ch_filter_inner = QHBoxLayout(ch_filter_container)
        ch_filter_inner.setContentsMargins(0, 0, 0, 0)
        ch_filter_inner.setSpacing(4)
        ch_filter_layout.addWidget(ch_filter_container, 1)
        ch_filter_layout.addStretch()
        layout.addWidget(ch_filter_group)

        # ── Row 2: File tree ──
        tree = QTreeWidget()
        tree.setHeaderLabels(["文件名", "通道"])
        tree.setColumnWidth(0, 420)
        tree.setColumnWidth(1, 180)
        tree.setStyleSheet(f"QTreeWidget{{background:{C[4]};color:{C[1]};border:1px solid #999;}} QHeaderView::section{{background:{C[5]};color:{C[1]};border:1px solid #ccc;padding:4px;font-weight:600;}}")
        layout.addWidget(tree, 1)

        # Mirror sidebar tree structure
        all_items = []
        def mirror(parent_dst, parent_src):
            for i in range(parent_src.childCount()):
                src = parent_src.child(i)
                text = src.text(0)
                key = src.data(0, Qt2.UserRole)
                fp = src.data(0, Qt2.UserRole + 1)

                if key == "__folder__":
                    dst = QTreeWidgetItem(parent_dst)
                    dst.setText(0, text)
                    dst.setFlags(dst.flags() | Qt2.ItemIsUserCheckable)
                    dst.setCheckState(0, Qt2.Unchecked)
                    mirror(dst, src)
                elif key == "__lif_container__":
                    dst = QTreeWidgetItem(parent_dst)
                    dst.setText(0, text)
                    dst.setFlags(dst.flags() | Qt2.ItemIsUserCheckable)
                    dst.setCheckState(0, Qt2.Unchecked)
                    mirror(dst, src)
                elif key and key not in ("__folder__", "__lif_container__"):
                    dst = QTreeWidgetItem(parent_dst)
                    dst.setText(0, text)
                    entry = self.file_index.get(key, {})
                    ch = entry.get('channel_names', [])
                    dst.setText(1, ", ".join(ch[:3]) if ch else "")
                    dst.setFlags(dst.flags() | Qt2.ItemIsUserCheckable)
                    dst.setCheckState(0, Qt2.Unchecked)
                    dst.setData(0, Qt2.UserRole, key)
                    dst.setData(0, Qt2.UserRole + 1, fp)
                    all_items.append(dst)

        mirror(tree.invisibleRootItem(), self.sidebar.tree.invisibleRootItem())

        # ── Dynamic channel filter update ──
        # Store current channel checkboxes: {channel_name: QCheckBox}
        _ch_filter_state = {}

        def _rebuild_channel_filter():
            """Rebuild channel checkboxes based on currently checked files."""
            from core.image_processor import _guess_color

            # Collect channel names + compute colors with correct per-file index
            nd2_channels = set()
            lif_channels = set()
            _ch_color_map = {}  # channel name → hex color

            def _collect_channels(p):
                for i in range(p.childCount()):
                    child = p.child(i)
                    k = child.data(0, Qt2.UserRole)
                    if k and k not in ("__folder__", "__lif_container__") and child.checkState(0) == Qt2.Checked:
                        entry = self.file_index.get(k, {})
                        ch_names = entry.get('channel_names', [])
                        lif_idx = entry.get('lif_image_index', -1)
                        for idx, cn in enumerate(ch_names):
                            if lif_idx >= 0:
                                lif_channels.add(cn)
                            else:
                                nd2_channels.add(cn)
                            # Compute color with correct channel index (matches export+viewer)
                            if cn not in _ch_color_map:
                                r, g, b = _guess_color(cn, idx)
                                _ch_color_map[cn] = f"#{r:02x}{g:02x}{b:02x}"
                    if child.childCount() > 0:
                        _collect_channels(child)
            _collect_channels(tree.invisibleRootItem())

            all_channels = sorted(nd2_channels | lif_channels)
            all_set = set(all_channels)
            _batch_ch_color_map.clear()
            _batch_ch_color_map.update(_ch_color_map)
            if merge_selection_customized:
                merge_channel_names.intersection_update(all_set)
            else:
                merge_channel_names.clear()
                merge_channel_names.update(all_set)
            _update_batch_merge_label()
            current_checked = set()
            for name, cb in _ch_filter_state.items():
                if cb.isChecked():
                    current_checked.add(name)
            # Preserve selections that still exist
            new_checked = current_checked & all_set
            # Auto-check newly appeared channels
            new_checked |= (all_set - set(_ch_filter_state.keys()))

            # Clear old
            while ch_filter_inner.count():
                w = ch_filter_inner.takeAt(0)
                if w.widget():
                    w.widget().deleteLater()
            _ch_filter_state.clear()

            for cn in all_channels:
                in_nd2 = cn in nd2_channels
                in_lif = cn in lif_channels
                label = cn
                if in_lif and not in_nd2:
                    label = f"{cn}(LIF)"

                hex_c = _ch_color_map.get(cn, "#3498DB")

                cb = QCheckBox(label)
                cb.setChecked(cn in new_checked)
                if in_nd2 and in_lif:
                    cb.setStyleSheet(f"color:{C[1]};font-weight:600;")
                else:
                    cb.setStyleSheet(f"color:{hex_c};font-weight:600;")
                _ch_filter_state[cn] = cb
                ch_filter_inner.addWidget(cb)

            if not all_channels:
                placeholder = QLabel("(勾选文件以显示通道)")
                placeholder.setStyleSheet("color:#888;")
                ch_filter_inner.addWidget(placeholder)

        # ── Cascade checkbox + update filter ──
        def on_check(item, col):
            if col != 0: return
            tree.blockSignals(True)
            st = item.checkState(0)
            def cascade(p, s):
                for i in range(p.childCount()):
                    ch = p.child(i); ch.setCheckState(0, s)
                    if ch.childCount(): cascade(ch, s)
            cascade(item, st)
            tree.blockSignals(False)
            # Debounce channel filter rebuild
            from PySide6.QtCore import QTimer as _QTimer2
            if hasattr(tree, '_filter_timer'):
                tree._filter_timer.stop()
            tree._filter_timer = _QTimer2(dlg)
            tree._filter_timer.setSingleShot(True)
            tree._filter_timer.timeout.connect(_rebuild_channel_filter)
            tree._filter_timer.start(150)
        tree.itemChanged.connect(on_check)

        # Select all toggle
        def toggle(checked):
            st = Qt2.Checked if checked else Qt2.Unchecked
            def rec(p):
                for i in range(p.childCount()):
                    ch = p.child(i); ch.setCheckState(0, st)
                    if ch.childCount(): rec(ch)
            rec(tree.invisibleRootItem())
            # Rebuild filter after select-all
            from PySide6.QtCore import QTimer as _QTimer3
            _QTimer3.singleShot(200, _rebuild_channel_filter)
        select_all.toggled.connect(toggle)

        # ── Export button ──
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        export_btn = QPushButton("📦 导出选中文件")
        export_btn.setStyleSheet("QPushButton{background:#007AFF;color:#FFF;border:none;border-radius:4px;padding:8px 20px;font-size:14px;font-weight:600;} QPushButton:hover{background:#0066D6;}")
        btn_layout.addWidget(export_btn)
        layout.addLayout(btn_layout)

        # ── Export logic ──
        def do_export():
            checked = []
            def collect(p):
                for i in range(p.childCount()):
                    ch = p.child(i)
                    k = ch.data(0, Qt2.UserRole)
                    if k and k not in ("__folder__", "__lif_container__") and ch.checkState(0) == Qt2.Checked:
                        checked.append((ch.text(0), k, ch.data(0, Qt2.UserRole + 1)))
                    if ch.childCount(): collect(ch)
            collect(tree.invisibleRootItem())
            if not checked:
                QMessageBox.information(dlg, "提示", "请至少选择一个文件。")
                return

            # Get selected channel names from filter
            selected_channels = set()
            for name, cb in _ch_filter_state.items():
                if cb.isChecked():
                    selected_channels.add(name)
            export_merge = merge_filter_cb.isChecked()
            if not export_merge and not selected_channels:
                QMessageBox.information(dlg, "提示", "请至少选择一个通道或 Merge。")
                return
            if export_merge and not merge_channel_names:
                QMessageBox.information(dlg, "提示", "请在 Merge 设置中至少选择一个通道。")
                return

            out = QFileDialog.getExistingDirectory(dlg, "选择导出文件夹", os.path.expanduser("~/Desktop"))
            if not out: return
            dlg.hide()

            from core.nd2_reader import read_pixels
            from core.lif_reader import read_lif_pixels
            from core.image_processor import get_merge_display, get_channel_display, _detect_nch
            from PIL import Image

            # Capture current LUT levels to apply to all exported files
            _blk_vals = self.controls.all_black_points()
            _wht_vals = self.controls.all_white_points()
            _br_vals = self.controls.all_brightness()
            _ct_vals = self.controls.all_contrast()

            ext = ".png" if fmt_combo.currentText() == "PNG" else ".tif"
            fmt = fmt_combo.currentText()

            total = len(checked)
            errors = []
            exported = []
            for idx, (display_name, key, fp) in enumerate(checked):
                self._update_status(f"批量导出 {idx+1}/{total}: {display_name}...")
                QApplication.processEvents()

                entry = self.file_index.get(key, {})
                ch_names = entry.get('channel_names', [])
                filename = entry.get('filename', os.path.basename(fp))
                lif_idx = entry.get('lif_image_index', -1)

                if lif_idx >= 0:
                    # LIF: build clean name "{lifstem}-{imagename}"
                    lif_stem = os.path.splitext(os.path.basename(fp))[0]
                    # Extract image name from filename format "stem [ImageName]"
                    if ' [' in filename:
                        img_name = filename.split(' [')[-1].rstrip(']')
                    elif '::' in key:
                        img_name = key.split('::')[-1]
                    else:
                        img_name = f"Image{lif_idx}"
                    base = f"{lif_stem}-{img_name}"
                else:
                    base = os.path.splitext(filename)[0]

                try:
                    if lif_idx >= 0:
                        raw = read_lif_pixels(fp, image_index=lif_idx)
                    else:
                        raw = read_pixels(fp)
                    nch = _detect_nch(raw)

                    if export_merge:
                        merge_path = os.path.join(out, f"{base}_Merge{ext}")
                        merge_enabled = [
                            (ch_names[ch] if ch < len(ch_names) else f"Ch{ch+1}")
                            in merge_channel_names
                            for ch in range(nch)
                        ]
                        merge = get_merge_display(raw, ch_black=_blk_vals, ch_white=_wht_vals,
                                                  ch_brightness=_br_vals, ch_contrast=_ct_vals,
                                                  channel_names=ch_names,
                                                  enabled_channels=merge_enabled)
                        merge = self._apply_scale_bar(merge, entry)
                        Image.fromarray(merge).save(merge_path, format=fmt)
                        exported.append(merge_path)

                    for ch in range(nch):
                        cn = ch_names[ch] if ch < len(ch_names) else f"Ch{ch+1}"
                        if cn not in selected_channels:
                            continue  # skip unselected channels
                        ch_path = os.path.join(out, f"{base}_{cn}{ext}")
                        img = get_channel_display(raw, channel=ch, colored=True,
                                                  channel_name=cn,
                                                  black_point=_blk_vals[ch] if ch < len(_blk_vals) else 0.0,
                                                  white_point=_wht_vals[ch] if ch < len(_wht_vals) else 255.0,
                                                  brightness=_br_vals[ch] if ch < len(_br_vals) else 0.0,
                                                  contrast=_ct_vals[ch] if ch < len(_ct_vals) else 1.0)
                        img = self._apply_scale_bar(img, entry)
                        Image.fromarray(img).save(ch_path, format=fmt)
                        exported.append(ch_path)
                except Exception as e:
                    import traceback as _tb
                    _log(f"[batch_export] ERROR on {display_name}: {e}\n{_tb.format_exc()}")
                    errors.append(f"{display_name}: {e}")

            # Verify
            missing = [f for f in exported if not os.path.exists(f)]
            if errors or missing:
                msg = ""
                if errors:
                    msg += f"{len(errors)} 个导出失败:\n" + "\n".join(errors[:10])
                if missing:
                    if msg: msg += "\n\n"
                    msg += f"{len(missing)} 个文件未写入:\n" + "\n".join(missing[:10])
                QMessageBox.warning(self, "导出问题", msg)
                self._update_status("批量导出完成 (有错误)")
            else:
                self._update_status(f"批量导出完成: {total} 个文件 → {len(exported)} 张图片 → {out}")
                QMessageBox.information(self, "导出完成", f"已导出 {total} 个文件 ({len(exported)} 张图片) 到:\n{out}")

        export_btn.clicked.connect(do_export)

        # Initialize filter (no files checked yet — show placeholder)
        _rebuild_channel_filter()

        dlg.exec()

    def open_file_from_finder(self, filepath: str):
        """Handle file opened from Finder (double-click). Adds folder to sidebar."""
        import os as _os
        if not _os.path.exists(filepath):
            _log(f"[open_file_from_finder] file not found: {filepath}")
            return
        folder = _os.path.dirname(filepath)
        self.settings.setValue("last_folder", folder)
        self._pending_open_file = filepath
        _log(f"[open_file_from_finder] pending={filepath}, folder={folder}")
        self._add_folder_scan(folder)

    def _add_folder_scan(self, folder: str):
        """Scan and add folder to existing sidebar tree.

        Runs synchronously on the main thread (~0.1s for typical folders).
        nd2/dask require the first file-open to happen on the main thread.
        """
        self._update_status(f"正在扫描 {os.path.basename(folder)}...")
        self._add_folder_root = folder
        _log(f"[_add_folder_scan] scanning {folder} (main thread)")
        try:
            file_index = scan_folder(folder, use_cache=False)
            _log(f"[_add_folder_scan] done, {len(file_index)} files")
            self._on_add_scan_finished(file_index)
        except Exception as e:
            _log(f"[_add_folder_scan] ERROR: {e}")
            import traceback as _tb
            _log(_tb.format_exc())
            self._on_scan_error(str(e))

    def _on_add_scan_finished(self, file_index: dict):
        """Add scanned folder results to sidebar."""
        root = getattr(self, '_add_folder_root', '')
        self._add_folder_root = ''
        _log(f"[_on_add_scan_finished] root={root}, found {len(file_index)} files")
        tree = build_folder_tree(file_index, root)
        self.sidebar.add_folder(tree, file_index)
        self.file_index.update(file_index)
        pending = getattr(self, '_pending_open_file', None)
        if pending:
            self._pending_open_file = None
            import os as _os
            p_base = _os.path.basename(pending)
            _log(f"[_on_add_scan_finished] looking for pending: {p_base}")
            found = None
            for key, entry in file_index.items():
                if entry.get('filepath') == pending or p_base in entry.get('filename',''):
                    found = key
                    _log(f"[_on_add_scan_finished] matched: key={key}")
                    break
            if found:
                _log(f"[_on_add_scan_finished] selecting: {found}")
                self._on_file_selected(found)
                from PySide6.QtCore import QTimer
                QTimer.singleShot(800, lambda k=found: self.sidebar.select_file(k))
            else:
                # Debug: list available keys
                _log(f"[_on_add_scan_finished] NOT FOUND! Available keys:")
                for k, e in list(file_index.items())[:10]:
                    _log(f"  key={k} fp={e.get('filepath','')} fn={e.get('filename','')}")
        self._update_status(f"已添加: {os.path.basename(root)}")


    def _on_about(self):
        QMessageBox.about(
            self,
            "关于 MicroView",
            "<h3>MicroView</h3>"
            "<p>版本 1.0.0</p>"
            "<p>一个简洁的 Nikon ND2 显微镜图像浏览器。</p>"
            "<p>功能：浏览 ND2 文件、切换通道、Merge 视图、调整亮度/对比度。</p>",
        )


# needed for PyInstaller path resolution
import sys
