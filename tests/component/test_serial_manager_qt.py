"""Deterministic FIFO and disposal tests without serial hardware."""

import sys
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from utils.serial_manager import SerialOperationResult
from utils.serial_manager_qt import SerialManagerQt


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
