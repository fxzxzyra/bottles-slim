#!/usr/bin/env python3
"""Meson test entry point: isolated display, configured package and pytest reports."""

import argparse
import gettext
import importlib.util
import os
import shutil
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
GROUPS = {
    "backend": "bottles/tests/backend",
    "frontend": "bottles/tests/frontend",
    "fvs": "bottles/tests/fvs",
    "downstream": "tests",
}



# Import names differ from distribution/package names (notably PyYAML).
PYTHON_DEPENDENCIES = {
    "pytest": "pytest", "pytest_mock": "pytest-mock", "freezegun": "freezegun",
    "yaml": "PyYAML", "pycurl": "pycurl", "chardet": "chardet",
    "requests": "requests", "markdown": "Markdown", "icoextract": "icoextract",
    "patoolib": "patool", "pathvalidate": "pathvalidate", "pefile": "pefile",
    "yara": "yara-python", "cairo": "pycairo", "gi": "PyGObject",
}
GI_DEPENDENCIES = {
    "GLib": "2.0", "Gio": "2.0", "Gdk": "4.0", "Gtk": "4.0",
    "Adw": "1", "GtkSource": "5", "GdkPixbuf": "2.0",
    "Xdp": "1.0", "XdpGtk4": "1.0",
}


def check_dependencies() -> list[str]:
    """Collect missing modules, unusable native bindings and GI namespaces at once."""
    problems = []
    gi = None
    for module, distribution in PYTHON_DEPENDENCIES.items():
        try:
            loaded = importlib.import_module(module)
            if module == "gi":
                gi = loaded
        except Exception as error:
            problems.append(f"{distribution} (import {module}): {error}")
    if gi is not None:
        selected = []
        # Select all versions before importing any namespace and its dependencies.
        for namespace, version in GI_DEPENDENCIES.items():
            try:
                gi.require_version(namespace, version)
                selected.append((namespace, version))
            except Exception as error:
                problems.append(f"GI {namespace}-{version}: {error}")
        for namespace, version in selected:
            try:
                importlib.import_module(f"gi.repository.{namespace}")
            except Exception as error:
                problems.append(f"GI {namespace}-{version}: {error}")
    return problems


def worker(group: str, build: Path) -> int:
    package = Path(os.environ.get("BOTTLES_TEST_PACKAGE_ROOT", ROOT)).resolve()
    sys.path.insert(0, str(package))
    import bottles

    if not Path(bottles.__file__).resolve().is_relative_to(package):
        raise RuntimeError("Tests imported a different Bottles checkout")
    # Build-tree tests use the generated modules, never unconfigured source params.
    # Verification of a staged installation uses its installed configured modules.
    if package == ROOT:
        for name in ("backend", "frontend"):
            qualified = f"bottles.{name}.params"
            spec = importlib.util.spec_from_file_location(
                qualified, build / "bottles" / name / "params.py"
            )
            module = importlib.util.module_from_spec(spec)
            sys.modules[qualified] = module
            spec.loader.exec_module(module)
    import gi
    gi.require_version("Gtk", "4.0")
    gi.require_version("Adw", "1")
    from bottles.backend import params

    if "@" in params.APP_VERSION:
        raise RuntimeError("Unconfigured params.py was imported")
    resource = Path(os.environ["BOTTLES_TEST_RESOURCE"])
    params.PKGDATADIR = str(resource.parent)
    params.SYSTEM_RUNNERS_DIR = str(Path(os.environ["XDG_DATA_HOME"]) / "system-runners")
    gettext.install("com.usebottles.bottles", os.environ["BOTTLES_TEST_LOCALEDIR"])
    import pytest

    logs = build / "meson-logs"
    logs.mkdir(exist_ok=True)
    return pytest.main([
        str(ROOT / GROUPS[group]), "--import-mode=importlib", "-ra",
        "--strict-config", "--strict-markers",
        "-W", "error::pytest.PytestUnhandledThreadExceptionWarning",
        "-W", "error::pytest.PytestUnraisableExceptionWarning",
        "--junitxml", str(logs / f"pytest-{group}.xml"),
    ])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--group", choices=GROUPS)
    parser.add_argument("--build-root", type=Path)
    parser.add_argument("--check-dependencies", action="store_true")
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.check_dependencies:
        problems = check_dependencies()
        print(f"Python: {sys.executable}")
        if problems:
            print("Missing or unusable test/runtime dependencies:")
            for problem in problems:
                print(f"  - {problem}")
            print("Prepare Python dependencies from requirements.txt and requirements.dev.txt.")
            print("GI typelibs and their native libraries must be provided by the build environment.")
            return 1
        print("Python runtime/test modules and GI namespaces are available.")
        return 0
    if args.group is None or args.build_root is None:
        parser.error("--group and --build-root are required for test execution")
    build = args.build_root.resolve()
    if args.worker:
        return worker(args.group, build)
    with tempfile.TemporaryDirectory(prefix=f"bottles-{args.group}-") as directory:
        temporary = Path(directory)
        environment = dict(os.environ)
        for key in ("FLATPAK_ID", "CPAK_CONTAINER_ID", "G_RESOURCE_OVERLAYS", "PYTHONPATH"):
            environment.pop(key, None)
        for name in ("DATA", "CONFIG", "CACHE", "STATE", "RUNTIME"):
            path = temporary / name.lower()
            path.mkdir(mode=0o700)
            key = "XDG_RUNTIME_DIR" if name == "RUNTIME" else f"XDG_{name}_HOME"
            environment[key] = str(path)
        home = temporary / "home"
        home.mkdir(mode=0o700)
        environment.update(
            HOME=str(home), GSETTINGS_BACKEND="memory", GDK_BACKEND="x11",
            GSK_RENDERER="gl", LIBGL_ALWAYS_SOFTWARE="1", LANGUAGE="C",
            PYTHONPATH=environment.get("BOTTLES_TEST_PACKAGE_ROOT", str(ROOT)),
        )
        resources = temporary / "resources"
        resources.mkdir()
        if "BOTTLES_TEST_RESOURCE" not in environment:
            for source in (
                build / "bottles/frontend/ui/bottles.gresource",
                build / "data/data.gresource",
                ROOT / "data/eagle-intel.sqlite",
                ROOT / "bottles/backend/managers/eagle.yar",
            ):
                shutil.copy2(source, resources / source.name)
        defaults = {
            "BOTTLES_TEST_RESOURCE": resources / "bottles.gresource",
            "BOTTLES_TEST_DATA_RESOURCE": resources / "data.gresource",
            "BOTTLES_TEST_LOCALEDIR": build / "po",
            "GSETTINGS_SCHEMA_DIR": build / "data",
        }
        for key, value in defaults.items():
            environment.setdefault(key, str(value))
        return subprocess.call([
            "xvfb-run", "-a", "dbus-run-session", "--", sys.executable,
            str(Path(__file__).resolve()), "--group", args.group,
            "--build-root", str(build), "--worker",
        ], env=environment, cwd=temporary)


if __name__ == "__main__":
    raise SystemExit(main())
