"""QSerial PySide6 / Qt Widgets application entry point."""

import argparse
import os
import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pages.main_window_qt import MainWindow


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--smoke-test", type=Path, metavar="REPORT_DIR",
                        help="Verify startup and translations with disposable configuration")
    arguments, qt_arguments = parser.parse_known_args()
    app = QApplication([sys.argv[0], *qt_arguments])
    if arguments.smoke_test is not None:
        from main.smoke_test_qt import run_smoke_test

        return run_smoke_test(app, arguments.smoke_test)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
