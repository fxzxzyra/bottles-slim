"""Installed components survive removal of their shared installation sources."""

import json
import shutil
import shlex
from pathlib import Path

import pytest

from bottles.backend.dlls import dll as dll_module
from bottles.backend.dlls.latencyflex import LatencyFleXComponent
from bottles.backend.models.config import BottleConfig
from bottles.backend.models.result import Result
from bottles.backend.utils.manager import ManagerUtils


@pytest.fixture
def latency_source(tmp_path, monkeypatch):
    source = tmp_path / "source"
    dlls = source / "wine/usr/lib/wine/x86_64-windows"
    dlls.mkdir(parents=True)
    for name in ("latencyflex_layer.dll", "latencyflex_wine.dll"):
        (dlls / name).write_bytes(name.encode())
    library = source / "layer/usr/lib/x86_64-linux-gnu/liblatencyflex_layer.so"
    library.parent.mkdir(parents=True)
    library.write_bytes(b"native latency layer")
    (library.parent / "liblatencyflex_alias.so").symlink_to(library)
    manifest = source / "layer/usr/share/vulkan/implicit_layer.d/latencyflex.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(json.dumps({"layer": {"library_path": "/usr/lib/x86_64-linux-gnu/liblatencyflex_layer.so"}}))
    monkeypatch.setattr(LatencyFleXComponent, "get_base_path", staticmethod(lambda _version: str(source)))
    monkeypatch.setattr(dll_module.Reg, "import_bundle", lambda *_args: Result(True))
    return source


def test_latencyflex_uses_a_complete_local_copy_after_cache_removal(tmp_path, latency_source):
    prefix = tmp_path / "container"
    system = prefix / "drive_c/windows/system32"
    system.mkdir(parents=True)
    config = BottleConfig(Path=str(prefix), LatencyFleX="selected")
    component = LatencyFleXComponent("selected")
    assert component.install(config)
    shutil.rmtree(latency_source)

    installed = Path(ManagerUtils.get_component_path(config, "latencyflex"))
    assert all(not path.is_symlink() for path in installed.rglob("*"))
    assert {str(path.relative_to(installed)) for path in installed.rglob("*") if path.is_file()} == {
        "lib/x86_64-linux-gnu/liblatencyflex_layer.so",
        "share/vulkan/implicit_layer.d/latencyflex.json",
    }
    manifest = installed / "share/vulkan/implicit_layer.d/latencyflex.json"
    library = (manifest.parent / json.loads(manifest.read_text())["layer"]["library_path"]).resolve()
    assert library.is_relative_to(installed)
    assert library.read_bytes() == b"native latency layer"
    for name in ("latencyflex_layer.dll", "latencyflex_wine.dll"):
        assert (system / name).read_bytes() == name.encode()
        assert not (system / name).is_symlink()
    # Uninstall needs only known DLL names, never the deleted cache.
    assert LatencyFleXComponent("selected").uninstall(config)
    assert not installed.exists()
    assert not (system / "latencyflex_wine.dll").exists()


def test_incomplete_latencyflex_cannot_reuse_another_instances_dlls(tmp_path, monkeypatch, latency_source):
    assert LatencyFleXComponent("complete").checked_dlls
    (latency_source / "wine/usr/lib/wine/x86_64-windows/latencyflex_wine.dll").unlink()
    assert not LatencyFleXComponent("incomplete").checked_dlls
    monkeypatch.setattr(LatencyFleXComponent, "get_base_path", staticmethod(lambda _version: str(tmp_path / "missing")))
    assert not LatencyFleXComponent("missing").checked_dlls


