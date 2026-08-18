"""
Viewer — multi-panel with synced zoom/pan or Merge-only view.
"""
import numpy as np
from PySide6.QtCore import Qt, QRectF, Signal, QPoint, QTimer
from PySide6.QtGui import QImage, QPainter, QPixmap, QWheelEvent, QMouseEvent, QColor, QTransform, QNativeGestureEvent
from PySide6.QtWidgets import (
    QGraphicsView, QGraphicsScene, QGraphicsPixmapItem,
    QGridLayout, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget,
)

# ── Synced Graphics View ──────────────────────────────────────

class SyncedView(QGraphicsView):
    """QGraphicsView that syncs zoom/pan with peer views."""
    _sync_group: list = []

    def __init__(self, parent=None):
        super().__init__(parent)
        self._zoom = 1.0
        self._pan_start: QPoint | None = None
        self._syncing = False
        self._wheel_timer = QTimer(self)
        self._wheel_timer.setSingleShot(True)
        self._wheel_timer.setInterval(60)
        self._pending_factor = 1.0
        self._on_zoom_changed = None  # callback(zoom_float) set by ViewerWidget
        self.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        self.setDragMode(QGraphicsView.NoDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorUnderMouse)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setViewportUpdateMode(QGraphicsView.SmartViewportUpdate)
        self.setBackgroundBrush(QColor(30, 30, 30))
        self.setFrameShape(QGraphicsView.NoFrame)
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self._item: QGraphicsPixmapItem | None = None

    def set_image(self, pixmap: QPixmap):
        self._scene.clear()
        self._item = QGraphicsPixmapItem(pixmap)
        self._scene.addItem(self._item)
        self._scene.setSceneRect(QRectF(pixmap.rect()))
        self.reset_zoom()

    def reset_zoom(self):
        self.resetTransform()
        self.fitInView(self._scene.sceneRect(), Qt.KeepAspectRatio)
        self._zoom = self.transform().m11()
        self._notify_zoom()

    def _notify_zoom(self):
        if self._on_zoom_changed:
            self._on_zoom_changed(self._zoom)

    # ── sync helpers ──

    def _sync_all(self):
        if self._syncing:
            return
        self._syncing = True
        t = self.transform()
        # Get the center point of the viewport in scene coords
        vp_center = self.mapToScene(self.viewport().rect().center())
        for peer in SyncedView._sync_group:
            if peer is not self and peer.isVisible():
                peer.setTransform(t)
                peer.centerOn(vp_center)
                peer._zoom = t.m11()
        self._syncing = False

    def _sync_pan(self):
        if self._syncing:
            return
        self._syncing = True
        vp_center = self.mapToScene(self.viewport().rect().center())
        for peer in SyncedView._sync_group:
            if peer is not self and peer.isVisible():
                peer.centerOn(vp_center)
        self._syncing = False

    # ── events ──

    def wheelEvent(self, event: QWheelEvent):
        delta = event.angleDelta().y()
        factor = 1.15 if delta > 0 else 1.0 / 1.15
        # Mouse wheel (NoScrollPhase): apply immediately
        if event.phase() == Qt.ScrollPhase.NoScrollPhase:
            z = self._zoom * factor
            if 0.02 <= z <= 50.0:
                self.scale(factor, factor)
                self._zoom = z
                self._sync_all()
                self._notify_zoom()
            return
        # Trackpad scroll: delay — may be superseded by native gesture
        self._pending_factor = self._zoom * factor / self._zoom
        if not self._wheel_timer.isActive():
            self._wheel_timer.timeout.connect(self._apply_wheel)
        self._wheel_timer.start()

    def _apply_wheel(self):
        z = self._zoom * self._pending_factor
        if 0.02 <= z <= 50.0:
            self.scale(self._pending_factor, self._pending_factor)
            self._zoom = z
            self._sync_all()
            self._notify_zoom()

    def event(self, event):
        """Handle native gestures (trackpad pinch-to-zoom + two-finger pan)."""
        if isinstance(event, QNativeGestureEvent):
            self._wheel_timer.stop()  # cancel pending wheel — gesture won
            gt = event.gestureType()
            if gt == Qt.ZoomNativeGesture:
                factor = 1.0 + event.value()
                z = self._zoom * factor
                if 0.02 <= z <= 50.0:
                    self.scale(factor, factor)
                    self._zoom = z
                    self._sync_all()
                    self._notify_zoom()
                return True
            if gt == Qt.PanNativeGesture:
                d = event.delta()
                if d:
                    self.horizontalScrollBar().setValue(
                        int(self.horizontalScrollBar().value() - d.x()))
                    self.verticalScrollBar().setValue(
                        int(self.verticalScrollBar().value() - d.y()))
                    self._sync_pan()
                return True
        return super().event(event)

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            self._pan_start = event.position().toPoint()
            self.setCursor(Qt.ClosedHandCursor)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._pan_start is not None:
            d = event.position().toPoint() - self._pan_start
            self._pan_start = event.position().toPoint()
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - d.x())
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - d.y())
            self._sync_pan()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            self._pan_start = None
            self.setCursor(Qt.ArrowCursor)
        super().mouseReleaseEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Keep scene centered after resize
        if self._item:
            self.fitInView(self._scene.sceneRect(), Qt.KeepAspectRatio)
            self._zoom = self.transform().m11()


