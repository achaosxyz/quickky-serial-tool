"""Tabbed workspace column."""

from PySide6.QtCore import QEvent, QSize, Qt
from PySide6.QtWidgets import QFrame, QMenu, QMessageBox, QTabBar, QTabWidget, QVBoxLayout, QWidget

from .work_tab_qt import WorkTab


class WorkColumn(QWidget):
    def __init__(self, config_manager, theme_manager=None, panel_type="main", on_column_activated=None, on_tab_data_sent=None, parent=None, port_provider=None):
        super().__init__(parent)
        self.config_manager, self.theme_manager, self.panel_type, self.on_column_activated, self.on_tab_data_sent, self.is_active = config_manager, theme_manager, panel_type, on_column_activated, on_tab_data_sent, False
        self.port_provider = port_provider
        self.notebook = QTabWidget()
        self.notebook.tabBar().setObjectName("serialTabBar")
        self.notebook.setTabsClosable(False)
        self.notebook.tabCloseRequested.connect(self._close_tab)
        self.notebook.currentChanged.connect(self._on_changed)
        self.notebook.tabBar().tabBarClicked.connect(self._on_tab_bar_clicked)
        self.notebook.tabBar().tabBarDoubleClicked.connect(self._close_tab_on_double_click)
        self.notebook.tabBar().setContextMenuPolicy(Qt.CustomContextMenu)
        self.notebook.tabBar().customContextMenuRequested.connect(self._tab_menu)
        self._add_tab_page = QWidget(self.notebook)
        self.notebook.blockSignals(True)
        self.notebook.addTab(self._add_tab_page, "+")
        self.notebook.blockSignals(False)
        self.top_border = QFrame()
        self.top_border.setFixedHeight(2)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.top_border)
        layout.addSpacing(4)
        layout.addWidget(self.notebook)
        self.set_active(False)
        self._add_new_tab(True)
    def _add_new_tab(self, first=False):
        tab = WorkTab(self.config_manager, is_first_tab=first,
                      on_data_sent=self.on_tab_data_sent, panel_type=self.panel_type,
                      parent=self, port_provider=self.port_provider)
        if self.theme_manager is not None:
            tab.apply_theme(self.theme_manager, self.config_manager.get_font_size())
        tab.port_changed.connect(self._on_tab_port_changed)
        self._watch_activation(tab)
        index = self.notebook.insertTab(self.notebook.indexOf(self._add_tab_page), tab, self.tr("New tab"))
        port = tab.serial_settings.get_current_port()
        self.notebook.setTabText(index, port or self.tr("New tab"))
        self.notebook.setCurrentIndex(index)
        self._refresh_close_buttons()
        return tab
    def _on_tab_port_changed(self, port):
        index = self.notebook.indexOf(self.sender())
        if index >= 0:
            self.notebook.setTabText(index, port)
    def _is_add_tab(self, index): return self.notebook.widget(index) is self._add_tab_page
    def _refresh_close_buttons(self):
        can_close = len(self.get_all_tabs()) > 1
        self.notebook.setTabsClosable(can_close)
        bar = self.notebook.tabBar()
        for side in (QTabBar.LeftSide, QTabBar.RightSide):
            button = bar.tabButton(self.notebook.indexOf(self._add_tab_page), side)
            if button is not None:
                bar.setTabButton(self.notebook.indexOf(self._add_tab_page), side, None)
                button.deleteLater()
        for tab in self.get_all_tabs():
            index = self.notebook.indexOf(tab)
            for side in (QTabBar.LeftSide, QTabBar.RightSide):
                button = bar.tabButton(index, side)
                if button is not None:
                    if button.size() != QSize(20, 20):
                        button.setFixedSize(20, 20)
                        # Re-registering refreshes cached geometry but hides the same button.
                        bar.setTabButton(index, side, button)
                        button.show()
                    button.setToolTip(self.tr("Close tab"))
    def _watch_activation(self, widget):
        widget.installEventFilter(self)
        for child in widget.findChildren(QWidget): child.installEventFilter(self)
    def eventFilter(self, watched, event):
        if event.type() == QEvent.MouseButtonPress and self.on_column_activated: self.on_column_activated(self)
        return super().eventFilter(watched, event)
    def _on_changed(self, _index):
        if self._is_add_tab(_index): self._add_new_tab(); return
        if self.on_column_activated: self.on_column_activated(self)
    def _on_tab_bar_clicked(self, _index):
        """Activate the column even when the selected tab is clicked again."""
        if self.on_column_activated: self.on_column_activated(self)
    def _close_tab(self, index):
        if self._is_add_tab(index) or len(self.get_all_tabs()) <= 1: return
        if self.notebook.currentIndex() == index:
            self.notebook.setCurrentIndex(index - 1 if index > 0 else index + 1)
        tab = self.notebook.widget(index)
        errors = tab.cleanup()
        if errors:
            QMessageBox.warning(self, self.tr("Problems closing tab"), "\n".join(dict.fromkeys(errors)))
        self.notebook.removeTab(index)
        tab.deleteLater()
        self._refresh_close_buttons()
    def _close_tab_on_double_click(self, index):
        if index >= 0: self._close_tab(index)
    def _tab_menu(self, pos):
        index = self.notebook.tabBar().tabAt(pos)
        menu = QMenu(self)
        add = menu.addAction(self.tr("New tab"))
        add.triggered.connect(self._add_new_tab)
        if index >= 0 and not self._is_add_tab(index) and len(self.get_all_tabs()) > 1:
            close = menu.addAction(self.tr("Close tab"))
            close.triggered.connect(lambda: self._close_tab(index))
        menu.exec(self.notebook.tabBar().mapToGlobal(pos))
    def get_current_tab(self): return self.notebook.currentWidget()
    def get_all_tabs(self): return [self.notebook.widget(index) for index in range(self.notebook.count()) if not self._is_add_tab(index)]
    def set_active(self, active):
        self.is_active = active
        colors = self.theme_manager.get_theme_colors() if self.theme_manager else {}
        color = colors.get("active_border", "#0E639C") if active else colors.get("background", "transparent")
        self.top_border.setStyleSheet(f"background-color: {color}; border: none;")
    def apply_theme(self, theme_manager):
        self.theme_manager = theme_manager
        for tab in self.get_all_tabs(): tab.apply_theme(theme_manager, self.config_manager.get_font_size())
        self.set_active(self.is_active)
    def cleanup(self):
        errors = []
        for tab in self.get_all_tabs():
            errors.extend(tab.cleanup())
        return list(dict.fromkeys(errors))
    def suspend(self):
        for tab in self.get_all_tabs(): tab.suspend()

    def retranslate_ui(self):
        for tab in self.get_all_tabs():
            if not tab.serial_settings.get_current_port():
                self.notebook.setTabText(self.notebook.indexOf(tab), self.tr("New tab"))
            for side in (QTabBar.LeftSide, QTabBar.RightSide):
                button = self.notebook.tabBar().tabButton(self.notebook.indexOf(tab), side)
                if button is not None:
                    button.setToolTip(self.tr("Close tab"))

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.LanguageChange and hasattr(self, "notebook"):
            self.retranslate_ui()
