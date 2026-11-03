"""Workspace and command panel regression tests."""

import sys
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QCoreApplication, QEvent, QTranslator, Qt
from PySide6.QtTest import QSignalSpy, QTest
from PySide6.QtWidgets import QApplication, QDialog, QDialogButtonBox


PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from components.quick_commands_panel_qt import QuickCommandsPanel
from components.work_column_qt import WorkColumn
from components.work_panel_qt import WorkPanel
from components.command_panel_qt import CommandPanel
from components.receive_settings_panel_qt import ReceiveSettingsPanel
from components.send_settings_panel_qt import SendSettingsPanel
from components.serial_settings_panel_qt import SerialSettingsPanel
from components.quick_command_dialog_qt import QuickCommandDialog
from pages.settings_dialog_qt import SettingsDialog
from pages.main_window_qt import MainWindow
from utils.config_manager import ConfigManager
from utils.i18n_qt import LanguageManagerQt


class WorkPanelAndCommandTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_send_requests_do_not_mutate_history_or_refresh_it(self):
        with tempfile.TemporaryDirectory() as directory:
            config = ConfigManager(str(Path(directory) / "config.json"))
            config.set_quick_command_groups([{"name": "g", "commands": [{"name": "a", "data": "hello", "mode": "TEXT"}]}])
            panel = CommandPanel(config)
            spy = QSignalSpy(panel.send_requested)
            table = panel.quick_commands_panel.group_notebook.widget(0)
            table.selectRow(0)
            panel.quick_commands_panel._send_command(table)
            self.assertEqual(spy.count(), 1)
            self.assertEqual(spy.at(0), ["hello", "TEXT"])
            self.assertEqual(config.get_send_history(), [])
            panel.deleteLater()

    def test_radio_change_saves_once_and_loading_saves_nothing(self):
        config = Mock()
        receive = ReceiveSettingsPanel(config)
        send = SendSettingsPanel(config)
        receive.load_config("COM1", {"mode": "TEXT", "encoding": "UTF-8"})
        send.load_config("COM1", {"mode": "TEXT"})
        config.update_receive_settings.assert_not_called()
        config.update_send_settings.assert_not_called()
        receive.hex_radio.setChecked(True)
        self.assertEqual(config.update_receive_settings.call_count, 1)
        receive.encoding_ascii.setChecked(True)
        self.assertEqual(config.update_receive_settings.call_count, 2)
        send.hex_radio.setChecked(True)
        self.assertEqual(config.update_send_settings.call_count, 1)
        receive.deleteLater()
        send.deleteLater()

    def test_language_change_retranslates_existing_panel(self):
        class Translator(QTranslator):
            def isEmpty(self):
                return False

            def translate(self, context, source, disambiguation=None, n=-1):
                if context == "ReceiveSettingsPanel" and source == "Receive settings":
                    return "Translated"
                return ""

        panel = ReceiveSettingsPanel(Mock())
        translator = Translator()
        self.app.installTranslator(translator)
        QCoreApplication.sendEvent(panel, QEvent(QEvent.LanguageChange))
        self.assertEqual(panel.title(), "Translated")
        self.app.removeTranslator(translator)
        panel.deleteLater()

    def test_real_translation_includes_qt_standard_buttons_and_switches_back(self):
        manager = LanguageManagerQt()
        try:
            manager.apply_language("zh_CN")
            buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
            self.assertIn("取消", buttons.button(QDialogButtonBox.Cancel).text())
            manager.apply_language("en_US")
            self.app.processEvents()
            self.assertIn("Cancel", buttons.button(QDialogButtonBox.Cancel).text())
            buttons.deleteLater()
        finally:
            manager.apply_language("en_US")

    def test_packaged_qt_translation_uses_bundled_resource_path(self):
        with patch("utils.i18n_qt.sys.frozen", True, create=True), \
             patch("utils.i18n_qt.resource_path", return_value="bundled") as resource:
            self.assertEqual(LanguageManagerQt._qt_translation_path(), "bundled")
        resource.assert_called_once_with("PySide6/translations")

    def test_invalid_hex_warning_uses_selected_language(self):
        manager = LanguageManagerQt()
        try:
            for language, expected in (("en_US", "Invalid HEX format."),
                                       ("zh_CN", "HEX 格式错误。")):
                with self.subTest(language=language):
                    manager.apply_language(language)
                    dialog = QuickCommandDialog()
                    dialog.name_text.setText("command")
                    dialog.mode_combo.setCurrentText("HEX")
                    dialog.data_text.setPlainText("not hex")
                    dialog.show()
                    with patch("components.quick_command_dialog_qt.QMessageBox.warning") as warning:
                        QTest.mouseClick(dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.Ok), Qt.LeftButton)
                    self.assertEqual(warning.call_args.args[2], expected)
                    dialog.close()
                    dialog.deleteLater()
        finally:
            manager.apply_language("en_US")

    def test_serial_options_retranslate_without_changing_or_saving_values(self):
        manager = LanguageManagerQt()
        config = Mock()
        callback = Mock()
        try:
            manager.apply_language("en_US")
            with patch("components.serial_settings_panel_qt.SerialManager.get_available_ports", return_value=[]):
                panel = SerialSettingsPanel(config, callback)
            panel.load_config({"parity": "Odd", "flow_control": "Hardware"})
            panel.port_combo.blockSignals(True)
            panel.port_combo.addItem("COM1")
            panel.port_combo.blockSignals(False)
            config.reset_mock()
            callback.reset_mock()
            manager.apply_language("zh_CN")
            self.app.processEvents()
            self.assertEqual(panel.parity_combo.currentText(), "奇校验")
            self.assertEqual(panel.flow_control_combo.currentText(), "硬件")
            self.assertEqual(panel.get_settings()["parity"], "Odd")
            self.assertEqual(panel.get_settings()["flow_control"], "Hardware")
            config.update_serial_settings.assert_not_called()
            callback.assert_not_called()
            panel.parity_combo.setCurrentIndex(panel.parity_combo.findData("Even"))
            self.assertEqual(config.update_serial_settings.call_args.args[1]["parity"], "Even")
            manager.apply_language("en_US")
            self.app.processEvents()
            self.assertEqual(panel.parity_combo.currentText(), "Even")
            self.assertEqual(panel.flow_control_combo.currentText(), "Hardware")
            panel.deleteLater()
        finally:
            manager.apply_language("en_US")

    def test_serial_ownership_error_is_translated(self):
        from utils.serial_manager import SerialManager
        language = LanguageManagerQt()
        manager = SerialManager()
        manager.serial_port = object()
        try:
            language.apply_language("zh_CN")
            result = manager.open("COM20")
            self.assertFalse(result.success)
            self.assertEqual(result.error, "上一个串口尚未关闭")
        finally:
            language.apply_language("en_US")

    def test_form_widgets_construct_and_retranslate(self):
        config = Mock(get_global_settings=Mock(return_value={}))
        with patch("components.serial_settings_panel_qt.SerialManager.get_available_ports", return_value=[]):
            widgets = [SerialSettingsPanel(config), QuickCommandDialog(), SettingsDialog(None, config)]
        for widget in widgets:
            with self.subTest(widget=type(widget).__name__):
                QCoreApplication.sendEvent(widget, QEvent(QEvent.LanguageChange))
                widget.retranslate_ui()
                widget.deleteLater()

    def test_column_owns_tab_title_updates_for_port_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            config = ConfigManager(str(Path(directory) / "config.json"))
            with patch("components.serial_settings_panel_qt.SerialManager.get_available_ports",
                       return_value=["COM20", "COM21"]):
                column = WorkColumn(config)
                try:
                    tab = column.get_current_tab()
                    index = column.notebook.indexOf(tab)
                    self.assertEqual(column.notebook.tabText(index), "COM20")
                    spy = QSignalSpy(tab.port_changed)
                    tab.serial_settings.port_combo.setCurrentText("COM21")
                    self.assertEqual(spy.count(), 1)
                    self.assertEqual(spy.at(0), ["COM21"])
                    self.assertEqual(column.notebook.tabText(index), "COM21")
                finally:
                    self.assertEqual(column.cleanup(), [])
                    column.deleteLater()

    def test_settings_dialog_saves_and_owner_applies_theme_only_on_accept(self):
        config = Mock(get_global_settings=Mock(return_value={}))
        dialog = SettingsDialog(None, config)
        dialog.font_size_spin.setValue(13)
        accepted = QSignalSpy(dialog.accepted)
        dialog.show()
        QTest.mouseClick(dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.Ok), Qt.LeftButton)
        self.assertEqual(accepted.count(), 1)
        self.assertEqual(config.set_global_settings.call_args.args[0]["fontSize"], 13)
        dialog.deleteLater()

        owner = Mock(config_manager=config)
        with patch("pages.main_window_qt.SettingsDialog") as dialog_type:
            dialog_type.return_value.exec.return_value = QDialog.Rejected
            MainWindow._settings(owner)
            owner.apply_theme.assert_not_called()
            dialog_type.return_value.exec.return_value = QDialog.Accepted
            MainWindow._settings(owner)
            owner.apply_theme.assert_called_once_with()

    def test_cleanup_aggregates_unique_errors_from_both_columns(self):
        panel = WorkPanel.__new__(WorkPanel)
        panel.main_column = Mock(cleanup=Mock(return_value=["serial", "log"]))
        panel.secondary_column = Mock(cleanup=Mock(return_value=["log", "other"]))
        self.assertEqual(WorkPanel.cleanup(panel), ["serial", "log", "other"])
        panel.secondary_column.cleanup.assert_called_once()

    def test_window_flushes_even_when_cleanup_raises(self):
        window = Mock()
        window.work_panel.cleanup.side_effect = RuntimeError("cleanup failed")
        event = Mock()
        with self.assertRaisesRegex(RuntimeError, "cleanup failed"):
            MainWindow.closeEvent(window, event)
        window.config_manager.flush_config.assert_called_once()

    def test_selected_system_language_is_persisted_not_effective_language(self):
        window = Mock()
        window.language_manager.apply_language.return_value = "en_US"
        MainWindow._change_language(window, "system")
        window.config_manager.set_language.assert_called_once_with("system")
        window.language_manager.apply_language.assert_called_once_with("system")

    def test_window_composes_with_empty_port_list(self):
        with tempfile.TemporaryDirectory() as directory:
            config = ConfigManager(str(Path(directory) / "config.json"))
            language = Mock(available_languages=Mock(return_value={"system": "System", "en_US": "English"}))
            with patch("pages.main_window_qt.ConfigManager", return_value=config), \
                 patch("pages.main_window_qt.LanguageManagerQt", return_value=language), \
                 patch("components.serial_settings_panel_qt.SerialManager.get_available_ports", return_value=[]):
                window = MainWindow()
                self.assertEqual(window.work_panel.cleanup(), [])
                window.deleteLater()

    def test_window_warns_and_preserves_invalid_configuration_during_startup(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text("{broken", encoding="utf-8")
            config = ConfigManager(str(path))
            with patch("pages.main_window_qt.ConfigManager", return_value=config), \
                 patch("components.serial_settings_panel_qt.SerialManager.get_available_ports", return_value=[]), \
                 patch("pages.main_window_qt.QMessageBox.warning") as warning:
                window = MainWindow()
                try:
                    window.show()
                    self.app.processEvents()
                    warning.assert_called_once()
                    self.assertEqual(path.read_text(encoding="utf-8"), "{broken")
                    window.close()
                    self.assertEqual(path.read_text(encoding="utf-8"), "{broken")
                finally:
                    window.language_manager.apply_language("en_US")
                    if window.isVisible():
                        window.close()
                    window.deleteLater()

    def test_hiding_secondary_column_does_not_permanently_cleanup_tabs(self):
        panel = WorkPanel.__new__(WorkPanel)
        panel.secondary_column = Mock()
        panel.main_column = Mock()
        panel.active_column = panel.secondary_column
        panel.config_manager = Mock()
        panel._update_column_highlight = Mock()

        WorkPanel.toggle_dual_panel_mode(panel, False)

        panel.secondary_column.setVisible.assert_called_once_with(False)
        panel.secondary_column.suspend.assert_called_once()
        panel.secondary_column.cleanup.assert_not_called()
        self.assertIs(panel.active_column, panel.main_column)

    def test_clicking_current_tab_activates_its_column(self):
        column = WorkColumn.__new__(WorkColumn)
        column.on_column_activated = Mock()

        WorkColumn._on_tab_bar_clicked(column, 0)

        column.on_column_activated.assert_called_once_with(column)

    def test_reordering_duplicate_named_groups_keeps_both_groups(self):
        groups = [
            {"name": "重复", "commands": [{"data": "A"}]},
            {"name": "重复", "commands": [{"data": "B"}]},
        ]
        panel = QuickCommandsPanel.__new__(QuickCommandsPanel)
        panel.config_manager = Mock(get_quick_command_groups=Mock(return_value=groups))

        QuickCommandsPanel._save_group_order(panel, 0, 1)

        saved_groups = panel.config_manager.set_quick_command_groups.call_args.args[0]
        self.assertEqual([group["commands"][0]["data"] for group in saved_groups], ["B", "A"])
