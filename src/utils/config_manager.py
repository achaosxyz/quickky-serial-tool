"""Configuration management and persistence."""

import json
import os
import tempfile
import time
from copy import deepcopy
from datetime import datetime

from .file_utils import get_base_path
from . import config_schema as schema


class ConfigManager:
    """Load, validate, and persist runtime configuration."""

    HISTORY_SAVE_INTERVAL_SECONDS = 2.0

    def __init__(self, config_file="config.json"):
        self.config_file = os.path.join(get_base_path(), config_file)
        self._last_config_write_at = 0.0
        self._dirty = False
        self._load_failed = False
        self._config = self._load_config()

    @property
    def config(self):
        """Return an independent snapshot of the configuration."""
        return deepcopy(self._config)

    @property
    def load_failed(self):
        """Whether the existing configuration could not be read or parsed."""
        return self._load_failed

    def _write_config(self, config):
        directory = os.path.dirname(os.path.abspath(self.config_file))
        file_descriptor, temporary_path = tempfile.mkstemp(
            prefix=".config-", suffix=".tmp", dir=directory, text=True,
        )
        try:
            with os.fdopen(file_descriptor, "w", encoding="utf-8") as stream:
                json.dump(config, stream, indent=2, ensure_ascii=False)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary_path, self.config_file)
        except OSError:
            try:
                os.unlink(temporary_path)
            except OSError:
                pass
            raise

    def _load_config(self):
        if not os.path.exists(self.config_file):
            config = schema.get_default_config()
            self._last_saved_config = deepcopy(config)
            return config
        try:
            with open(self.config_file, "r", encoding="utf-8") as stream:
                raw = json.load(stream)
            config = schema.normalize_config(raw)
        except (OSError, ValueError, RecursionError) as error:
            print(f"Configuration I/O failed: {error}")
            self._load_failed = True
            config = schema.get_default_config()
            self._last_saved_config = deepcopy(config)
            return config
        self._last_saved_config = deepcopy(raw)
        self._dirty = config != raw
        if self._dirty:
            try:
                self._write_config(config)
            except OSError as error:
                print(f"Configuration I/O failed: {error}")
            else:
                self._last_saved_config = deepcopy(config)
                self._dirty = False
                self._last_config_write_at = time.monotonic()
        return config

    def save_config(self, force=False, min_interval=0.0):
        self._dirty = self._dirty or self._config != self._last_saved_config
        if not self._dirty:
            return True
        if self._load_failed:
            return False
        if not force and min_interval > 0 and time.monotonic() - self._last_config_write_at < min_interval:
            return True
        try:
            self._write_config(self._config)
        except OSError as error:
            print(f"Configuration I/O failed: {error}")
            return False
        self._last_saved_config = deepcopy(self._config)
        self._last_config_write_at = time.monotonic()
        self._dirty = False
        return True

    def get_last_port(self, panel="main"):
        return self._config["last_port_secondary" if panel == "secondary" else "last_port_main"]

    def set_last_port(self, port, panel="main"):
        self._config["last_port_secondary" if panel == "secondary" else "last_port_main"] = port
        self.save_config()

    def get_last_log_directory(self):
        """Return the last selected log directory."""
        return self._config["last_log_directory"]

    def set_last_log_directory(self, directory):
        """Persist the directory without storing the log file path."""
        self._config["last_log_directory"] = directory if isinstance(directory, str) else ""
        self.save_config()

    def _ensure_port_config(self, port):
        if port not in self._config["port_configs"]:
            self._config["port_configs"][port] = schema.get_default_port_config()
            self.save_config()
        config = self._config["port_configs"][port]
        config["receive_settings"]["save_log"] = False
        return config

    def get_port_config(self, port):
        return deepcopy(self._ensure_port_config(port))

    def save_port_config(self, port, config):
        self._config["port_configs"][port] = schema.normalize_port_config(config)
        self.save_config()

    def update_serial_settings(self, port, settings):
        port_config = self._ensure_port_config(port)
        port_config["serial_settings"].update(settings)
        self.save_port_config(port, port_config)

    def update_receive_settings(self, port, settings):
        port_config = self._ensure_port_config(port)
        port_config["receive_settings"].update(settings)
        self.save_port_config(port, port_config)

    def update_send_settings(self, port, settings):
        port_config = self._ensure_port_config(port)
        port_config["send_settings"].update(settings)
        self.save_port_config(port, port_config)

    def export_config(self, file_path):
        try:
            with open(file_path, "w", encoding="utf-8") as stream:
                json.dump(self._config, stream, indent=2, ensure_ascii=False)
            return True
        except OSError as error:
            print(f"Configuration export failed: {error}")
            return False

    def import_config(self, file_path):
        try:
            with open(file_path, "r", encoding="utf-8") as stream:
                raw = json.load(stream)
            config = schema.normalize_config(raw)
            self._write_config(config)
            self._config = config
            self._last_saved_config = deepcopy(config)
            self._last_config_write_at = time.monotonic()
            self._dirty = False
            self._load_failed = False
            return True
        except (OSError, ValueError, json.JSONDecodeError, RecursionError) as error:
            print(f"Configuration import failed: {error}")
            return False

    def get_quick_command_groups(self):
        return deepcopy(self._config["quick_command_groups"])

    def set_quick_command_groups(self, groups):
        self._config["quick_command_groups"] = schema.normalize_quick_command_groups(groups)
        self.save_config()

    def add_send_history(self, data, mode="TEXT"):
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        history = self._config["send_history"]
        if history and history[0]["data"] == data and history[0]["mode"] == mode:
            history[0]["time"] = current_time
        else:
            history.insert(0, {"data": data, "mode": mode, "time": current_time})
        max_history = self.get_global_settings()["send_history_max"]
        del history[max_history:]
        self.save_config(min_interval=self.HISTORY_SAVE_INTERVAL_SECONDS)

    def flush_config(self):
        """Flush pending changes when the window closes."""
        return self.save_config(force=True)

    def get_send_history(self):
        return deepcopy(self._config["send_history"])

    def clear_send_history(self):
        self._config["send_history"] = []
        self.save_config()

    def get_command_panel_visible(self):
        return self._config["command_panel_visible"]

    def set_command_panel_visible(self, visible):
        self._config["command_panel_visible"] = bool(visible)
        self.save_config()

    def get_send_text(self, port):
        return self.get_port_config(port)["send_text"]

    def set_send_text(self, port, text):
        port_config = self._ensure_port_config(port)
        port_config["send_text"] = text if isinstance(text, str) else ""
        self.save_port_config(port, port_config)

    def get_dual_panel_mode(self):
        return self._config["dual_panel_mode"]

    def set_dual_panel_mode(self, enabled):
        self._config["dual_panel_mode"] = bool(enabled)
        self.save_config()

    def get_global_settings(self):
        return deepcopy(self._config["global_settings"])

    def set_global_settings(self, settings):
        raw = dict(self._config)
        raw["global_settings"] = settings
        self._config = schema.normalize_config(raw)
        self.save_config()

    def get_theme(self):
        return self._config["theme"]

    def get_language(self):
        return self._config["language"]

    def set_language(self, language):
        self._config["language"] = (
            language if isinstance(language, str) and language in schema.LANGUAGES else "system"
        )
        self.save_config()

    def set_theme(self, theme_name):
        self._config["theme"] = theme_name if isinstance(theme_name, str) and theme_name in schema.THEMES else "light"
        self.save_config()

    def get_font_size(self):
        return self.get_global_settings()["fontSize"]

    def set_font_size(self, size):
        settings = dict(self.get_global_settings())
        settings["fontSize"] = size
        self.set_global_settings(settings)
