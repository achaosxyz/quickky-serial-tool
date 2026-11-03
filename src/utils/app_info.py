"""
Application metadata helpers.

Author: aCHAOS
Email: achaosxyz@gmail.com
"""

import os
import sys
from html import escape

from PySide6.QtCore import QCoreApplication

from .file_utils import get_base_path


class AppInfo:
    """Application metadata and formatted about text."""

    # Basic application metadata.
    APP_NAME = "QSerial"
    APP_FULL_NAME = "Quickky Serial Tool"
    AUTHOR = "aCHAOS"
    EMAIL = "achaosxyz@gmail.com"

    # Source repository.
    GITHUB_URL = "https://github.com/achaosxyz/quickky-serial-tool"

    # English source text is translated when displayed.
    DESCRIPTION = "A powerful serial debugging tool"

    @classmethod
    def _get_version_info(cls):
        """
        Read the generated version information.

        Returns:
            tuple: (version, build_time)
        """
        try:
            # The generated version module lives in the application base path.
            sys.path.insert(0, get_base_path())
            import version
            return version.VERSION, version.BUILD_TIME
        except:
            return "1.0.0", QCoreApplication.translate("AppInfo", "Unknown")

    @classmethod
    def get_about_text(cls):
        """
        Build plain text for the about dialog.

        Returns:
            str: Formatted about text.
        """
        version, build_time = cls._get_version_info()
        translate = QCoreApplication.translate
        version_label = translate("AppInfo", "Version:")
        build_time_label = translate("AppInfo", "Build time:")
        author_label = translate("AppInfo", "Author:")
        email_label = translate("AppInfo", "Email:")
        source_label = translate("AppInfo", "Open source:")
        description = translate("AppInfo", "A powerful serial debugging tool")

        return f"""{cls.APP_NAME} ({cls.APP_FULL_NAME})

{version_label} {version}
{build_time_label} {build_time}

{author_label} {cls.AUTHOR}
{email_label} {cls.EMAIL}

{description}

{source_label}
GitHub: {cls.GITHUB_URL}"""

    @classmethod
    def get_about_html(cls):
        """Build about-dialog HTML with clickable repository links."""
        version, build_time = cls._get_version_info()
        translate = QCoreApplication.translate
        version_label = translate("AppInfo", "Version:")
        build_time_label = translate("AppInfo", "Build time:")
        author_label = translate("AppInfo", "Author:")
        email_label = translate("AppInfo", "Email:")
        source_label = translate("AppInfo", "Open source:")
        description = translate("AppInfo", "A powerful serial debugging tool")
        return f"""<b>{escape(cls.APP_NAME)} ({escape(cls.APP_FULL_NAME)})</b><br><br>
{version_label} {escape(version)}<br>
{build_time_label} {escape(build_time)}<br><br>
{author_label} {escape(cls.AUTHOR)}<br>
{email_label} {escape(cls.EMAIL)}<br><br>
{escape(description)}<br><br>
{source_label}<br>
GitHub: <a href=\"{escape(cls.GITHUB_URL)}\">{escape(cls.GITHUB_URL)}</a>"""

    @classmethod
    def get_window_title(cls):
        """
        Return the versioned window title.

        Returns:
            str: Window title.
        """
        version, _ = cls._get_version_info()
        return f'{cls.APP_NAME} v{version} - by {cls.AUTHOR}'

    @classmethod
    def get_app_name(cls):
        """Return the short application name."""
        return cls.APP_NAME

    @classmethod
    def get_full_name(cls):
        """Return the full application name."""
        return cls.APP_FULL_NAME

    @classmethod
    def get_author(cls):
        """Return the author name."""
        return cls.AUTHOR

    @classmethod
    def get_email(cls):
        """Return the author email."""
        return cls.EMAIL

    @classmethod
    def get_description(cls):
        """Return the translated application description."""
        return QCoreApplication.translate("AppInfo", "A powerful serial debugging tool")
