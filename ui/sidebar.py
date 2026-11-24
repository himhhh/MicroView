"""
Sidebar — folder tree with ND2 files + LIF containers (expandable).
"""
import os
from pathlib import Path
from PySide6.QtCore import Qt, Signal, QPoint, QMimeData, QUrl, QTimer
from PySide6.QtGui import QDrag
from PySide6.QtWidgets import (
    QApplication, QAbstractItemView, QHBoxLayout, QLabel, QLineEdit, QMenu, QPushButton,
    QTreeWidget, QTreeWidgetItem, QTreeWidgetItemIterator, QVBoxLayout, QWidget,
)


class ExportTreeWidget(QTreeWidget):
    export_name_ready = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.export_files = None
        self.setDragEnabled(True)
        self.setDragDropMode(QAbstractItemView.DragOnly)
        self.setDefaultDropAction(Qt.CopyAction)

    def _create_drag_mime_data(self):
        item = self.currentItem()
        key = item.data(0, Qt.UserRole) if item else None
        if not key or key in ("__folder__", "__lif_container__") or not self.export_files:
            return None
        paths = self.export_files(key)
        if not paths:
            return None
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(str(path)) for path in paths])
        return mime

    def startDrag(self, supported_actions):
        item = self.currentItem()
        name = ((item.data(0, Qt.UserRole + 2) or Path(item.data(0, Qt.UserRole + 1) or '').name)
                if item else '')
        mime = self._create_drag_mime_data()
        if mime is None:
            return
        drag = QDrag(self)
        drag.setMimeData(mime)
        if name:
            self.export_name_ready.emit(name)
        drag.exec(Qt.CopyAction, Qt.CopyAction)
        if name:
            # Native Office drops may return IgnoreAction or replace clipboard
            # data. Publish the source name again after leaving the drag loop.
            QTimer.singleShot(0, self, lambda value=name: self.export_name_ready.emit(value))
        drag.deleteLater()


