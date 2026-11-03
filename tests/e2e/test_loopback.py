"""QTest coverage of the real application over a configured serial pair."""

import os
import sys
import tempfile
import time
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

import serial
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QTabBar

from components.work_tab_qt import ConnectionState
from pages.main_window_qt import MainWindow
from tests.e2e.environment import ensure_ports_available, load_endpoints


class LoopbackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.ports = load_endpoints()
            ensure_ports_available(cls.ports)
        except RuntimeError as error:
            raise unittest.SkipTest(str(error)) from error
        if cls.ports[0].casefold() == cls.ports[1].casefold():
            raise AssertionError("E2E endpoints must be distinct")
        try:
            with serial.Serial(cls.ports[0], timeout=0), serial.Serial(cls.ports[1], timeout=0):
                pass
        except serial.SerialException as error:
            raise unittest.SkipTest(f"E2E endpoint unavailable or occupied: {error}") from error
        cls.app = QApplication.instance() or QApplication([])

    def wait_for(self, predicate, message, timeout=5000):
        deadline = time.monotonic() + timeout / 1000
        while not predicate() and time.monotonic() < deadline:
            QTest.qWait(10)
        self.assertTrue(predicate(), message)

    def test_real_window_bidirectional_loopback_and_cleanup(self):
        with tempfile.TemporaryDirectory(prefix="qserial-e2e-") as directory, ExitStack() as stack:
            with patch("utils.config_manager.get_base_path", return_value=directory):
                warning = stack.enter_context(patch("pages.main_window_qt.QMessageBox.warning"))
                window = MainWindow()
                window.show()
                stack.callback(window.close)
                self.assertEqual(Path(window.config_manager.config_file).parent, Path(directory))
                column = window.work_panel.main_column
                a = column.get_current_tab()
                bar = column.notebook.tabBar()
                QTest.mouseClick(bar, Qt.LeftButton, pos=bar.tabRect(column.notebook.count() - 1).center())
                b = column.get_current_tab()
                self.assertIsNot(a, b)
                for tab, port in zip((a, b), self.ports):
                    tab.serial_settings.port_combo.setCurrentText(port)
                    QTest.mouseClick(tab.connect_btn, Qt.LeftButton)
                    self.wait_for(lambda: tab.connection_state == ConnectionState.OPEN,
                                  f"Could not open {port}: {tab.receive_text.toPlainText()}")

                column.notebook.setCurrentWidget(a)
                a.send_text.setPlainText("hello\n世界")
                QTest.mouseClick(a.send_btn, Qt.LeftButton)
                text_bytes = len("hello\r\n世界".encode("utf-8"))
                self.wait_for(lambda: b.rx_count == text_bytes, "TEXT A to B failed")
                self.assertIn("hello\n世界", b.receive_text.toPlainText())
                self.assertEqual(a.tx_count, text_bytes)

                column.notebook.setCurrentWidget(b)
                QTest.mouseClick(b.send_settings.hex_radio, Qt.LeftButton)
                QTest.mouseClick(a.receive_settings.hex_radio, Qt.LeftButton)
                b.send_text.setPlainText("00 41 FF")
                QTest.mouseClick(b.send_btn, Qt.LeftButton)
                self.wait_for(lambda: a.rx_count == 3, "HEX B to A failed")
                self.assertIn("00 41 FF", a.receive_text.toPlainText())
                self.assertEqual(b.tx_count, 3)

                # Re-send the last HEX history item through the selected tab.
                history = window.command_panel.send_history_panel.table
                window.command_panel.notebook.setCurrentWidget(window.command_panel.send_history_panel)
                self.assertGreater(history.rowCount(), 0)
                old_a_tx, old_b_tx = a.tx_count, b.tx_count
                rect = history.visualItemRect(history.item(0, 1))
                QTest.mouseClick(history.viewport(), Qt.LeftButton, pos=rect.center())
                self.assertEqual(history.currentRow(), 0)
                QTest.mouseDClick(history.viewport(), Qt.LeftButton, pos=rect.center())
                self.wait_for(lambda: b.tx_count == old_b_tx + 3, "History did not route to the selected tab")
                self.assertEqual(a.tx_count, old_a_tx)

                column.notebook.setCurrentWidget(a)
                QTest.mouseClick(a.send_settings.loop_send_check, Qt.LeftButton, pos=QPoint(5, 5))
                self.assertTrue(a.send_settings.loop_send_check.isChecked())
                a.send_settings.period_spin.setValue(50)
                a.send_text.setPlainText("L")
                before = b.rx_count
                QTest.mouseClick(a.send_btn, Qt.LeftButton)
                self.wait_for(lambda: b.rx_count >= before + 3, "Loop send did not repeat")
                QTest.mouseClick(a.send_btn, Qt.LeftButton)
                self.wait_for(lambda: not a._send_in_flight, "Loop send did not settle")
                QTest.qWait(150)
                settled = b.rx_count
                QTest.qWait(200)
                self.assertEqual(b.rx_count, settled, "Loop send continued after cancellation")

                log_path = Path(directory) / "receive.log"
                column.notebook.setCurrentWidget(b)
                with patch("components.work_tab_qt.QFileDialog.getSaveFileName", return_value=(str(log_path), "")):
                    QTest.mouseClick(b.receive_settings.save_log_check, Qt.LeftButton, pos=QPoint(5, 5))
                self.assertTrue(b.receive_settings.save_log_check.isChecked())
                column.notebook.setCurrentWidget(a)
                QTest.mouseClick(a.send_settings.loop_send_check, Qt.LeftButton, pos=QPoint(5, 5))
                a.send_text.setPlainText("LOG-CHECK")
                QTest.mouseClick(a.send_btn, Qt.LeftButton)
                self.wait_for(lambda: "LOG-CHECK" in b.receive_text.toPlainText(), "Log payload not received")
                close_button = bar.tabButton(column.notebook.indexOf(b), QTabBar.RightSide)
                QTest.mouseClick(close_button, Qt.LeftButton)
                self.assertNotIn(b, column.get_all_tabs())
                self.assertIn("LOG-CHECK", log_path.read_text(encoding="utf-8"))
                with serial.Serial(self.ports[1], timeout=0):
                    pass
                window.close()
                warning.assert_not_called()
                for port in self.ports:
                    with serial.Serial(port, timeout=0):
                        pass


if __name__ == "__main__":
    unittest.main()
