"""Exercise the packaged application without touching user configuration or ports."""

import json
import tempfile
import traceback
from pathlib import Path

from PySide6.QtCore import QTimer

from pages.main_window_qt import MainWindow
from utils.app_info import AppInfo
from utils.config_manager import ConfigManager


def run_smoke_test(app, report_directory):
    """Run the real event loop, capture both languages, and exit with a test result."""
    report_directory = Path(report_directory).resolve()
    report_directory.mkdir(parents=True, exist_ok=True)
    report = {"success": False, "languages": []}
    window = None
    with tempfile.TemporaryDirectory(prefix="qserial-smoke-config-") as directory:
        try:
            config = ConfigManager(str(Path(directory) / "config.json"))
            config.set_language("en_US")
            window = MainWindow(config_manager=config)
            window.show()

            def verify():
                # Exceptions must become a nonzero result, not escape a Qt slot.
                try:
                    tab = window.work_panel.main_column.get_current_tab()
                    if not window.isVisible() or not tab.connect_btn.isEnabled():
                        raise RuntimeError("Main window did not initialize")
                    for language, label in (("en_US", "Open port"), ("zh_CN", "打开串口")):
                        window.language_manager.apply_language(language)
                        app.processEvents()
                        if tab.connect_btn.text() != label:
                            raise RuntimeError(f"Missing application translation: {language}")
                        if not window.grab().save(str(report_directory / f"{language}.png")):
                            raise RuntimeError(f"Could not capture {language} window")
                        report["languages"].append(language)
                    errors = window.work_panel.cleanup()
                    if errors:
                        raise RuntimeError("; ".join(errors))
                    if not config.flush_config():
                        raise RuntimeError("Could not save isolated configuration")
                    report["version"], _ = AppInfo._get_version_info()
                    window.close()
                    report["success"] = True
                    app.exit(0)
                except Exception:
                    report["error"] = traceback.format_exc()
                    app.exit(1)

            QTimer.singleShot(0, verify)
            exit_code = app.exec()
        except Exception:
            report["error"] = traceback.format_exc()
            exit_code = 1
        finally:
            if window is not None:
                errors = window.work_panel.cleanup()
                if errors:
                    report["success"] = False
                    report["error"] = "; ".join(errors)
                    exit_code = 1
            (report_directory / "result.json").write_text(
                json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8",
            )
    return exit_code if report["success"] else 1