@pytest.mark.parametrize("kind", ["dxvk", "vkd3d", "nvapi"])
def test_dll_installation_and_backups_do_not_link_to_the_source(tmp_path, monkeypatch, kind):
    from bottles.backend.dlls.dxvk import DXVKComponent
    from bottles.backend.dlls.vkd3d import VKD3DComponent
    from bottles.backend.dlls import nvapi

    monkeypatch.setattr(nvapi, "get_nvidia_dll_path", lambda: None)
    component_type = {"dxvk": DXVKComponent, "vkd3d": VKD3DComponent, "nvapi": nvapi.NVAPIComponent}[kind]
    source = tmp_path / "cache"
    external = tmp_path / "downloaded-payload.dll"
    external.write_bytes(b"downloaded-native-dll")
    for arch, names in component_type.dlls.items():
        directory = source / arch
        directory.mkdir(parents=True)
        for name in names:
            (directory / name).symlink_to(external)
    prefix = tmp_path / "container"
    for system in ("system32", "syswow64"):
        directory = prefix / "drive_c/windows" / system
        directory.mkdir(parents=True)
        for names in component_type.dlls.values():
            for name in names:
                (directory / name).write_bytes(b"previous-dll")
    monkeypatch.setattr(component_type, "get_base_path", staticmethod(lambda _version: str(source)))
    monkeypatch.setattr(dll_module.Reg, "import_bundle", lambda *_args: Result(True))
    config = BottleConfig(Path=str(prefix))
    assert component_type("selected").install(config)
    shutil.rmtree(source)
    external.unlink()
    installed = prefix / "drive_c/windows/system32" / ("nvapi64.dll" if kind == "nvapi" else next(iter(component_type.dlls.values()))[0])
    assert installed.read_bytes() == b"downloaded-native-dll"
    assert not installed.is_symlink()
    assert component_type("selected").uninstall(config)
    assert installed.read_bytes() == b"previous-dll"
    assert not installed.is_symlink()


def test_launch_environment_uses_the_installed_latencyflex_copy(tmp_path, monkeypatch, latency_source, runner_factory):
    from bottles.backend.wine import winecommand

    prefix = tmp_path / "container"
    (prefix / "drive_c/windows/system32").mkdir(parents=True)
    runner = runner_factory("wine")
    config = BottleConfig(Path=str(prefix), Runner=runner.identifier, LatencyFleX="selected")
    config.Parameters.latencyflex = True
    config.Parameters.use_runtime = False
    config.Parameters.use_eac_runtime = False
    config.Parameters.use_be_runtime = False
    assert LatencyFleXComponent("selected").install(config)
    shutil.rmtree(latency_source)
    command = winecommand.WineCommand.__new__(winecommand.WineCommand)
    command.config = config
    command.runner = shlex.quote(runner.wine_for_arch(config.Arch))
    command.minimal = False
    command.terminal = False
    command.gamescope_activated = False
    command.arguments = ""
    monkeypatch.setattr(winecommand.GPUUtils, "get_gpu", lambda _self: {
        "prime": {"discrete": None, "integrated": None}, "vendors": {},
    })
    monkeypatch.setattr(winecommand.DisplayUtils, "check_nvidia_device", lambda: None)
    monkeypatch.setattr(winecommand, "is_ntsync_available", lambda _runner: False)
    env = command.get_env()
    installed = Path(ManagerUtils.get_component_path(config, "latencyflex"))
    assert str(installed / "share/vulkan/implicit_layer.d") in env["VK_ADD_LAYER_PATH"].split(":")
    assert str(installed / "lib/x86_64-linux-gnu") in env["LD_LIBRARY_PATH"].split(":")
    assert env["LFX"] == "1"


@pytest.mark.parametrize("missing", [
    "layer/usr/lib/x86_64-linux-gnu/liblatencyflex_layer.so",
    "layer/usr/share/vulkan/implicit_layer.d/latencyflex.json",
])
def test_latencyflex_requires_its_native_layer_as_well_as_wine_dlls(latency_source, missing):
    (latency_source / missing).unlink()
    assert not LatencyFleXComponent("incomplete").checked_dlls


