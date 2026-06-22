"""
Settings dialog — channel color mapping for ND2 and LIF (both by name).
"""
import json
from PySide6.QtCore import Qt, QSettings
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QPushButton,
    QGroupBox, QLineEdit, QGridLayout, QMessageBox,
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


class ColorSettingsDialog(QDialog):
    def __init__(self, dlg_colors_fn, parent=None):
        super().__init__(parent)
        self._dlg_colors = dlg_colors_fn
        self.setWindowTitle("设置")
        self.setMinimumSize(480, 420)
        C = self._dlg_colors()
        self.setStyleSheet(f"QDialog{{background:{C[0]};}}")

        self._nd2_rows = []   # list of (QLineEdit, QComboBox, QHBoxLayout)
        self._lif_rows = []   # list of (QLineEdit, QComboBox, QHBoxLayout)

        self._settings = QSettings("MicroView", "MicroView")
        self._setup_ui()
        self._load()

    def _setup_ui(self):
        C = self._dlg_colors()
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # ── ND2 section ──
        nd2_group = QGroupBox("ND2 通道颜色（按名称）")
        nd2_group.setStyleSheet(f"QGroupBox{{font-weight:600;color:{C[1]};}}")
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
            """Keep the add-row name field color in sync with the adjacent combo."""
            hex_c = _COLOR_HEX[_COLOR_NAMES[self._new_color.currentIndex()]]
            self._new_name.setStyleSheet(
                f"QLineEdit{{background:{C[6]};color:{hex_c};border:1px solid #999;"
                f"border-radius:3px;padding:3px 6px;font-weight:600;}}"
            )
        _sync_add_name_color()
        self._new_color.currentIndexChanged.connect(lambda _: _sync_add_name_color())

        add_btn = QPushButton("+ 添加")
        add_btn.setStyleSheet(
            f"QPushButton{{background:{C[2]};color:{C[3]};border:1px solid #999;border-radius:3px;padding:4px 10px;}}"
            f"QPushButton:hover{{background:{C[5]};}}"
        )
        add_btn.clicked.connect(lambda: self._add_nd2_row(
            name=self._new_name.text().strip(),
            color_idx=self._new_color.currentIndex(),
            deletable=True))
        add_row.addWidget(add_btn)
        add_row.addStretch()
        nd2_layout.addLayout(add_row)
        layout.addWidget(nd2_group)

        # ── LIF section ──
        lif_group = QGroupBox("LIF 通道颜色（按名称）")
        lif_group.setStyleSheet(f"QGroupBox{{font-weight:600;color:{C[1]};}}")
        lif_layout = QVBoxLayout(lif_group)
        self._lif_rows_layout = QVBoxLayout()
        lif_layout.addLayout(self._lif_rows_layout)

        # Add row at the bottom (below existing mappings)
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
                f"border-radius:3px;padding:3px 6px;font-weight:600;}}"
            )
        _sync_lif_add_color()
        self._lif_new_color.currentIndexChanged.connect(lambda _: _sync_lif_add_color())

        lif_add_btn = QPushButton("+ 添加")
        lif_add_btn.setStyleSheet(
            f"QPushButton{{background:{C[2]};color:{C[3]};border:1px solid #999;border-radius:3px;padding:4px 10px;}}"
            f"QPushButton:hover{{background:{C[5]};}}"
        )
        lif_add_btn.clicked.connect(lambda: self._add_lif_row(
            name=self._lif_new_name.text().strip(),
            color_idx=self._lif_new_color.currentIndex(),
            deletable=True))
        lif_add_row.addWidget(lif_add_btn)
        lif_add_row.addStretch()
        lif_layout.addLayout(lif_add_row)
        layout.addWidget(lif_group)

        # ── Buttons ──
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        reset_btn = QPushButton("恢复默认")
        reset_btn.setStyleSheet(
            f"QPushButton{{background:{C[2]};color:{C[3]};border:1px solid #999;border-radius:4px;padding:6px 16px;}}"
            f"QPushButton:hover{{background:{C[5]};}}"
        )
        reset_btn.clicked.connect(self._reset)
        btn_row.addWidget(reset_btn)
        cancel_btn = QPushButton("取消")
        cancel_btn.setStyleSheet(
            f"QPushButton{{background:{C[2]};color:{C[3]};border:1px solid #999;border-radius:4px;padding:6px 16px;}}"
            f"QPushButton:hover{{background:{C[5]};}}"
        )
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)
        save_btn = QPushButton("保存")
        save_btn.setStyleSheet(
            "QPushButton{background:#007AFF;color:#FFF;border:none;border-radius:4px;padding:6px 20px;font-weight:600;}"
            "QPushButton:hover{background:#0066D6;}"
        )
        save_btn.clicked.connect(self._save_and_accept)
        btn_row.addWidget(save_btn)
        layout.addLayout(btn_row)

    def _make_combo(self, C):
        combo = QComboBox()
        combo.setFixedWidth(100)
        combo.setStyleSheet(
            f"QComboBox{{background:{C[6]};color:{C[1]};border:1px solid #999;border-radius:3px;padding:4px 10px;font-size:13px;}}"
            f"QComboBox:hover{{background:{C[2]};}}"
            f"QComboBox QAbstractItemView{{background:{C[0]};selection-background-color:#007AFF;padding:4px;min-width:120px;}}"
        )
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
            """Sync the name label's text color to the current combo selection."""
            hex_c = _COLOR_HEX[_COLOR_NAMES[combo.currentIndex()]]
            name_edit.setStyleSheet(
                f"QLineEdit{{background:{C[6]};color:{hex_c};border:1px solid #999;"
                f"border-radius:3px;padding:3px 6px;font-weight:600;}}"
            )
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
                f"QPushButton:hover{{color:#E74C3C;}}"
            )
            row.addWidget(del_btn)
            del_btn.clicked.connect(lambda: self._remove_nd2_row(row_widget=row, entry=(name_edit, combo, row)))
        else:
            row.addSpacing(30)  # balance the missing delete button
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
        """Add a row to the LIF section (same pattern as _add_nd2_row)."""
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
                f"border-radius:3px;padding:3px 6px;font-weight:600;}}"
            )
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
                f"QPushButton:hover{{color:#E74C3C;}}"
            )
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

    def _load(self):
        # Load user ND2 map (or use defaults)
        raw = self._settings.value("nd2_channel_colors")
        nd2_map = {}
        if raw:
            try:
                nd2_map = json.loads(raw)
            except Exception:
                pass
        if not nd2_map:
            nd2_map = dict(_DEFAULT_ND2)

        # Build case-insensitive lookup (backward compat with old lowercase keys)
        default_names_lower = {n.lower() for n in _DEFAULT_ND2}
        nd2_lower_to_case = {}
        nd2_lower_to_color = {}
        for k, v in nd2_map.items():
            kl = k.lower()
            nd2_lower_to_case[kl] = k
            nd2_lower_to_color[kl] = v

        custom_lower = set(nd2_lower_to_case.keys()) - default_names_lower

        # Show default rows first (in fixed order, with proper case)
        for name in _DEFAULT_ND2:
            kl = name.lower()
            if kl in nd2_lower_to_color:
                try:
                    idx = _COLOR_NAMES.index(nd2_lower_to_color[kl])
                except ValueError:
                    idx = 0
                self._add_nd2_row(name, idx, deletable=False)

        # Show custom rows (with their original case)
        for kl in sorted(custom_lower):
            try:
                idx = _COLOR_NAMES.index(nd2_lower_to_color[kl])
            except ValueError:
                idx = 0
            self._add_nd2_row(nd2_lower_to_case[kl], idx, deletable=True)

        raw = self._settings.value("lif_channel_colors")
        lif_map = {}
        if raw:
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, dict):
                    lif_map = parsed
                # Old list format: silently ignored
            except Exception:
                pass
        if not lif_map:
            lif_map = dict(_DEFAULT_LIF)

        # Build case-insensitive lookup
        default_lif_lower = {n.lower() for n in _DEFAULT_LIF}
        lif_lower_to_case = {}
        lif_lower_to_color = {}
        for k, v in lif_map.items():
            kl = k.lower()
            lif_lower_to_case[kl] = k
            lif_lower_to_color[kl] = v

        custom_lif_lower = set(lif_lower_to_case.keys()) - default_lif_lower

        # Show default rows first
        for name in _DEFAULT_LIF:
            kl = name.lower()
            if kl in lif_lower_to_color:
                try:
                    idx = _COLOR_NAMES.index(lif_lower_to_color[kl])
                except ValueError:
                    idx = 0
                self._add_lif_row(name, idx, deletable=False)

        # Show custom rows
        for kl in sorted(custom_lif_lower):
            try:
                idx = _COLOR_NAMES.index(lif_lower_to_color[kl])
            except ValueError:
                idx = 0
            self._add_lif_row(lif_lower_to_case[kl], idx, deletable=True)

    def _save_and_accept(self):
        nd2_map = {}
        for name_edit, combo, _ in self._nd2_rows:
            name = name_edit.text().strip()
            if name:
                nd2_map[name] = _COLOR_NAMES[combo.currentIndex()]
        self._settings.setValue("nd2_channel_colors", json.dumps(nd2_map))

        lif_map = {}
        for name_edit, combo, _ in self._lif_rows:
            name = name_edit.text().strip()
            if name:
                lif_map[name] = _COLOR_NAMES[combo.currentIndex()]
        self._settings.setValue("lif_channel_colors", json.dumps(lif_map))
        self.accept()

    def _reset(self):
        # Clear ND2 rows by removing all items from layout
        while self._nd2_rows:
            name_edit, combo, row_layout = self._nd2_rows.pop()
            while row_layout.count():
                item = row_layout.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
            self._nd2_rows_layout.removeItem(row_layout)
        # Reload defaults
        for name, color_name in _DEFAULT_ND2.items():
            idx = _COLOR_NAMES.index(color_name)
            self._add_nd2_row(name, idx, deletable=False)
        # Clear LIF rows
        while self._lif_rows:
            name_edit, combo, row_layout = self._lif_rows.pop()
            while row_layout.count():
                item = row_layout.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
            self._lif_rows_layout.removeItem(row_layout)
        # Reload defaults
        for name, color_name in _DEFAULT_LIF.items():
            idx = _COLOR_NAMES.index(color_name)
            self._add_lif_row(name, idx, deletable=False)
        # Remove user LIF name→color overrides so LUTName auto-detection resumes
        self._settings.remove("lif_channel_colors")
