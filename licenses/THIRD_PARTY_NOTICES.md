# Third-Party Components and License Notices

QSerial project code is licensed under the [MIT License](../LICENSE).

The released Windows single-file application uses PySide6 (Qt for Python) and the Qt runtime under LGPLv3. The distribution's `licenses/LGPL-3.0.txt` and `licenses/GPL-3.0.txt` contain the complete license texts. Corresponding source code and license information are available from the official Qt locations: <https://download.qt.io/official_releases/qt/> and <https://code.qt.io/cgit/pyside/pyside-setup.git/>.

The project does not modify PySide6 or Qt source code. The Windows single-file build bundles and extracts the Qt/PySide6 runtime at execution time. Before release, confirm the relinking, debugging-modification, and installation-information obligations for the specific PyInstaller and Qt/PySide6 versions. The project provides complete source code and `build.bat` for rebuilding the distribution from source.

pyserial is licensed under the BSD License; its license and source information are available at <https://github.com/pyserial/pyserial>.
