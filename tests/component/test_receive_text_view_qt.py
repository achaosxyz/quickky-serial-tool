"""Receive display bounds and formatting tests."""

import sys
import unittest
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QEvent, Qt
from PySide6.QtGui import QAction, QTextCursor
from PySide6.QtTest import QTest
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

    def test_continuous_text_uses_bounded_blocks_without_changing_copy_or_logs(self):
        view = ReceiveTextView()
        payload = "0123456789" * 3000
        logged = "".join(view.append_text(payload[i:i + 77], auto_scroll=False)
                         for i in range(0, len(payload), 77))
        self.assertEqual(logged, payload)
        self.assertEqual(view.toPlainText(), payload)
        self.assertGreater(view.document().blockCount(), 1)
        block = view.document().begin()
        while block.isValid():
            self.assertLessEqual(block.length() - 1, view.MAX_BLOCK_CHARS)
            block = block.next()
        view.selectAll()
        view.copy()
        self.assertEqual(self.app.clipboard().text(), payload)

    def test_real_newlines_and_utf16_selection_survive_display_splits(self):
        view = ReceiveTextView()
        payload = "中🙂" * 1500 + "\n" + "x" * 2048 + "\nlast"
        view.append_text(payload, auto_scroll=False)
        self.assertEqual(view.toPlainText(), payload)
        view.selectAll()
        view.copy()
        self.assertEqual(self.app.clipboard().text(), payload)
        cursor = QTextCursor(view.document())
        # Select across a synthetic boundary using Qt's UTF-16 positions.
        cursor.setPosition(1010)
        cursor.setPosition(1050, QTextCursor.KeepAnchor)
        view.setTextCursor(cursor)
        view.copy()
        selected = self.app.clipboard().text()
        self.assertNotIn("\n", selected)
        self.assertTrue(selected)

    def test_natural_newline_at_exact_display_boundary_is_not_duplicated(self):
        view = ReceiveTextView()
        payload = "A" * view.MAX_BLOCK_CHARS
        view.append_text(payload, auto_scroll=False)
        view.append_text("\nB", auto_scroll=False)
        self.assertEqual(view.toPlainText(), payload + "\nB")
        self.assertEqual(view.document().blockCount(), 2)

    def test_selection_and_scroll_position_are_preserved_when_not_following(self):
        view = ReceiveTextView()
        view.resize(500, 300)
        view.show()
        self.addCleanup(view.close)
        view.append_text("line\n" * 300, auto_scroll=True)
        QTest.qWait(20)
        cursor = QTextCursor(view.document())
        cursor.setPosition(5)
        cursor.setPosition(9, QTextCursor.KeepAnchor)
        view.setTextCursor(cursor)
        view.verticalScrollBar().setValue(10)
        selected = view.textCursor().selectedText()
        view.append_text("new\n" * 20, auto_scroll=False)
        QTest.qWait(20)
        self.assertEqual(view.textCursor().selectedText(), selected)
        self.assertEqual(view.verticalScrollBar().value(), 10)
        QTest.keyClick(view, Qt.Key_C, Qt.ControlModifier)
        self.assertEqual(self.app.clipboard().text(), "line")

    def test_trim_clear_and_theme_do_not_leave_continuation_state(self):
        view = ReceiveTextView(max_chars=3000)
        view.append_text("x" * 5000, max_blocks=100, auto_scroll=False)
        self.assertLessEqual(view.document().characterCount(), 3000)
        self.assertNotIn("\n", view.toPlainText())
        view.apply_theme(None)
        view.selectAll()
        view.copy()
        self.assertEqual(self.app.clipboard().text(), view.toPlainText())
        view.clear()
        view.append_text("new\nline", auto_scroll=False)
        self.assertEqual(view.toPlainText(), "new\nline")

    def test_character_trim_never_retains_half_a_surrogate_pair(self):
        view = ReceiveTextView(max_chars=6)
        view.append_text("A😀BCDE", auto_scroll=False)
        self.assertEqual(view.toPlainText(), "BCDE")
        view.clear()
        view.append_text("😀😀AB", auto_scroll=False)
        self.assertEqual(view.toPlainText(), "😀AB")
        self.assertLessEqual(view.document().characterCount(), 6)
        view.toPlainText().encode("utf-8")

    def test_repeated_prefix_eviction_keeps_a_contiguous_logical_suffix(self):
        view = ReceiveTextView(max_chars=36)
        view.MAX_BLOCK_CHARS = 17
        full = ""
        for chunk in ("a" * 30, "\nreal line\n", "😀中文" * 10, "\n", "tail " * 20, "\nend"):
            full += chunk
            view.append_text(chunk, auto_scroll=False, max_blocks=3)
            logical = view.toPlainText()
            self.assertTrue(logical)
            self.assertTrue(full.endswith(logical))
            self.assertLessEqual(view.document().characterCount(), 36)
            self.assertLessEqual(view.blockCount(), 3)
            view.selectAll()
            view.copy()
            self.assertEqual(self.app.clipboard().text(), logical)

    def test_hex_uses_long_display_segments_and_preserves_byte_tokens(self):
        view = ReceiveTextView()
        payload = (bytes(range(256)) * 10).hex(" ").upper() + " "
        view.append_text(payload, auto_scroll=False)
        self.assertEqual(view.toPlainText(), payload)
        block = view.document().begin()
        self.assertGreater(len(block.text().split()), 64)
        while block.isValid():
            self.assertLessEqual(block.length() - 1, view.MAX_BLOCK_CHARS)
            self.assertTrue(all(len(token) == 2 for token in block.text().split()))
            block = block.next()

    def test_system_separator_uses_tail_block_not_full_document_export(self):
        from unittest.mock import patch

        view = ReceiveTextView()
        view.append_text("A" * 5000, auto_scroll=False)
        with patch.object(view, "toPlainText", side_effect=AssertionError("Unexpected full export")):
            logged = view.append_text("warning\n", level="warning", auto_scroll=False)
        self.assertEqual(logged, "\nwarning\n")
        self.assertEqual(view.toPlainText(), "A" * 5000 + "\nwarning\n")

    def test_native_context_copy_and_keyboard_copy_survive_view_destruction(self):
        payload = "a" * 3000 + "\n" + "中🙂" * 800
        view = ReceiveTextView()
        view.append_text(payload, auto_scroll=False)
        view.selectAll()
        menu = view.createStandardContextMenu()
        menu.findChild(QAction, "edit-copy").trigger()
        self.assertEqual(self.app.clipboard().text(), payload)
        menu.deleteLater()
        QTest.keyClick(view, Qt.Key_C, Qt.ControlModifier)
        self.assertEqual(self.app.clipboard().text(), payload)
        view.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        self.assertEqual(self.app.clipboard().text(), payload)

    def test_continuation_metadata_survives_block_eviction_and_theme_changes(self):
        view = ReceiveTextView()
        payload = "a" * (view.MAX_BLOCK_CHARS * 8)
        view.append_text(payload, max_blocks=3, auto_scroll=False)
        self.assertEqual(view.document().blockCount(), 3)
        self.assertEqual(view.toPlainText(), "a" * (view.MAX_BLOCK_CHARS * 3))
        view.apply_theme(None)
        view.append_text("\nlast", max_blocks=3, auto_scroll=False)
        self.assertEqual(view.toPlainText(), "a" * (view.MAX_BLOCK_CHARS * 2) + "\nlast")

    def test_short_lines_are_not_rewrapped(self):
        view = ReceiveTextView()
        payload = "A" * 900 + "\n\n" + "B" * 900 + "\n"
        view.append_text(payload, auto_scroll=False)
        self.assertEqual(view.document().blockCount(), 4)
        self.assertEqual(view.document().toPlainText(), payload)

    def test_split_boundaries_are_independent_of_chunking_and_utf16_safe(self):
        import random

        randomizer = random.Random(20261103)
        payload = "".join(randomizer.choice(("A", " ", "中", "🙂", "\n")) for _ in range(8000))
        view = ReceiveTextView()
        for offset in range(0, len(payload), 31):
            view.append_text(payload[offset:offset + 31], auto_scroll=False)
        self.assertEqual(view.toPlainText(), payload)
        block = view.document().begin()
        while block.isValid():
            self.assertLessEqual(block.length() - 1, view.MAX_BLOCK_CHARS)
            block = block.next()
