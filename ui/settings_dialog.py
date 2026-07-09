"""
Settings dialog — channel color mapping for ND2 and LIF (both by name).
"""
import json, os
from PySide6.QtCore import Qt, QSettings
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QPushButton,
    QGroupBox, QLineEdit, QGridLayout, QMessageBox, QFileDialog, QCheckBox,
    QScrollArea, QWidget, QSpinBox, QDoubleSpinBox, QFontComboBox,
)

_COLOR_NAMES = ["蓝色", "绿色", "红色", "青色", "品红", "黄色"]
_COLOR_RGB = {
    "蓝色": (0, 0, 255), "绿色": (0, 255, 0), "红色": (255, 0, 0),
    "青色": (0, 255, 255), "品红": (255, 0, 255), "黄色": (255, 255, 0),
}
_COLOR_HEX = {
    "蓝色": "#3498DB", "绿色": "#2ECC71", "红色": "#E74C3C",
    "青色": "#00BCD4", "品红": "#E91E63", "黄色": "#FFC107",
}

_DEFAULT_ND2 = {"DAPI": "蓝色", "FITC": "绿色", "TxRed": "红色",
                "GFP": "绿色", "mCherry": "品红"}
_DEFAULT_LIF = {"Blue": "蓝色", "Green": "绿色", "Red": "红色"}


def _resolve_app_path(fp):
    import os as _os, glob as _glob
    fp = fp.rstrip('/')
    if fp.endswith('.app') or _os.path.isdir(fp):
        macos_dir = _os.path.join(fp, 'Contents', 'MacOS')
        if _os.path.isdir(macos_dir):
            bins = sorted(_glob.glob(_os.path.join(macos_dir, '*')))
            for b in bins:
                if not _os.path.basename(b).startswith('.') and _os.path.isfile(b):
                    return b
    return fp


