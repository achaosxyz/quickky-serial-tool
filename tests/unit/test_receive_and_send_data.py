"""Receive and send data conversion regression tests."""

import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from utils.receive_data_utils import ReceiveLogFormatter, ReceivePipeline, ReceiveTextDecoder, ReceiveTextSegmenter
from utils.send_data_utils import SendDataUtils


class ReceiveAndSendDataTests(unittest.TestCase):
    def test_incremental_utf8_and_empty_line_filtering(self):
        decoder = ReceiveTextDecoder()
        encoded = "中".encode("utf-8")
        self.assertEqual(decoder.decode(encoded[:2], "UTF-8"), "")
        self.assertEqual(decoder.decode(encoded[2:], "UTF-8"), "中")
        self.assertEqual(list(ReceiveTextSegmenter().iter_segments("A\n\nB")), ["A\n", "B"])

    def test_log_mode_splits_continuous_data_by_timestamp_duration(self):
        formatter = ReceiveLogFormatter()
        started = datetime(2026, 1, 1, 12, 0, 0)
        self.assertEqual(formatter.format("A", True, started), "[12:00:00.000] A")
        self.assertEqual(formatter.format("B", True, started + timedelta(milliseconds=50)), "B")
        self.assertEqual(formatter.format("C", True, started + timedelta(milliseconds=101)), "\n[12:00:00.101] C")

    def test_hex_separators_and_invalid_text_conversion(self):
        self.assertEqual(SendDataUtils.parse_hex("0x01, 0x02:03-04\n"), b"\x01\x02\x03\x04")
        self.assertEqual(SendDataUtils.hex_to_text("FF 41"), "\ufffdA")

    def test_text_and_hex_conversion_follow_selected_line_ending(self):
        self.assertEqual(SendDataUtils.encode_text("A\nB", "UTF-8", "CR")[2], b"A\rB")
        self.assertEqual(SendDataUtils.encode_text("A\r\nB", "UTF-8", "LF")[2], b"A\nB")
        self.assertEqual(SendDataUtils.text_to_hex("A\nB", line_ending="CR"), "41 0D 42")
        self.assertEqual(SendDataUtils.hex_to_text("41 0D 42", line_ending="CR"), "A\r\nB")

    def test_pipeline_reset_clears_incremental_and_format_state(self):
        pipeline = ReceivePipeline()
        settings = {"mode": "TEXT", "encoding": "UTF-8", "log_mode": False}
        self.assertEqual(pipeline.process(b"\xe4\xb8", settings), "")
        self.assertEqual(pipeline.process(b"\xad", settings), "中")
        self.assertEqual(pipeline.format_system("!", False), "!")
        pipeline.reset()
        self.assertEqual(pipeline.process(b"A\n\nB", settings), "A\nB")
        settings["mode"] = "HEX"
        self.assertEqual(pipeline.process(b"\x00\xff", settings), "00 FF ")

    def test_prepare_returns_exact_wire_bytes(self):
        self.assertEqual(SendDataUtils.prepare("A\nB", "TEXT", "UTF-8", "CR"), b"A\rB")
        self.assertEqual(SendDataUtils.prepare("0x01 FF", "HEX", "UTF-8"), b"\x01\xff")