class SidebarWidget(QWidget):
    file_selected = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(250)
        self.setMaximumWidth(420)
        self._file_index: dict = {}
        self._folder_tree: dict | None = None
        self._cropped_keys = set()
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        title = QWidget()
        title.setObjectName("sidebarTitle")
        title.setFixedHeight(44)
        tl = QHBoxLayout(title)
        tl.setContentsMargins(12, 0, 12, 0)
        tlabel = QLabel("📁 文件浏览")
        tlabel.setObjectName("sidebarTitleLabel")
        tl.addWidget(tlabel)
        layout.addWidget(title)

        self.tree = ExportTreeWidget()
        self.tree.setObjectName("fileTree")
        self.tree.setHeaderHidden(True)
        self.tree.setIndentation(20)
        self.tree.setAnimated(True)
        self.tree.setRootIsDecorated(True)
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._on_context_menu)
        self.tree.currentItemChanged.connect(self._on_item_changed)
        layout.addWidget(self.tree, 1)
        self.scan_label = QLabel("正在扫描...")
        self.scan_label.setObjectName("scanIndicator")
        self.scan_label.setAlignment(Qt.AlignCenter)
        self.scan_label.hide()
        layout.addWidget(self.scan_label)
        self.footer = QLabel("未加载文件夹")
        self.footer.setObjectName("sidebarFooter")
        self.footer.setAlignment(Qt.AlignCenter)
        self.footer.setFixedHeight(28)
        layout.addWidget(self.footer)

    def clear(self):
        self.tree.clear(); self._file_index = {}; self._folder_tree = None

    def show_scanning_indicator(self, v: bool):
        self.scan_label.setVisible(v)

    def set_cropped_files(self, keys):
        self._cropped_keys = set(keys)
        iterator = QTreeWidgetItemIterator(self.tree)
        while iterator.value():
            self._update_crop_marker(iterator.value())
            iterator += 1

    def _update_crop_marker(self, item):
        key = item.data(0, Qt.UserRole)
        if not key or key in ('__folder__', '__lif_container__'):
            return
        if item.data(0, Qt.UserRole + 3) is None:
            item.setData(0, Qt.UserRole + 3, item.text(0))
            item.setData(0, Qt.UserRole + 4, item.toolTip(0))
        text = item.data(0, Qt.UserRole + 3)
        tip = item.data(0, Qt.UserRole + 4)
        cropped = key in self._cropped_keys
        item.setText(0, f'✂ {text}' if cropped else text)
        item.setToolTip(0, f'{tip}\n已裁剪' if cropped else tip)

    def populate(self, folder_tree: dict, file_index: dict[str, dict]):
        """Replace entire tree (File > Open Folder)."""
        self.clear()
        self._file_index = file_index
        root_name = folder_tree.get("name", "")
        root_item = QTreeWidgetItem(self.tree)
        cnt = self._count_all(folder_tree)
        root_item.setText(0, f"📁 {root_name}  ({cnt})")
        root_item.setData(0, Qt.UserRole, "__folder__")
        root_item.setToolTip(0, folder_tree.get("path", ""))
        self._add_node(root_item, folder_tree)
        root_item.setExpanded(True)
        self._update_footer()

    def add_folder(self, folder_tree: dict, file_index: dict[str, dict]):
        """Add folder alongside existing ones (double-click)."""
        root_name = folder_tree.get("name", "")
        folder_path = folder_tree.get("path", "")
        for i in range(self.tree.topLevelItemCount()):
            existing_path = self.tree.topLevelItem(i).toolTip(0)
            if existing_path == folder_path:
                self._file_index.update(file_index)
                self._update_footer()
                return
        folder_item = QTreeWidgetItem(self.tree)
        cnt = self._count_all(folder_tree)
        folder_item.setText(0, f"📁 {root_name}  ({cnt})")
        folder_item.setData(0, Qt.UserRole, "__folder__")
        folder_item.setToolTip(0, folder_tree.get("path", ""))
        self._add_node(folder_item, folder_tree)
        folder_item.setExpanded(True)
        self._file_index.update(file_index)
        self._update_footer()

        self._update_footer()

    def _update_footer(self):
        nd2 = sum(1 for e in self._file_index.values() if e.get("lif_image_index", -1) < 0)
        lif = sum(1 for e in self._file_index.values() if e.get("lif_image_index", -1) >= 0)
        parts = []
        if nd2: parts.append(f"{nd2} ND2")
        if lif: parts.append(f"{lif} LIF")
        extra = f" ({', '.join(parts)})" if parts else ""
        self.footer.setText(f"共 {len(self._file_index)} 个文件{extra}")

    def _add_node(self, parent, node: dict):
        for name in sorted(node.get("folders", {}).keys()):
            sub = node["folders"][name]; cnt = self._count_all(sub)
            item = QTreeWidgetItem(parent)
            item.setText(0, f"📁 {name}  ({cnt})")
            item.setData(0, Qt.UserRole, "__folder__")
            item.setToolTip(0, sub.get("path", ""))
            self._add_node(item, sub)
        for lp, lif in sorted(node.get("lif_containers", {}).items(), key=lambda x: x[1]["name"]):
            imgs = lif["images"]
            lif_item = QTreeWidgetItem(parent)
            lif_item.setText(0, f"📷 {lif['name']}  ({len(imgs)})")
            lif_item.setData(0, Qt.UserRole, "__lif_container__")
            lif_item.setToolTip(0, lp)
            for img_entry in imgs:
                img_item = QTreeWidgetItem(lif_item)
                ln = Path(lp).name
                raw_name = img_entry.get("filename", "")
                prefix = f"{ln} ["
                img_name = (raw_name[len(prefix):-1]
                            if raw_name.startswith(prefix) and raw_name.endswith("]") else raw_name)
                display = f"{ln} - {img_name}"
                img_item.setText(0, f"🔬 {display}")
                img_item.setData(0, Qt.UserRole, img_entry.get("_idx_key", img_entry.get("filepath", "")))
                img_item.setData(0, Qt.UserRole + 1, img_entry.get("filepath", ""))
                img_item.setData(0, Qt.UserRole + 2, display)
                ch_names = img_entry.get("channel_names", [])
                ch_str = ", ".join(ch_names[:3]) if ch_names else f"{img_entry.get('channel_count',1)}ch"
                w, h = img_entry.get("width", 0), img_entry.get("height", 0)
                tip = f"{display}\n通道: {ch_str}"
                if w and h: tip += f"\n尺寸: {w}×{h}"
                img_item.setToolTip(0, tip)
                self._update_crop_marker(img_item)
        for entry in node.get("files", []):
            fp = entry.get("filepath", ""); name = entry.get("filename", "?")
            item = QTreeWidgetItem(parent)
            item.setText(0, f"🔬 {name}")
            item.setData(0, Qt.UserRole, entry.get("_idx_key", fp))
            item.setData(0, Qt.UserRole + 1, fp)
            item.setData(0, Qt.UserRole + 2, name)
            ch_names = entry.get("channel_names", [])
            ch_str = ", ".join(ch_names[:3]) if ch_names else f"{entry.get('channel_count',1)}ch"
            w, h = entry.get("width", 0), entry.get("height", 0)
            tip = f"{name}\n通道: {ch_str}"
            if w and h: tip += f"\n尺寸: {w}×{h}"
            item.setToolTip(0, tip)
            self._update_crop_marker(item)

    def select_file(self, key: str):
        """Find and highlight a file in the tree."""
        def find(parent):
            for i in range(parent.childCount()):
                item = parent.child(i)
                if item.data(0, Qt.UserRole) == key:
                    p = item.parent()
                    while p:
                        p.setExpanded(True)
                        p = p.parent()
                    self.tree.setCurrentItem(item)
                    self.tree.scrollToItem(item)
                    return True
                if find(item):
                    return True
            return False
        find(self.tree.invisibleRootItem())

    def _remove_folder(self, item):
        """Remove a folder node (root or sub-folder)."""
        parent = item.parent()
        if parent is None:
            idx = self.tree.indexOfTopLevelItem(item)
            if idx >= 0:
                self.tree.takeTopLevelItem(idx)
        else:
            parent.removeChild(item)
        self._update_footer()

    def _count_all(self, node: dict) -> int:
        n = len(node.get("files", []))
        for lif in node.get("lif_containers", {}).values(): n += len(lif["images"])
        for sub in node.get("folders", {}).values(): n += self._count_all(sub)
        return n
        self._update_footer()
    def _on_item_changed(self, current, previous):
        if current is None: return
        key = current.data(0, Qt.UserRole)
        if key and key not in ("__folder__", "__lif_container__"):
            self.file_selected.emit(key)

    def _on_context_menu(self, pos: QPoint):
        item = self.tree.itemAt(pos)
        if item is None: return
        fp = item.data(0, Qt.UserRole + 1)
        key = item.data(0, Qt.UserRole)
        menu = QMenu(self)
        actions = {}

        # ── Folder nodes (root or sub-folder) ──
        if key == "__folder__":
            actions["close"] = menu.addAction("关闭文件夹")
            actions["reveal"] = menu.addAction("在 Finder 中显示")
            act = menu.exec(self.tree.viewport().mapToGlobal(pos))
            if act == actions["close"]:
                self._remove_folder(item)
            elif act == actions["reveal"]:
                import subprocess, sys as _sys
                fp2 = item.toolTip(0) or ''
                if fp2:
                    if _sys.platform == 'darwin': subprocess.run(['open', '-R', fp2])
                    else: subprocess.run(['explorer', '/select,', fp2])
            return

        # ── LIF container nodes ──
        if key == "__lif_container__":
            if item.isExpanded():
                actions["collapse"] = menu.addAction("折叠")
            else:
                actions["expand"] = menu.addAction("展开")
            actions["reveal"] = menu.addAction("在 Finder 中显示")
            act = menu.exec(self.tree.viewport().mapToGlobal(pos))
            if act == actions.get("collapse"):
                item.setExpanded(False)
            elif act == actions.get("expand"):
                item.setExpanded(True)
            elif act == actions.get("reveal"):
                import subprocess, sys as _sys
                fp2 = item.toolTip(0) or ''
                if fp2:
                    if _sys.platform == 'darwin': subprocess.run(['open', '-R', fp2])
                    else: subprocess.run(['explorer', '/select,', fp2])
            return

        # ── File items ──
        if not fp: return
        actions["copy_name"] = menu.addAction("复制文件名")
        actions["copy_path"] = menu.addAction("复制图片路径")
        actions["reveal"] = menu.addAction("在 Finder 中显示")
        act = menu.exec(self.tree.viewport().mapToGlobal(pos))
        if act == actions["copy_name"]:
            name = item.data(0, Qt.UserRole + 2) or Path(fp).name
            QApplication.clipboard().setText(name)
        elif act == actions["copy_path"]:
            QApplication.clipboard().setText(fp)
        elif act == actions["reveal"]:
            import subprocess, sys as _sys
            if _sys.platform == 'darwin':
                subprocess.run(['open', '-R', fp])
            else:
                subprocess.run(["explorer", "/select,", fp])