class ColorSettingsDialog(QDialog):
    def __init__(self, dlg_colors_fn, parent=None):
        super().__init__(parent)
        self._dlg_colors = dlg_colors_fn
        self.setWindowTitle("设置")
        self.setMinimumSize(500, 480)
        self.resize(520, 720)
        C = self._dlg_colors()
        self.setStyleSheet(
            f"QDialog{{background:{C[0]};}}"
            f"QLabel{{background:none;color:{C[1]};}}")

        self._nd2_rows = []   # list of (QLineEdit, QComboBox, QHBoxLayout)
        self._lif_rows = []   # list of (QLineEdit, QComboBox, QHBoxLayout)
        self._px_um_from_file = 0.0
        self._settings = QSettings("MicroView", "MicroView")

        # Scroll area
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        self._content = QWidget()
        self._content.setStyleSheet(f"background:{C[0]};")
        scroll.setWidget(self._content)
        scroll.setStyleSheet(
            f"QScrollArea{{background:{C[0]};border:none;}}"
            f"QScrollArea QWidget#qt_scrollarea_viewport{{background:{C[0]};}}")

        dlg_layout = QVBoxLayout(self)
        dlg_layout.setContentsMargins(0, 0, 0, 0)
        dlg_layout.addWidget(scroll)
        self.setLayout(dlg_layout)

        self._setup_ui()
        self._load()

    def _setup_ui(self):
        C = self._dlg_colors()
        layout = QVBoxLayout(self._content)
        layout.setSpacing(10)

        # ── ND2 section ──
        nd2_group = QGroupBox("ND2 通道颜色（按名称）")
        nd2_group.setStyleSheet(f"QGroupBox{{font-weight:600;color:{C[1]};background:{C[0]};border:1px solid #555;border-radius:4px;padding-top:16px;}}")
        nd2_layout = QVBoxLayout(nd2_group)
        self._nd2_rows_layout = QVBoxLayout()
        nd2_layout.addLayout(self._nd2_rows_layout)

        add_row = QHBoxLayout()
        self._new_name = QLineEdit()
        self._new_name.setPlaceholderText("输入通道名（如 Cy5）")
        add_row.addWidget(self._new_name)
        self._new_color = self._make_combo(C)
        add_row.addWidget(self._new_color)

        def _sync_add_name_color():
            hex_c = _COLOR_HEX[_COLOR_NAMES[self._new_color.currentIndex()]]
            self._new_name.setStyleSheet(
                f"QLineEdit{{background:{C[6]};color:{hex_c};border:1px solid #999;"
                f"border-radius:3px;padding:3px 6px;font-weight:600;}}")
        _sync_add_name_color()
        self._new_color.currentIndexChanged.connect(lambda _: _sync_add_name_color())

        add_btn = QPushButton("+ 添加")
        add_btn.setStyleSheet(
            f"QPushButton{{background:{C[2]};color:{C[3]};border:1px solid #999;"
            f"border-radius:3px;padding:4px 10px;}}"
            f"QPushButton:hover{{background:{C[5]};}}")
        add_btn.clicked.connect(lambda: self._add_nd2_row(
            name=self._new_name.text().strip(),
            color_idx=self._new_color.currentIndex(), deletable=True))
        add_row.addWidget(add_btn)
        add_row.addStretch()
        nd2_layout.addLayout(add_row)
        layout.addWidget(nd2_group)

        # ── LIF section ──
        lif_group = QGroupBox("LIF 通道颜色（按名称）")
        lif_group.setStyleSheet(f"QGroupBox{{font-weight:600;color:{C[1]};background:{C[0]};border:1px solid #555;border-radius:4px;padding-top:16px;}}")
        lif_layout = QVBoxLayout(lif_group)
        self._lif_rows_layout = QVBoxLayout()
        lif_layout.addLayout(self._lif_rows_layout)

        lif_add_row = QHBoxLayout()
        self._lif_new_name = QLineEdit()
        self._lif_new_name.setPlaceholderText("输入通道名（如 Yellow）")
        lif_add_row.addWidget(self._lif_new_name)
        self._lif_new_color = self._make_combo(C)
        lif_add_row.addWidget(self._lif_new_color)

        def _sync_lif_add_color():
            hex_c = _COLOR_HEX[_COLOR_NAMES[self._lif_new_color.currentIndex()]]
            self._lif_new_name.setStyleSheet(
                f"QLineEdit{{background:{C[6]};color:{hex_c};border:1px solid #999;"
                f"border-radius:3px;padding:3px 6px;font-weight:600;}}")
        _sync_lif_add_color()
        self._lif_new_color.currentIndexChanged.connect(lambda _: _sync_lif_add_color())

        lif_add_btn = QPushButton("+ 添加")
        lif_add_btn.setStyleSheet(
            f"QPushButton{{background:{C[2]};color:{C[3]};border:1px solid #999;"
            f"border-radius:3px;padding:4px 10px;}}"
            f"QPushButton:hover{{background:{C[5]};}}")
        lif_add_btn.clicked.connect(lambda: self._add_lif_row(
            name=self._lif_new_name.text().strip(),
            color_idx=self._lif_new_color.currentIndex(), deletable=True))
        lif_add_row.addWidget(lif_add_btn)
        lif_add_row.addStretch()
        lif_layout.addLayout(lif_add_row)
        layout.addWidget(lif_group)

        # ── ImageJ/Fiji section ──
        ij_group = QGroupBox("ImageJ/Fiji")
        ij_group.setStyleSheet(f"QGroupBox{{font-weight:600;color:{C[1]};background:{C[0]};border:1px solid #555;border-radius:4px;padding-top:16px;}}")
        ij_layout = QVBoxLayout(ij_group)
        ij_layout.setSpacing(6)

        ij_r1 = QHBoxLayout()
        self._ij_path_edit = QLineEdit()
        self._ij_path_edit.setReadOnly(True)
        self._ij_path_edit.setPlaceholderText("请选择 Fiji/ImageJ 可执行文件...")
        self._ij_path_edit.setStyleSheet(
            f"QLineEdit{{background:{C[6]};color:{C[1]};border:1px solid #999;"
            f"border-radius:3px;padding:3px 6px;}}")
        ij_r1.addWidget(self._ij_path_edit, 1)
        ij_browse_btn = QPushButton("浏览...")
        ij_browse_btn.setStyleSheet(
            f"QPushButton{{background:{C[2]};color:{C[3]};border:1px solid #999;"
            f"border-radius:3px;padding:4px 10px;}}"
            f"QPushButton:hover{{background:{C[5]};}}")
        ij_browse_btn.clicked.connect(self._browse_imagej)
        ij_r1.addWidget(ij_browse_btn)
        ij_layout.addLayout(ij_r1)

        ij_r2 = QHBoxLayout()
        self._ij_mode_combo = QComboBox()
        self._ij_mode_combo.addItems(["完整文件", "当前 Merge", "所有通道", "Merge + 所有通道"])
        self._ij_mode_combo.setFixedWidth(160)
        self._ij_mode_combo.setStyleSheet(
            f"QComboBox{{background:{C[6]};color:{C[1]};border:1px solid #999;"
            f"border-radius:3px;padding:4px 10px;font-size:13px;}}"
            f"QComboBox:hover{{background:{C[2]};}}"
            f"QComboBox QAbstractItemView{{background:{C[0]};color:{C[1]};"
            f"selection-background-color:#007AFF;padding:4px;}}")
        ij_r2.addWidget(QLabel("打开方式:"))
        ij_r2.addWidget(self._ij_mode_combo)
        ij_r2.addStretch()
        ij_layout.addLayout(ij_r2)

        self._ij_warning_label = QLabel(
            "⚠ 打开的是原始文件，亮度/对比度/LUT 等参数不会应用")
        self._ij_warning_label.setStyleSheet(f"color:#E67E22;font-size:11px;padding:2px 0;")
        self._ij_adj_cb = QCheckBox("应用本软件进行的 LUT/亮度/对比度调整")
        self._ij_adj_cb.setChecked(True)
        self._ij_adj_cb.setStyleSheet(f"color:{C[1]};font-size:12px;")
        ij_layout.addWidget(self._ij_warning_label)
        ij_layout.addWidget(self._ij_adj_cb)

        def _on_ij_mode(idx):
            self._ij_warning_label.setVisible(idx == 0)
            self._ij_adj_cb.setVisible(idx != 0)
        self._ij_mode_combo.currentIndexChanged.connect(_on_ij_mode)
        _on_ij_mode(0)
        layout.addWidget(ij_group)

        # ── Scale bar section ──
        sb_group = QGroupBox("导出比例尺")
        sb_group.setStyleSheet(f"QGroupBox{{font-weight:600;color:{C[1]};background:{C[0]};border:1px solid #555;border-radius:4px;padding-top:16px;}}")
        sb_layout = QVBoxLayout(sb_group)
        sb_layout.setSpacing(6)

        # preview + export toggles
        sb_r0 = QHBoxLayout()
        self._sb_preview_cb = QCheckBox("预览中显示")
        self._sb_preview_cb.setStyleSheet(f"color:{C[1]};")
        sb_r0.addWidget(self._sb_preview_cb)
        self._sb_export_cb = QCheckBox("导出时添加")
        self._sb_export_cb.setChecked(True)
        self._sb_export_cb.setStyleSheet(f"color:{C[1]};")
        sb_r0.addWidget(self._sb_export_cb)
        sb_r0.addStretch()
        sb_layout.addLayout(sb_r0)

        # style + position
        sb_r1 = QHBoxLayout()
        sb_r1.addWidget(QLabel("样式:"))
        self._sb_style_cb = QComboBox()
        self._sb_style_cb.addItems(["线条 + 文字", "填充矩形", "仅线条"])
        self._sb_style_cb.setFixedWidth(120)
        self._sb_style_cb.setStyleSheet(
            f"QComboBox{{background:{C[6]};color:{C[1]};border:1px solid #999;"
            f"border-radius:3px;padding:4px 10px;font-size:13px;}}"
            f"QComboBox:hover{{background:{C[2]};}}"
            f"QComboBox QAbstractItemView{{background:{C[0]};color:{C[1]};"
            f"selection-background-color:#007AFF;padding:4px;}}")
        sb_r1.addWidget(self._sb_style_cb)
        sb_r1.addStretch()
        sb_r1.addWidget(QLabel("位置:"))
        self._sb_pos_cb = QComboBox()
        self._sb_pos_cb.addItems(["右下", "左下", "右上", "左上"])
        self._sb_pos_cb.setFixedWidth(80)
        self._sb_pos_cb.setStyleSheet(
            f"QComboBox{{background:{C[6]};color:{C[1]};border:1px solid #999;"
            f"border-radius:3px;padding:4px 10px;font-size:13px;}}"
            f"QComboBox:hover{{background:{C[2]};}}"
            f"QComboBox QAbstractItemView{{background:{C[0]};color:{C[1]};"
            f"selection-background-color:#007AFF;padding:4px;}}")
        sb_r1.addWidget(self._sb_pos_cb)
        sb_layout.addLayout(sb_r1)

        # color + length
        sb_r2 = QHBoxLayout()
        sb_r2.addWidget(QLabel("颜色:"))
        self._sb_color_cb = QComboBox()
        self._sb_color_cb.addItems(["白色", "红色", "黄色", "黑色"])
        self._sb_color_cb.setFixedWidth(80)
        self._sb_color_cb.setStyleSheet(
            f"QComboBox{{background:{C[6]};color:{C[1]};border:1px solid #999;"
            f"border-radius:3px;padding:4px 10px;font-size:13px;}}"
            f"QComboBox:hover{{background:{C[2]};}}"
            f"QComboBox QAbstractItemView{{background:{C[0]};color:{C[1]};"
            f"selection-background-color:#007AFF;padding:4px;}}")
        sb_r2.addWidget(self._sb_color_cb)
        sb_r2.addStretch()
        sb_r2.addWidget(QLabel("长度(µm):"))
        self._sb_len_sb = QSpinBox()
        self._sb_len_sb.setRange(0, 1000)
        self._sb_len_sb.setToolTip("0 = 自动选择长度")
        self._sb_len_sb.setFixedWidth(75)
        self._sb_len_sb.setStyleSheet(
            f"QSpinBox{{background:{C[6]};color:{C[1]};border:1px solid #999;"
            f"border-radius:3px;padding:3px 6px;font-size:13px;}}")
        sb_r2.addWidget(QLabel("0=自动"))
        sb_r2.addWidget(self._sb_len_sb)
        sb_layout.addLayout(sb_r2)

        # thickness + font size + show label
        sb_r3 = QHBoxLayout()
        sb_r3.addWidget(QLabel("粗细:"))
        self._sb_thick_sb = QSpinBox()
        self._sb_thick_sb.setRange(1, 20)
        self._sb_thick_sb.setValue(5)
        self._sb_thick_sb.setFixedWidth(60)
        self._sb_thick_sb.setStyleSheet(
            f"QSpinBox{{background:{C[6]};color:{C[1]};border:1px solid #999;"
            f"border-radius:3px;padding:3px 6px;font-size:13px;}}")
        sb_r3.addWidget(self._sb_thick_sb)
        sb_r3.addStretch()
        sb_r3.addWidget(QLabel("字号:"))
        self._sb_font_sb = QSpinBox()
        self._sb_font_sb.setRange(1, 100)
        self._sb_font_sb.setValue(30)
        self._sb_font_sb.setFixedWidth(60)
        self._sb_font_sb.setStyleSheet(
            f"QSpinBox{{background:{C[6]};color:{C[1]};border:1px solid #999;"
            f"border-radius:3px;padding:3px 6px;font-size:13px;}}")
        sb_r3.addWidget(self._sb_font_sb)
        sb_r3.addStretch()
        self._sb_label_cb = QCheckBox("文字")
        self._sb_label_cb.setChecked(True)
        self._sb_label_cb.setStyleSheet(f"color:{C[1]};")
        sb_r3.addWidget(self._sb_label_cb)
        sb_layout.addLayout(sb_r3)

        # font family
        sb_r4 = QHBoxLayout()
        sb_r4.addWidget(QLabel("字体:"))
        self._sb_font_cb = QCheckBox("指定字体:")
        self._sb_font_cb.setChecked(True)
        self._sb_font_cb.setStyleSheet(f"color:{C[1]};")
        sb_r4.addWidget(self._sb_font_cb)
        self._sb_font_family = QFontComboBox()
        self._sb_font_family.setFixedWidth(180)
        # Default to Times New Roman
        _tnr = self._sb_font_family.findText("Times New Roman")
        if _tnr >= 0: self._sb_font_family.setCurrentIndex(_tnr)
        self._sb_font_family.setStyleSheet(
            f"QFontComboBox{{background:{C[6]};color:{C[1]};border:1px solid #999;"
            f"border-radius:3px;padding:3px 6px;font-size:12px;}}"
            f"QFontComboBox:hover{{background:{C[2]};}}"
            f"QFontComboBox QAbstractItemView{{background:{C[0]};color:{C[1]};"
            f"selection-background-color:#007AFF;padding:4px;}}")
        self._sb_font_cb.toggled.connect(self._sb_font_family.setEnabled)
        sb_r4.addWidget(self._sb_font_family)
        sb_r4.addStretch()
        sb_layout.addLayout(sb_r4)

        # pixel size info + override
        sb_px = QHBoxLayout()
        self._sb_px_info = QLabel("像素大小: 从文件读取")
        self._sb_px_info.setStyleSheet(f"color:{C[1]};font-size:11px;")
        sb_px.addWidget(self._sb_px_info)
        sb_px.addStretch()
        self._sb_px_override_cb = QCheckBox("手动覆盖(µm/px):")
        self._sb_px_override_cb.setStyleSheet(f"color:{C[1]};font-size:11px;")
        sb_px.addWidget(self._sb_px_override_cb)
        self._sb_px_override_sb = QDoubleSpinBox()
        self._sb_px_override_sb.setRange(0.001, 100.0)
        self._sb_px_override_sb.setDecimals(4)
        self._sb_px_override_sb.setValue(1.0)
        self._sb_px_override_sb.setFixedWidth(85)
        self._sb_px_override_sb.setEnabled(False)
        self._sb_px_override_sb.setStyleSheet(
            f"QDoubleSpinBox{{background:{C[6]};color:{C[1]};border:1px solid #999;"
            f"border-radius:3px;padding:3px 6px;font-size:13px;}}")
        self._sb_px_override_cb.toggled.connect(self._sb_px_override_sb.setEnabled)
        sb_px.addWidget(self._sb_px_override_sb)
        sb_layout.addLayout(sb_px)

        layout.addWidget(sb_group)

        # ── Buttons ──
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        reset_btn = QPushButton("恢复默认")
        reset_btn.setStyleSheet(
            f"QPushButton{{background:{C[2]};color:{C[3]};border:1px solid #999;"
            f"border-radius:4px;padding:6px 16px;}}"
            f"QPushButton:hover{{background:{C[5]};}}")
        reset_btn.clicked.connect(self._reset)
        btn_row.addWidget(reset_btn)
        cancel_btn = QPushButton("取消")
        cancel_btn.setStyleSheet(
            f"QPushButton{{background:{C[2]};color:{C[3]};border:1px solid #999;"
            f"border-radius:4px;padding:6px 16px;}}"
            f"QPushButton:hover{{background:{C[5]};}}")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)
        save_btn = QPushButton("保存")
        save_btn.setStyleSheet(
            "QPushButton{background:#007AFF;color:#FFF;border:none;"
            "border-radius:4px;padding:6px 20px;font-weight:600;}"
            "QPushButton:hover{background:#0066D6;}")
        save_btn.clicked.connect(self._save_and_accept)
        btn_row.addWidget(save_btn)
        layout.addLayout(btn_row)

    def _make_combo(self, C):
        combo = QComboBox()
        combo.setFixedWidth(100)
        combo.setStyleSheet(
            f"QComboBox{{background:{C[6]};color:{C[1]};border:1px solid #999;"
            f"border-radius:3px;padding:4px 10px;font-size:13px;}}"
            f"QComboBox:hover{{background:{C[2]};}}"
            f"QComboBox QAbstractItemView{{background:{C[0]};"
            f"selection-background-color:#007AFF;padding:4px;min-width:120px;}}")
        for name in _COLOR_NAMES:
            hex_c = _COLOR_HEX[name]
            combo.addItem(f"● {name}")
            combo.setItemData(combo.count() - 1, QColor(hex_c), Qt.ForegroundRole)
        return combo

    def _add_nd2_row(self, name="", color_idx=0, deletable=True):
        C = self._dlg_colors()
        name_edit = QLineEdit(name)
        name_edit.setPlaceholderText("通道名")
        if not deletable:
            name_edit.setReadOnly(True)
        combo = self._make_combo(C)
        combo.setCurrentIndex(color_idx)

        def _apply_name_color():
            hex_c = _COLOR_HEX[_COLOR_NAMES[combo.currentIndex()]]
            name_edit.setStyleSheet(
                f"QLineEdit{{background:{C[6]};color:{hex_c};border:1px solid #999;"
                f"border-radius:3px;padding:3px 6px;font-weight:600;}}")
        _apply_name_color()
        combo.currentIndexChanged.connect(lambda _: _apply_name_color())

        row = QHBoxLayout()
        row.addWidget(name_edit)
        row.addWidget(combo)
        if deletable:
            del_btn = QPushButton("✕")
            del_btn.setFixedSize(24, 24)
            del_btn.setStyleSheet(
                f"QPushButton{{background:transparent;color:{C[1]};border:none;font-size:14px;}}"
                f"QPushButton:hover{{color:#E74C3C;}}")
            row.addWidget(del_btn)
            del_btn.clicked.connect(lambda: self._remove_nd2_row(
                row_widget=row, entry=(name_edit, combo, row)))
        else:
            row.addSpacing(30)
        self._nd2_rows_layout.addLayout(row)
        self._nd2_rows.append((name_edit, combo, row))

    def _remove_nd2_row(self, row_widget, entry):
        while row_widget.count():
            item = row_widget.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._nd2_rows_layout.removeItem(row_widget)
        if entry in self._nd2_rows:
            self._nd2_rows.remove(entry)

    def _add_lif_row(self, name="", color_idx=0, deletable=True):
        C = self._dlg_colors()
        name_edit = QLineEdit(name)
        name_edit.setPlaceholderText("通道名")
        if not deletable:
            name_edit.setReadOnly(True)
        combo = self._make_combo(C)
        combo.setCurrentIndex(color_idx)

        def _apply_color():
            hex_c = _COLOR_HEX[_COLOR_NAMES[combo.currentIndex()]]
            name_edit.setStyleSheet(
                f"QLineEdit{{background:{C[6]};color:{hex_c};border:1px solid #999;"
                f"border-radius:3px;padding:3px 6px;font-weight:600;}}")
        _apply_color()
        combo.currentIndexChanged.connect(lambda _: _apply_color())

        row = QHBoxLayout()
        row.addWidget(name_edit)
        row.addWidget(combo)
        if deletable:
            del_btn = QPushButton("✕")
            del_btn.setFixedSize(24, 24)
            del_btn.setStyleSheet(
                f"QPushButton{{background:transparent;color:{C[1]};border:none;font-size:14px;}}"
                f"QPushButton:hover{{color:#E74C3C;}}")
            row.addWidget(del_btn)
            del_btn.clicked.connect(
                lambda: self._remove_lif_row(row_widget=row, entry=(name_edit, combo, row)))
        else:
            row.addSpacing(30)
        self._lif_rows_layout.addLayout(row)
        self._lif_rows.append((name_edit, combo, row))

    def _remove_lif_row(self, row_widget, entry):
        while row_widget.count():
            item = row_widget.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._lif_rows_layout.removeItem(row_widget)
        if entry in self._lif_rows:
            self._lif_rows.remove(entry)

    def _browse_imagej(self):
        import sys as _sys
        if _sys.platform == 'darwin':
            fp, _ = QFileDialog.getOpenFileName(
                self, "选择 Fiji/ImageJ（.app 或可执行文件）",
                "/Applications", "所有文件 (*)")
            if fp:
                self._ij_path_edit.setText(_resolve_app_path(fp))
        else:
            fp, _ = QFileDialog.getOpenFileName(
                self, "选择 Fiji/ImageJ 可执行文件",
                "C:\\", "可执行文件 (*.exe);;所有文件 (*)")
            if fp:
                self._ij_path_edit.setText(fp)

    def set_pixel_size_info(self, px_um):
        """Update the pixel size label AND override spinbox with current file's value."""
        if px_um and px_um > 0:
            self._sb_px_info.setText(f"像素大小: {px_um:.4f} µm/px")
            # Pre-fill override spinbox with the file's actual value
            self._sb_px_override_sb.setValue(px_um)
            self._px_um_from_file = px_um
        else:
            self._sb_px_info.setText("像素大小: 未知")
            self._sb_px_override_sb.setValue(0.0)
            self._px_um_from_file = 0.0

    def _load(self):
        # ND2
        raw = self._settings.value("nd2_channel_colors")
        nd2_map = json.loads(raw) if raw else {}
        if not nd2_map:
            nd2_map = dict(_DEFAULT_ND2)
        default_lower = {n.lower() for n in _DEFAULT_ND2}
        lower_case, lower_color = {}, {}
        for k, v in nd2_map.items():
            kl = k.lower(); lower_case[kl] = k; lower_color[kl] = v
        custom = set(lower_case.keys()) - default_lower

        for name in _DEFAULT_ND2:
            kl = name.lower()
            if kl in lower_color:
                try: idx = _COLOR_NAMES.index(lower_color[kl])
                except ValueError: idx = 0
                self._add_nd2_row(name, idx, deletable=False)
        for kl in sorted(custom):
            try: idx = _COLOR_NAMES.index(lower_color[kl])
            except ValueError: idx = 0
            self._add_nd2_row(lower_case[kl], idx, deletable=True)

        # LIF
        raw = self._settings.value("lif_channel_colors")
        lif_map = {}
        if raw:
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, dict): lif_map = parsed
            except: pass
        if not lif_map: lif_map = dict(_DEFAULT_LIF)

        default_lif = {n.lower() for n in _DEFAULT_LIF}
        lif_lc, lif_col = {}, {}
        for k, v in lif_map.items():
            kl = k.lower(); lif_lc[kl] = k; lif_col[kl] = v
        custom_lif = set(lif_lc.keys()) - default_lif

        for name in _DEFAULT_LIF:
            kl = name.lower()
            if kl in lif_col:
                try: idx = _COLOR_NAMES.index(lif_col[kl])
                except ValueError: idx = 0
                self._add_lif_row(name, idx, deletable=False)
        for kl in sorted(custom_lif):
            try: idx = _COLOR_NAMES.index(lif_col[kl])
            except ValueError: idx = 0
            self._add_lif_row(lif_lc[kl], idx, deletable=True)

        # ImageJ
        ij = self._settings.value("imagej_path", "")
        if ij: self._ij_path_edit.setText(ij)
        mode = self._settings.value("imagej_lif_mode", "完整文件")
        idx = self._ij_mode_combo.findText(mode)
        if idx >= 0: self._ij_mode_combo.setCurrentIndex(idx)
        self._ij_adj_cb.setChecked(
            self._settings.value("imagej_apply_adjustments", True, type=bool))

        # Scale bar
        self._sb_preview_cb.setChecked(
            self._settings.value("scalebar_preview", False, type=bool))
        self._sb_export_cb.setChecked(
            self._settings.value("scalebar_export", True, type=bool))
        _cmap = {"white": 0, "red": 1, "yellow": 2, "black": 3}
        self._sb_color_cb.setCurrentIndex(
            _cmap.get(self._settings.value("scalebar_color", "white"), 0))
        pm = {"br": 0, "bl": 1, "tr": 2, "tl": 3}
        self._sb_pos_cb.setCurrentIndex(
            pm.get(self._settings.value("scalebar_position", "br"), 0))
        sm = {"line_text": 0, "filled": 1, "line_only": 2}
        self._sb_style_cb.setCurrentIndex(
            sm.get(self._settings.value("scalebar_style", "line_text"), 0))
        self._sb_len_sb.setValue(
            self._settings.value("scalebar_length_um", 0, type=int))
        self._sb_thick_sb.setValue(
            self._settings.value("scalebar_thickness", 5, type=int))
        self._sb_font_sb.setValue(
            self._settings.value("scalebar_font_size", 30, type=int))
        self._sb_label_cb.setChecked(
            self._settings.value("scalebar_show_label", True, type=bool))
        ff = self._settings.value("scalebar_font_family", "Times New Roman")
        if ff:
            self._sb_font_cb.setChecked(True)
            idx = self._sb_font_family.findText(ff)
            if idx >= 0: self._sb_font_family.setCurrentIndex(idx)

        # pixel size override
        ov = self._settings.value("scalebar_pixel_size_override", 0.0, type=float)
        if ov > 0:
            self._sb_px_override_cb.setChecked(True)
            self._sb_px_override_sb.setValue(ov)

    def _save_and_accept(self):
        self._settings.setValue("nd2_channel_colors", json.dumps(
            {ed.text().strip(): _COLOR_NAMES[cb.currentIndex()]
             for ed, cb, _ in self._nd2_rows if ed.text().strip()}))
        self._settings.setValue("lif_channel_colors", json.dumps(
            {ed.text().strip(): _COLOR_NAMES[cb.currentIndex()]
             for ed, cb, _ in self._lif_rows if ed.text().strip()}))

        self._settings.setValue("imagej_path", self._ij_path_edit.text())
        self._settings.setValue("imagej_lif_mode", self._ij_mode_combo.currentText())
        self._settings.setValue("imagej_apply_adjustments", self._ij_adj_cb.isChecked())

        self._settings.setValue("scalebar_preview", self._sb_preview_cb.isChecked())
        self._settings.setValue("scalebar_export", self._sb_export_cb.isChecked())
        _cmap = {0: "white", 1: "red", 2: "yellow", 3: "black"}
        self._settings.setValue("scalebar_color",
            _cmap.get(self._sb_color_cb.currentIndex(), "white"))
        self._settings.setValue("scalebar_position",
            {0: "br", 1: "bl", 2: "tr", 3: "tl"}.get(self._sb_pos_cb.currentIndex(), "br"))
        self._settings.setValue("scalebar_style",
            {0: "line_text", 1: "filled", 2: "line_only"}.get(self._sb_style_cb.currentIndex(), "line_text"))
        self._settings.setValue("scalebar_length_um", self._sb_len_sb.value())
        self._settings.setValue("scalebar_thickness", self._sb_thick_sb.value())
        self._settings.setValue("scalebar_font_size", self._sb_font_sb.value())
        self._settings.setValue("scalebar_show_label", self._sb_label_cb.isChecked())
        if self._sb_font_cb.isChecked():
            self._settings.setValue("scalebar_font_family", self._sb_font_family.currentText())
        else:
            self._settings.remove("scalebar_font_family")
        if self._sb_px_override_cb.isChecked():
            self._settings.setValue("scalebar_pixel_size_override", self._sb_px_override_sb.value())
        else:
            self._settings.remove("scalebar_pixel_size_override")
        self.accept()

    def _reset(self):
        for lst, ly in [(self._nd2_rows, self._nd2_rows_layout),
                         (self._lif_rows, self._lif_rows_layout)]:
            while lst:
                ed, cb, rl = lst.pop()
                while rl.count():
                    it = rl.takeAt(0)
                    if it.widget(): it.widget().deleteLater()
                ly.removeItem(rl)

        for name, cn in _DEFAULT_ND2.items():
            self._add_nd2_row(name, _COLOR_NAMES.index(cn), deletable=False)
        for name, cn in _DEFAULT_LIF.items():
            self._add_lif_row(name, _COLOR_NAMES.index(cn), deletable=False)
        self._settings.remove("lif_channel_colors")

        for k in ["imagej_path", "imagej_lif_mode", "imagej_apply_adjustments",
                   "scalebar_preview", "scalebar_export", "scalebar_color",
                   "scalebar_position", "scalebar_style", "scalebar_length_um",
                   "scalebar_thickness", "scalebar_font_size", "scalebar_show_label",
                   "scalebar_font_family", "scalebar_pixel_size_override"]:
            self._settings.remove(k)

        self._ij_path_edit.clear()
        self._ij_mode_combo.setCurrentIndex(0)
        self._ij_adj_cb.setChecked(True)
        self._sb_preview_cb.setChecked(False)
        self._sb_export_cb.setChecked(True)
        self._sb_color_cb.setCurrentIndex(0)
        self._sb_pos_cb.setCurrentIndex(0)
        self._sb_style_cb.setCurrentIndex(0)
        self._sb_len_sb.setValue(0)
        self._sb_thick_sb.setValue(5)
        self._sb_font_sb.setValue(30)
        self._sb_label_cb.setChecked(True)
        self._sb_font_cb.setChecked(True)
        _tnr = self._sb_font_family.findText("Times New Roman")
        if _tnr >= 0: self._sb_font_family.setCurrentIndex(_tnr)
