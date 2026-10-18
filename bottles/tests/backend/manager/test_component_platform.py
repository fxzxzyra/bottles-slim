import tarfile
from types import SimpleNamespace

import pytest

from bottles.backend.globals import Paths
from bottles.backend.managers import component as component_module
from bottles.backend.managers.component import ComponentManager
from bottles.backend.utils import generic


@pytest.fixture
def arm64_linux(monkeypatch):
    monkeypatch.setattr(component_module, "get_host_architecture", lambda: "aarch64")
    monkeypatch.setattr(component_module.sys, "platform", "linux")


@pytest.mark.parametrize(
    ("machine", "expected"),
    [("AMD64", "x86_64"), ("arm64", "aarch64"), ("aarch64", "aarch64")],
)
def test_host_architecture_aliases(monkeypatch, machine, expected):
    monkeypatch.setattr(generic.platform, "machine", lambda: machine)
    assert generic.get_host_architecture() == expected


def test_cache_and_download_select_same_platform_file(arm64_linux, monkeypatch, tmp_path):
    monkeypatch.setattr(Paths, "temp", str(tmp_path))
    selected = {
        "architecture": "aarch64",
        "platform": "linux",
        "file_name": "runtime-arm.tar.xz",
        "url": "https://example.invalid/runtime-arm.tar.xz",
    }
    manifest = {"File": [
        {"architecture": "x86_64", "file_name": "runtime-x86.tar.xz"},
        {"architecture": "aarch64", "platform": "darwin", "file_name": "runtime-mac.tar.xz"},
        selected,
    ]}
    manager = object.__new__(ComponentManager)
    manager._ComponentManager__manifests = {}
    manager._ComponentManager__repo = SimpleNamespace(get=lambda *_args: manifest)
    download = []
    monkeypatch.setattr(manager, "download", lambda **kwargs: download.append(kwargs) or component_module.Result(False))

    (tmp_path / "runtime-x86.tar.xz").write_bytes(b"wrong host")
    assert not manager.is_component_cached("runtime-test")
    (tmp_path / selected["file_name"]).write_bytes(b"matching host")
    assert manager.is_component_cached("runtime-test")
    manager.install("runtime", "runtime-test")
    assert download[0]["file"] == selected["file_name"]
    assert download[0]["download_url"] == selected["url"]


def test_specific_file_beats_generic_fallback(arm64_linux):
    generic_file = {"file_name": "generic.tar.xz"}
    arch_file = {"architecture": "aarch64", "file_name": "arm.tar.xz"}
    exact_file = {"architecture": "aarch64", "platform": "linux", "file_name": "linux-arm.tar.xz"}
    select = component_module._select_component_file
    assert select({"File": [generic_file, arch_file, exact_file]}) is exact_file
    assert select({"File": [generic_file, arch_file]}) is arch_file
    assert select({"File": [generic_file]}) is generic_file
    assert select({"File": [{"architecture": "x86_64"}]}) is None


def test_catalog_filters_host_metadata_and_keeps_generic_components(arm64_linux):
    entries = {
        "generic": {"Category": "dxvk", "Channel": "stable"},
        "linux-arm": {"Category": "dxvk", "Channel": "stable", "Architectures": ["aarch64"], "Platforms": ["linux"]},
        "linux-x86": {"Category": "dxvk", "Channel": "stable", "Architectures": ["x86_64"]},
        "mac-arm": {"Category": "dxvk", "Channel": "stable", "Platforms": ["darwin"]},
    }
    repo = SimpleNamespace(catalog=entries)
    manager = SimpleNamespace(
        is_cli=True,
        repository_manager=SimpleNamespace(get_repo=lambda *_args, **_kwargs: repo),
        runtimes_available=[], d7vk_available=[], dxvk_available=[],
        vkd3d_available=[], nvapi_available=[], latencyflex_available=[], winebridge_available=[],
    )
    assert set(ComponentManager(manager).fetch_catalog()["dxvk"]) == {"generic", "linux-arm"}


@pytest.mark.parametrize("suffix", ["-aarch64", "_aarch64", "-x86_64", "_x86_64"])
def test_runtime_archive_architecture_suffix(tmp_path, monkeypatch, suffix):
    cache = tmp_path / "cache"
    runtimes = tmp_path / "runtimes"
    cache.mkdir()
    runtimes.mkdir()
    source = tmp_path / "source"
    source.mkdir()
    (source / "payload").write_text("runtime")
    root = "runtime-test" + suffix
    archive = cache / "runtime.tar.xz"
    with tarfile.open(archive, "w:xz") as stream:
        stream.add(source, arcname=root)
    monkeypatch.setattr(Paths, "temp", str(cache))
    monkeypatch.setattr(Paths, "runtimes", str(runtimes))

    assert ComponentManager.extract("runtime-test", "runtime", archive.name)
    assert (runtimes / "runtime-test" / "payload").read_text() == "runtime"
    assert not (runtimes / root).exists()
