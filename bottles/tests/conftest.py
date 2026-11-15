"""Shared runner fixtures and per-test bottle index isolation."""

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


@pytest.fixture(autouse=True)
def isolated_bottle_index(tmp_path, monkeypatch):
    from bottles.backend.globals import Paths
    monkeypatch.setattr(Paths, "bottle_index", str(tmp_path / "user-data/bottles.sqlite"))
