import os, sys
def _add_repo_root_to_syspath() -> None:
    this_dir = os.path.dirname(__file__)
    repo_root = os.path.abspath(os.path.join(this_dir, os.pardir, os.pardir))
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)
_add_repo_root_to_syspath()


import pytest


@pytest.fixture
def runner_factory(tmp_path, monkeypatch):
    """Explicit local runner fixture; Wine itself is never required by unit tests."""
    from bottles.backend.utils.runners import RunnerRegistry

    monkeypatch.setattr(RunnerRegistry, "entries", {})

    def create(identifier="soda-11.0", source="user"):
        root = tmp_path / "runner-fixtures" / identifier
        (root / "bin").mkdir(parents=True, exist_ok=True)
        for name in ("wine", "wineserver"):
            executable = root / "bin" / name
            executable.write_text("#!/bin/sh\nexit 0\n")
            executable.chmod(0o755)
        info = RunnerRegistry.inspect(identifier, str(root), source)
        RunnerRegistry.entries[identifier] = info
        return info

    return create


@pytest.fixture
def local_runner(runner_factory):
    return runner_factory()
