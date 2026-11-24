import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtCore import QCoreApplication, QEvent, QPoint, Qt
from PySide6.QtWidgets import QApplication
from ui.sidebar import SidebarWidget


class CopyFilenameTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_right_click_copies_file_or_series_name(self):
        sidebar = SidebarWidget()
        sidebar.populate({
            'name': 'images', 'path': '/images',
            'files': [{'filepath': '/images/实验.nd2', 'filename': '实验.nd2'}],
            'lif_containers': {'/images/实验.lif': {
                'name': '实验.lif', 'images': [{
                    'filepath': '/images/实验.lif',
                    'filename': '实验.lif [Series001]',
                    '_idx_key': '/images/实验.lif:::Series001',
                }],
            }},
        }, {})
        root = sidebar.tree.topLevelItem(0)
        series = root.child(0).child(0)
        nd2 = root.child(1)

        try:
            for item, action_name, expected in (
                (nd2, '复制文件名', '实验.nd2'),
                (series, '复制文件名', '实验.lif - Series001'),
                (nd2, '复制图片路径', '/images/实验.nd2'),
                (series, '复制图片路径', '/images/实验.lif'),
            ):
                with self.subTest(expected=expected):
                    with patch.object(sidebar.tree, 'itemAt', return_value=item), patch('ui.sidebar.QMenu') as menu:
                        menu.return_value.addAction.side_effect = lambda text: text
                        menu.return_value.exec.return_value = action_name
                        sidebar._on_context_menu(QPoint())
                        menu.return_value.addAction.assert_any_call(action_name)
                    self.assertEqual(QApplication.clipboard().text(), expected)
        finally:
            sidebar.deleteLater()
            QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)

    def test_crop_badge_is_per_series_idempotent_and_survives_repopulate(self):
        sidebar = SidebarWidget()
        tree = {
            'name': 'images', 'path': '/images',
            'files': [{'filepath': '/images/实验.nd2', 'filename': '实验.nd2'}],
            'lif_containers': {'/images/实验.lif': {
                'name': '实验.lif', 'images': [
                    {'filepath': '/images/实验.lif', 'filename': f'实验.lif [Series00{i}]',
                     '_idx_key': f'/images/实验.lif:::Series00{i}'} for i in (1, 2)
                ],
            }},
        }
        try:
            sidebar.populate(tree, {})
            keys = {'/images/实验.nd2', '/images/实验.lif:::Series001'}
            sidebar.set_cropped_files(keys)
            sidebar.set_cropped_files(keys)
            for _ in range(2):
                root = sidebar.tree.topLevelItem(0)
                series1, series2, nd2 = root.child(0).child(0), root.child(0).child(1), root.child(1)
                self.assertEqual(series1.text(0).count('✂'), 1)
                self.assertEqual(nd2.text(0).count('✂'), 1)
                self.assertNotIn('✂', series2.text(0))
                self.assertIn('已裁剪', series1.toolTip(0))
                self.assertEqual(series1.data(0, Qt.UserRole + 2), '实验.lif - Series001')
                self.assertEqual(series1.data(0, Qt.UserRole + 1), '/images/实验.lif')
                sidebar.populate(tree, {})
            sidebar.set_cropped_files(set())
            root = sidebar.tree.topLevelItem(0)
            self.assertNotIn('✂', root.child(0).child(0).text(0))
            self.assertNotIn('已裁剪', root.child(0).child(0).toolTip(0))
            self.assertNotIn('✂', root.child(1).text(0))
        finally:
            sidebar.deleteLater()
            QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)


if __name__ == '__main__':
    unittest.main()
