import os
import subprocess
import sys
from pathlib import Path

import pytest

@pytest.mark.parametrize("value", ["", "relative/path"])
def test_invalid_xdg_variables_use_defaults(tmp_path, value):
    environment = dict(os.environ, HOME=str(tmp_path))
    for name in ("DATA", "CONFIG", "CACHE", "STATE"):
        environment[f"XDG_{name}_HOME"] = value
    subprocess.run(
        [
            sys.executable,
            "-c",
            "from bottles.backend.globals import Paths; "
            "from pathlib import Path; "
            "assert Paths.base == str(Path.home() / '.local/share/bottles'); "
            "assert Paths.config == str(Path.home() / '.config/bottles'); "
            "assert Paths.temp == str(Path.home() / '.cache/bottles/temp'); "
            "assert Paths.state == str(Path.home() / '.local/state/bottles')",
        ],
        env=environment,
        check=True,
    )


def test_importing_paths_does_not_create_user_directories(tmp_path):
    environment = dict(os.environ)
    for name in ("DATA", "CONFIG", "CACHE", "STATE"):
        environment[f"XDG_{name}_HOME"] = str(tmp_path / name.lower())
    subprocess.run(
        [sys.executable, "-c", "from bottles.backend.globals import Paths"],
        env=environment, check=True,
    )
    assert list(tmp_path.iterdir()) == []
