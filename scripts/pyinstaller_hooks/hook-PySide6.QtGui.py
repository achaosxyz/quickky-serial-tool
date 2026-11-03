"""Bundle Windows and offscreen platform plugins for runtime and smoke tests."""

from pathlib import Path

from PyInstaller.utils.hooks import get_module_file_attribute


_pyside_dir = Path(get_module_file_attribute("PySide6.QtGui")).parent

hiddenimports = ["PySide6.QtCore"]
binaries = [
    (str(_pyside_dir / "plugins" / "platforms" / name), "PySide6/plugins/platforms")
    for name in ("qwindows.dll", "qoffscreen.dll")
]
datas = []
