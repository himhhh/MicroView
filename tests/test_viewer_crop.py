import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtCore import QCoreApplication, QEvent, QPointF, QRectF, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from ui.viewer import ViewerWidget


class ViewerCropTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_scalebar_too_long_for_crop_updates_its_physical_label(self):
        from core.image_processor import draw_scale_bar
        with patch('PIL.ImageDraw.ImageDraw.text') as text:
            draw_scale_bar(np.zeros((100, 100, 3), dtype=np.uint8), 1.0, bar_um=500)
        self.assertEqual(text.call_args.args[1], '76 µm')

    def test_live_size_fields_manual_dimensions_and_square_link(self):
        viewer = ViewerWidget()
        image = np.zeros((100, 200, 3), dtype=np.uint8)
        try:
            viewer.display_image(image, [image], ['Blue'])
            viewer.crop_btn.click()
            viewer._on_crop_selection(QRectF(20.2, 10.3, 80.4, 50.5))
            self.assertEqual(viewer.crop_width_sb.value(), 81)
            self.assertEqual(viewer.crop_height_sb.value(), 51)
            viewer.crop_width_sb.setValue(120)
            viewer.crop_height_sb.setValue(60)
            self.assertEqual(viewer._pending_crop.size().width(), 120)
            self.assertEqual(viewer._pending_crop.size().height(), 60)
            self.assertTrue(QRectF(0, 0, 200, 100).contains(viewer._pending_crop))
            viewer.crop_square_cb.setChecked(True)
            viewer.crop_height_sb.setValue(42)
            self.assertEqual(viewer.crop_width_sb.value(), 42)
            self.assertEqual(viewer._pending_crop.width(), 42)
            self.assertEqual(viewer._pending_crop.height(), 42)
        finally:
            viewer.deleteLater()
            QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)

    def test_default_size_is_centered_clamped_and_does_not_confirm_itself(self):
        viewer = ViewerWidget()
        image = np.zeros((100, 200, 3), dtype=np.uint8)
        confirmed = []
        viewer.crop_confirmed.connect(confirmed.append)
        try:
            viewer.set_default_crop_size((80, 60))
            viewer.display_image(image, [image], ['Blue'])
            viewer.crop_btn.click()
            self.assertEqual(viewer._pending_crop, QRectF(60, 20, 80, 60))
            self.assertEqual(confirmed, [])
            self.assertIsNone(viewer._crop_region)
            viewer.crop_cancel_btn.click()
            viewer.set_default_crop_size((300, 400))
            viewer.crop_btn.click()
            self.assertEqual(viewer._pending_crop, QRectF(0, 0, 200, 100))
            viewer.crop_cancel_btn.click()
            viewer.set_crop_region((10, 20, 40, 70))
            viewer.crop_btn.click()
            self.assertEqual(viewer._pending_crop, QRectF(10, 20, 30, 50))
        finally:
            viewer.deleteLater()
            QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)

    def test_selection_sync_confirm_cancel_and_clear_in_both_modes(self):
        viewer = ViewerWidget()
        viewer.resize(900, 600)
        viewer.show()
        image = np.zeros((100, 200, 3), dtype=np.uint8)
        confirmed, cleared = [], []
        viewer.crop_confirmed.connect(confirmed.append)
        viewer.crop_cleared.connect(lambda: cleared.append(True))
        try:
            for multi in (True, False):
                viewer._set_mode(multi)
                viewer.display_image(image, [image, image], ['Blue', 'Green'])
                QTest.qWait(20)
                viewer.crop_btn.click()
                views = viewer._sync_views if multi else [viewer.single_view]
                rect = QRectF(20, 10, 80, 50)
                views[-1].crop_selection_changed.emit(rect)
                self.assertTrue(all(view._crop_rect == rect for view in views))
                viewer.crop_confirm_btn.click()
                self.assertEqual(confirmed[-1], (20, 10, 100, 60))
                self.assertFalse(viewer.crop_editing)
                viewer.set_crop_region(confirmed[-1])
                viewer.crop_btn.click()
                views[-1].crop_selection_changed.emit(QRectF(0, 0, 10, 10))
                viewer.crop_cancel_btn.click()
                self.assertEqual(viewer._crop_region, (20, 10, 100, 60))
                viewer.crop_clear_btn.click()
                self.assertTrue(cleared)
                self.assertIsNone(viewer._crop_region)
        finally:
            viewer.close()
            viewer.deleteLater()
            QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)

    def test_mouse_selection_move_and_resize_are_shared(self):
        viewer = ViewerWidget()
        viewer.resize(1000, 700)
        image = np.zeros((100, 200, 3), dtype=np.uint8)
        viewer.show()
        try:
            for multi in (True, False):
                viewer.set_crop_region(None)
                viewer._set_mode(multi)
                viewer.display_image(image, [image, image], ['Blue', 'Green'])
                viewer.crop_btn.click()
                QTest.qWait(30)
                view = viewer._sync_views[-1] if multi else viewer.single_view

                def drag(start, end):
                    QTest.mousePress(view.viewport(), Qt.LeftButton, pos=view.mapFromScene(start))
                    QTest.mouseMove(view.viewport(), view.mapFromScene(end))
                    QTest.mouseRelease(view.viewport(), Qt.LeftButton, pos=view.mapFromScene(end))

                drag(QPointF(40, 20), QPointF(140, 80))
                first = QRectF(view._crop_rect)
                self.assertAlmostEqual(first.left(), 40, delta=1)
                self.assertAlmostEqual(first.width(), 100, delta=2)
                peers = viewer._sync_views if multi else [view]
                self.assertTrue(all(peer._crop_rect == first for peer in peers))
                drag(first.center(), first.center() + QPointF(10, 5))
                moved = QRectF(view._crop_rect)
                self.assertAlmostEqual(moved.width(), first.width(), delta=.01)
                self.assertAlmostEqual(moved.left(), first.left() + 10, delta=1)
                drag(moved.bottomRight(), moved.bottomRight() + QPointF(10, 5))
                self.assertGreater(view._crop_rect.width(), moved.width())
                self.assertTrue(all(peer._crop_rect == view._crop_rect for peer in peers))
                viewer.crop_cancel_btn.click()
        finally:
            viewer.close()
            viewer.deleteLater()
            QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)

    def test_square_option_constrains_draw_resize_and_pixel_bounds(self):
        viewer = ViewerWidget()
        viewer.resize(1000, 700)
        viewer.show()
        image = np.zeros((100, 200, 3), dtype=np.uint8)
        try:
            for multi in (True, False):
                viewer._set_mode(multi)
                viewer.display_image(image, [image, image], ['Blue', 'Green'])
                viewer.crop_btn.click()
                QTest.qWait(20)
                view = viewer._sync_views[-1] if multi else viewer.single_view
                viewer._on_crop_selection(QRectF(20, 10, 80, 50))
                viewer.crop_square_cb.setChecked(True)
                self.assertAlmostEqual(view._crop_rect.width(), view._crop_rect.height())

                def drag(start, end):
                    QTest.mousePress(view.viewport(), Qt.LeftButton, pos=view.mapFromScene(start))
                    QTest.mouseMove(view.viewport(), view.mapFromScene(end))
                    QTest.mouseRelease(view.viewport(), Qt.LeftButton, pos=view.mapFromScene(end))

                viewer._on_crop_selection(QRectF())
                drag(QPointF(30, 10), QPointF(80, 35))
                first = QRectF(view._crop_rect)
                self.assertAlmostEqual(first.width(), first.height())
                drag(first.bottomRight(), first.bottomRight() + QPointF(15, 5))
                self.assertAlmostEqual(view._crop_rect.width(), view._crop_rect.height())
                resized = QRectF(view._crop_rect)
                drag(QPointF(resized.right(), resized.center().y()),
                     QPointF(resized.right() + 10, resized.center().y()))
                self.assertAlmostEqual(view._crop_rect.width(), view._crop_rect.height())
                peers = viewer._sync_views if multi else [view]
                self.assertTrue(all(peer._crop_rect == view._crop_rect for peer in peers))
                viewer._on_crop_selection(QRectF(10.2, 20.7, 42.4, 42.4))
                viewer.crop_confirm_btn.click()
                x0, y0, x1, y1 = viewer._crop_region
                self.assertEqual(x1 - x0, y1 - y0)

                viewer.set_crop_region(None)
                viewer.crop_btn.click()
                drag(QPointF(190, 90), QPointF(-10, -10))
                self.assertAlmostEqual(view._crop_rect.width(), view._crop_rect.height())
                self.assertTrue(view.scene().sceneRect().contains(view._crop_rect))
                viewer.crop_square_cb.setChecked(False)
                viewer._on_crop_selection(QRectF())
                drag(QPointF(30, 10), QPointF(80, 35))
                self.assertGreater(abs(view._crop_rect.width() - view._crop_rect.height()), 10)
                viewer.crop_cancel_btn.click()
        finally:
            viewer.close()
            viewer.deleteLater()
            QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)


if __name__ == '__main__':
    unittest.main()
