"""Real GUI removal, retry, restoration, and cancellation over TCP."""

import os
import socket
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]

from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QSignalSpy, QTest
from PySide6.QtWidgets import QApplication
import serial

from components.work_tab_qt import ConnectionState
from pages.main_window_qt import MainWindow
from tests.e2e.socket_relay import SocketRelay


class ReconnectTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def wait_for(self, predicate, message, timeout=5000):
        deadline = time.monotonic() + timeout / 1000
        while not predicate() and time.monotonic() < deadline:
            QTest.qWait(10)
        self.assertTrue(predicate(), message() if callable(message) else message)

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="qserial-reconnect-")
        self.addCleanup(self.directory.cleanup)
        self.relay = SocketRelay()
        self.addCleanup(self.relay.close)
        self.config_patch = patch("utils.config_manager.get_base_path", return_value=self.directory.name)
        self.config_patch.start()
        self.addCleanup(self.config_patch.stop)
        self.warning = patch("pages.main_window_qt.QMessageBox.warning")
        warning = self.warning.start()
        self.addCleanup(self.warning.stop)
        self.addCleanup(warning.assert_not_called)
        self.window = MainWindow(port_provider=self.relay.get_available_ports)
        self.addCleanup(self.window.close)
        self.window.language_manager.apply_language("en_US")
        settings = self.window.config_manager.get_global_settings()
        settings["reconnect_interval"] = 1
        self.window.config_manager.set_global_settings(settings)
        self.window.show()
        self.column = self.window.work_panel.main_column
        self.a = self.column.get_current_tab()
        bar = self.column.notebook.tabBar()
        QTest.mouseClick(bar, Qt.LeftButton, pos=bar.tabRect(self.column.notebook.count() - 1).center())
        self.b = self.column.get_current_tab()
        for tab, port in zip((self.a, self.b), self.relay.endpoints):
            self.column.notebook.setCurrentWidget(tab)
            tab.serial_settings.port_combo.setCurrentText(port)
            self.assertEqual(tab.serial_settings.get_current_port(), port)
            QTest.mouseClick(tab.connect_btn, Qt.LeftButton)
            self.wait_for(lambda: tab.connection_state == ConnectionState.OPEN,
                          lambda: f"Initial open failed: {tab.connection_state}, {tab.receive_text.toPlainText()}")
        self.wait_for(lambda: all(event.is_set() for event in self.relay.connected), "Relay did not accept clients")

    def send(self, tab, text):
        self.column.notebook.setCurrentWidget(tab)
        tab.send_text.setPlainText(text)
        QTest.mouseClick(tab.send_btn, Qt.LeftButton)

    def capture(self, state):
        directory = os.environ.get("QSERIAL_RECONNECT_SCREENSHOT_DIR")
        if directory:
            output = Path(directory)
            output.mkdir(parents=True, exist_ok=True)
            self.column.notebook.setCurrentWidget(self.a)
            QTest.qWait(20)
            self.assertTrue(self.window.grab().save(str(output / f"reconnect-{state}.png")))

    def remove_a(self):
        self.relay.set_available(0, False)
        self.wait_for(lambda: self.a.connection_state == ConnectionState.DISCONNECTED,
                      "Unexpected removal did not disconnect A")
        self.assertFalse(self.a.serial_manager.has_port_ownership())
        self.assertFalse(self.a.send_btn.isEnabled())
        self.assertTrue(self.a.connect_btn.isEnabled())
        self.assertEqual(self.b.connection_state, ConnectionState.OPEN)
        self.assertTrue(self.relay.connected[1].is_set())
        address = ("127.0.0.1", int(self.relay.endpoints[0].rsplit(":", 1)[1]))
        with self.assertRaises(OSError):
            socket.create_connection(address, timeout=1)

    def test_removal_retries_and_restores_original_session(self):
        self.column.notebook.setCurrentWidget(self.a)
        QTest.mouseClick(self.a.receive_settings.auto_reconnect_check, Qt.LeftButton, pos=QPoint(5, 5))
        QTest.mouseClick(self.a.send_settings.loop_send_check, Qt.LeftButton, pos=QPoint(5, 5))
        self.a.send_settings.period_spin.setValue(50)
        self.send(self.a, "L")
        self.wait_for(lambda: self.b.rx_count >= 2, "Loop send did not start")
        completions = QSignalSpy(self.a.serial_manager.operation_completed)
        self.remove_a()
        self.assertFalse(self.a.loop_timer.isActive())
        self.assertTrue(self.a.reconnect_timer.isActive())
        self.a.serial_settings.refresh_ports()
        self.assertNotEqual(self.a.serial_settings.get_current_port(), self.relay.endpoints[1],
                            "Refresh redirected to the peer")
        self.capture("removed")
        self.wait_for(lambda: any(completions.at(i)[0] == "open" and not completions.at(i)[1].success
                                  for i in range(completions.count())), "Unavailable endpoint was not retried")
        self.assertEqual(self.b.connection_state, ConnectionState.OPEN)
        self.send(self.b, "STALE")
        self.wait_for(lambda: self.b.tx_count >= 5, "Peer could not send while A was absent")
        self.wait_for(lambda: self.relay.discarded[1] >= 5, "Relay did not discard absent-session data")
        self.relay.set_available(0, True)
        self.wait_for(lambda: self.a.connection_state == ConnectionState.OPEN, "Automatic reconnect failed", timeout=8000)
        self.wait_for(lambda: self.relay.connected[0].is_set(), "Restored endpoint was not accepted")
        self.assertEqual(self.a.serial_settings.get_current_port(), self.relay.endpoints[0])
        self.assertFalse(self.a.loop_timer.isActive())
        self.capture("restored")
        before_a, before_b = self.a.rx_count, self.b.rx_count
        self.send(self.b, "fresh-B")
        self.wait_for(lambda: self.a.rx_count >= before_a + 7, "Restored A did not receive")
        self.assertEqual(self.a.rx_count, before_a + 7)
        self.assertNotIn("STALE", self.a.receive_text.toPlainText())
        self.column.notebook.setCurrentWidget(self.a)
        QTest.mouseClick(self.a.send_settings.loop_send_check, Qt.LeftButton, pos=QPoint(5, 5))
        self.send(self.a, "fresh-A")
        self.wait_for(lambda: self.b.rx_count >= before_b + 7, "Peer did not receive after reconnect")
        self.assertEqual(self.b.rx_count, before_b + 7)
        QTest.mouseClick(self.a.connect_btn, Qt.LeftButton)
        self.wait_for(lambda: self.a.connection_state == ConnectionState.DISCONNECTED, "Manual close failed")
        self.assertFalse(self.a.reconnect_timer.isActive())
        QTest.qWait(1200)
        self.assertEqual(self.a.connection_state, ConnectionState.DISCONNECTED)
        self.assertFalse(self.relay.connected[0].is_set())

    def test_disabled_auto_reconnect_and_cleanup_cancel_retry(self):
        self.remove_a()
        self.assertFalse(self.a.reconnect_timer.isActive())
        self.relay.set_available(0, True)
        QTest.qWait(1200)
        self.assertEqual(self.a.connection_state, ConnectionState.DISCONNECTED)
        self.assertFalse(self.relay.connected[0].is_set())
        self.column.notebook.setCurrentWidget(self.a)
        QTest.mouseClick(self.a.receive_settings.auto_reconnect_check, Qt.LeftButton, pos=QPoint(5, 5))
        QTest.mouseClick(self.a.connect_btn, Qt.LeftButton)
        self.wait_for(lambda: self.a.connection_state == ConnectionState.OPEN, "Manual open failed")
        self.remove_a()
        self.assertTrue(self.a.reconnect_timer.isActive())
        QTest.mouseClick(self.a.receive_settings.auto_reconnect_check, Qt.LeftButton, pos=QPoint(5, 5))
        self.assertFalse(self.a.reconnect_timer.isActive())
        self.relay.set_available(0, True)
        QTest.qWait(1200)
        self.assertEqual(self.a.connection_state, ConnectionState.DISCONNECTED)
        self.assertFalse(self.relay.connected[0].is_set())
        QTest.mouseClick(self.a.receive_settings.auto_reconnect_check, Qt.LeftButton, pos=QPoint(5, 5))
        QTest.mouseClick(self.a.connect_btn, Qt.LeftButton)
        self.wait_for(lambda: self.a.connection_state == ConnectionState.OPEN, "Manual reopen failed")
        self.remove_a()
        self.assertTrue(self.a.reconnect_timer.isActive())
        self.window.close()
        self.assertFalse(self.a.reconnect_timer.isActive())
        self.relay.set_available(0, True)
        QTest.qWait(1200)
        self.assertFalse(self.relay.connected[0].is_set())
        self.assertFalse(self.relay.connected[1].is_set())

    def test_explicit_port_change_cancels_old_retry(self):
        self.column.notebook.setCurrentWidget(self.a)
        QTest.mouseClick(self.a.receive_settings.auto_reconnect_check, Qt.LeftButton, pos=QPoint(5, 5))
        self.remove_a()
        self.assertTrue(self.a.reconnect_timer.isActive())
        self.a.serial_settings.refresh_ports()
        self.a.serial_settings.port_combo.setCurrentText(self.relay.endpoints[1])
        self.assertEqual(self.a.serial_settings.get_current_port(), self.relay.endpoints[1])
        self.assertFalse(self.a.reconnect_timer.isActive())
        self.column.notebook.setCurrentWidget(self.b)
        QTest.mouseClick(self.b.connect_btn, Qt.LeftButton)
        self.wait_for(lambda: self.b.connection_state == ConnectionState.DISCONNECTED, "Peer close failed")
        self.wait_for(lambda: not self.relay.connected[1].is_set(), "Peer endpoint not released")
        self.relay.set_available(0, True)
        QTest.qWait(1200)
        self.assertEqual(self.a.connection_state, ConnectionState.DISCONNECTED)
        self.assertFalse(self.relay.connected[0].is_set())
        self.assertFalse(self.relay.connected[1].is_set())
        self.column.notebook.setCurrentWidget(self.a)
        self.a.serial_settings.baudrate_combo.setCurrentText("9600")
        QTest.mouseClick(self.a.connect_btn, Qt.LeftButton)
        self.wait_for(lambda: self.a.connection_state == ConnectionState.OPEN, "Selected port did not open")
        self.assertEqual(self.a.serial_manager._manager.last_config["port"], self.relay.endpoints[1])
        self.assertEqual(self.a.serial_manager._manager.last_config["baudrate"], 9600)
        with serial.serial_for_url(self.relay.endpoints[0], timeout=2) as peer:
            self.wait_for(lambda: self.relay.connected[0].is_set(), "Peer reopen failed")
            peer.write(b"switched")
            self.wait_for(lambda: self.a.rx_count == len(b"switched"), "Selected port received wrong data")
            self.assertIn("switched", self.a.receive_text.toPlainText())

    def test_all_ports_absent_restores_without_losing_draft(self):
        self.column.notebook.setCurrentWidget(self.a)
        QTest.mouseClick(self.a.receive_settings.auto_reconnect_check, Qt.LeftButton, pos=QPoint(5, 5))
        self.relay.set_available(1, False)
        self.wait_for(lambda: self.b.connection_state == ConnectionState.DISCONNECTED, "B did not disconnect")
        self.relay.set_available(0, False)
        self.wait_for(lambda: self.a.connection_state == ConnectionState.DISCONNECTED, "A did not disconnect")
        self.assertFalse(self.a.serial_manager.has_port_ownership())
        self.a.serial_settings.refresh_ports()
        self.assertEqual(self.a.serial_settings.port_combo.count(), 0)
        self.a.send_text.setPlainText("unsaved draft")
        self.relay.set_available(1, True)
        self.column.notebook.setCurrentWidget(self.b)
        QTest.mouseClick(self.b.connect_btn, Qt.LeftButton)
        self.wait_for(lambda: self.b.connection_state == ConnectionState.OPEN, "B did not reopen")
        self.wait_for(lambda: self.relay.connected[1].is_set(), "B was not accepted")
        prepared = []

        def send_before_open_completion():
            if prepared:
                return
            # Keep the GUI callback queued while real worker threads exchange bytes.
            deadline = time.monotonic() + 3
            while not self.a.serial_manager.is_open() and time.monotonic() < deadline:
                threading.Event().wait(.01)
            if not self.a.serial_manager.is_open():
                prepared.append(False)
                return
            self.b.serial_manager.send_async(b"new session data")
            while time.monotonic() < deadline:
                with self.a.serial_manager._lock:
                    if self.a.serial_manager._pending_bytes >= len(b"new session data"):
                        prepared.append(True)
                        return
                threading.Event().wait(.01)
            prepared.append(False)

        self.a.reconnect_timer.timeout.connect(send_before_open_completion)
        self.relay.set_available(0, True)
        self.wait_for(lambda: self.a.connection_state == ConnectionState.OPEN, "A did not reconnect", timeout=8000)
        self.assertEqual(prepared, [True], "Could not queue real received bytes before GUI open completion")
        self.assertEqual(self.a.serial_settings.get_current_port(), self.relay.endpoints[0])
        self.wait_for(lambda: self.a.rx_count == len(b"new session data"), "New data was lost")
        self.assertIn("new session data", self.a.receive_text.toPlainText())
        self.assertEqual(self.a.send_text.toPlainText(), "unsaved draft")


if __name__ == "__main__":
    unittest.main()