# ── Zoomable Merge View (standalone, not synced) ──────────────

class _ZoomView(QGraphicsView):
    zoom_changed = Signal(float)
    def __init__(self, scene, parent=None):
        super().__init__(scene, parent)
        self._zoom = 1.0; self._pan_start = None
        self._wheel_timer = QTimer(self)
        self._wheel_timer.setSingleShot(True)
        self._wheel_timer.setInterval(60)
        self._pending_factor = 1.0
        self.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        self.setDragMode(QGraphicsView.NoDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorUnderMouse)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setViewportUpdateMode(QGraphicsView.SmartViewportUpdate)
        self.setBackgroundBrush(QColor(50, 50, 50))
    def wheelEvent(self, e: QWheelEvent):
        d = e.angleDelta().y()
        f = 1.15 if d > 0 else 1.0 / 1.15
        # Mouse wheel: immediate
        if e.phase() == Qt.ScrollPhase.NoScrollPhase:
            z = self._zoom * f
            if 0.05 <= z <= 50.0:
                self.scale(f, f); self._zoom = z
                self.zoom_changed.emit(self._zoom)
            return
        # Trackpad scroll: delayed (may be superseded by gesture)
        self._pending_factor = self._zoom * f / self._zoom
        if not self._wheel_timer.isActive():
            self._wheel_timer.timeout.connect(self._apply_wheel)
        self._wheel_timer.start()

    def _apply_wheel(self):
        z = self._zoom * self._pending_factor
        if 0.05 <= z <= 50.0:
            self.scale(self._pending_factor, self._pending_factor)
            self._zoom = z
            self.zoom_changed.emit(self._zoom)

    def event(self, ev):
        """Handle native gestures (trackpad pinch-to-zoom)."""
        if isinstance(ev, QNativeGestureEvent):
            self._wheel_timer.stop()  # cancel pending wheel — gesture won
            gt = ev.gestureType()
            if gt == Qt.ZoomNativeGesture:
                f = 1.0 + ev.value()
                z = self._zoom * f
                if 0.05 <= z <= 50.0:
                    self.scale(f, f); self._zoom = z
                    self.zoom_changed.emit(self._zoom)
                return True
            if gt == Qt.PanNativeGesture:
                d = ev.delta()
                if d:
                    self.horizontalScrollBar().setValue(
                        int(self.horizontalScrollBar().value() - d.x()))
                    self.verticalScrollBar().setValue(
                        int(self.verticalScrollBar().value() - d.y()))
                return True
        return super().event(ev)

    def mousePressEvent(self, e: QMouseEvent):
        if e.button() == Qt.LeftButton: self._pan_start = e.position().toPoint(); self.setCursor(Qt.ClosedHandCursor)
        super().mousePressEvent(e)
    def mouseMoveEvent(self, e: QMouseEvent):
        if self._pan_start is not None:
            d = e.position().toPoint() - self._pan_start; self._pan_start = e.position().toPoint()
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - d.x())
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - d.y())
        super().mouseMoveEvent(e)
    def mouseReleaseEvent(self, e: QMouseEvent):
        if e.button() == Qt.LeftButton: self._pan_start = None; self.setCursor(Qt.ArrowCursor)
        super().mouseReleaseEvent(e)
    def reset_zoom(self): self.resetTransform(); self._zoom = 1.0; self.zoom_changed.emit(self._zoom)


# ── Main Viewer Widget ─────────────────────────────────────────

