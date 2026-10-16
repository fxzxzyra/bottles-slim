# vulkan.py
#
# Copyright 2025 mirkobrombin <brombin94@gmail.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, in version 3 of the License.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

import ctypes
import filecmp
import os
from functools import lru_cache
from glob import glob


class _InstanceCreateInfo(ctypes.Structure):
    # VkInstanceCreateInfo, using native pointer alignment on both ILP32 and LP64.
    _fields_ = [
        ("sType", ctypes.c_uint32),
        ("pNext", ctypes.c_void_p),
        ("flags", ctypes.c_uint32),
        ("pApplicationInfo", ctypes.c_void_p),
        ("enabledLayerCount", ctypes.c_uint32),
        ("ppEnabledLayerNames", ctypes.POINTER(ctypes.c_char_p)),
        ("enabledExtensionCount", ctypes.c_uint32),
        ("ppEnabledExtensionNames", ctypes.POINTER(ctypes.c_char_p)),
    ]


@lru_cache(maxsize=1)
def _probe_vulkan() -> tuple[bool, str]:
    """Probe the current process ABI via the system loader, without WSI or a CLI.

    A null application info requests Vulkan 1.0. No layers or extensions are
    required; the loader handles ICD selection and the user's Vulkan environment.
    This checks device enumeration, not DXVK feature levels or 32-bit Wine.
    """
    try:
        loader = ctypes.CDLL("libvulkan.so.1")
        create = loader.vkCreateInstance
        create.argtypes = [
            ctypes.POINTER(_InstanceCreateInfo),
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_void_p),
        ]
        create.restype = ctypes.c_int32
        enumerate_devices = loader.vkEnumeratePhysicalDevices
        enumerate_devices.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_uint32),
            ctypes.POINTER(ctypes.c_void_p),
        ]
        enumerate_devices.restype = ctypes.c_int32
        destroy = loader.vkDestroyInstance
        destroy.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        destroy.restype = None
    except (OSError, AttributeError) as error:
        return False, f"Vulkan loader unavailable: {error}"

    instance = ctypes.c_void_p()
    result = create(
        ctypes.byref(_InstanceCreateInfo(sType=1)), None, ctypes.byref(instance)
    )
    if result != 0:
        return False, f"vkCreateInstance failed: VkResult {result}"
    try:
        # The device set may change between the count and list calls.
        for _attempt in range(3):
            count = ctypes.c_uint32()
            result = enumerate_devices(instance, ctypes.byref(count), None)
            if result != 0:
                return False, f"vkEnumeratePhysicalDevices failed: VkResult {result}"
            if count.value == 0:
                return False, "Vulkan loader found no physical devices"
            devices = (ctypes.c_void_p * count.value)()
            result = enumerate_devices(instance, ctypes.byref(count), devices)
            if result == 5:  # VK_INCOMPLETE: retry with the new count.
                continue
            if result != 0:
                return False, f"vkEnumeratePhysicalDevices failed: VkResult {result}"
            return (
                bool(count.value),
                f"Vulkan physical devices: {count.value} (process ABI: {ctypes.sizeof(ctypes.c_void_p) * 8}-bit)",
            )
        return False, "Vulkan device enumeration remained incomplete"
    finally:
        destroy(instance, None)


class VulkanUtils:
    __vk_icd_dirs = [
        "/usr/share/vulkan",
        "/etc/vulkan",
        "/usr/local/share/vulkan",
        "/usr/local/etc/vulkan",
    ]
    if "FLATPAK_ID" in os.environ:
        __vk_icd_dirs += [
            "/usr/lib/x86_64-linux-gnu/GL/vulkan",
            "/usr/lib/i386-linux-gnu/GL/vulkan",
        ]

    def __init__(self):
        self.loaders = self.__get_vk_icd_loaders()

    def __get_vk_icd_loaders(self):
        loaders = {"nvidia": [], "nouveau": [], "amd": [], "intel": []}

        for _dir in self.__vk_icd_dirs:
            _files = glob(f"{_dir}/icd.d/*.json", recursive=True)

            for file in _files:
                if "nvidia" in file.lower():
                    # Workaround for nvidia flatpak bug: https://github.com/flathub/org.freedesktop.Platform.GL.nvidia/issues/112
                    should_skip = False
                    for nvidia_loader in loaders["nvidia"]:
                        try:
                            if filecmp.cmp(nvidia_loader, file):
                                should_skip = True
                                continue
                        except:
                            pass
                    if not should_skip:
                        loaders["nvidia"] += [file]
                elif "nouveau" in file.lower() or "nvk" in file.lower():
                    loaders["nouveau"] += [file]
                elif "amd" in file.lower() or "radeon" in file.lower():
                    loaders["amd"] += [file]
                elif "intel" in file.lower():
                    loaders["intel"] += [file]

        return loaders

    def get_vk_icd(self, vendor: str, as_string=False):
        vendors = ["nvidia", "nouveau", "amd", "intel"]
        icd = []

        if vendor in vendors:
            icd = self.loaders[vendor]

        if as_string:
            icd = ":".join(icd)

        return icd

    @staticmethod
    def check_support() -> bool:
        """Return whether the system loader can enumerate Vulkan devices."""
        return _probe_vulkan()[0]

    @staticmethod
    def test_vulkan():
        return _probe_vulkan()[1]
