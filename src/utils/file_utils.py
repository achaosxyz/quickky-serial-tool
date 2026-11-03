"""
File path helpers.

Author: aCHAOS
Email: achaosxyz@gmail.com
"""

import os
import sys


def resource_path(filename):
    """
    Return a resource path.
    Use the source tree in development and PyInstaller's temporary directory when packaged.

    Args:
        filename (str): Resource filename.

    Returns:
        str: Absolute resource path.
    """
    if hasattr(sys, "_MEIPASS"):
        # PyInstaller extracts bundled resources to this temporary directory.
        return os.path.join(sys._MEIPASS, filename)

    # In development, resources live in the project root two levels above utils.
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(os.path.dirname(current_dir))
    return os.path.join(project_root, filename)


def get_base_path():
    """
    Return the application base path.

    Returns:
        str: Base path for runtime configuration.
    """
    if getattr(sys, 'frozen', False):
        # Store configuration beside the packaged executable.
        return os.path.dirname(sys.executable)
    else:
        # Use the project root during development.
        current_dir = os.path.dirname(os.path.abspath(__file__))
        return os.path.dirname(os.path.dirname(current_dir))