def test_registry_overrides_are_restored_from_installed_dlls_without_cache(tmp_path, monkeypatch):
    from bottles.backend.dlls.dxvk import DXVKComponent

    system = tmp_path / "container/drive_c/windows/system32"
    system.mkdir(parents=True)
    (system / "dxgi.dll").write_bytes(b"installed-dxvk")
    monkeypatch.setattr(DXVKComponent, "get_base_path", staticmethod(lambda _version: str(tmp_path / "removed-cache")))
    bundles = []
    monkeypatch.setattr(dll_module.Reg, "import_bundle", lambda _self, bundle: bundles.append(bundle) or Result(True))
    component = DXVKComponent("installed")
    assert not component.checked_dlls
    config = BottleConfig(Path=str(tmp_path / "container"))
    assert component.install(config, overrides_only=True)
    assert bundles == [{r"HKEY_CURRENT_USER\Software\Wine\DllOverrides": [
        {"value": "dxgi", "data": "native,builtin"},
    ]}]
    assert (system / "dxgi.dll").read_bytes() == b"installed-dxvk"


@pytest.mark.parametrize("kind", ["latencyflex", "nvapi"])
@pytest.mark.parametrize("failure", ["registry", "save", "exception"])
def test_failed_auxiliary_update_reports_failure_and_can_be_retried(tmp_path, monkeypatch, latency_source, kind, failure):
    from bottles.backend.dlls import nvapi
    from bottles.backend.managers.manager import Manager
    from bottles.backend.managers.registry_rule import RegistryRuleManager
    from bottles.backend.utils.vulkan import VulkanUtils

    monkeypatch.setattr(nvapi, "get_nvidia_dll_path", lambda: None)
    monkeypatch.setattr(VulkanUtils, "check_support", lambda: True)
    monkeypatch.setattr(RegistryRuleManager, "apply_rules", lambda *_args, **_kwargs: None)
    cls = LatencyFleXComponent if kind == "latencyflex" else nvapi.NVAPIComponent
    source = latency_source if kind == "latencyflex" else tmp_path / "nvapi-cache"
    if kind == "nvapi":
        for arch, names in cls.dlls.items():
            (source / arch).mkdir(parents=True)
            for name in names:
                (source / arch / name).write_bytes(b"old")
    monkeypatch.setattr(cls, "get_base_path", staticmethod(lambda _version: str(source)))
    prefix = tmp_path / "container"
    for system in ("system32", "syswow64"):
        (prefix / "drive_c/windows" / system).mkdir(parents=True)
    version_key, flag = ("LatencyFleX", "latencyflex") if kind == "latencyflex" else ("NVAPI", "dxvk_nvapi")
    config = BottleConfig(Path=str(prefix))
    setattr(config, version_key, "old")
    setattr(config.Parameters, flag, True)
    manager = object.__new__(Manager)
    manager.local_bottles = {config.Id: config}
    assert manager.install_dll_component(config, kind).ok
    assert config.dump(str(prefix / "bottle.yml")).ok

    newer = tmp_path / "new-source"
    shutil.copytree(source, newer)
    for file in newer.rglob("*.dll"):
        file.unlink()  # Source fixtures may be symlinks.
        file.write_bytes(b"new")
    shutil.rmtree(source)
    monkeypatch.setattr(cls, "get_base_path", staticmethod(lambda version: str(newer if version == "new" else source)))
    before = {str(path.relative_to(prefix)): path.read_bytes() for path in prefix.rglob("*") if path.is_file()}
    registry_calls = []

    def registry(_self, bundle):
        registry_calls.append(bundle)
        if len(registry_calls) == 1 and failure == "exception":
            raise OSError("Registry unavailable")
        return Result(not (len(registry_calls) == 1 and failure == "registry"))

    monkeypatch.setattr(dll_module.Reg, "import_bundle", registry)
    dump = BottleConfig.dump
    if failure == "save":
        monkeypatch.setattr(BottleConfig, "dump", lambda *_args, **_kwargs: Result(False))
    result = manager.set_dll_component(config, kind, True, "new")

    assert not result.ok
    assert getattr(config, version_key) == "old"
    assert getattr(config.Parameters, flag)
    assert not source.exists()
    assert (prefix / "bottle.yml").read_bytes() == before["bottle.yml"]
    name = "latencyflex_wine.dll" if kind == "latencyflex" else "nvapi64.dll"
    assert (prefix / "drive_c/windows/system32" / name).read_bytes() == b"new"
    assert len(registry_calls) == 1  # Failure is reported, not compensated by another install.
    monkeypatch.setattr(BottleConfig, "dump", dump)
    result = manager.set_dll_component(config, kind, True, "new")
    assert result.ok
    assert getattr(config, version_key) == "new"
    assert getattr(BottleConfig.load(str(prefix / "bottle.yml")).data, version_key) == "new"
    assert (prefix / "drive_c/windows/system32" / name).read_bytes() == b"new"


