# dxvk.py
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

import json
import os

from bottles.backend.dlls.dll import DLLComponent
from bottles.backend.utils.manager import ManagerUtils


class LatencyFleXComponent(DLLComponent):
    component_id = "latencyflex"
    native_files = {
        "layer/usr/lib/x86_64-linux-gnu/liblatencyflex_layer.so": "lib/x86_64-linux-gnu/liblatencyflex_layer.so",
        "layer/usr/share/vulkan/implicit_layer.d/latencyflex.json": "share/vulkan/implicit_layer.d/latencyflex.json",
    }
    dlls = {
        "wine/usr/lib/wine/x86_64-windows": [
            "latencyflex_layer.dll",
            "latencyflex_wine.dll",
        ]
    }

    def check(self):
        if not super().check():
            return False
        path, names = next(iter(self.dlls.items()))
        if any(not os.path.isfile(os.path.join(self.base_path, path, name)) for name in names):
            self.checked_dlls = {}
            return False
        return True

    @staticmethod
    def get_override_keys() -> str:
        return "latencyflex_layer,latencyflex_wine"

    @staticmethod
    def get_base_path(version: str) -> str:
        return ManagerUtils.get_latencyflex_path(version)

    def prepare_native_payload(self, directory):
        manifest_path = os.path.join(directory, "share", "vulkan", "implicit_layer.d", "latencyflex.json")
        with open(manifest_path, encoding="utf-8") as stream:
            manifest = json.load(stream)
        library = os.path.join(directory, "lib", "x86_64-linux-gnu", "liblatencyflex_layer.so")
        manifest["layer"]["library_path"] = os.path.relpath(library, os.path.dirname(manifest_path))
        with open(manifest_path, "w", encoding="utf-8") as stream:
            json.dump(manifest, stream, indent=2)
