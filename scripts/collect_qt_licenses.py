"""Copy the Qt/PySide6 license texts stored with the source release."""

import shutil
import sys
from pathlib import Path


def main():
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python3 scripts/collect_qt_licenses.py <target-directory>")
    target = Path(sys.argv[1])
    target.mkdir(parents=True, exist_ok=True)
    root = Path(__file__).resolve().parent.parent / "licenses"
    for filename in ("LGPL-3.0.txt", "GPL-3.0.txt"):
        source = root / filename
        if not source.exists() or source.stat().st_size < 1000:
            raise RuntimeError(f"Complete license text is missing: {source}")
        shutil.copy2(source, target / filename)
    print(f"Copied the complete LGPLv3 and GPLv3 license texts to {target}")


if __name__ == "__main__":
    main()
