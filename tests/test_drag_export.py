import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
from PIL import Image

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtCore import QCoreApplication, QEvent, QSettings, Qt
from PySide6.QtWidgets import QApplication, QTreeWidgetItem
from core.image_processor import get_channel_display
from ui.main_window import MainWindow
from ui.settings_dialog import ColorSettingsDialog


class DragExportTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = MainWindow()
        self.settings_dir = tempfile.TemporaryDirectory()
        self.window.settings = QSettings(str(Path(self.settings_dir.name) / 'settings.ini'), QSettings.IniFormat)
        self.window.viewer.set_default_crop_size(None)
        self.key = "/data/sample.nd2"
        self.raw = np.arange(3 * 16 * 16, dtype=np.uint16).reshape(3, 16, 16)
        self.window.current_filepath = self.key
        self.window.current_raw_data = self.raw
        self.window.file_index = {self.key: {
            "filepath": self.key, "channel_names": ["Blue", "Green", "Red"],
            "lif_image_index": -1,
        }}
        self.window.controls.set_channels(["Blue", "Green", "Red"])
        self.window.controls.restore_settings(
            [20, 30, 40], [210, 220, 230], [True, False, True],
            [5, 10, 15], [1.1, 1.2, 1.3],
        )

    def tearDown(self):
        self.window._render_timer.stop()
        for directory in getattr(self.window, "_drag_export_dirs", []):
            directory.cleanup()
        self.window.close()
        self.window.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        self.settings_dir.cleanup()

    def test_all_channels_with_adjustments_and_preview_merge(self):
        with patch.object(self.window, "_apply_scale_bar", side_effect=lambda img, entry, **kw: img) as scale:
            paths = self.window._prepare_drag_files(self.key)
        self.assertEqual(scale.call_count, 4)
        self.assertEqual([Path(p).name for p in paths], [
            "sample_Merge.png", "sample_Blue.png", "sample_Green.png", "sample_Red.png",
        ])
        channels = []
        for ch, name in enumerate(["Blue", "Green", "Red"]):
            expected = get_channel_display(
                self.raw, channel=ch, channel_name=name,
                black_point=20 + ch * 10, white_point=210 + ch * 10,
                brightness=5 + ch * 5, contrast=1.1 + ch * .1,
            )
            channels.append(expected)
            with Image.open(paths[ch + 1]) as image:
                np.testing.assert_array_equal(np.asarray(image), expected)
        with Image.open(paths[0]) as image:
            np.testing.assert_array_equal(np.asarray(image), np.maximum(channels[0], channels[2]))

    def test_lif_names_are_safe_unique_and_include_series(self):
        entry = self.window.file_index[self.key]
        entry.update(filepath="/data/实验.lif", filename="实验.lif [Series/2]",
                     lif_image_index=1, channel_names=["Red", "Red", "../Merge"])
        with patch.object(self.window, "_apply_scale_bar", side_effect=lambda img, entry, **kw: img):
            paths = self.window._prepare_drag_files(self.key)
        names = [Path(p).name for p in paths]
        self.assertEqual(len(set(names)), 4)
        self.assertTrue(all(name.startswith("实验-Series_2_") for name in names))
        self.assertEqual(len({Path(p).parent for p in paths}), 1)
        self.assertTrue(all(Path(p).is_file() for p in paths))

    def test_custom_centimeters_preserve_pixels_and_apply_to_every_png(self):
        settings = self.window.settings
        settings.setValue('drag_export_size_enabled', True)
        settings.setValue('drag_export_width_cm', 5.0)
        settings.setValue('drag_export_height_cm', 3.0)
        settings.setValue('drag_export_keep_aspect', False)
        with patch.object(self.window, '_apply_scale_bar', side_effect=lambda img, entry, **kw: img):
            paths = self.window._prepare_drag_files(self.key)
        for path in paths:
            with Image.open(path) as image:
                self.assertEqual(image.size, (16, 16))
                dpi_x, dpi_y = image.info['dpi']
                self.assertAlmostEqual(image.width * 2.54 / dpi_x, 5.0, delta=.01)
                self.assertAlmostEqual(image.height * 2.54 / dpi_y, 3.0, delta=.01)

    def test_aspect_lock_uses_current_image_ratio(self):
        self.window.current_raw_data = self.raw[:, :12, :]
        settings = self.window.settings
        settings.setValue('drag_export_size_enabled', True)
        settings.setValue('drag_export_width_cm', 5.0)
        settings.setValue('drag_export_height_cm', 3.0)
        settings.setValue('drag_export_keep_aspect', True)
        with patch.object(self.window, '_apply_scale_bar', side_effect=lambda img, entry, **kw: img):
            paths = self.window._prepare_drag_files(self.key)
        with Image.open(paths[0]) as image:
            dpi_x, dpi_y = image.info['dpi']
            self.assertAlmostEqual(dpi_x, dpi_y)
            self.assertAlmostEqual(image.height * 2.54 / dpi_y, 3.75, delta=.01)

    def test_disabled_custom_size_does_not_add_resolution_metadata(self):
        with patch.object(self.window, '_apply_scale_bar', side_effect=lambda img, entry, **kw: img):
            paths = self.window._prepare_drag_files(self.key)
        with Image.open(paths[0]) as image:
            self.assertNotIn('dpi', image.info)

    def test_size_settings_sync_both_dimensions_and_persist(self):
        with patch('ui.settings_dialog.QSettings', return_value=self.window.settings):
            dialog = ColorSettingsDialog(self.window._dlg_colors, self.window, image_size=(1600, 800))
            dialog._drag_size_cb.setChecked(True)
            dialog._drag_copy_name_cb.setChecked(True)
            dialog._drag_width_sb.setValue(6)
            self.assertEqual(dialog._drag_height_sb.value(), 3)
            dialog._drag_height_sb.setValue(2)
            self.assertEqual(dialog._drag_width_sb.value(), 4)
            dialog._drag_aspect_cb.setChecked(False)
            dialog._drag_height_sb.setValue(3)
            self.assertEqual(dialog._drag_width_sb.value(), 4)
            dialog._save_and_accept()
            loaded = ColorSettingsDialog(self.window._dlg_colors, self.window, image_size=(1600, 800))
            self.assertTrue(loaded._drag_size_cb.isChecked())
            self.assertTrue(loaded._drag_copy_name_cb.isChecked())
            self.assertFalse(loaded._drag_aspect_cb.isChecked())
            self.assertEqual(loaded._drag_width_sb.value(), 4)
            self.assertEqual(loaded._drag_height_sb.value(), 3)

    def test_sidebar_payload_is_files_and_containers_do_not_export(self):
        tree = self.window.sidebar.tree
        tree.blockSignals(True)
        item = QTreeWidgetItem(tree)
        item.setData(0, Qt.UserRole, self.key)
        tree.setCurrentItem(item)
        with patch.object(tree, "export_files", return_value=["/tmp/实验_Blue.png"]) as export:
            mime = tree._create_drag_mime_data()
            self.assertEqual([u.toLocalFile() for u in mime.urls()], ["/tmp/实验_Blue.png"])
            export.assert_called_once_with(self.key)
            for key in ("__folder__", "__lif_container__"):
                item.setData(0, Qt.UserRole, key)
                self.assertIsNone(tree._create_drag_mime_data())
            self.assertEqual(export.call_count, 1)

    def test_native_drag_only_allows_copy(self):
        tree = self.window.sidebar.tree
        tree.blockSignals(True)
        item = QTreeWidgetItem(tree)
        item.setData(0, Qt.UserRole, self.key)
        tree.setCurrentItem(item)
        with patch.object(tree, "export_files", return_value=["/tmp/sample.png"]):
            with patch("ui.sidebar.QDrag") as drag:
                tree.startDrag(Qt.CopyAction | Qt.MoveAction)
                drag.return_value.exec.assert_called_once_with(Qt.CopyAction, Qt.CopyAction)

    def test_drag_copies_source_name_even_when_native_target_returns_ignore(self):
        tree = self.window.sidebar.tree
        tree.blockSignals(True)
        item = QTreeWidgetItem(tree)
        item.setData(0, Qt.UserRole, self.key)
        item.setData(0, Qt.UserRole + 2, 'Control.lif - Series005')
        tree.setCurrentItem(item)
        tree.blockSignals(False)
        for enabled, action in ((False, Qt.CopyAction), (True, Qt.CopyAction), (True, Qt.IgnoreAction)):
            with self.subTest(enabled=enabled, action=action):
                QApplication.clipboard().setText('keep clipboard')
                self.window.settings.setValue('drag_export_copy_name', enabled)
                with patch.object(tree, 'export_files', return_value=['/tmp/Control-Series005_Merge.png']):
                    with patch('ui.sidebar.QDrag') as drag:
                        drag.return_value.exec.return_value = action
                        tree.startDrag(Qt.CopyAction)
                QCoreApplication.processEvents()
                expected = 'Control.lif - Series005' if enabled else 'keep clipboard'
                self.assertEqual(QApplication.clipboard().text(), expected)
        QApplication.clipboard().setText('keep clipboard')
        with patch.object(tree, 'export_files', return_value=[]):
            tree.startDrag(Qt.CopyAction)
        self.assertEqual(QApplication.clipboard().text(), 'keep clipboard')

    def test_drag_name_is_ready_before_exec_and_restored_after_target_changes_clipboard(self):
        tree = self.window.sidebar.tree
        tree.blockSignals(True)
        item = QTreeWidgetItem(tree)
        item.setData(0, Qt.UserRole, self.key)
        item.setData(0, Qt.UserRole + 2, 'Control.lif - Series005')
        tree.setCurrentItem(item)
        tree.blockSignals(False)
        self.window.settings.setValue('drag_export_copy_name', True)

        def native_drag(*args):
            self.assertEqual(QApplication.clipboard().text(), 'Control.lif - Series005')
            QApplication.clipboard().clear()
            return Qt.IgnoreAction

        with patch.object(tree, 'export_files', return_value=['/tmp/export.png']):
            with patch('ui.sidebar.QDrag') as drag:
                drag.return_value.exec.side_effect = native_drag
                tree.startDrag(Qt.CopyAction)
        QCoreApplication.processEvents()
        self.assertEqual(QApplication.clipboard().text(), 'Control.lif - Series005')

    def test_render_failure_aborts_drag_and_restores_cursor(self):
        with patch("core.image_processor.get_channel_display", side_effect=RuntimeError("test error")):
            self.assertEqual(self.window._prepare_drag_files(self.key), [])
        self.assertEqual(self.window._drag_export_dirs, [])
        self.assertIsNone(QApplication.overrideCursor())

    def test_failed_or_mismatched_selection_cannot_export_stale_pixels(self):
        self.assertEqual(self.window._prepare_drag_files("other"), [])
        self.window.current_raw_data = None
        self.assertEqual(self.window._prepare_drag_files(self.key), [])

    def test_crop_is_per_file_and_per_lif_series(self):
        self.window._crop_regions[self.key] = (2, 3, 10, 12)
        image = np.arange(16 * 16 * 3, dtype=np.uint8).reshape(16, 16, 3)
        np.testing.assert_array_equal(self.window._crop_image(image, self.key), image[3:12, 2:10])
        self.assertIs(self.window._crop_image(image, 'other.nd2'), image)
        entry1 = {'filepath': '/data/file.lif', 'lif_image_index': 0, '_idx_key': 'file:::Series001'}
        entry2 = {'filepath': '/data/file.lif', 'lif_image_index': 1, '_idx_key': 'file:::Series002'}
        self.window._crop_regions[entry1['_idx_key']] = (1, 2, 8, 9)
        with patch.object(self.window, '_apply_scale_bar', side_effect=lambda img, entry, **kw: img):
            np.testing.assert_array_equal(self.window._prepare_export_image(image, entry1), image[2:9, 1:8])
            self.assertIs(self.window._prepare_export_image(image, entry2), image)

    def test_drag_crops_before_scalebar_and_uses_cropped_cm_dimensions(self):
        self.window._crop_regions[self.key] = (2, 3, 10, 15)
        self.window.settings.setValue('drag_export_size_enabled', True)
        self.window.settings.setValue('drag_export_width_cm', 5.0)
        self.window.settings.setValue('drag_export_keep_aspect', True)
        with patch.object(self.window, '_apply_scale_bar', side_effect=lambda img, entry, **kw: img) as scale:
            paths = self.window._prepare_drag_files(self.key)
        self.assertEqual(len(paths), 4)
        self.assertTrue(all(call.args[0].shape == (12, 8, 3) for call in scale.call_args_list))
        for path in paths:
            with Image.open(path) as image:
                self.assertEqual(image.size, (8, 12))
                self.assertAlmostEqual(image.width * 2.54 / image.info['dpi'][0], 5, delta=.02)
                self.assertAlmostEqual(image.height * 2.54 / image.info['dpi'][1], 7.5, delta=.02)

    def test_single_merge_and_preview_use_confirmed_crop_and_clear(self):
        from core.image_processor import normalize_to_8bit
        self.window._cached_norm = [normalize_to_8bit(channel) for channel in self.raw]
        with patch('ui.main_window.QSettings', return_value=self.window.settings), \
                patch.object(self.window, '_get_pixel_size_um', return_value=None):
            self.window._on_crop_confirmed((2, 3, 10, 12))
            self.window._render_timer.stop()
            self.window._do_render()
            self.assertEqual(self.window.viewer._cached_merge.shape, (9, 8, 3))
            self.assertTrue(all(img.shape == (9, 8, 3) for img in self.window.viewer._cached_channels))
            path = str(Path(self.settings_dir.name) / 'cropped.png')
            self.window._save_merge(path)
            with Image.open(path) as image:
                self.assertEqual(image.size, (8, 9))
            self.window._on_crop_cleared()
            self.window._render_timer.stop()
            self.window._do_render()
            self.assertEqual(self.window.viewer._cached_merge.shape, (16, 16, 3))

    def test_crop_is_bounded_contiguous_and_never_empty(self):
        image = np.zeros((16, 16, 3), dtype=np.uint8)
        self.window._crop_regions[self.key] = (-5, -5, 100, 100)
        self.assertEqual(self.window._crop_image(image, self.key).shape, image.shape)
        self.window._crop_regions[self.key] = (16, 16, 16, 16)
        self.assertEqual(self.window._crop_image(image, self.key).shape, (1, 1, 3))
        self.window._crop_regions[self.key] = (2, 3, 10, 12)
        self.assertTrue(self.window._crop_image(image, self.key).flags.c_contiguous)

    def test_confirmed_size_is_persistent_default_without_cropping_other_files(self):
        self.window._on_crop_confirmed((2, 3, 10, 12))
        self.assertEqual(self.window.settings.value('crop_default_width_px', type=int), 8)
        self.assertEqual(self.window.settings.value('crop_default_height_px', type=int), 9)
        self.assertNotIn('other.nd2', self.window._crop_regions)
        with patch('ui.main_window.QSettings', return_value=self.window.settings):
            reloaded = MainWindow()
            try:
                self.assertEqual(reloaded.viewer._default_crop_size, (8, 9))
                self.assertEqual(reloaded._crop_regions, {})
            finally:
                reloaded.deleteLater()
                QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)

    def test_reentering_crop_uses_full_source_and_defaults_do_not_crop_new_file(self):
        from core.image_processor import normalize_to_8bit
        self.window._cached_norm = [normalize_to_8bit(channel) for channel in self.raw]
        with patch('ui.main_window.QSettings', return_value=self.window.settings):
            self.window._on_crop_confirmed((2, 3, 10, 12))
            self.window._render_timer.stop()
            self.window._do_render()
            self.window.viewer.crop_btn.click()
            self.assertEqual(self.window.viewer._cached_merge.shape, (16, 16, 3))
            self.assertEqual(self.window.viewer.crop_width_sb.value(), 8)
            self.assertEqual(self.window.viewer.crop_height_sb.value(), 9)
            self.window.viewer.crop_cancel_btn.click()
            self.assertEqual(self.window.viewer._cached_merge.shape, (9, 8, 3))
            self.window.current_filepath = 'other.nd2'
            self.window.file_index['other.nd2'] = dict(self.window.file_index[self.key])
            self.window._do_render()
            self.window.viewer.crop_btn.click()
            self.assertEqual(self.window.viewer.crop_width_sb.value(), 8)
            self.assertEqual(self.window.viewer.crop_height_sb.value(), 9)
            self.assertNotIn('other.nd2', self.window._crop_regions)
            self.window.viewer.crop_cancel_btn.click()
            self.assertEqual(self.window.viewer._cached_merge.shape, (16, 16, 3))


if __name__ == "__main__":
    unittest.main()
