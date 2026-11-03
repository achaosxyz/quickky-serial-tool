"""Release ZIP validation and isolated executable invocation."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts import smoke_windows


class PackageSmokeTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="qserial-zip-test-")
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.archive = self.directory / "package.zip"
        self.output = self.directory / "reports"

    def package(self, extra=None):
        with ZipFile(self.archive, "w") as archive:
            for name in ("QSerial.exe", "LICENSE", "licenses/THIRD_PARTY_NOTICES.md"):
                archive.writestr(name, "test data")
            if extra is not None:
                archive.writestr(extra, "unexpected data")

    def test_rejects_configuration_and_invalid_paths(self):
        for extra in ("config.json", "dev.env", "licenses/../../config.json"):
            self.package(extra)
            with self.subTest(extra=extra), self.assertRaises(RuntimeError):
                smoke_windows.extract_package(self.archive, self.directory / "extract")

    def test_requires_executable_and_license_materials(self):
        with ZipFile(self.archive, "w") as archive:
            archive.writestr("QSerial.exe", "test")
        with self.assertRaisesRegex(RuntimeError, "missing"):
            smoke_windows.extract_package(self.archive, self.directory / "extract")

    def test_launches_extracted_executable_and_requires_matching_fresh_report(self):
        self.package()
        self.output.mkdir()
        report_path = self.output / "result.json"
        report_path.write_text("stale", encoding="utf-8")
        def run(command, **kwargs):
            self.assertFalse(report_path.exists())
            self.assertNotEqual(Path(kwargs["cwd"]), Path.cwd())
            self.assertEqual(Path(command[0]).parent, Path(kwargs["cwd"]))
            self.assertEqual(command[1:], ["--smoke-test", str(self.output.resolve())])
            self.assertEqual(kwargs["env"]["QT_QPA_PLATFORM"], "offscreen")
            self.assertNotIn("QT_PLUGIN_PATH", kwargs["env"])
            report_path.write_text(json.dumps({"success": True, "version": "3.0.0",
                                              "languages": ["en_US", "zh_CN"]}), encoding="utf-8")
        with patch.dict(os.environ, {"QT_PLUGIN_PATH": "host Qt"}), \
             patch.object(smoke_windows.subprocess, "run", side_effect=run):
            smoke_windows.smoke_package(self.archive, "3.0.0", self.output)

    def test_a_live_or_failed_process_is_not_success(self):
        self.package()
        with patch.object(smoke_windows.subprocess, "run", side_effect=subprocess.TimeoutExpired("QSerial", 1)):
            with self.assertRaises(subprocess.TimeoutExpired):
                smoke_windows.smoke_package(self.archive, "3.0.0", self.output)
