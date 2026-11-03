"""Main window composition, menus, and application services."""

from pathlib import Path

from PySide6.QtCore import QEvent, QTimer, Qt
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import (QApplication, QDialog, QDialogButtonBox, QFileDialog,
                               QLabel, QMainWindow, QMessageBox, QSplitter, QVBoxLayout)

from components.command_panel_qt import CommandPanel
from components.work_panel_qt import WorkPanel
from pages.settings_dialog_qt import SettingsDialog
from utils.app_info import AppInfo
from utils.config_manager import ConfigManager
from utils.file_utils import resource_path
from utils.i18n_qt import LanguageManagerQt
from utils.theme_manager_qt import ThemeManagerQt


class MainWindow(QMainWindow):
    def __init__(self, config_manager=None, port_provider=None):
        super().__init__()
        QApplication.setStyle("Windows")
        self.setWindowTitle(AppInfo.get_window_title())
        self.resize(1200, 720)
        icon = Path(resource_path("icon.png"))
        if icon.exists(): self.setWindowIcon(QIcon(str(icon)))
        self.config_manager = ConfigManager() if config_manager is None else config_manager
        self.port_provider = port_provider
        self.theme_manager = ThemeManagerQt()
        self.language_manager = LanguageManagerQt()
        self.language_manager.apply_language(self.config_manager.get_language())
        self._create_widgets()
        self._create_menu()
        self.apply_theme()
        if self.config_manager.load_failed:
            QTimer.singleShot(0, self._warn_config_load_failure)

    def _warn_config_load_failure(self):
        QMessageBox.warning(
            self,
            self.tr("Configuration could not be loaded"),
            self.tr("The existing configuration was preserved. Changes cannot be saved until you import a valid configuration."),
        )
    def _create_widgets(self):
        self.work_panel = WorkPanel(self.config_manager, self.theme_manager, self._on_data_sent, self, self.port_provider)
        self.command_panel = CommandPanel(self.config_manager, self)
        self.command_panel.send_requested.connect(self.work_panel.send_data)
        self.splitter = QSplitter()
        self.splitter.setChildrenCollapsible(False)
        self.splitter.addWidget(self.work_panel)
        self.splitter.addWidget(self.command_panel)
        self.splitter.setCollapsible(0, False)
        self.splitter.setCollapsible(1, False)
        self.splitter.setStretchFactor(0, 1)
        self.command_panel.setVisible(self.config_manager.get_command_panel_visible())
        self.setCentralWidget(self.splitter)
        QTimer.singleShot(0, self._sync_command_panel_width)
    def _create_menu(self):
        self.file_menu = self.menuBar().addMenu(self.tr("File"))
        self.export_action = self._action(self.file_menu, self.tr("Export configuration"), self._export_config)
        self.import_action = self._action(self.file_menu, self.tr("Import configuration"), self._import_config)
        self.file_menu.addSeparator()
        self.settings_action = self._action(self.file_menu, self.tr("Settings"), self._settings)
        self.file_menu.addSeparator()
        self.exit_action = self._action(self.file_menu, self.tr("Exit"), self.close)
        self.view_menu = self.menuBar().addMenu(self.tr("View"))
        self.dual_action = self._action(self.view_menu, self.tr("Dual columns"), self._toggle_dual, checkable=True)
        self.dual_action.setChecked(self.config_manager.get_dual_panel_mode())
        self.command_action = self._action(self.view_menu, self.tr("Command panel"), self._toggle_command, checkable=True)
        self.command_action.setChecked(self.config_manager.get_command_panel_visible())
        self.theme_menu = self.menuBar().addMenu(self.tr("Theme"))
        self.theme_actions = []
        for name in self.theme_manager.get_available_themes():
            action = self._action(self.theme_menu, name.capitalize(), lambda checked=False, value=name: self._change_theme(value), checkable=True)
            action.setData(name)
            self.theme_actions.append(action)
        self.language_menu = self.menuBar().addMenu(self.tr("Language"))
        self.language_actions = []
        for code, label in self.language_manager.available_languages().items():
            action = self._action(self.language_menu, label, lambda checked=False, value=code: self._change_language(value), checkable=True)
            action.setData(code)
            self.language_actions.append(action)
        self.help_menu = self.menuBar().addMenu(self.tr("Help"))
        self.about_action = self._action(self.help_menu, self.tr("About"), self._about)
        self.retranslate_ui()

    def _change_language(self, code):
        self.config_manager.set_language(code)
        self.language_manager.apply_language(code)
        self.retranslate_ui()

    def retranslate_ui(self):
        if not hasattr(self, "file_menu"):
            return
        self.file_menu.setTitle(self.tr("File"))
        self.export_action.setText(self.tr("Export configuration"))
        self.import_action.setText(self.tr("Import configuration"))
        self.settings_action.setText(self.tr("Settings"))
        self.exit_action.setText(self.tr("Exit"))
        self.view_menu.setTitle(self.tr("View"))
        self.dual_action.setText(self.tr("Dual columns"))
        self.command_action.setText(self.tr("Command panel"))
        self.theme_menu.setTitle(self.tr("Theme"))
        for action in self.theme_actions:
            if action.data() == "light":
                action.setText(self.tr("Light"))
            elif action.data() == "dark":
                action.setText(self.tr("Dark"))
        self.language_menu.setTitle(self.tr("Language"))
        self.help_menu.setTitle(self.tr("Help"))
        self.about_action.setText(self.tr("About"))
        for action in self.language_actions:
            action.setChecked(action.data() == self.config_manager.get_language())
            if action.data() == "system":
                action.setText(self.tr("System"))

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.LanguageChange:
            self.retranslate_ui()
    @staticmethod
    def _action(menu, title, callback, checkable=False):
        action = QAction(title, menu)
        action.setCheckable(checkable)
        action.triggered.connect(callback)
        menu.addAction(action)
        return action
    def _on_data_sent(self): self.command_panel.refresh_history()
    def _toggle_dual(self, checked): self.work_panel.toggle_dual_panel_mode(checked)
    def _toggle_command(self, checked): self.command_panel.setVisible(checked); self.config_manager.set_command_panel_visible(checked); QTimer.singleShot(0, self._sync_command_panel_width)
    def _sync_command_panel_width(self):
        if not self.command_panel.isVisible() or self.splitter.width() <= 0: return
        command_width = self.command_panel.width()
        work_width = max(0, self.splitter.width() - command_width - self.splitter.handleWidth())
        self.splitter.setSizes([work_width, command_width])
    def _change_theme(self, name): self.config_manager.set_theme(name); self.apply_theme()
    def apply_theme(self):
        name = self.config_manager.get_theme()
        self.theme_manager.load_theme(name)
        app = QApplication.instance()
        palette = self.theme_manager.palette()
        scheme = Qt.ColorScheme.Dark if palette.window().color().lightness() < 128 else Qt.ColorScheme.Light
        app.styleHints().setColorScheme(scheme)
        app.setPalette(palette)
        self.setStyleSheet(self.theme_manager.stylesheet())
        self.work_panel.apply_theme()
        for action in self.theme_actions:
            action.setChecked(action.data() == self.theme_manager.current_theme)
    def _export_config(self):
        path, _ = QFileDialog.getSaveFileName(self, self.tr("Export configuration"), "config.json", self.tr("JSON files (*.json)"))
        if path:
            QMessageBox.information(self, self.tr("Export configuration"), self.tr("Configuration exported.") if self.config_manager.export_config(path) else self.tr("Configuration export failed."))
    def _import_config(self):
        path, _ = QFileDialog.getOpenFileName(self, self.tr("Import configuration"), "", self.tr("JSON files (*.json)"))
        if path:
            QMessageBox.information(self, self.tr("Import configuration"), self.tr("Configuration imported. Restart to apply it.") if self.config_manager.import_config(path) else self.tr("Configuration import failed."))
    def _settings(self):
        if SettingsDialog(self, self.config_manager).exec() == QDialog.Accepted:
            self.apply_theme()
    def _about(self):
        dialog = QDialog(self)
        dialog.setWindowTitle(self.tr("About"))
        layout = QVBoxLayout(dialog)
        label = QLabel(AppInfo.get_about_html() + "<br><br>" + self.tr("Qt/PySide6 is used under LGPLv3."))
        label.setTextFormat(Qt.RichText)
        label.setTextInteractionFlags(Qt.TextBrowserInteraction)
        label.setOpenExternalLinks(True)
        layout.addWidget(label)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok)
        buttons.accepted.connect(dialog.accept)
        layout.addWidget(buttons)
        dialog.exec()
    def closeEvent(self, event):
        try:
            errors = self.work_panel.cleanup()
        finally:
            saved = self.config_manager.flush_config()
        if not saved:
            errors.append(self.tr("Could not save the latest configuration before exit."))
        if errors:
            QMessageBox.warning(self, self.tr("Problems during shutdown"), "\n".join(dict.fromkeys(errors)))
        event.accept()
