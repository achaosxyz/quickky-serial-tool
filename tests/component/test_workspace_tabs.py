"""Native serial-tab controls and column highlight regressions."""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QColor, QEnterEvent
from PySide6.QtTest import QSignalSpy, QTest
from PySide6.QtWidgets import QApplication, QStyle, QStyleOptionTab, QTabBar, QToolButton

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from components.work_column_qt import WorkColumn
from components.work_panel_qt import WorkPanel
from utils.config_manager import ConfigManager
from utils.i18n_qt import LanguageManagerQt
from utils.theme_manager_qt import ThemeManagerQt


class WorkspaceTabTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setStyle("Windows")

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.config = ConfigManager(str(Path(directory.name) / "config.json"))
        ports = patch("components.serial_settings_panel_qt.SerialManager.get_available_ports",
                      return_value=["COM20", "COM21"])
        ports.start()
        self.addCleanup(ports.stop)
        self.theme = ThemeManagerQt()
        self.theme.load_theme("dark")
        self.column = WorkColumn(self.config, self.theme)
        self.addCleanup(self.dispose_column)
        self.column.resize(800, 720)
        self.column.show()
        self.app.processEvents()

    def dispose_column(self):
        self.assertEqual(self.column.cleanup(), [])
        self.column.close()
        self.column.deleteLater()
        self.config.flush_config()
        self.app.processEvents()

    def close_button(self, index):
        bar = self.column.notebook.tabBar()
        return next((bar.tabButton(index, side)
                     for side in (QTabBar.LeftSide, QTabBar.RightSide)
                     if bar.tabButton(index, side) is not None), None)

    def assert_add_page_has_no_close_button(self):
        notebook = self.column.notebook
        index = notebook.indexOf(self.column._add_tab_page)
        self.assertEqual(index, notebook.count() - 1)
        self.assertIsNone(self.close_button(index))

    def test_new_tabs_immediately_use_current_receive_text_colors(self):
        first = self.column.get_current_tab()
        first.receive_text.append_text("Original data\n", auto_scroll=False)
        first.receive_text.append_text("Original status\n", "info", auto_scroll=False)
        original_text = first.receive_text.toPlainText()
        bar = self.column.notebook.tabBar()
        for theme in ("dark", "light", "dark"):
            self.theme.load_theme(theme)
            self.column.setStyleSheet(self.theme.stylesheet())
            self.column.apply_theme(self.theme)
            QTest.mouseClick(bar, Qt.LeftButton, pos=bar.tabRect(self.column.notebook.count() - 1).center())
            added = self.column.get_current_tab()
            self.assertIsNot(added, first)
            added.receive_text.append_text("New data 00 41 FF\n", auto_scroll=False)
            added.receive_text.append_text("New status\n", "info", auto_scroll=False)
            for tab in (first, added):
                with self.subTest(theme=theme, new_tab=tab is added):
                    block = tab.receive_text.document().firstBlock()
                    for color_key in ("text_fg", "log_info_color"):
                        fragment = block.begin().fragment()
                        self.assertEqual(
                            fragment.charFormat().foreground().color(),
                            QColor(self.theme.get_theme_colors()[color_key]),
                        )
                        block = block.next()
            self.assertEqual(first.receive_text.toPlainText(), original_text)

    def test_native_close_controls_survive_repeated_add_close_cycles(self):
        notebook = self.column.notebook
        first = self.column.get_current_tab()
        for _ in range(3):
            self.assertFalse(notebook.tabsClosable())
            self.assertIsNone(self.close_button(0))
            self.assert_add_page_has_no_close_button()
            bar = notebook.tabBar()
            QTest.mouseClick(bar, Qt.LeftButton, pos=bar.tabRect(notebook.count() - 1).center())
            added = self.column.get_current_tab()
            self.assertIsNot(added, first)
            self.assertTrue(notebook.tabsClosable())
            self.assert_add_page_has_no_close_button()
            for index in (0, 1):
                button = self.close_button(index)
                self.assertIsNotNone(button)
                self.assertNotIsInstance(button, QToolButton)
                self.assertEqual(button.toolTip(), self.column.tr("Close tab"))
            requested = QSignalSpy(notebook.tabCloseRequested)
            QTest.mouseClick(self.close_button(1), Qt.LeftButton)
            self.assertEqual(requested.count(), 1)
            self.assertEqual(requested.at(0), [1])
            self.assertEqual(self.column.get_all_tabs(), [first])
            self.assertIs(self.column.get_current_tab(), first)
            self.column._close_tab(0)
            self.column._close_tab(notebook.indexOf(self.column._add_tab_page))
            self.assertEqual(self.column.get_all_tabs(), [first])

    def test_themed_tabs_keep_geometry_when_created_through_plus(self):
        language = LanguageManagerQt()
        self.addCleanup(language.apply_language, "en_US")
        notebook = self.column.notebook
        bar = notebook.tabBar()
        for locale in ("en_US", "zh_CN"):
            language.apply_language(locale)
            for theme in ("light", "dark"):
                while len(self.column.get_all_tabs()) > 1:
                    self.column._close_tab(notebook.count() - 2)
                self.app.sendPostedEvents(None, QEvent.DeferredDelete)
                self.theme.load_theme(theme)
                self.column.setStyleSheet(self.theme.stylesheet())
                self.column.apply_theme(self.theme)
                self.app.processEvents()
                for count in range(2, 7):
                    QTest.mouseClick(bar, Qt.LeftButton, pos=bar.tabRect(notebook.count() - 1).center())
                    self.app.processEvents()
                    with self.subTest(locale=locale, theme=theme, count=count):
                        self.assertEqual(len(self.column.get_all_tabs()), count)
                        self.assert_add_page_has_no_close_button()
                        widths = []
                        for index in range(count):
                            button = self.close_button(index)
                            tab_rect = bar.tabRect(index)
                            self.assertTrue(button.isVisible())
                            self.assertIs(
                                self.column.childAt(button.mapTo(self.column, button.rect().center())), button
                            )
                            self.assertEqual(button.size().toTuple(), (20, 20))
                            self.assertTrue(tab_rect.contains(button.geometry()))
                            self.assertFalse(button.geometry().intersects(bar.tabRect(notebook.count() - 1)))
                            self.assertLessEqual(abs(button.geometry().center().y() - tab_rect.center().y()), 1)
                            option = QStyleOptionTab()
                            bar.initStyleOption(option, index)
                            label_rect = bar.style().subElementRect(QStyle.SE_TabBarTabText, option, bar)
                            self.assertGreaterEqual(
                                label_rect.width(), bar.fontMetrics().horizontalAdvance(bar.tabText(index))
                            )
                            if index > 0:
                                widths.append(tab_rect.width())
                        self.assertEqual(len(set(widths)), 1)

    def test_tab_height_stays_stable_when_close_controls_appear_and_disappear(self):
        notebook = self.column.notebook
        bar = notebook.tabBar()
        for theme in ("light", "dark"):
            with self.subTest(theme=theme):
                while len(self.column.get_all_tabs()) > 1:
                    self.column._close_tab(notebook.count() - 2)
                self.theme.load_theme(theme)
                self.column.setStyleSheet(self.theme.stylesheet())
                self.column.apply_theme(self.theme)
                self.app.processEvents()
                initial_height = bar.height()
                QTest.mouseClick(bar, Qt.LeftButton, pos=bar.tabRect(notebook.count() - 1).center())
                self.app.processEvents()
                self.assertEqual(bar.height(), initial_height)
                QTest.mouseClick(self.close_button(1), Qt.LeftButton)
                self.app.processEvents()
                self.assertEqual(bar.height(), initial_height)
                self.assertFalse(notebook.tabsClosable())

    def test_closing_background_tab_preserves_selection_and_remaining_buttons(self):
        notebook = self.column.notebook
        first = self.column.get_current_tab()
        second = self.column._add_new_tab()
        third = self.column._add_new_tab()
        QTest.mouseClick(self.close_button(notebook.indexOf(second)), Qt.LeftButton)
        self.assertEqual(self.column.get_all_tabs(), [first, third])
        self.assertIs(self.column.get_current_tab(), third)
        self.assertTrue(notebook.tabsClosable())
        self.assertIsNotNone(self.close_button(0))
        self.assertIsNotNone(self.close_button(1))
        self.assert_add_page_has_no_close_button()
        QTest.mouseClick(self.close_button(1), Qt.LeftButton)
        self.assertIs(self.column.get_current_tab(), first)
        self.assertFalse(notebook.tabsClosable())

    def test_native_close_tooltips_retranslate_without_recreating_tabs(self):
        language = LanguageManagerQt()
        self.addCleanup(language.apply_language, "en_US")
        self.column._add_new_tab()
        tabs = self.column.get_all_tabs()
        for locale in ("zh_CN", "en_US"):
            language.apply_language(locale)
            self.app.processEvents()
            for index in (0, 1):
                self.assertEqual(self.close_button(index).toolTip(), self.column.tr("Close tab"))
            self.assertEqual(self.column.get_all_tabs(), tabs)
            self.assert_add_page_has_no_close_button()

    def test_close_glyph_remains_visible_in_both_themes(self):
        self.column._add_new_tab()
        for theme in ("light", "dark"):
            with self.subTest(theme=theme):
                self.theme.load_theme(theme)
                self.column.setStyleSheet(self.theme.stylesheet())
                self.column.apply_theme(self.theme)
                self.app.processEvents()
                button = self.close_button(0)
                self.assertTrue(button.isVisible())
                self.assertEqual(button.size().toTuple(), (20, 20))
                image = button.grab().toImage()
                glyph_pixels = []
                for y in range(image.height()):
                    for x in range(image.width()):
                        lightness = image.pixelColor(x, y).lightness()
                        if (theme == "dark" and lightness > 150) or (theme == "light" and lightness < 128):
                            glyph_pixels.append((x, y))
                self.assertGreater(len(glyph_pixels), 10, "Close glyph is missing or lacks contrast")
                glyph_width = max(x for x, y in glyph_pixels) - min(x for x, y in glyph_pixels) + 1
                glyph_height = max(y for x, y in glyph_pixels) - min(y for x, y in glyph_pixels) + 1
                self.assertLessEqual(glyph_width, image.width() * 0.45)
                self.assertLessEqual(glyph_height, image.height() * 0.45)

    def test_native_close_button_states_stay_transparent_and_inside_tabs(self):
        for _ in range(3):
            self.column._add_new_tab()
        self.column.notebook.setCurrentIndex(0)
        bar = self.column.notebook.tabBar()
        for theme in ("light", "dark"):
            self.theme.load_theme(theme)
            self.column.setStyleSheet(self.theme.stylesheet())
            self.column.apply_theme(self.theme)
            self.app.processEvents()
            for index in range(4):
                with self.subTest(theme=theme, selected=index == 0):
                    button = self.close_button(index)
                    self.app.sendEvent(button, QEvent(QEvent.Leave))
                    normal = button.grab().toImage()
                    position = QPointF(button.rect().center())
                    global_position = QPointF(button.mapToGlobal(button.rect().center()))
                    self.app.sendEvent(button, QEnterEvent(position, position, global_position))
                    self.assertTrue(button.underMouse())
                    self.assertEqual(button.grab().toImage(), normal)
                    self.assertTrue(bar.tabRect(index).contains(button.geometry()))
                    QTest.mousePress(button, Qt.LeftButton, pos=button.rect().center())
                    try:
                        self.assertTrue(button.isDown())
                        self.assertEqual(button.grab().toImage(), normal)
                        self.assertTrue(bar.tabRect(index).contains(button.geometry()))
                    finally:
                        QTest.mouseRelease(button, Qt.LeftButton, pos=QPoint(-10, -10))
                    self.assertEqual(len(self.column.get_all_tabs()), 4)
                    self.app.sendEvent(button, QEvent(QEvent.Leave))

    def test_highlight_reserves_separate_space_and_does_not_shift_on_activation(self):
        self.column.setStyleSheet(self.theme.stylesheet())
        self.app.processEvents()
        notebook_geometry = self.column.notebook.geometry()
        self.assertEqual(self.column.top_border.height(), 2)
        self.assertEqual(notebook_geometry.top() - self.column.top_border.geometry().bottom() - 1, 4)
        for active in (True, False, True):
            self.column.set_active(active)
            self.app.processEvents()
            self.assertEqual(self.column.notebook.geometry(), notebook_geometry)
            self.assertEqual(self.column.is_active, active)
        self.assertEqual(self.column.notebook.tabBar().objectName(), "serialTabBar")

    def test_dual_column_highlight_tracks_selected_send_target(self):
        panel = WorkPanel(self.config, self.theme)
        try:
            panel.toggle_dual_panel_mode(True)
            panel._activate(panel.secondary_column)
            self.assertFalse(panel.main_column.is_active)
            self.assertTrue(panel.secondary_column.is_active)
            self.assertIs(panel.get_current_work_tab(), panel.secondary_column.get_current_tab())
            panel.toggle_dual_panel_mode(False)
            self.assertFalse(panel.main_column.is_active)
            self.assertFalse(panel.secondary_column.is_active)
            self.assertIs(panel.get_current_work_tab(), panel.main_column.get_current_tab())
        finally:
            self.assertEqual(panel.cleanup(), [])
            panel.deleteLater()


if __name__ == "__main__":
    unittest.main()
