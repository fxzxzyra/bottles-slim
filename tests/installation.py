#!/usr/bin/env python3
"""Meson integration test of the actual staged Python/resource installation."""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


def main():
    build, package_root, data_root = map(Path, sys.argv[1:])
    resources = data_root / "bottles/resources"
    runners = data_root / "bottles/runners"
    with tempfile.TemporaryDirectory(prefix="bottles-installation-") as directory:
        stage = Path(directory)
        subprocess.run([
            "meson", "install", "-C", str(build), "--no-rebuild", "--destdir", str(stage),
        ], check=True)
        installed = json.loads(subprocess.check_output([
            "meson", "introspect", "--installed", str(build),
        ], text=True))
        staged_package = stage / package_root.relative_to("/")
        staged_resources = stage / resources.relative_to("/")
        expected_init = str(package_root / "bottles/__init__.py")
        if expected_init not in installed.values():
            raise RuntimeError("Bottles package is absent from Python's installation mapping")
        for name in ("bottles.gresource", "data.gresource", "eagle-intel.sqlite", "eagle.yar"):
            if not (staged_resources / name).is_file():
                raise RuntimeError(f"Missing installed resource: {name}")
        if list(staged_resources.parent.rglob("*.py")):
            raise RuntimeError("Python modules were installed as shared application data")
        environment = dict(os.environ, PYTHONPATH=str(staged_package))
        subprocess.run([
            sys.executable, "-c",
            "from pathlib import Path; import bottles; "
            "from bottles.backend import params; "
            "from bottles.frontend import params as frontend; "
            "import sys; "
            "assert Path(bottles.__file__).resolve() == Path(sys.argv[1]).resolve(); "
            "assert params.PKGDATADIR == sys.argv[2]; "
            "assert params.SYSTEM_RUNNERS_DIR == sys.argv[3]; "
            "assert params.APP_VERSION == frontend.APP_VERSION; "
            "assert '@' not in frontend.APP_ID + frontend.APP_VERSION",
            str(staged_package / "bottles/__init__.py"), str(resources), str(runners),
        ], cwd=stage, env=environment, check=True)


if __name__ == "__main__":
    main()
