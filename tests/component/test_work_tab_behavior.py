"""Regression tests for Qt session tab behavior."""

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from PySide6.QtCore import QCoreApplication, QEvent, QTranslator
from PySide6.QtWidgets import QApplication


PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from components.work_tab_qt import ConnectionState, WorkTab
from utils.serial_manager import SerialOperationResult
from utils.config_manager import ConfigManager


class WorkTabBehaviorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_external_send_records_history_by_default(self):
        tab = WorkTab.__new__(WorkTab)
        tab.send_text = Mock()
        tab._send_data = Mock()
        WorkTab.send_data(tab, "快捷指令", "TEXT")
        tab.send_text.setPlainText.assert_called_once_with("快捷指令")
        tab._send_data.assert_called_once_with("TEXT", add_to_history=True)

    def test_rx_count_includes_dropped_display_bytes(self):
        tab = WorkTab.__new__(WorkTab)
        tab.serial_manager = Mock(drain=Mock(return_value=(b"", 7)))
        tab.log_writer = Mock(take_dropped_bytes=Mock(return_value=0), take_error_events=Mock(return_value=[]))
        tab._log_generation = 0
        tab.rx_count = 0
        tab._update_counts = Mock()
        tab._append_text = Mock()
        WorkTab._flush_receive(tab)
        self.assertEqual(tab.rx_count, 7)
        tab._update_counts.assert_called_once()

    def test_close_failure_is_shown_to_user(self):
        tab = WorkTab.__new__(WorkTab)
        tab._cleaning_up = False
        tab.connection_state = ConnectionState.CLOSING
        tab._reset_receive_session = Mock()
        tab.connect_btn = Mock()
        tab._apply_connection_state = Mock()
        tab._append_system = Mock()

        WorkTab._on_operation_completed(tab, "close", SerialOperationResult(False, "driver failure"))

        tab._reset_receive_session.assert_called_once()
        tab._apply_connection_state.assert_called_once_with(ConnectionState.CLOSE_FAILED)
        tab._append_system.assert_called_once_with("[Error] Could not close port: driver failure\n", "error")

    def test_log_file_dialog_reuses_last_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            selected_file = str(Path(directory) / "serial.log")
            tab = WorkTab.__new__(WorkTab)
            tab.serial_settings = Mock(get_current_port=Mock(return_value="COM1"))
            tab.config_manager = Mock(get_last_log_directory=Mock(return_value=directory))
            tab.log_writer = Mock(open=Mock(return_value=True))
            tab._log_generation = 0
            tab._append_system = Mock()

            with patch("components.work_tab_qt.QFileDialog.getSaveFileName", return_value=(selected_file, "")) as dialog:
                self.assertTrue(WorkTab._choose_log_file(tab))

            self.assertTrue(dialog.call_args.args[2].startswith(directory))
            tab.config_manager.set_last_log_directory.assert_called_once_with(directory)
            tab.log_writer.open.assert_called_once_with(selected_file, 0)

    def test_manual_close_blocks_queued_auto_reconnect(self):
        tab = WorkTab.__new__(WorkTab)
        tab._manual_close = True
        tab.receive_settings = Mock(get_settings=Mock(return_value={"auto_reconnect": True}))
        tab.serial_manager = Mock(is_open=Mock(return_value=False))
        tab._connection_in_flight = False
        tab._open_connection = Mock()
        WorkTab._try_reconnect(tab)
        tab._open_connection.assert_not_called()

    def test_suspend_disables_log_checkbox_after_closing_log_session(self):
        tab = WorkTab.__new__(WorkTab)
        tab._stop_loop_send = Mock()
        tab.reconnect_timer = Mock()
        tab._reset_receive_session = Mock()
        tab._close_log_writer = Mock()
        tab.receive_settings = Mock()
        tab.receive_settings.save_log_check.isChecked.return_value = True
        tab.serial_manager = Mock(is_open=Mock(return_value=False))
        tab.connection_state = ConnectionState.DISCONNECTED
        tab._apply_connection_state = Mock()

        WorkTab.suspend(tab)

        self.assertTrue(tab._manual_close)
        tab.receive_settings.save_log_check.setChecked.assert_called_once_with(False)
        tab._apply_connection_state.assert_called_once_with(ConnectionState.DISCONNECTED)

    def test_open_completion_does_not_reopen_while_closing(self):
        tab = WorkTab.__new__(WorkTab)
        tab._cleaning_up = False
        tab.connection_state = ConnectionState.CLOSING
        tab._apply_connection_state = Mock()
        WorkTab._on_operation_completed(tab, "open", SerialOperationResult(True))
        tab._apply_connection_state.assert_not_called()

    def test_old_log_error_does_not_disable_current_session(self):
        tab = WorkTab.__new__(WorkTab)
        tab.serial_manager = Mock(drain=Mock(return_value=(b"", 0)))
        tab.log_writer = Mock(take_dropped_bytes=Mock(return_value=0),
                              take_error_events=Mock(return_value=[(1, "old close failed")]))
        tab._log_generation = 2
        tab._log_enabled = True
        tab._disable_logging = Mock()
        tab._append_text = Mock()
        WorkTab._flush_receive(tab)
        tab._disable_logging.assert_not_called()
        self.assertIn("old close failed", tab._append_text.call_args.args[0])

    def test_log_overflow_disables_current_session(self):
        tab = WorkTab.__new__(WorkTab)
        tab.serial_manager = Mock(drain=Mock(return_value=(b"", 0)))
        tab.log_writer = Mock(take_dropped_bytes=Mock(return_value=12),
                              take_error_events=Mock(return_value=[]))
        tab._disable_logging = Mock()
        WorkTab._flush_receive(tab)
        tab._disable_logging.assert_called_once_with("Log buffer full; dropped 12 bytes")

    def test_cleanup_propagates_serial_and_final_log_errors_once(self):
        tab = WorkTab.__new__(WorkTab)
        tab._cleanup_errors = None
        tab.flush_timer = Mock()
        tab.reconnect_timer = Mock()
        tab._stop_loop_send = Mock()
        tab._reset_receive_session = Mock()
        tab.serial_manager = Mock(wait_disposed=Mock(return_value=SerialOperationResult(False, "driver")))
        tab.log_writer = Mock(stop=Mock(return_value=True),
                              take_error_events=Mock(return_value=[(1, "flush failed")]),
                              take_dropped_bytes=Mock(return_value=0))
        errors = WorkTab.cleanup(tab)
        self.assertEqual(errors, ["Could not close port: driver", "flush failed"])
        self.assertEqual(WorkTab.cleanup(tab), errors)
        tab.serial_manager.dispose.assert_called_once()
        tab.serial_manager.wait_disposed.assert_called_once_with(2.0)
        tab.log_writer.stop.assert_called_once()

    def test_language_change_updates_controls_without_changing_draft(self):
        class Translator(QTranslator):
            def translate(self, context, source, disambiguation=None, n=-1):
                if context == "WorkTab" and source == "Send":
                    return "Translated send"
                return ""

        with tempfile.TemporaryDirectory() as directory:
            with patch("utils.serial_manager.SerialManager.get_available_ports", return_value=[]):
                tab = WorkTab(ConfigManager(str(Path(directory) / "config.json")))
            try:
                tab.send_text.setPlainText("user draft")
                translator = Translator()
                QCoreApplication.installTranslator(translator)
                QCoreApplication.sendEvent(tab, QEvent(QEvent.LanguageChange))
                self.assertEqual(tab.send_btn.text(), "Translated send")
                self.assertEqual(tab.send_text.toPlainText(), "user draft")
                QCoreApplication.removeTranslator(translator)
            finally:
                tab.cleanup()
                tab.deleteLater()
