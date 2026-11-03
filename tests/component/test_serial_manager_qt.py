"""Deterministic FIFO and disposal tests without serial hardware."""

import sys
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import serial
from PySide6.QtTest import QSignalSpy, QTest
from PySide6.QtWidgets import QApplication

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from utils.serial_manager import SerialOperationResult
from utils.serial_manager_qt import SerialManagerQt
from tests.e2e.socket_relay import SocketRelay


class FakeManager:
    def __init__(self):
        self.entered = threading.Event()
        self.release = threading.Event()
        self.calls = []

    def set_receive_callback(self, callback):
        pass

    def set_disconnect_callback(self, callback):
        pass

    def open(self, **settings):
        self.calls.append("open")
        self.entered.set()
        self.release.wait(2)
        return SerialOperationResult(True)

    def close(self):
        self.calls.append("close")
        return SerialOperationResult(True)

    def send(self, data):
        self.calls.append(data)
        return SerialOperationResult(True)


class SerialManagerQtTests(unittest.TestCase):
    def test_socket_operations_and_receive_queue(self):
        app = QApplication.instance() or QApplication([])
        with SocketRelay() as relay:
            adapter = SerialManagerQt()
            self.addCleanup(lambda: (adapter.dispose(), adapter.wait_disposed(3)))
            completed = QSignalSpy(adapter.operation_completed)
            with serial.serial_for_url(relay.endpoints[1], timeout=2) as peer:
                self.assertTrue(adapter.open_async(port=relay.endpoints[0]))
                deadline = time.monotonic() + 5
                while (completed.count() < 1 or not all(event.is_set() for event in relay.connected)) and time.monotonic() < deadline:
                    QTest.qWait(10)
                self.assertEqual(completed.count(), 1)
                self.assertEqual(completed.at(0)[0], "open")
                self.assertTrue(completed.at(0)[1].success)
                peer.write(b"component input")
                data = bytearray()
                deadline = time.monotonic() + 5
                while len(data) < 15 and time.monotonic() < deadline:
                    QTest.qWait(10)
                    chunk, dropped = adapter.drain()
                    self.assertEqual(dropped, 0)
                    data.extend(chunk)
                self.assertEqual(data, b"component input")
                self.assertTrue(adapter.send_async(b"component output"))
                self.assertEqual(peer.read(16), b"component output")
                adapter.dispose()
                self.assertTrue(adapter.wait_disposed(3).success)
        self.assertIsNotNone(app)

    def test_dispose_drains_fifo_and_reuses_queued_close(self):
        manager = FakeManager()
        with patch("utils.serial_manager_qt.SerialManager", return_value=manager):
            adapter = SerialManagerQt()
        completed = []
        adapter._emit_operation_completed = lambda operation, result: completed.append((operation, result.success))
        self.assertTrue(adapter.open_async(port="COM1"))
        self.assertTrue(manager.entered.wait(1))
        self.assertTrue(adapter.send_async(b"abc"))
        self.assertTrue(adapter.close_async())
        adapter.dispose()
        adapter.dispose()
        self.assertFalse(adapter.open_async(port="COM2"))
        self.assertFalse(adapter.send_async(b"later"))
        self.assertFalse(adapter.wait_disposed(0).success)
        manager.release.set()
        self.assertTrue(adapter.wait_disposed(1).success)
        adapter._worker.join(1)
        self.assertEqual(manager.calls, ["open", b"abc", "close"])
        self.assertEqual(completed, [("open", True), ("send", True), ("close", True)])

    def test_dispose_adds_final_close_after_open(self):
        manager = FakeManager()
        with patch("utils.serial_manager_qt.SerialManager", return_value=manager):
            adapter = SerialManagerQt()
        adapter.open_async(port="COM1")
        self.assertTrue(manager.entered.wait(1))
        adapter.dispose()
        manager.release.set()
        self.assertTrue(adapter.wait_disposed(1).success)
        self.assertEqual(manager.calls, ["open", "close"])

    def test_dispose_reuses_close_already_running(self):
        class BlockingCloseManager(FakeManager):
            def close(self):
                self.calls.append("close")
                self.entered.set()
                self.release.wait(2)
                return SerialOperationResult(False, "close failed")

        manager = BlockingCloseManager()
        with patch("utils.serial_manager_qt.SerialManager", return_value=manager):
            adapter = SerialManagerQt()
        self.assertTrue(adapter.close_async())
        self.assertTrue(manager.entered.wait(1))
        adapter.dispose()
        manager.release.set()
        result = adapter.wait_disposed(1)
        self.assertFalse(result.success)
        self.assertEqual(result.error, "close failed")
        self.assertEqual(manager.calls, ["close"])
