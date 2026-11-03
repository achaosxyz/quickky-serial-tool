"""Capture isolated bilingual application and settings views for manual review."""

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from PySide6.QtCore import QTimer, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialogButtonBox, QMessageBox

from components.quick_command_dialog_qt import QuickCommandDialog
from pages.main_window_qt import MainWindow
from pages.settings_dialog_qt import SettingsDialog


def main():
    output = Path(os.environ["QSERIAL_VISUAL_DIR"])
    output.mkdir(parents=True, exist_ok=True)
    app = QApplication.instance() or QApplication([])
    with tempfile.TemporaryDirectory(prefix="qserial-visual-") as directory:
        with patch("utils.config_manager.get_base_path", return_value=directory):
            window = MainWindow()
            window.show()
            try:
                for language in ("en_US", "zh_CN"):
                    window.language_manager.apply_language(language)
                    for theme in ("light", "dark"):
                        window._change_theme(theme)
                        QTest.qWait(100)
                        if not window.grab().save(str(output / f"window-{language}-{theme}.png")):
                            raise RuntimeError("Could not save window screenshot")
                    window.dual_action.trigger()
                    QTest.qWait(100)
                    if not window.grab().save(str(output / f"dual-{language}.png")):
                        raise RuntimeError("Could not save dual-column screenshot")
                    window.dual_action.trigger()
                    dialog = SettingsDialog(window, window.config_manager)
                    dialog.show()
                    QTest.qWait(100)
                    if not dialog.grab().save(str(output / f"settings-{language}.png")):
                        raise RuntimeError("Could not save settings screenshot")
                    dialog.close()
                    history = window.command_panel.send_history_panel
                    message = QMessageBox(QMessageBox.Question, history.tr("Confirm"),
                                          history.tr("Clear all send history?"),
                                          QMessageBox.Yes | QMessageBox.No, window)
                    message.show()
                    QTest.qWait(100)
                    if not message.grab().save(str(output / f"message-{language}.png")):
                        raise RuntimeError("Could not save message screenshot")
                    message.close()
                    command = QuickCommandDialog(window)
                    command.name_text.setText("command")
                    command.mode_combo.setCurrentText("HEX")
                    command.data_text.setPlainText("not hex")
                    command.show()
                    captured = []

                    def capture_warning():
                        warning = QApplication.activeModalWidget()
                        captured.append(isinstance(warning, QMessageBox) and warning.grab().save(
                            str(output / f"invalid-hex-{language}.png")))
                        if warning:
                            warning.accept()

                    QTimer.singleShot(100, capture_warning)
                    QTest.mouseClick(command.findChild(QDialogButtonBox).button(QDialogButtonBox.Ok), Qt.LeftButton)
                    if captured != [True]:
                        raise RuntimeError("Could not save HEX validation warning screenshot")
                    command.close()
                    captured.clear()

                    def capture_config_warning():
                        warning = QApplication.activeModalWidget()
                        captured.append(isinstance(warning, QMessageBox) and warning.grab().save(
                            str(output / f"config-warning-{language}.png")))
                        if warning:
                            warning.accept()

                    QTimer.singleShot(100, capture_config_warning)
                    window._warn_config_load_failure()
                    if captured != [True]:
                        raise RuntimeError("Could not save configuration warning screenshot")
            finally:
                window.close()
                app.processEvents()
    print(f"Visual artifacts: {output}")


if __name__ == "__main__":
    main()
