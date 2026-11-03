"""Integration coverage of the serial manager over real TCP sockets."""

import sys
import socket
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from tests.e2e.socket_relay import SocketRelay
from utils.serial_manager import SerialManager


class SocketSerialTests(unittest.TestCase):
    def test_relay_drains_after_source_eof(self):
        with SocketRelay() as relay:
            addresses = [("127.0.0.1", int(endpoint.rsplit(":", 1)[1]))
                         for endpoint in relay.endpoints]
            with socket.create_connection(addresses[0]) as source, socket.create_connection(addresses[1]) as target:
                self.assertTrue(all(event.wait(2) for event in relay.connected))
                payload = b"EOF-DRAIN-" * 512
                source.sendall(payload)
                source.close()
                target.settimeout(2)
                received = bytearray()
                while len(received) < len(payload):
                    chunk = target.recv(len(payload) - len(received))
                    self.assertTrue(chunk, "Relay closed before forwarding the payload")
                    received.extend(chunk)
                self.assertEqual(received, payload)

    def test_bidirectional_burst_and_disconnect(self):
        relay = SocketRelay()
        self.addCleanup(relay.close)
        a, b = SerialManager(), SerialManager()
        self.addCleanup(a.close)
        self.addCleanup(b.close)
        received = [bytearray(), bytearray()]
        events = [threading.Event(), threading.Event()]
        disconnected = threading.Event()
        payloads = [bytes(range(256)) * 128, b"response"]

        def callback(index):
            def receive(data):
                received[index].extend(data)
                if len(received[index]) >= len(payloads[1 - index]):
                    events[index].set()
            return receive

        a.receive_callback = callback(0)
        b.receive_callback = callback(1)
        a.disconnect_callback = lambda *_args: disconnected.set()
        self.assertTrue(a.open(relay.endpoints[0]))
        self.assertTrue(b.open(relay.endpoints[1]))
        with patch.object(a, "_is_port_available", side_effect=AssertionError("COM enumeration used")):
            self.assertEqual(a._check_port_health(a.serial_port), (True, None))
        self.assertTrue(a.send(payloads[0]))
        self.assertTrue(b.send(payloads[1]))
        self.assertTrue(events[0].wait(5))
        self.assertTrue(events[1].wait(5))
        self.assertEqual(bytes(received[0]), payloads[1])
        self.assertEqual(bytes(received[1]), payloads[0])
        relay.close()
        self.assertFalse(any(event.is_set() for event in relay.connected))
        self.assertFalse(any(event.is_set() for event in relay.available))
        self.assertTrue(disconnected.wait(5), "EOF did not trigger disconnect")


if __name__ == "__main__":
    unittest.main()
