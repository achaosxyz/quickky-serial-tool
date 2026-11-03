"""Receive display bounds and formatting tests."""

import sys
import unittest
from pathlib import Path

from PySide6.QtWidgets import QApplication

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from components.receive_text_view_qt import ReceiveTextView


class ReceiveTextViewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_system_message_is_separated_and_characters_are_bounded(self):
        view = ReceiveTextView(max_chars=10)
        view.append_text("abc", auto_scroll=False)
        view.append_text("warning", level="warning", auto_scroll=False)
        self.assertLessEqual(view.document().characterCount(), 10)
        self.assertTrue(view.toPlainText().endswith("warning"))
        self.assertIn("\n", view.toPlainText())

    def test_line_limit_and_theme_preserve_text(self):
        view = ReceiveTextView()
        view.append_text("first\nsecond\nthird", max_blocks=2, auto_scroll=False)
        self.assertEqual(view.toPlainText(), "second\nthird")
        view.apply_theme(None)
        self.assertEqual(view.toPlainText(), "second\nthird")
