import os
import subprocess
import sys
from pathlib import Path

import pytest

@pytest.mark.parametrize("value", ["", "relative/path"])
def test_invalid_xdg_variables_use_defaults(tmp_path, value):
    environment = dict(os.environ, HOME=str(tmp_path))
    environment.pop("FLATPAK_ID", None)
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


def test_flatpak_uses_private_xdg_roots_without_extra_namespace(tmp_path):
    environment = dict(os.environ, HOME=str(tmp_path), FLATPAK_ID="com.usebottles.bottles")
    for name in ("DATA", "CONFIG", "CACHE", "STATE"):
        environment[f"XDG_{name}_HOME"] = str(tmp_path / name.lower())
    subprocess.run(
        [sys.executable, "-c", """
import os
from bottles.backend.globals import Paths
assert Paths.base == os.environ["XDG_DATA_HOME"]
assert Paths.config == os.environ["XDG_CONFIG_HOME"]
assert Paths.cache == os.environ["XDG_CACHE_HOME"]
assert Paths.state == os.environ["XDG_STATE_HOME"]
assert Paths.user_settings == Paths.config + "/data.yml"
assert Paths.bottle_index == Paths.base + "/bottles.sqlite"
assert not hasattr(Paths, "user_runners")
assert Paths.temp == Paths.cache + "/temp"
"""],
        env=environment, check=True,
    )
    assert list(tmp_path.iterdir()) == []
