"""QTest coverage of the real application over a local TCP relay."""

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
from tests.e2e.socket_relay import SocketRelay


class LoopbackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def wait_for(self, predicate, message, timeout=5000):
        deadline = time.monotonic() + timeout / 1000
        while not predicate() and time.monotonic() < deadline:
            QTest.qWait(10)
        self.assertTrue(predicate(), message() if callable(message) else message)

    def test_real_window_bidirectional_loopback_and_cleanup(self):
        with SocketRelay() as relay, tempfile.TemporaryDirectory(prefix="qserial-e2e-") as directory, ExitStack() as stack:
            self.ports = relay.endpoints
            with patch("utils.config_manager.get_base_path", return_value=directory):
                warning = stack.enter_context(patch("pages.main_window_qt.QMessageBox.warning"))
                window = MainWindow(port_provider=lambda: self.ports)
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
                    column.notebook.setCurrentWidget(tab)
                    tab.serial_settings.refresh_ports()
                    self.assertEqual(tab.serial_settings.port_combo.count(), 2)
                    tab.serial_settings.port_combo.setCurrentText(port)
                    self.assertEqual(tab.serial_settings.get_current_port(), port)
                    QTest.mouseClick(tab.connect_btn, Qt.LeftButton)
                    self.assertNotEqual(tab.connection_state, ConnectionState.DISCONNECTED,
                                        tab.receive_text.toPlainText())
                    self.wait_for(lambda: tab.connection_state == ConnectionState.OPEN,
                                  lambda: f"Could not open {port}: {tab.connection_state} {tab.receive_text.toPlainText()}")

                if os.environ.get("QSERIAL_E2E_SCREENSHOT_DIR"):
                    output = Path(os.environ["QSERIAL_E2E_SCREENSHOT_DIR"])
                    output.mkdir(parents=True, exist_ok=True)
                    for language in ("en_US", "zh_CN"):
                        window.language_manager.apply_language(language)
                        for theme in ("light", "dark"):
                            window._change_theme(theme)
                            QTest.qWait(100)
                            self.assertTrue(window.grab().save(str(output / f"socket-{language}-{theme}.png")))
                    window.language_manager.apply_language("en_US")

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
                self.assertFalse(a.loop_timer.isActive(), "Loop timer did not stop")
                self.wait_for(lambda: not a._send_in_flight, "Loop send did not settle")
                settled = a.tx_count
                self.wait_for(lambda: b.rx_count == settled, "Sent bytes did not reach the receiver")
                QTest.qWait(200)
                self.assertEqual(a.tx_count, settled, "Loop send continued after cancellation")
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
                self.wait_for(lambda: not relay.connected[1].is_set(), "Closed tab retained endpoint")
                window.close()
                warning.assert_not_called()
                self.wait_for(lambda: not any(event.is_set() for event in relay.connected),
                              "Window retained endpoints")
                with serial.serial_for_url(self.ports[0], timeout=2) as first, serial.serial_for_url(self.ports[1], timeout=2) as second:
                    self.wait_for(lambda: all(event.is_set() for event in relay.connected), "Reopen failed")
                    first.write(b"reopened A")
                    self.assertEqual(second.read(10), b"reopened A")
                    second.write(b"reopened B")
                    self.assertEqual(first.read(10), b"reopened B")


if __name__ == "__main__":
    unittest.main()