def test_invalid_layer_manifest_fails_before_installed_files_are_changed(tmp_path, monkeypatch, latency_source):
    from unittest.mock import Mock
    from bottles.backend.managers.manager import Manager

    prefix = tmp_path / "container"
    (prefix / "drive_c/windows/system32").mkdir(parents=True)
    config = BottleConfig(Path=str(prefix), LatencyFleX="old")
    config.Parameters.latencyflex = True
    assert LatencyFleXComponent("old").install(config)
    assert config.dump(str(prefix / "bottle.yml")).ok
    before = {str(path.relative_to(prefix)): path.read_bytes() for path in prefix.rglob("*") if path.is_file()}
    (latency_source / "layer/usr/share/vulkan/implicit_layer.d/latencyflex.json").write_text("invalid JSON")
    registry = Mock()
    monkeypatch.setattr(dll_module.Reg, "import_bundle", registry)
    manager = object.__new__(Manager)
    manager.local_bottles = {config.Id: config}

    assert not manager.set_dll_component(config, "latencyflex", True, "new").ok
    registry.assert_not_called()
    assert {str(path.relative_to(prefix)): path.read_bytes() for path in prefix.rglob("*") if path.is_file()} == before


def test_dll_copy_failure_stops_before_other_files_or_registry_are_changed(tmp_path, monkeypatch):
    from unittest.mock import Mock
    from bottles.backend.dlls.dxvk import DXVKComponent

    source = tmp_path / "source/x64"
    source.mkdir(parents=True)
    system = tmp_path / "container/drive_c/windows/system32"
    system.mkdir(parents=True)
    for name in ("d3d8.dll", "dxgi.dll"):
        (source / name).write_bytes(b"new")
        (system / name).write_bytes(b"old")
    monkeypatch.setattr(DXVKComponent, "get_base_path", staticmethod(lambda _version: str(source.parent)))
    copy = shutil.copyfile

    def fail_first_payload(src, dest, **kwargs):
        if Path(src) == source / "d3d8.dll":
            raise OSError("No space left on device")
        return copy(src, dest, **kwargs)

    monkeypatch.setattr(dll_module.shutil, "copyfile", fail_first_payload)
    registry = Mock()
    monkeypatch.setattr(dll_module.Reg, "import_bundle", registry)
    assert not DXVKComponent("new").install(BottleConfig(Path=str(tmp_path / "container")))
    registry.assert_not_called()
    assert {path.name: path.read_bytes() for path in system.iterdir()} == {
        "d3d8.dll": b"old", "dxgi.dll": b"old",
    }


