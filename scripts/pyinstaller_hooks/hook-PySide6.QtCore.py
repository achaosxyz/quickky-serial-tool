"""Bundle the Qt standard-widget translation used by QSerial."""

from PyInstaller.utils.hooks import collect_data_files

hiddenimports = []
binaries = []
datas = collect_data_files("PySide6", includes=["translations/qtbase_zh_CN.qm"])