class ViewerWidget(QWidget):
    channel_clicked = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("viewerWidget")
        self._dark_mode = True
        self._multi_mode = True
        self._cached_merge = None
        self._cached_channels: list = []
        self._cached_names: list = []
        self._cached_colors: list = []
        self._sync_views: list[SyncedView] = []
        self._setup_ui()

    def set_dark_mode(self, dark: bool):
        """Update all viewer styles for light/dark mode."""
        self._dark_mode = dark
        self._apply_styles()
        if self._cached_merge is not None:
            self._render()

    def _apply_styles(self):
        """(Re)apply styles based on current dark_mode."""
        d = self._dark_mode
        # Color palette
        bar_bg    = "#3a3a3a" if d else "#e8e8e8"
        lbl_color = "#CCC" if d else "#555"
        btn_bg    = "#555" if d else "#ddd"
        btn_bdr   = "#777" if d else "#bbb"
        btn_color = "#CCC" if d else "#333"
        btn_hover = "#666" if d else "#ccc"
        merge_lb  = "#FFF" if d else "#222"
        view_bg   = QColor(30, 30, 30) if d else QColor(235, 235, 235)
        zoom_bg   = QColor(50, 50, 50) if d else QColor(220, 220, 220)

        if hasattr(self, 'single_view'):
            self.single_view.setBackgroundBrush(zoom_bg)

        style = f"""
            #viewerBar {{ background: {bar_bg}; }}
            QPushButton {{
                background: {btn_bg}; border: 1px solid {btn_bdr};
                border-radius: 3px; color: {btn_color}; font-size: 11px;
            }}
            QPushButton:hover {{ background: {btn_hover}; }}
            QPushButton:checked {{ background: #007AFF; border-color: #007AFF; color: #FFF; }}
        """
        if hasattr(self, 'btn_multi'):
            self.btn_multi.setStyleSheet(style)
            self.btn_single.setStyleSheet(style)
            self.reset_zoom_btn.setStyleSheet(style)
        if hasattr(self, 'mode_label'):
            self.mode_label.setStyleSheet(f"color: {lbl_color}; font-size: 11px;")
        if hasattr(self, 'zoom_label'):
            self.zoom_label.setStyleSheet(f"color: {lbl_color}; font-size: 11px;")
        if hasattr(self, 'bar'):
            self.bar.setStyleSheet(f"#viewerBar {{ background: {bar_bg}; }}")

        # Placeholder
        if hasattr(self, 'placeholder'):
            ph_color = "#999" if d else "#888"
            ph_bg = "#1e1e1e" if d else "#F5F5F5"
            self.placeholder.setStyleSheet(f"color: {ph_color}; font-size: 16px; background: {ph_bg};")

        # Update Merge title color and view backgrounds
        for v in self._sync_views:
            v.setBackgroundBrush(view_bg)

    def _setup_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Toggle bar
        self.bar = QWidget(); self.bar.setObjectName("viewerBar"); self.bar.setFixedHeight(32)
        bl = QHBoxLayout(self.bar); bl.setContentsMargins(8, 0, 8, 0); bl.setSpacing(6)
        self.mode_label = QLabel("视图:"); bl.addWidget(self.mode_label)
        self.btn_multi = QPushButton("多通道"); self.btn_multi.setCheckable(True); self.btn_multi.setChecked(True)
        self.btn_multi.setFixedSize(64, 22); self.btn_multi.clicked.connect(lambda: self._set_mode(True))
        bl.addWidget(self.btn_multi)
        self.btn_single = QPushButton("Merge"); self.btn_single.setCheckable(True); self.btn_single.setFixedSize(64, 22)
        self.btn_single.clicked.connect(lambda: self._set_mode(False))
        bl.addWidget(self.btn_single)
        bl.addStretch()
        self.reset_zoom_btn = QPushButton("🔍 重置大小")
        self.reset_zoom_btn.setFixedSize(80, 22)
        self.reset_zoom_btn.clicked.connect(self._reset_all_zoom)
        bl.addWidget(self.reset_zoom_btn)
        self.zoom_label = QLabel("100%"); bl.addWidget(self.zoom_label)
        outer.addWidget(self.bar)

        # Content stack
        self.stack = QWidget()
        sl = QVBoxLayout(self.stack); sl.setContentsMargins(0, 0, 0, 0); sl.setSpacing(0)
        outer.addWidget(self.stack, 1)

        # Multi mode: grid of SyncedViews
        self.multi_widget = QWidget()
        self.multi_grid = QGridLayout(self.multi_widget)
        self.multi_grid.setContentsMargins(2, 2, 2, 2); self.multi_grid.setSpacing(2)
        sl.addWidget(self.multi_widget)

        # Single (Merge) mode: zoomable
        self.single_widget = QWidget()
        single_l = QVBoxLayout(self.single_widget); single_l.setContentsMargins(0, 0, 0, 0); single_l.setSpacing(0)
        self.placeholder = QLabel("打开一个 ND2 或 LIF 文件以查看图像")
        self.placeholder.setAlignment(Qt.AlignCenter)
        self.scene = QGraphicsScene(self)
        self.single_view = _ZoomView(self.scene, self); self.single_view.hide()
        self.single_view.zoom_changed.connect(self._on_zoom)
        single_l.addWidget(self.placeholder, 1); single_l.addWidget(self.single_view, 1)
        sl.addWidget(self.single_widget); self.single_widget.hide()

        # Apply initial styles
        self._apply_styles()

    # ── mode ──

    def _set_mode(self, multi: bool):
        self._multi_mode = multi
        self.btn_multi.setChecked(multi); self.btn_single.setChecked(not multi)
        self.multi_widget.setVisible(multi); self.single_widget.setVisible(not multi)
        if self._cached_merge is not None:
            self._render()

    # ── display ──

    def display_image(self, merge_rgb, channel_imgs, channel_names, channel_colors_hex=None,
                      preserve_view: bool = False):
        zoom_state = self.get_zoom_state() if preserve_view and self._cached_merge is not None else None
        self._cached_merge = merge_rgb
        self._cached_channels = channel_imgs
        self._cached_names = channel_names
        self._cached_colors = channel_colors_hex or ["#3498DB","#2ECC71","#E74C3C","#00BCD4","#E91E63","#FFC107"]
        self._render()
        if zoom_state is not None:
            # Grid cells receive their final size after the layout event.
            # Restoring immediately is overwritten by SyncedView.resizeEvent.
            QTimer.singleShot(0, lambda state=zoom_state: self.set_zoom_state(*state))

    def _render(self):
        if self._cached_merge is None: return
        if self._multi_mode: self._render_grid()
        else: self._render_merge_only()

    def _build_merge_label(self) -> str:
        """Build an HTML 'Merge' label colored by enabled channel colors.

        Top 3 channels by color priority (blue > green > red > cyan > magenta > yellow).
        1 channel  → "Merge"  in that color
        2 channels → "Mer"/"ge"  in two colors
        3 channels → "M"/"er"/"ge"  in three colors
        No channels → plain color (dark/light mode).
        """
        colors = self._cached_colors
        if not colors:
            c = "#FFF" if self._dark_mode else "#222"
            return f"<span style='color:{c}'>Merge</span>"

        def _priority(hex_c):
            r, g, b = int(hex_c[1:3], 16), int(hex_c[3:5], 16), int(hex_c[5:7], 16)
            if b > r and b > g: return 0  # blue
            if g > r and g > b: return 1  # green
            if r > g and r > b: return 2  # red
            if b > r and g > r: return 3  # cyan
            if r > g and b > g: return 4  # magenta
            return 5                       # yellow

        top = sorted(colors, key=_priority)[:3]
        n = len(top)
        if n == 1:
            return f"<span style='color:{top[0]}'>Merge</span>"
        elif n == 2:
            return (f"<span style='color:{top[0]}'>Mer</span>"
                    f"<span style='color:{top[1]}'>ge</span>")
        else:
            return (f"<span style='color:{top[0]}'>M</span>"
                    f"<span style='color:{top[1]}'>er</span>"
                    f"<span style='color:{top[2]}'>ge</span>")

    def _render_grid(self):
        self.single_widget.hide(); self.multi_widget.show()
        # Clear old
        while self.multi_grid.count():
            w = self.multi_grid.takeAt(0).widget()
            if w: w.deleteLater()
        self._sync_views.clear()
        SyncedView._sync_group.clear()

        merge = self._cached_merge
        channels = self._cached_channels
        names = self._cached_names
        colors = self._cached_colors

        merge_html = self._build_merge_label()
        all_imgs = [(merge_html, merge, None)]  # color=None → RichText label
        for i, (img, name) in enumerate(zip(channels, names)):
            all_imgs.append((name, img, colors[i % len(colors)]))

        n = len(all_imgs)
        if n <= 2: cols, rows = n, 1
        elif n <= 4: cols, rows = 2, (n + 1) // 2
        elif n <= 6: cols, rows = 3, (n + 2) // 3
        else: cols, rows = 4, (n + 3) // 4

        view_bg = QColor(30, 30, 30) if self._dark_mode else QColor(235, 235, 235)
        for idx, (title, img, color) in enumerate(all_imgs):
            h, w = img.shape[:2]
            qimg = QImage(img.data, w, h, w * 3, QImage.Format_RGB888)
            pix = QPixmap.fromImage(qimg)

            view = SyncedView()
            view.set_image(pix)
            view.setBackgroundBrush(view_bg)
            view.setToolTip(title)
            view._on_zoom_changed = self._on_zoom
            SyncedView._sync_group.append(view)
            self._sync_views.append(view)

            wrap = QWidget()
            wl = QVBoxLayout(wrap); wl.setContentsMargins(0,0,0,0); wl.setSpacing(2)
            tlabel = QLabel(title); tlabel.setAlignment(Qt.AlignCenter)
            if idx == 0:
                tlabel.setTextFormat(Qt.RichText)
                tlabel.setStyleSheet("font-size: 12px; font-weight: 700;")
            else:
                tlabel.setStyleSheet(f"color: {color}; font-size: 12px; font-weight: 600;")
            wl.addWidget(tlabel)
            wl.addWidget(view, 1)

            row, col = idx // cols, idx % cols
            self.multi_grid.addWidget(wrap, row, col)

        for c in range(cols): self.multi_grid.setColumnStretch(c, 1)
        for r in range(rows): self.multi_grid.setRowStretch(r, 1)

    def _render_merge_only(self):
        self.multi_widget.hide(); self.single_widget.show()
        merge = self._cached_merge
        h, w = merge.shape[:2]
        qimg = QImage(merge.data, w, h, w * 3, QImage.Format_RGB888)
        pixmap = QPixmap.fromImage(qimg)
        self.scene.clear()
        self.scene.addItem(QGraphicsPixmapItem(pixmap))
        self.scene.setSceneRect(QRectF(pixmap.rect()))
        self.placeholder.hide(); self.single_view.show()
        self.single_view.reset_zoom()
        self.single_view.fitInView(self.scene.sceneRect(), Qt.KeepAspectRatio)
        self._on_zoom(self.single_view.transform().m11())

    def _on_zoom(self, zoom: float):
        self.zoom_label.setText(f"{int(zoom * 100)}%")

    def _reset_all_zoom(self):
        """Reset all views to fit-in-view."""
        if self._multi_mode:
            for v in self._sync_views:
                v.reset_zoom()
            # Sync zoom label from first view
            if self._sync_views:
                self.zoom_label.setText(f"{int(self._sync_views[0].transform().m11() * 100)}%")
        else:
            self.single_view.reset_zoom()
            self.single_view.fitInView(self.scene.sceneRect(), Qt.KeepAspectRatio)
            self.zoom_label.setText(f"{int(self.single_view.transform().m11() * 100)}%")

    def get_zoom_state(self):
        """Return (zoom, center_x, center_y) for current view."""
        if self._multi_mode and self._sync_views:
            v = self._sync_views[0]
            c = v.mapToScene(v.viewport().rect().center())
            return (v.transform().m11(), c.x(), c.y())
        elif not self._multi_mode:
            v = self.single_view
            c = v.mapToScene(v.viewport().rect().center())
            return (v.transform().m11(), c.x(), c.y())
        return (1.0, 0, 0)

    def set_zoom_state(self, zoom, cx, cy):
        """Restore zoom/pan to a previous state."""
        if self._multi_mode and self._sync_views:
            for v in self._sync_views:
                v.resetTransform()
                v.scale(zoom, zoom)
                v.centerOn(cx, cy)
                v._zoom = zoom
            self.zoom_label.setText(f"{int(zoom * 100)}%")
        elif not self._multi_mode:
            v = self.single_view
            v.resetTransform()
            v.scale(zoom, zoom)
            v.centerOn(cx, cy)
            v._zoom = zoom
            self.zoom_label.setText(f"{int(zoom * 100)}%")

    def has_image(self) -> bool:
        return self._cached_merge is not None