def test_installed_nvapi_can_be_removed_without_vulkan_or_download_cache(tmp_path, monkeypatch):
    from bottles.backend.dlls import nvapi
    from bottles.backend.managers.manager import Manager
    from bottles.backend.utils.vulkan import VulkanUtils

    system = tmp_path / "container/drive_c/windows/system32"
    system.mkdir(parents=True)
    (system / "nvapi64.dll").write_bytes(b"installed-nvapi")
    config = BottleConfig(Path=str(tmp_path / "container"), NVAPI="cache-removed")
    monkeypatch.setattr(nvapi, "get_nvidia_dll_path", lambda: None)
    monkeypatch.setattr(nvapi.NVAPIComponent, "get_base_path", staticmethod(lambda _version: str(tmp_path / "missing")))
    monkeypatch.setattr(VulkanUtils, "check_support", lambda: pytest.fail("Removal must not probe Vulkan"))
    monkeypatch.setattr(dll_module.Reg, "import_bundle", lambda *_args: Result(True))
    manager = object.__new__(Manager)
    assert manager.install_dll_component(config, "nvapi", remove=True).ok
    assert not (system / "nvapi64.dll").exists()


def test_native_component_layout_and_lifecycle_are_shared(tmp_path, monkeypatch):
    from bottles.backend.dlls.dll import DLLComponent

    source = tmp_path / "download"
    files = {
        "x64/extra.dll": b"windows library",
        "native/libextra.so": b"native library",
        "native/worker": b"#!/bin/sh\nexit 0\n",
        "metadata/options.ini": b"setting=true\n",
        "unused/build.log": b"not part of the installation",
    }
    for relative, content in files.items():
        path = source / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    (source / "native/worker").chmod(0o755)
    external_library = tmp_path / "external-library.so"
    (source / "native/libextra.so").replace(external_library)
    (source / "native/libextra.so").symlink_to(external_library)

    class NativeComponent(DLLComponent):
        component_id = "example"
        dlls = {"x64": ["extra.dll"]}
        native_files = {
            "native/libextra.so": "lib/x86_64-linux-gnu/libextra.so",
            "native/worker": "bin/worker",
            "metadata/options.ini": "share/options.ini",
        }

        @staticmethod
        def get_base_path(_version):
            return str(source)

        @staticmethod
        def get_override_keys():
            return "extra"

    prefix = tmp_path / "container"
    system = prefix / "drive_c/windows/system32"
    system.mkdir(parents=True)
    (system / "extra.dll").write_bytes(b"original dll")
    config = BottleConfig(Path=str(prefix))
    monkeypatch.setattr(dll_module.Reg, "import_bundle", lambda *_args: Result(True))
    assert NativeComponent("v1").install(config)
    installed = prefix / "components/example"
    assert {str(path.relative_to(installed)): path.read_bytes() for path in installed.rglob("*") if path.is_file()} == {
        "lib/x86_64-linux-gnu/libextra.so": b"native library",
        "bin/worker": b"#!/bin/sh\nexit 0\n",
        "share/options.ini": b"setting=true\n",
    }
    assert (installed / "bin/worker").stat().st_mode & 0o111
    assert (system / "extra.dll").read_bytes() == b"windows library"
    # A different component owns a separate subtree and must survive this uninstall.
    other = prefix / "components/other/lib/keep.so"
    other.parent.mkdir(parents=True)
    other.write_bytes(b"other component")
    shutil.rmtree(source)
    external_library.unlink()
    assert not (installed / "lib/x86_64-linux-gnu/libextra.so").is_symlink()
    assert (installed / "lib/x86_64-linux-gnu/libextra.so").read_bytes() == b"native library"
    assert NativeComponent("v1").uninstall(config)
    assert not installed.exists()
    assert (system / "extra.dll").read_bytes() == b"original dll"
    assert other.read_bytes() == b"other component"


def test_unsupported_windows_architecture_is_rejected_before_native_install(tmp_path, monkeypatch, latency_source):
    from unittest.mock import Mock

    prefix = tmp_path / "win32-container"
    (prefix / "drive_c/windows/system32").mkdir(parents=True)
    registry = Mock()
    monkeypatch.setattr(dll_module.Reg, "import_bundle", registry)
    assert not LatencyFleXComponent("selected").install(BottleConfig(Path=str(prefix), Arch="win32"))
    assert not (prefix / "components").exists()
    assert list((prefix / "drive_c/windows/system32").iterdir()) == []
    registry.assert_not_called()
