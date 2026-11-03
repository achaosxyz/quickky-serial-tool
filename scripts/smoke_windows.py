"""Validate a release ZIP and smoke-test its executable with isolated settings."""

import argparse
import json
import os
import subprocess
import tempfile
from pathlib import Path, PurePosixPath
from zipfile import ZipFile


def extract_package(archive_path, destination):
    """Check the distribution contract before extracting the tested package."""
    with ZipFile(archive_path) as archive:
        names = set(archive.namelist())
        required = {"QSerial.exe", "LICENSE", "licenses/THIRD_PARTY_NOTICES.md"}
        if not required <= names:
            raise RuntimeError("Release ZIP is missing executable or license materials")
        for name in names:
            path = PurePosixPath(name)
            if path.is_absolute() or ".." in path.parts or "\\" in name:
                raise RuntimeError(f"Invalid release path: {name}")
            if name not in required and not name.startswith("licenses/"):
                raise RuntimeError(f"Unexpected release file: {name}")
        archive.extractall(destination)


def smoke_package(archive_path, version, output_directory, timeout=90):
    """Require clean process exit and a fresh successful bilingual report."""
    output_directory = Path(output_directory).resolve()
    output_directory.mkdir(parents=True, exist_ok=True)
    report_path = output_directory / "result.json"
    report_path.unlink(missing_ok=True)
    environment = os.environ.copy()
    for key in ("QT_PLUGIN_PATH", "QT_QPA_PLATFORM_PLUGIN_PATH", "PYTHONPATH"):
        environment.pop(key, None)
    environment["QT_QPA_PLATFORM"] = "offscreen"
    environment.setdefault("QT_QPA_FONTDIR", str(Path(os.environ["WINDIR"]) / "Fonts"))
    with tempfile.TemporaryDirectory(prefix="qserial-package-") as directory:
        extract_package(archive_path, directory)
        subprocess.run(
            [str(Path(directory) / "QSerial.exe"), "--smoke-test", str(output_directory)],
            cwd=directory, env=environment, timeout=timeout, check=True,
        )
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if not report["success"] or report["version"] != version:
        raise RuntimeError(f"Packaged startup failed: {report}")
    if report["languages"] != ["en_US", "zh_CN"]:
        raise RuntimeError("Packaged startup did not verify both languages")
    print(f"Packaged smoke test passed: QSerial {version} (English and Chinese)")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("--version", required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    smoke_package(arguments.archive, arguments.version, arguments.output)


if __name__ == "__main__":
    main()
