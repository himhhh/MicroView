import os
import sys
import unittest
from pathlib import Path

import numpy as np

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from ui.viewer import ViewerWidget


class ViewerZoomPreservationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_channel_toggle_preserves_zoom_in_both_view_modes(self):
        image = np.zeros((1024, 1024, 3), dtype=np.uint8)

        for multi_mode in (True, False):
            with self.subTest(multi_mode=multi_mode):
                viewer = ViewerWidget()
                viewer.resize(1000, 700)
                viewer.show()
                QTest.qWait(50)
                viewer._set_mode(multi_mode)
                viewer.display_image(
                    image,
                    [image.copy() for _ in range(3)],
                    ["C1", "C2", "C3"],
                )
                QTest.qWait(100)

                viewer.set_zoom_state(2.25, 400, 420)
                QTest.qWait(20)
                zoom_before = viewer.get_zoom_state()[0]

                viewer.display_image(
                    image,
                    [image.copy() for _ in range(2)],
                    ["C1", "C2"],
                    preserve_view=True,
                )
                QTest.qWait(200)
                zoom_after = viewer.get_zoom_state()[0]

                self.assertAlmostEqual(zoom_after, zoom_before, places=6)
                viewer.close()


if __name__ == "__main__":
    unittest.main()
