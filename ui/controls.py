"""
Controls — per-channel brightness/contrast, batch export, naming export.
"""
import numpy as np
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox, QHBoxLayout, QLabel, QPushButton, QSlider, QVBoxLayout, QWidget,
    QButtonGroup,
)
from .lut_widget import LutCurveWidget


class ControlsWidget(QWidget):
    """Bottom control bar with per-channel LUT curve and export."""

    channel_changed = Signal(object)
    levels_changed = Signal()               # global mode: LUT dragged
    brightness_changed = Signal(float)      # global mode: BC slider moved
    contrast_changed = Signal(float)        # global mode: BC slider moved
    per_channel_changed = Signal(list, list)  # (black_list, white_list)
    export_requested = Signal()             # export merge only
    export_channels_requested = Signal()    # export all channels
    batch_export_requested = Signal()       # batch export all files
    channel_toggle_changed = Signal()       # per-channel merge/grid toggle
    global_apply_changed = Signal(bool)     # apply current display settings on file switch
    imagej_requested = Signal()             # open current file in ImageJ/Fiji

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("controlsWidget")
        self.setFixedHeight(180)
        self._dark_mode = True
        self._channel_names: list[str] = []
        self._n_channels: int = 0
        self._ch_buttons: list[QPushButton] = []
        self._ch_checkboxes: list[QCheckBox] = []
        self._ch_btn_group = QButtonGroup(self)
        self._ch_btn_group.setExclusive(True)
        self._selected_ch = -1  # -1 = all, 0,1,2... = specific channel
        self._per_black: list[float] = []
        self._per_white: list[float] = []
        self._per_brightness: list[float] = []
        self._per_contrast: list[float] = []
        self._per_channel_enabled: list[bool] = []
        self._histograms: list[np.ndarray] = []

        self._setup_ui()

    def set_dark_mode(self, dark: bool):
        """Update control button styles for light/dark mode."""
        self._dark_mode = dark
        d = dark
        # Base button style for "全部" and "自动"
        btn_bg = "#3c3c3c" if d else "#F0F0F0"
        btn_bd = "#555" if d else "#CCC"
        btn_fg = "#CCC" if d else "#555"
        btn_ho = "#4a4a4a" if d else "#E0E0E0"
        base_style = (
            f"QPushButton {{ background:{btn_bg}; border:1px solid {btn_bd}; "
            f"border-radius:3px; font-size:10px; color:{btn_fg}; }}"
            f"QPushButton:hover {{ background:{btn_ho}; }}"
            f"QPushButton:checked {{ background:#007AFF; border-color:#007AFF; color:#FFF; }}"
        )
        self.btn_all.setStyleSheet(base_style)
        self.auto_btn.setStyleSheet(base_style)
        # Rebuild per-channel button styles
        from core.image_processor import _guess_color as _gc2
        for i, btn in enumerate(self._ch_buttons):
            if i < len(self._channel_names):
                r, g, b = _gc2(self._channel_names[i], i)
                c = f"#{r:02X}{g:02X}{b:02X}"
            else:
                c = "#3498DB"
            btn.setStyleSheet(
                f"QPushButton {{ background:{btn_bg}; border:1px solid {btn_bd}; "
                f"border-radius:3px; font-size:10px; color:{btn_fg}; }}"
                f"QPushButton:checked {{ background:{c}; border-color:{c}; color:#FFF; font-weight:600; }}"
            )
        # LUT curve widget
        self.lut.set_dark_mode(dark)
        # Checkboxes: native look (same as batch export), no custom ::indicator style

    def _setup_ui(self):
        main = QVBoxLayout(self)
        main.setContentsMargins(12, 6, 12, 6)
        main.setSpacing(2)

        # ── Row 1: Channel buttons + sliders ──
        row1 = QHBoxLayout()
        row1.setSpacing(8)

        # Channel label (aligned with buttons)
        ch_label = QLabel("通道")
        ch_label.setObjectName("controlLabel")
        ch_label.setFixedWidth(28)
        row1.addWidget(ch_label, alignment=Qt.AlignTop)

        # "全部" button (outside _ch_btn_layout — survives set_channels cleanup)
        self.btn_all = QPushButton("全部")
        self.btn_all.setCheckable(True)
        self.btn_all.setChecked(True)
        self.btn_all.setFixedSize(40, 20)
        self.btn_all.clicked.connect(lambda: self._select_ch(-1))
        self._ch_btn_group.addButton(self.btn_all)
        row1.addWidget(self.btn_all, alignment=Qt.AlignTop)

        # Per-channel buttons container (horizontal)
        self._ch_btn_layout = QHBoxLayout()
        self._ch_btn_layout.setContentsMargins(0, 0, 0, 0)
        self._ch_btn_layout.setSpacing(8)
        row1.addLayout(self._ch_btn_layout)

        row1.addStretch()

        # Brightness mini slider
        b_label = QLabel("亮度")
        b_label.setObjectName("controlLabel")
        b_label.setFixedWidth(28)
        row1.addWidget(b_label, alignment=Qt.AlignVCenter)

        self.b_slider = QSlider(Qt.Horizontal)
        self.b_slider.setRange(-100, 100)
        self.b_slider.setValue(0)
        self.b_slider.setFixedWidth(80)
        self.b_slider.valueChanged.connect(self._on_slider_change)
        row1.addWidget(self.b_slider, alignment=Qt.AlignVCenter)

        self.b_value = QLabel("0")
        self.b_value.setFixedWidth(24)
        self.b_value.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.b_value.setObjectName("valueLabel")
        row1.addWidget(self.b_value, alignment=Qt.AlignVCenter)

        # Contrast mini slider
        c_label = QLabel("对比度")
        c_label.setObjectName("controlLabel")
        c_label.setFixedWidth(40)
        row1.addWidget(c_label, alignment=Qt.AlignVCenter)

        self.c_slider = QSlider(Qt.Horizontal)
        self.c_slider.setRange(10, 300)
        self.c_slider.setValue(100)
        self.c_slider.setFixedWidth(80)
        self.c_slider.valueChanged.connect(self._on_slider_change)
        row1.addWidget(self.c_slider, alignment=Qt.AlignVCenter)

        self.c_value = QLabel("1.0×")
        self.c_value.setFixedWidth(36)
        self.c_value.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.c_value.setObjectName("valueLabel")
        row1.addWidget(self.c_value, alignment=Qt.AlignVCenter)

        # Auto button
        self.auto_btn = QPushButton("自动")
        self.auto_btn.setFixedSize(36, 20)
        self.auto_btn.setToolTip("自动对比度")
        self.auto_btn.clicked.connect(self._on_auto)
        row1.addWidget(self.auto_btn, alignment=Qt.AlignVCenter)

        main.addLayout(row1)

        # ── Row 1b: Channel toggle checkboxes ──
        row1b = QHBoxLayout()
        row1b.setSpacing(8)  # match button row spacing

        # Align checkboxes under buttons: match the button row spacing
        # Buttons row: [ch_label 28px] [spacing 8] [btn_all 40px] [spacing 8] [buttons...]
        # Toggle row:  [toggle_label 28px] [spacing 8] [CB centered in 40px] [spacing 8] [checkboxes...]

        self.toggle_label = QLabel("开关")
        self.toggle_label.setObjectName("controlLabel")
        self.toggle_label.setFixedWidth(28)
        row1b.addWidget(self.toggle_label)

        # "全选" checkbox (outside _ch_checkbox_layout — survives set_channels cleanup)
        self.all_toggle_cb = QCheckBox()
        self.all_toggle_cb.setToolTip("全选 / 取消全选通道")
        self.all_toggle_cb.setChecked(True)
        self.all_toggle_cb.toggled.connect(self._on_toggle_all)
        all_cb_wrap = QWidget()
        all_cb_wrap.setFixedWidth(40)
        all_cb_inner = QHBoxLayout(all_cb_wrap)
        all_cb_inner.setContentsMargins(0, 0, 0, 0)
        all_cb_inner.setAlignment(Qt.AlignCenter)
        all_cb_inner.addWidget(self.all_toggle_cb)
        row1b.addWidget(all_cb_wrap)

        # Per-channel checkboxes container (horizontal)
        self._ch_checkbox_layout = QHBoxLayout()
        self._ch_checkbox_layout.setContentsMargins(0, 0, 0, 0)
        self._ch_checkbox_layout.setSpacing(8)
        row1b.addLayout(self._ch_checkbox_layout)

        self.global_apply_cb = QCheckBox("应用到全局")
        self.global_apply_cb.setToolTip("切换图片时，使用当前通道、LUT、亮度和对比度设置")
        self.global_apply_cb.toggled.connect(self.global_apply_changed.emit)
        row1b.addWidget(self.global_apply_cb)

        row1b.addStretch()
        main.addLayout(row1b)

        # ── Row 2: LUT curve widget ──
        self.lut = LutCurveWidget()
        self.lut.levels_changed.connect(self._on_levels_changed)
        main.addWidget(self.lut, 1)

        # ── Row 3: Export buttons ──
        row2 = QHBoxLayout()
        row2.setSpacing(6)

        row2.addStretch()

        reset_btn = QPushButton("重置")
        reset_btn.setObjectName("resetBtn")
        reset_btn.setFixedSize(40, 22)
        reset_btn.clicked.connect(self._on_reset)
        row2.addWidget(reset_btn)

        imagej_btn = QPushButton("🔬 ImageJ")
        imagej_btn.setFixedSize(80, 22)
        imagej_btn.setToolTip("在 ImageJ/Fiji 中打开当前文件")
        imagej_btn.clicked.connect(lambda: self.imagej_requested.emit())
        imagej_btn.setStyleSheet(
            "QPushButton { background: #27AE60; border: 1px solid #27AE60; border-radius: 4px;"
            "font-size: 10px; font-weight: 600; color: #FFF; }"
            "QPushButton:hover { background: #1E8449; }"
        )
        row2.addWidget(imagej_btn)

        export_btn = QPushButton("💾 导出 Merge")
        export_btn.setObjectName("exportBtn")
        export_btn.setFixedSize(90, 22)
        export_btn.clicked.connect(lambda: self.export_requested.emit())
        export_btn.setToolTip("导出当前 Merge 视图")
        row2.addWidget(export_btn)

        export_ch_btn = QPushButton("📸 导出通道")
        export_ch_btn.setFixedSize(80, 22)
        export_ch_btn.setToolTip("分别导出每个通道和 Merge")
        export_ch_btn.clicked.connect(lambda: self.export_channels_requested.emit())
        export_ch_btn.setStyleSheet("""
            QPushButton { background: #5C6BC0; border: 1px solid #5C6BC0; border-radius: 4px;
                          font-size: 10px; font-weight: 600; color: #FFF; }
            QPushButton:hover { background: #3F51B5; }
        """)
        row2.addWidget(export_ch_btn)

        batch_btn = QPushButton("📦 批量导出")
        batch_btn.setFixedSize(80, 22)
        batch_btn.setToolTip("导出当前文件夹所有文件的 Merge 和通道图")
        batch_btn.clicked.connect(lambda: self.batch_export_requested.emit())
        batch_btn.setStyleSheet("""
            QPushButton { background: #E67E22; border: 1px solid #E67E22; border-radius: 4px;
                          font-size: 10px; font-weight: 600; color: #FFF; }
            QPushButton:hover { background: #D35400; }
        """)
        row2.addWidget(batch_btn)

        main.addLayout(row2)

        # Apply initial dark mode styles
        self.set_dark_mode(self._dark_mode)

    # ── public API ─────────────────────────────────────────────

    def set_channels(self, names: list[str]):
        """Rebuild per-channel buttons and checkboxes in aligned columns."""
        # Clear old
        for btn in self._ch_buttons:
            self._ch_btn_group.removeButton(btn)
            btn.deleteLater()
        self._ch_buttons.clear()
        # Checkboxes are children of wrappers — deleting wrappers cleans them up
        self._ch_checkboxes.clear()
        while self._ch_btn_layout.count():
            w = self._ch_btn_layout.takeAt(0).widget()
            if w: w.deleteLater()
        while self._ch_checkbox_layout.count():
            w = self._ch_checkbox_layout.takeAt(0).widget()
            if w: w.deleteLater()

        self._channel_names = names
        self._n_channels = len(names)
        self._per_black = [0.0] * max(1, self._n_channels)
        self._per_white = [255.0] * max(1, self._n_channels)
        self._per_brightness = [0.0] * max(1, self._n_channels)
        self._per_contrast = [1.0] * max(1, self._n_channels)
        self._per_channel_enabled = [True] * max(1, self._n_channels)
        self.all_toggle_cb.setChecked(True)

        d = self._dark_mode
        btn_bg = "#3c3c3c" if d else "#F0F0F0"
        btn_bd = "#555" if d else "#CCC"
        btn_fg = "#CCC" if d else "#555"

        for i, name in enumerate(names):
            # Compute the effective colour for this channel via _guess_color()
            from core.image_processor import _guess_color as _gc
            r, g, b = _gc(name, i)
            c = f"#{r:02X}{g:02X}{b:02X}"
            btn = QPushButton(name)
            btn.setCheckable(True)
            btn.setFixedSize(40, 20)
            btn.clicked.connect(lambda checked, ch=i: self._select_ch(ch))
            btn.setStyleSheet(
                f"QPushButton {{ background:{btn_bg}; border:1px solid {btn_bd}; "
                f"border-radius:3px; font-size:10px; color:{btn_fg}; }}"
                f"QPushButton:checked {{ background:{c}; border-color:{c}; color:#FFF; font-weight:600; }}"
            )
            self._ch_buttons.append(btn)
            self._ch_btn_group.addButton(btn)
            self._ch_btn_layout.addWidget(btn)

            cb = QCheckBox()
            cb.setChecked(True)
            cb.setToolTip(f"切换 {name} 在 Merge 和网格中的显示")
            cb.toggled.connect(lambda checked, ch=i: self._on_toggle_ch(ch, checked))
            self._ch_checkboxes.append(cb)
            # Wrap in 40px-wide container to align with the 40px button above
            wrap = QWidget()
            wrap.setFixedWidth(40)
            inner = QHBoxLayout(wrap)
            inner.setContentsMargins(0, 0, 0, 0)
            inner.setAlignment(Qt.AlignCenter)
            inner.addWidget(cb)
            self._ch_checkbox_layout.addWidget(wrap)

        # Re-apply dark/light mode styles to new controls
        self.set_dark_mode(self._dark_mode)
        self._select_ch(-1)

    def reset_to_defaults(self):
        """Reset all channels to default levels + BC."""
        for i in range(self._n_channels):
            self._per_black[i] = 0.0
            self._per_white[i] = 255.0
            self._per_brightness[i] = 0.0
            self._per_contrast[i] = 1.0
            self._per_channel_enabled[i] = True
        for cb in self._ch_checkboxes:
            cb.setChecked(True)
        self.all_toggle_cb.setChecked(True)
        self._select_ch(-1)

    def restore_settings(self, black_list: list, white_list: list,
                         enabled_list: list = None, brightness_list=None, contrast_list=None):
        """Restore per-channel settings for a previously viewed file."""
        for i in range(min(len(black_list), self._n_channels)):
            self._per_black[i] = black_list[i]
        for i in range(min(len(white_list), self._n_channels)):
            self._per_white[i] = white_list[i]
        if brightness_list is not None:
            for i in range(min(len(brightness_list), self._n_channels)):
                self._per_brightness[i] = brightness_list[i]
        if contrast_list is not None:
            for i in range(min(len(contrast_list), self._n_channels)):
                self._per_contrast[i] = contrast_list[i]
        if enabled_list is not None:
            for i in range(min(len(enabled_list), self._n_channels)):
                self._per_channel_enabled[i] = enabled_list[i]
                if i < len(self._ch_checkboxes):
                    self._ch_checkboxes[i].setChecked(enabled_list[i])
            all_on = all(self._per_channel_enabled) if self._per_channel_enabled else False
            self.all_toggle_cb.setChecked(all_on)
        self._select_ch(-1)

    def _select_ch(self, ch: int):
        self._selected_ch = ch
        self.btn_all.setChecked(ch == -1)
        for i, btn in enumerate(self._ch_buttons):
            btn.setChecked(i == ch)
        # Update LUT to reflect selected channel's histogram + levels
        self._refresh_lut()

    def _refresh_lut(self):
        """Update LUT widget + BC sliders to current channel's values."""
        if self._selected_ch == -1:
            idx = 0
        else:
            idx = self._selected_ch
        if idx < len(self._per_black) and idx < len(self._histograms):
            hist = self._histograms[idx]
        else:
            hist = np.zeros(256, dtype=np.int32)
        black = self._per_black[idx] if idx < len(self._per_black) else 0.0
        white = self._per_white[idx] if idx < len(self._per_white) else 255.0
        b = self._per_brightness[idx] if idx < len(self._per_brightness) else 0.0
        c = self._per_contrast[idx] if idx < len(self._per_contrast) else 1.0

        self.lut.blockSignals(True)
        self.lut.set_histogram(hist)
        self.lut.set_levels(black, white)
        self.lut.blockSignals(False)

        self.b_slider.blockSignals(True)
        self.c_slider.blockSignals(True)
        self.b_slider.setValue(int(b))
        self.c_slider.setValue(int(c * 100))
        self.b_value.setText(str(int(b)))
        self.c_value.setText(f"{c:.1f}×")
        self.b_slider.blockSignals(False)
        self.c_slider.blockSignals(False)

        self.channel_changed.emit(self._selected_ch)

    def _on_toggle_ch(self, ch: int, checked: bool):
        """Handle per-channel merge/grid visibility toggle."""
        if 0 <= ch < len(self._per_channel_enabled):
            self._per_channel_enabled[ch] = checked
        # Update "全选" checkbox state
        all_on = all(self._per_channel_enabled) if self._per_channel_enabled else False
        self.all_toggle_cb.blockSignals(True)
        self.all_toggle_cb.setChecked(all_on)
        self.all_toggle_cb.blockSignals(False)
        self.channel_toggle_changed.emit()

    def _on_toggle_all(self, checked: bool):
        """Toggle all channels on/off."""
        for i in range(len(self._per_channel_enabled)):
            self._per_channel_enabled[i] = checked
            if i < len(self._ch_checkboxes):
                self._ch_checkboxes[i].blockSignals(True)
                self._ch_checkboxes[i].setChecked(checked)
                self._ch_checkboxes[i].blockSignals(False)
        self.channel_toggle_changed.emit()

    def _on_slider_change(self):
        """BC slider moved — chain with LUT: levels first, then BC fine-tune."""
        b = float(self.b_slider.value())
        c = self.c_slider.value() / 100.0
        self.b_value.setText(str(int(b)))
        self.c_value.setText(f"{c:.1f}×")

        if self._selected_ch == -1:
            for i in range(self._n_channels):
                self._per_brightness[i] = b
                self._per_contrast[i] = c
            self.brightness_changed.emit(b)
            self.contrast_changed.emit(c)
        else:
            if 0 <= self._selected_ch < self._n_channels:
                self._per_brightness[self._selected_ch] = b
                self._per_contrast[self._selected_ch] = c
            self.per_channel_changed.emit(list(self._per_black), list(self._per_white))

    def _on_levels_changed(self, black: float, white: float):
        """LUT handle was dragged — store and emit."""
        if self._selected_ch == -1:
            # Apply to all channels
            for i in range(self._n_channels):
                self._per_black[i] = black
                self._per_white[i] = white
            self.levels_changed.emit()
        else:
            if 0 <= self._selected_ch < self._n_channels:
                self._per_black[self._selected_ch] = black
                self._per_white[self._selected_ch] = white
            self.per_channel_changed.emit(list(self._per_black), list(self._per_white))

    def _on_auto(self):
        """Reset selected channel levels + BC to defaults."""
        if self._selected_ch == -1:
            for i in range(self._n_channels):
                self._per_black[i] = 0.0
                self._per_white[i] = 255.0
                self._per_brightness[i] = 0.0
                self._per_contrast[i] = 1.0
        else:
            if 0 <= self._selected_ch < self._n_channels:
                self._per_black[self._selected_ch] = 0.0
                self._per_white[self._selected_ch] = 255.0
                self._per_brightness[self._selected_ch] = 0.0
                self._per_contrast[self._selected_ch] = 1.0
        self._refresh_lut()
        self.levels_changed.emit()
        self.brightness_changed.emit(0.0)
        self.contrast_changed.emit(1.0)
        self.per_channel_changed.emit(list(self._per_black), list(self._per_white))

    def _on_reset(self):
        for i in range(self._n_channels):
            self._per_black[i] = 0.0
            self._per_white[i] = 255.0
            self._per_brightness[i] = 0.0
            self._per_contrast[i] = 1.0
        self._select_ch(-1)
        self._refresh_lut()
        self.levels_changed.emit()
        self.brightness_changed.emit(0.0)
        self.contrast_changed.emit(1.0)
        self.per_channel_changed.emit(list(self._per_black), list(self._per_white))

    # ── simple getters ───────────────────────────────────────

    def all_black_points(self) -> list[float]:
        return list(self._per_black)

    def all_white_points(self) -> list[float]:
        return list(self._per_white)

    def all_brightness(self) -> list[float]:
        return list(self._per_brightness)

    def all_contrast(self) -> list[float]:
        return list(self._per_contrast)

    def all_enabled(self) -> list[bool]:
        return list(self._per_channel_enabled)

    def global_apply_enabled(self) -> bool:
        return self.global_apply_cb.isChecked()

    def current_channel(self):
        return self._selected_ch

    def set_histograms(self, histograms: list):
        """Receive per-channel histogram data from main_window."""
        self._histograms = histograms
        self._refresh_lut()
