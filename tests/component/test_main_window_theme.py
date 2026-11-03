"""Application color-scheme requests for native window decorations."""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, call, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent, Qt
from PySide6.QtWidgets import QApplication

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from pages.main_window_qt import MainWindow
from utils.config_manager import ConfigManager


class MainWindowThemeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.config = ConfigManager(str(Path(directory.name) / "config.json"))
        self.config.set_language("en_US")
        palette = self.app.palette()
        self.addCleanup(self.app.setPalette, palette)
        self.hints = Mock()
        hints = patch("pages.main_window_qt.QApplication.styleHints", return_value=self.hints)
        hints.start()
        self.addCleanup(hints.stop)
        ports = patch("components.serial_settings_panel_qt.SerialManager.get_available_ports",
                      return_value=[])
        ports.start()
        self.addCleanup(ports.stop)

    def create_window(self):
        window = MainWindow(self.config)
        self.app.processEvents()
        self.addCleanup(self.dispose_window, window)
        return window

    def dispose_window(self, window):
        window.close()
        window.deleteLater()
        self.app.sendPostedEvents(None, QEvent.DeferredDelete)
        self.app.processEvents()

    def test_light_startup_requests_light_native_scheme_before_show(self):
        self.config.set_theme("light")
        window = self.create_window()
        self.assertFalse(window.isVisible())
        self.hints.setColorScheme.assert_called_once_with(Qt.ColorScheme.Light)

    def test_dark_startup_requests_dark_native_scheme_before_show(self):
        self.config.set_theme("dark")
        window = self.create_window()
        self.assertFalse(window.isVisible())
        self.hints.setColorScheme.assert_called_once_with(Qt.ColorScheme.Dark)

    def test_switching_theme_requests_native_scheme_before_custom_palette(self):
        window = self.create_window()
        tab = window.work_panel.get_current_work_tab()
        events = Mock()
        events.attach_mock(self.hints.setColorScheme, "scheme")
        with patch.object(self.app, "setPalette", wraps=self.app.setPalette) as set_palette:
            events.attach_mock(set_palette, "palette")
            for theme, scheme in (("dark", Qt.ColorScheme.Dark), ("light", Qt.ColorScheme.Light)):
                with self.subTest(theme=theme):
                    events.reset_mock()
                    window._change_theme(theme)
                    self.assertEqual(events.mock_calls[0], call.scheme(scheme))
                    self.assertEqual(events.mock_calls[1][0], "palette")
                    palette = events.mock_calls[1].args[0]
                    self.assertEqual(palette.window().color(), window.theme_manager.palette().window().color())
                    self.assertIs(window.work_panel.get_current_work_tab(), tab)


if __name__ == "__main__":
    unittest.main()
