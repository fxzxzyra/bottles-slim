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
            "assert Paths.process_metrics == str(Path.home() / '.local/state/bottles/process_metrics.sqlite')",
        ],
        env=environment,
        check=True,
    )


def test_xdg_overrides_ignore_legacy_files_and_create_only_current_directories(tmp_path):
    environment = dict(os.environ)
    for name in ("DATA", "CONFIG", "CACHE", "STATE"):
        environment[f"XDG_{name}_HOME"] = str(tmp_path / name.lower())
    legacy = tmp_path / "data/bottles"
    legacy.mkdir(parents=True)
    (legacy / "data.yml").write_text("custom_bottles_path: /srv/wine\n")
    subprocess.run(
        [sys.executable, "-c", "from bottles.backend.globals import Paths"],
        env=environment,
        check=True,
    )
    assert not (tmp_path / "config/bottles/data.yml").exists()
    assert (legacy / "data.yml").read_text() == "custom_bottles_path: /srv/wine\n"
    assert not (legacy / ".xdg-layout-v1").exists()
    assert not (legacy / ".xdg-migration.lock").exists()
    for role in ("config", "cache", "state"):
        directory = tmp_path / role / "bottles"
        assert directory.is_dir()
        assert directory.stat().st_mode & 0o777 == 0o700
    assert not (tmp_path / "data/bottles/temp").exists()
