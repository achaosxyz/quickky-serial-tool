"""Update or compile Qt translation resources with PySide6 tools."""

import argparse
import subprocess
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent.parent
SOURCE_DIR = ROOT_DIR / "src"
I18N_DIR = ROOT_DIR / "i18n"
ZH_TS_FILE = I18N_DIR / "qserial_zh_CN.ts"
ZH_QM_FILE = I18N_DIR / "qserial_zh_CN.qm"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--update",
        action="store_true",
        help="Extract current source strings into the TS file before compiling it",
    )
    arguments = parser.parse_args()
    I18N_DIR.mkdir(parents=True, exist_ok=True)

    if arguments.update:
        sources = [str(path) for path in sorted(SOURCE_DIR.rglob("*.py"))]
        subprocess.run(
            ["pyside6-lupdate", *sources, "-ts", str(ZH_TS_FILE)],
            cwd=ROOT_DIR,
            check=True,
        )
    elif not ZH_TS_FILE.is_file():
        raise RuntimeError(f"Translation source not found: {ZH_TS_FILE}")

    subprocess.run(
        ["pyside6-lrelease", str(ZH_TS_FILE), "-qm", str(ZH_QM_FILE)],
        cwd=ROOT_DIR,
        check=True,
    )
    print(f"Generated translation: {ZH_QM_FILE}")


if __name__ == "__main__":
    main()
