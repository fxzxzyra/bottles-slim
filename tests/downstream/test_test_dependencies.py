"""Dependency diagnostics without importing the application or requiring native UI libraries."""

import importlib.util
from pathlib import Path
from types import SimpleNamespace

SPEC = importlib.util.spec_from_file_location(
    "test_entry_point", Path(__file__).resolve().parents[2] / "tests/run.py"
)
entry = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(entry)


def test_preflight_reports_python_and_gi_failures_together(monkeypatch):
    def require(namespace, version):
        if namespace == "GtkSource":
            raise ValueError("Namespace GtkSource not available")

    def load(name):
        if name == "yaml":
            raise ModuleNotFoundError("No module named 'yaml'")
        if name == "pycurl":
            raise ImportError("libcurl.so unavailable")
        if name == "gi":
            return SimpleNamespace(require_version=require)
        return SimpleNamespace()

    monkeypatch.setattr(entry.importlib, "import_module", load)
    problems = entry.check_dependencies()
    assert len(problems) == 3
    assert any("PyYAML (import yaml)" in item for item in problems)
    assert any("pycurl" in item and "libcurl.so" in item for item in problems)
    assert any("GI GtkSource-5" in item for item in problems)


def test_preflight_still_lists_all_python_failures_without_pygobject(monkeypatch):
    def load(name):
        raise ModuleNotFoundError(name)

    monkeypatch.setattr(entry.importlib, "import_module", load)
    problems = entry.check_dependencies()
    assert len(problems) == len(entry.PYTHON_DEPENDENCIES)
    assert any("PyGObject" in item for item in problems)
    assert any("pytest-mock" in item for item in problems)
