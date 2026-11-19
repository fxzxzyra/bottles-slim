# globals.py
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

import os
import shutil
from pathlib import Path
from typing import Dict

from bottles.backend.params import SYSTEM_RUNNERS_DIR
from bottles.backend.utils import json, yaml


def _xdg_home(variable: str, default: str) -> str:
    """XDG base directories must be nonempty absolute paths."""
    value = os.environ.get(variable, "")
    return value if os.path.isabs(value) else os.path.join(Path.home(), default)


def _has_windows_unsafe_component(path: str) -> bool:
    return any(
        part.endswith((".", " "))
        for part in Path(os.path.abspath(path)).parts
        if part != os.path.sep
    )


def _application_home(path: str) -> str:
    return path if "FLATPAK_ID" in os.environ else os.path.join(path, "bottles")


def _get_wine_compatible_base(path: str) -> str:
    path = os.path.abspath(path)
    if (
        "FLATPAK_ID" in os.environ
        and _has_windows_unsafe_component(path)
        and os.path.isdir("/var/data")
        and os.path.exists(path)
        and os.path.samefile(path, "/var/data")
    ):
        return "/var/data"
    return path


class Paths:
    xdg_data_home = _xdg_home("XDG_DATA_HOME", ".local/share")
    xdg_config_home = _xdg_home("XDG_CONFIG_HOME", ".config")
    xdg_cache_home = _xdg_home("XDG_CACHE_HOME", ".cache")
    xdg_state_home = _xdg_home("XDG_STATE_HOME", ".local/state")

    # Icon paths
    icons_user = f"{xdg_data_home}/icons"

    # Local paths
    base = _get_wine_compatible_base(_application_home(xdg_data_home))
    config = _application_home(xdg_config_home)
    cache = _application_home(xdg_cache_home)
    state = _application_home(xdg_state_home)
    user_settings = f"{config}/data.yml"
    journal = f"{state}/journal.yml"
    crash_log = f"{state}/crash.log"

    # User applications path
    applications = f"{xdg_data_home}/applications/"

    temp = f"{cache}/temp"
    runtimes = f"{base}/runtimes"
    winebridge = f"{base}/winebridge"
    # The package configures this from prefix/datadir: /app/share for Flatpak,
    # or the selected native prefix. No host-specific fallback directories.
    system_runners = (SYSTEM_RUNNERS_DIR,) if os.path.isabs(SYSTEM_RUNNERS_DIR) else ()
    bottle_index = f"{base}/bottles.sqlite"
    d7vk = f"{base}/d7vk"
    dxvk = f"{base}/dxvk"
    vkd3d = f"{base}/vkd3d"
    nvapi = f"{base}/nvapi"
    latencyflex = f"{base}/latencyflex"
    templates = f"{cache}/templates"

    @staticmethod
    def is_vkbasalt_available():
        vkbasalt_paths = [
            "/usr/lib/extensions/vulkan/vkBasalt/etc/vkBasalt",
            "/usr/local",
            "/usr/share/vkBasalt",
        ]
        for path in vkbasalt_paths:
            if os.path.exists(path):
                return True
        return False

    @staticmethod
    def get_lsfg_vk_version():
        layer_dirs = [
            path
            for path in os.environ.get("VK_ADD_LAYER_PATH", "").split(os.pathsep)
            if path
        ]
        layer_dirs += [
            "/usr/lib/extensions/vulkan/lsfgvk/share/vulkan/implicit_layer.d",
            f"{Paths.xdg_data_home}/vulkan/implicit_layer.d",
            "/usr/local/share/vulkan/implicit_layer.d",
            "/usr/share/vulkan/implicit_layer.d",
            "/etc/vulkan/implicit_layer.d",
        ]
        for version, manifest in (
            (2, "VkLayer_LSFGVK_frame_generation.json"),
            (1, "VkLayer_LS_frame_generation.json"),
        ):
            if any(
                os.path.isfile(os.path.join(layer_dir, manifest))
                for layer_dir in layer_dirs
            ):
                return version
        return 0


def check_flatpak_extension(cmd: str, path: str):
    if "FLATPAK_ID" in os.environ:
        if not os.path.exists(path):
            return False
    return shutil.which(cmd) or False

# Check if some tools are available
gamemode_available = shutil.which("gamemoderun") or False
gamescope_available = check_flatpak_extension("gamescope", "/usr/lib/extensions/vulkan/gamescope/bin/gamescope")
hdr_wsi_available = os.path.exists(
    "/usr/lib/extensions/vulkan/HdrWsi/lib/libVkLayer_hdr_wsi.so"
)
vkbasalt_available = Paths.is_vkbasalt_available()
lsfg_vk_version = Paths.get_lsfg_vk_version()
lsfg_vk_available = bool(lsfg_vk_version)
mangohud_available = check_flatpak_extension("mangohud", "/usr/lib/extensions/vulkan/MangoHud/bin/mangohud")
obs_vkc_available = check_flatpak_extension("obs-vkcapture", "/usr/lib/extensions/vulkan/OBSVkCapture/bin/obs-vkcapture")
vmtouch_available = shutil.which("vmtouch") or False
base_version = ""
if os.path.isfile("/app/manifest.json"):
    with open("/app/manifest.json", mode="r", encoding="utf-8") as file:
        base_version = (
            json.load(file)  # type: ignore
            .get("base-version", "")
            .removeprefix("stable-")
        )

# encoding detection correction, following windows defaults
locale_encodings: Dict[str, str] = {"ja_JP": "cp932", "zh_CN": "gbk"}
