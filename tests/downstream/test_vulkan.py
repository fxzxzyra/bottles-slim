import ctypes
from types import SimpleNamespace

import pytest

from bottles.backend.utils import vulkan


class Function:
    def __init__(self, call):
        self.call = call

    def __call__(self, *args):
        return self.call(*args)


@pytest.fixture(autouse=True)
def clear_probe_cache():
    vulkan._probe_vulkan.cache_clear()
    yield
    vulkan._probe_vulkan.cache_clear()


def fake_loader(monkeypatch, create_result=0, device_count=1, enumeration_result=0):
    destroyed = []

    def create(info, allocator, instance):
        assert info._obj.sType == 1
        assert not info._obj.enabledLayerCount
        assert not info._obj.enabledExtensionCount
        instance._obj.value = 123
        return create_result

    def enumerate_devices(instance, count, devices):
        count._obj.value = device_count
        return enumeration_result if devices is not None else 0

    loader = SimpleNamespace(
        vkCreateInstance=Function(create),
        vkEnumeratePhysicalDevices=Function(enumerate_devices),
        vkDestroyInstance=Function(
            lambda instance, allocator: destroyed.append(instance.value)
        ),
    )
    monkeypatch.setattr(vulkan.ctypes, "CDLL", lambda name: loader)
    return destroyed


def test_support_uses_loader_and_releases_instance(monkeypatch):
    destroyed = fake_loader(monkeypatch)
    monkeypatch.setenv("PATH", "")
    assert vulkan.VulkanUtils.check_support()
    assert "physical devices: 1" in vulkan.VulkanUtils.test_vulkan()
    assert destroyed == [123]


@pytest.mark.parametrize("count,result", [(0, 0), (1, -3), (1, 5)])
def test_failed_enumeration_releases_instance(monkeypatch, count, result):
    destroyed = fake_loader(monkeypatch, device_count=count, enumeration_result=result)
    assert not vulkan.VulkanUtils.check_support()
    assert destroyed == [123]


def test_instance_failure_is_not_support(monkeypatch):
    destroyed = fake_loader(monkeypatch, create_result=-9)
    assert not vulkan.VulkanUtils.check_support()
    assert "VkResult -9" in vulkan.VulkanUtils.test_vulkan()
    assert destroyed == []


def test_missing_loader_is_not_support(monkeypatch):
    def missing(name):
        raise OSError("missing loader")

    monkeypatch.setattr(vulkan.ctypes, "CDLL", missing)
    assert not vulkan.VulkanUtils.check_support()


def test_incomplete_enumeration_can_recover(monkeypatch):
    destroyed = fake_loader(monkeypatch)
    loader = vulkan.ctypes.CDLL("libvulkan.so.1")
    attempts = []

    def enumerate_devices(instance, count, devices):
        count._obj.value = 1
        if devices is not None:
            attempts.append(True)
            return 5 if len(attempts) == 1 else 0
        return 0

    loader.vkEnumeratePhysicalDevices = Function(enumerate_devices)
    assert vulkan.VulkanUtils.check_support()
    assert len(attempts) == 2
    assert destroyed == [123]
