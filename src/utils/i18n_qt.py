"""Qt-native application language selection and translator ownership."""

import sys

from PySide6.QtCore import QCoreApplication, QLibraryInfo, QLocale, QTranslator
from PySide6.QtWidgets import QApplication

from .file_utils import resource_path


class LanguageManagerQt:
    """Own the installed application translator and current language."""

    LANGUAGES = {"system": "System", "zh_CN": "简体中文", "en_US": "English"}

    def __init__(self):
        self._current_language = self._system_language()
        self._translator = None
        self._qt_translator = None

    @property
    def current_language(self):
        return self._current_language

    def available_languages(self):
        languages = dict(self.LANGUAGES)
        languages["system"] = QCoreApplication.translate("LanguageManagerQt", "System")
        return languages

    @staticmethod
    def _system_language():
        return "zh_CN" if QLocale.system().name().lower().startswith("zh") else "en_US"

    @staticmethod
    def _qt_translation_path():
        if getattr(sys, "frozen", False):
            return resource_path("PySide6/translations")
        return QLibraryInfo.path(QLibraryInfo.TranslationsPath)

    def apply_language(self, language):
        """Install the selected translation and return its normalized code."""
        selected = language if language in self.LANGUAGES else "system"
        effective = self._system_language() if selected == "system" else selected
        app = QApplication.instance()
        if app is None:
            raise RuntimeError("QApplication must exist before applying a language")

        translator = None
        qt_translator = None
        if effective != "en_US":
            translator = QTranslator(app)
            path = resource_path(f"i18n/qserial_{effective}.qm")
            if not translator.load(path):
                raise RuntimeError(f"Unable to load translation: {path}")
            qt_translator = QTranslator(app)
            qt_path = self._qt_translation_path()
            if not qt_translator.load(f"qtbase_{effective}", qt_path):
                raise RuntimeError(f"Unable to load Qt translation: {qt_path}")

        if self._translator is not None:
            app.removeTranslator(self._translator)
        if self._qt_translator is not None:
            app.removeTranslator(self._qt_translator)
        if qt_translator is not None:
            app.installTranslator(qt_translator)
        if translator is not None:
            app.installTranslator(translator)
        self._translator = translator
        self._qt_translator = qt_translator
        self._current_language = effective
        return effective
