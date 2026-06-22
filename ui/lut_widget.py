"""
LutCurveWidget — histogram + dual-handle LUT curve control.
Replaces brightness/contrast sliders with a visual levels adjustment.
"""
import numpy as np
from PySide6.QtCore import Qt, Signal, QRectF, QPointF
from PySide6.QtGui import QPainter, QColor, QPen, QBrush, QFont, QPolygonF, QPainterPath
from PySide6.QtWidgets import QWidget


class LutCurveWidget(QWidget):
    """Custom widget: pixel histogram with two draggable level handles.

    ┌──────────────────────────────────────────┐
    │  255 ┤                        ╱           │
    │      ┤          ██            ╱            │
    │      ┤    ██   ████   ███   ╱ ██          │
    │      ┤  ██████████████████╱██████         │
    │    0 ┤──────────────╱─────────────────────│
    │        0     ◄──►       255               │
    │           ▼ black   ▲ white               │
    └──────────────────────────────────────────┘
    """

    levels_changed = Signal(float, float)  # (black_point, white_point) in 0–255

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(80)
        self.setMouseTracking(True)

        self._dark_mode = True
        self._histogram = np.zeros(256, dtype=np.int32)
        self._black = 0.0   # 0–255
        self._white = 255.0  # 0–255
        self._dragging = None  # 'black', 'white', or None
        self._margin = 28  # px for axis labels

        self._apply_colors()

    # ── Public API ─────────────────────────────────────────────

    def set_dark_mode(self, dark: bool):
        """Theme switch — ADD_UI_COMPONENT.md 方式 B."""
        self._dark_mode = dark
        self._apply_colors()
        self.update()

    def set_histogram(self, data: np.ndarray):
        """Supply 1-D uint8 pixel values for the histogram."""
        if data is None or len(data) == 0:
            self._histogram = np.zeros(256, dtype=np.int32)
        else:
            hist, _ = np.histogram(data, bins=256, range=(0, 255))
            self._histogram = hist.astype(np.int32)
        self.update()

    def set_levels(self, black: float, white: float):
        """Set handle positions from outside (e.g. channel switch)."""
        self._black = max(0.0, min(255.0, black))
        self._white = max(0.0, min(255.0, white))
        if self._black >= self._white:
            self._white = min(255.0, self._black + 2)
        self.update()

    def black_point(self) -> float:
        return self._black

    def white_point(self) -> float:
        return self._white

    # ── Colors ─────────────────────────────────────────────────

    def _apply_colors(self):
        d = self._dark_mode
        self._bg_color = QColor("#2d2d2d" if d else "#FFFFFF")
        self._hist_color = QColor(85, 85, 85, 180) if d else QColor(200, 200, 200, 200)
        self._line_color = QColor("#007AFF")
        self._handle_fill = QColor("#FFF" if d else "#333")
        self._handle_stroke = QColor("#007AFF")
        self._text_color = QColor("#999" if d else "#666")
        self._grid_color = QColor(68, 68, 68, 100) if d else QColor(224, 224, 224, 200)

    # ── Coordinate helpers ─────────────────────────────────────

    def _plot_rect(self) -> QRectF:
        """The drawable area inside margins."""
        m = self._margin
        return QRectF(m, 4, self.width() - 2 * m, self.height() - 8)

    def _val_to_x(self, val: float) -> float:
        r = self._plot_rect()
        return r.left() + (val / 255.0) * r.width()

    def _x_to_val(self, x: float) -> float:
        r = self._plot_rect()
        return max(0.0, min(255.0, (x - r.left()) / r.width() * 255.0))

    # ── Mouse interaction ──────────────────────────────────────

    def _handle_at(self, pos: QPointF):
        """Return 'black', 'white', or None."""
        bx = self._val_to_x(self._black)
        wx = self._val_to_x(self._white)
        r = self._plot_rect()
        bx_pt = QPointF(bx, r.bottom())
        wx_pt = QPointF(wx, r.bottom())
        hit = 12  # px radius
        if (pos - bx_pt).manhattanLength() < hit * 2:
            return 'black'
        if (pos - wx_pt).manhattanLength() < hit * 2:
            return 'white'
        return None

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            target = self._handle_at(event.position())
            if target:
                self._dragging = target
                self.setCursor(Qt.ClosedHandCursor)
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._dragging:
            val = self._x_to_val(event.position().x())
            if self._dragging == 'black':
                self._black = max(0.0, min(self._white - 2, val))
            else:
                self._white = max(self._black + 2, min(255.0, val))
            self.levels_changed.emit(self._black, self._white)
            self.update()
            event.accept()
            return
        # Update cursor for hover
        target = self._handle_at(event.position())
        if target:
            self.setCursor(Qt.OpenHandCursor)
        else:
            self.setCursor(Qt.ArrowCursor)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._dragging:
            self._dragging = None
            self.setCursor(Qt.ArrowCursor)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    # ── Paint ──────────────────────────────────────────────────

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = self._plot_rect()

        # Background
        p.fillRect(self.rect(), self._bg_color)

        # Grid lines
        pen = QPen(self._grid_color, 1, Qt.DashLine)
        p.setPen(pen)
        for frac in (0.25, 0.5, 0.75):
            y = r.top() + frac * r.height()
            p.drawLine(QPointF(r.left(), y), QPointF(r.right(), y))
            x = r.left() + frac * r.width()
            p.drawLine(QPointF(x, r.top()), QPointF(x, r.bottom()))

        # Histogram bars
        if self._histogram.max() > 0:
            hist_max = float(self._histogram.max())
            bar_w = max(1.0, r.width() / 256.0)
            p.setPen(Qt.NoPen)
            p.setBrush(self._hist_color)
            for i, count in enumerate(self._histogram):
                if count == 0:
                    continue
                h = (count / hist_max) * r.height() * 0.85
                x = r.left() + (i / 255.0) * r.width()
                p.drawRect(QRectF(x, r.bottom() - h, bar_w + 1, h))

        # Diagonal line from (black,0) to (white,255)
        bx = self._val_to_x(self._black)
        wx = self._val_to_x(self._white)
        p.setPen(QPen(self._line_color, 2))
        p.drawLine(QPointF(bx, r.bottom()), QPointF(wx, r.top()))

        # Handles
        self._draw_handle(p, bx, r.bottom(), True)   # ▼ black
        self._draw_handle(p, wx, r.bottom(), False)   # ▲ white

        # Axis labels
        font = QFont()
        font.setPixelSize(10)
        p.setFont(font)
        p.setPen(self._text_color)
        p.drawText(QRectF(r.left() - 20, r.bottom() - 6, 20, 12), Qt.AlignRight, "0")
        p.drawText(QRectF(r.left() - 20, r.top() - 6, 20, 12), Qt.AlignRight, "255")
        p.drawText(QRectF(r.left() - 4, r.bottom() + 2, 20, 14), Qt.AlignLeft, "0")
        p.drawText(QRectF(r.right() - 20, r.bottom() + 2, 24, 14), Qt.AlignRight, "255")

        # Bottom axis labels
        bl = int(self._black)
        wh = int(self._white)
        p.drawText(QRectF(bx - 20, r.bottom() + 2, 40, 14), Qt.AlignCenter, str(bl))
        p.drawText(QRectF(wx - 20, r.bottom() + 2, 40, 14), Qt.AlignCenter, str(wh))

        p.end()

    def _draw_handle(self, p: QPainter, x: float, y: float, is_black: bool):
        """Draw a triangle handle at (x, y)."""
        size = 8
        tri = QPolygonF()
        if is_black:
            # ▼ pointing down
            tri.append(QPointF(x - size, y - size * 0.6))
            tri.append(QPointF(x + size, y - size * 0.6))
            tri.append(QPointF(x, y + size * 1.2))
        else:
            # ▲ pointing up
            tri.append(QPointF(x - size, y + size * 0.6))
            tri.append(QPointF(x + size, y + size * 0.6))
            tri.append(QPointF(x, y - size * 1.2))

        p.setPen(QPen(self._handle_stroke, 1.5))
        p.setBrush(self._handle_fill)
        p.drawPolygon(tri)
