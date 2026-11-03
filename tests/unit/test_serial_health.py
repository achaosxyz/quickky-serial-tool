"""Exercise physical-port removal boundaries without serial hardware."""

import io
import sys
import threading
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from utils.serial_manager import SerialManager


class SerialHealthTests(unittest.TestCase):
    def _assert_removal_disconnect(self, *, missing_from_enumeration):
        removed = threading.Event()
        enumerated = threading.Event()
        disconnected = threading.Event()
        notifications = []

        class Port:
            port = "COM42"
            is_open = True
            cts = False
            dsr = False
            close_calls = 0

            @property
            def in_waiting(self):
                if removed.is_set() and not missing_from_enumeration:
                    raise OSError("Device removed while reading status")
                return 0

            def close(self):
                self.close_calls += 1
                self.is_open = False

        def enumerate_ports():
            enumerated.set()
            if removed.is_set() and missing_from_enumeration:
                return []
            return [SimpleNamespace(device="COM42")]

        def on_disconnect():
            notifications.append("disconnected")
            disconnected.set()

        manager = SerialManager()
        port = Port()
        stop = threading.Event()
        manager.serial_port = port
        manager.is_running = True
        manager._open_generation = 1
        manager._receive_stop_event = stop
        manager.check_interval = 0
        manager.receive_callback = Mock()
        manager.disconnect_callback = on_disconnect
        receiver = threading.Thread(target=manager._receive_loop,
                                    args=(port, stop, 1), daemon=True)
        manager.receive_thread = receiver

        with patch("utils.serial_manager.serial.tools.list_ports.comports",
                   side_effect=enumerate_ports), redirect_stdout(io.StringIO()):
            receiver.start()
            try:
                self.assertTrue(enumerated.wait(1), "Initial COM enumeration did not run")
                removed.set()
                self.assertTrue(disconnected.wait(2), "Removal did not trigger a disconnect")
                receiver.join(1)
                self.assertFalse(receiver.is_alive(), "Removed-port receiver did not stop")
            finally:
                stop.set()
                manager.close()
                receiver.join(1)

        self.assertEqual(notifications, ["disconnected"])
        self.assertEqual(port.close_calls, 1)
        self.assertFalse(port.is_open)
        self.assertFalse(manager.is_running)
        self.assertFalse(manager.has_port_ownership())
        self.assertIsNone(manager.serial_port)
        self.assertIsNone(manager.receive_thread)
        manager.receive_callback.assert_not_called()

    def test_disappearing_com_device_disconnects_current_session(self):
        self._assert_removal_disconnect(missing_from_enumeration=True)

    def test_removed_device_status_error_disconnects_current_session(self):
        self._assert_removal_disconnect(missing_from_enumeration=False)


if __name__ == "__main__":
    unittest.main()
