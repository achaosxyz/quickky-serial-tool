"""Tests for the E2E environment boundary without opening serial ports."""

import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from tests.e2e.environment import ensure_ports_available, load_endpoints


class E2EEnvironmentTests(unittest.TestCase):
    def test_loads_configured_endpoints(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "dev.env"
            path.write_text(
                "# virtual loopback\nQSERIAL_E2E_TX_PORT=COM20\n"
                "QSERIAL_E2E_RX_PORT=COM21\n",
                encoding="utf-8",
            )
            self.assertEqual(load_endpoints(path), ("COM20", "COM21"))

    def test_rejects_missing_endpoint(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "dev.env"
            path.write_text("QSERIAL_E2E_TX_PORT=COM20\n", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "QSERIAL_E2E_RX_PORT"):
                load_endpoints(path)

    def test_preflight_checks_both_ports_without_opening_them(self):
        ports = [SimpleNamespace(device="COM20")]
        with patch("tests.e2e.environment.serial.tools.list_ports.comports", return_value=ports):
            with self.assertRaisesRegex(RuntimeError, "COM21"):
                ensure_ports_available(("COM20", "COM21"))


if __name__ == "__main__":
    unittest.main()
