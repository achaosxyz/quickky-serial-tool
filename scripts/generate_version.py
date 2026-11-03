"""
Version file generation script.

Author: aCHAOS
Email: achaosxyz@gmail.com
"""

from datetime import datetime
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent.parent
VERSION_FILE = ROOT_DIR / "VERSION"


def load_version() -> str:
    """Read the only version source from the project root."""
    try:
        version = VERSION_FILE.read_text(encoding="utf-8").strip()
    except FileNotFoundError as error:
        raise RuntimeError(f"Version file not found: {VERSION_FILE}") from error

    if not version:
        raise RuntimeError(f"Version file is empty: {VERSION_FILE}")
    return version

def generate_version_file():
    """Generate version.py."""
    version = load_version()
    build_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    content = f'''"""
Version information (generated automatically; do not edit manually).

Author: aCHAOS
Email: achaosxyz@gmail.com
"""

VERSION = "{version}"
BUILD_TIME = "{build_time}"
'''
    
    # Write the generated module to the project root.
    version_file = ROOT_DIR / "version.py"
    
    with version_file.open('w', encoding='utf-8') as f:
        f.write(content)
    
    print(f"Generated version file: {version_file}")
    print(f"Version: {version}")
    print(f"Build time: {build_time}")

if __name__ == '__main__':
    generate_version_file()
