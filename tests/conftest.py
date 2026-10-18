"""Keep imports on the package selected by the Meson test entry point."""

import os
from pathlib import Path
import sys

package_root = os.environ.get("BOTTLES_TEST_PACKAGE_ROOT", str(Path(__file__).resolve().parents[1]))
if package_root not in sys.path:
    sys.path.insert(0, package_root)
