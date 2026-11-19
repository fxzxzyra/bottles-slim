# dll.py
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

import contextlib
import os
import shutil
import tempfile
from abc import abstractmethod
from copy import deepcopy

from bottles.backend.logger import Logger
from bottles.backend.models.config import BottleConfig
from bottles.backend.models.enum import Arch
from bottles.backend.utils.manager import ManagerUtils
from bottles.backend.wine.reg import Reg

logging = Logger()


class DLLComponent:
    base_path: str
    dlls: dict = {}
    checked_dlls: dict = {}
    version: str = ""
    restore_builtin: bool = False
    component_id: str
    # Source-relative file -> component-root-relative installed file.
    native_files: dict[str, str] = {}

    def __init__(self, version: str):
        self.checked_dlls = {}
        self.version = version
        self.base_path = self.get_base_path(version)
        self.check()

    @staticmethod
    @abstractmethod
    def get_base_path(version: str) -> str:
        pass

    @staticmethod
    @abstractmethod
    def get_override_keys() -> str:
        pass

    @staticmethod
    def get_backup_path(target: str) -> str:
        return f"{target}.bck"

    def prepare_install(self, target: str, backup: str, backup_created: bool) -> bool:
        return True

    def cancel_install(self, target: str, backup: str, backup_created: bool) -> None:
        if backup_created:
            with contextlib.suppress(FileNotFoundError):
                os.remove(backup)

    def complete_install(self, target: str, backup: str) -> None:
        pass

    def finish_uninstall(self, target: str, backup: str) -> None:
        pass

    def complete_uninstall(self, target: str, backup: str) -> None:
        pass

    def prepare_uninstall(self, target: str, backup: str) -> bool:
        return True

    def check(self) -> bool:
        found = deepcopy(self.dlls)

        if None in self.dlls:
            logging.error(
                f'DLL(s) "{self.dlls[None]}" path haven\'t been found, ignoring...'
            )
            return False

        for path in self.dlls:
            _path = os.path.join(self.base_path, path)
            if not os.path.exists(_path):
                del found[path]
                continue
            for dll in self.dlls[path]:
                _dll = os.path.join(_path, dll)
                if not os.path.exists(_dll):
                    found[path].remove(dll)
            if not found[path]:
                del found[path]

        if len(found) == 0:
            return False

        if any(not os.path.isfile(os.path.join(self.base_path, source)) for source in self.native_files):
            return False
        self.checked_dlls = found
        return True

    def prepare_native_payload(self, directory: str) -> None:
        """Adjust staged metadata before any installed file is changed."""

    def install(self, config: BottleConfig, overrides_only: bool = False, exclude=None):
        try:
            return self._install(config, overrides_only, exclude)
        except (OSError, ValueError) as error:
            logging.error(f"Could not install {self.component_id}: {error}")
            return False

    def _install(self, config, overrides_only, exclude):
        if overrides_only:
            windows = os.path.join(ManagerUtils.get_bottle_path(config), "drive_c", "windows")
            names = [name for name in self.get_override_keys().split(",")
                     if any(os.path.isfile(os.path.join(windows, system, name + ".dll"))
                            for system in ("system32", "syswow64"))]
            if not names:
                return False
            return Reg(config).import_bundle({
                r"HKEY_CURRENT_USER\Software\Wine\DllOverrides": [
                    {"value": name, "data": "native,builtin"} for name in names
                ],
            }).ok
        if not self.checked_dlls:
            return False
        if None in self.checked_dlls:
            return False
        exclude = exclude or []
        stage_root = ManagerUtils.get_temp_path("", config)
        with tempfile.TemporaryDirectory(dir=stage_root, prefix="component-") as stage:
            dlls = []
            for path, names in self.checked_dlls.items():
                for name in names:
                    if name in exclude or not self.__get_sys_path(config, path):
                        continue
                    source = os.path.join(self.base_path, path, name)
                    staged = os.path.join(stage, "dlls", str(len(dlls)), os.path.basename(name))
                    os.makedirs(os.path.dirname(staged), exist_ok=True)
                    shutil.copyfile(source, staged)
                    dlls.append((path, name, staged))
            if not dlls:
                return False
            native = os.path.join(stage, "native")
            for source, relative in self.native_files.items():
                destination = os.path.join(native, relative)
                os.makedirs(os.path.dirname(destination), exist_ok=True)
                shutil.copy2(os.path.join(self.base_path, source), destination)
            if self.native_files:
                self.prepare_native_payload(native)
                installed = ManagerUtils.get_component_path(config, self.component_id)
                if os.path.islink(installed):
                    raise ValueError("Component installation must be inside the container")
                for relative in self.native_files.values():
                    destination = os.path.join(installed, relative)
                    parent = os.path.dirname(destination)
                    if os.path.commonpath((os.path.realpath(installed), os.path.realpath(parent))) != os.path.realpath(installed):
                        raise ValueError("Component installation must be inside the container")
                    os.makedirs(parent, exist_ok=True)
                    os.replace(os.path.join(native, relative), destination)
            overrides = []
            for path, name, staged in dlls:
                if not self.__install_dll(config, path, name, source_override=staged):
                    return False
                overrides.append({"value": name.rsplit("/", 1)[-1].split(".")[0], "data": "native,builtin"})
        return Reg(config).import_bundle({
            r"HKEY_CURRENT_USER\Software\Wine\DllOverrides": overrides,
        }).ok

    def uninstall(self, config: BottleConfig, exclude=None):
        try:
            return self._uninstall(config, exclude)
        except (OSError, ValueError) as error:
            logging.error(f"Could not remove {self.component_id}: {error}")
            return False

    def _uninstall(self, config, exclude):
        reg = Reg(config)
        dll_in = []
        bundle = {"HKEY_CURRENT_USER\\Software\\Wine\\DllOverrides": []}

        if exclude is None:
            exclude = []

        if None in self.dlls:
            logging.error(
                f'DLL(s) "{self.dlls[None]}" path haven\'t been found, ignoring...'
            )
            return False

        for path in self.dlls:
            for dll in self.dlls[path]:
                if dll not in exclude:
                    dll_name = dll.split("/")[-1].split(".")[0]
                    if self.__uninstall_dll(config, path, dll):
                        dll_in.append(dll_name)
                    else:
                        return False

        for dll in dll_in:
            bundle["HKEY_CURRENT_USER\\Software\\Wine\\DllOverrides"].append(
                {"value": dll, "data": "-"}
            )

        if not reg.import_bundle(bundle).ok:
            return False
        if self.native_files:
            installed = ManagerUtils.get_component_path(config, self.component_id)
            if os.path.isdir(installed):
                shutil.rmtree(installed)
        return True

    @staticmethod
    def __get_sys_path(config: BottleConfig, path: str) -> str:
        if config.Arch == Arch.WIN32:
            if path in ["x32", "x86"]:
                return "system32"
        if config.Arch == Arch.WIN64:
            if path in ["x64"] or any(
                arch in path for arch in ("x86_64", "lib64", "lib/")
            ):
                return "system32"
            if path in ["x32", "x86"]:
                return "syswow64"
        return ""

    def __get_builtin_path(self, config: BottleConfig, system: str, dll: str):
        runner = ManagerUtils.get_runner_path(config.Runner)

        arch = "i386" if system == "syswow64" or config.Arch == Arch.WIN32 else "x86_64"
        for directory in (
            "lib",
            "lib64",
            "lib32",
            "lib/x86_64-linux-gnu",
            "lib/i386-linux-gnu",
        ):
            source = os.path.join(runner, directory, "wine", f"{arch}-windows", dll)
            if os.path.isfile(source):
                return source
        return None

    def __install_dll(
        self, config: BottleConfig, path: str, dll: str, remove: bool = False, source_override: str | None = None
    ):
        dll_name = dll.split("/")[-1]
        bottle = ManagerUtils.get_bottle_path(config)
        bottle = os.path.join(bottle, "drive_c", "windows")
        source = source_override if source_override is not None else os.path.join(self.base_path, path, dll)
        path = self.__get_sys_path(config, path)

        if path != "":
            target = os.path.join(bottle, path, dll_name)
        else:
            target = None

        if target is None:
            return True

        print(f"{source} -> {target}")

        if target is not None:
            backup = self.get_backup_path(target)
            if not remove:
                backup_created = False
                temporary = None
                try:
                    if os.path.exists(target) and not os.path.exists(backup):
                        shutil.copy(target, backup)
                        backup_created = True
                    if not self.prepare_install(target, backup, backup_created):
                        self.cancel_install(target, backup, backup_created)
                        return False
                    fd, temporary = tempfile.mkstemp(dir=os.path.dirname(target))
                    os.close(fd)
                    shutil.copyfile(source, temporary)
                    os.replace(temporary, target)
                    self.complete_install(target, backup)
                except OSError:
                    if temporary:
                        with contextlib.suppress(FileNotFoundError):
                            os.remove(temporary)
                    self.cancel_install(target, backup, backup_created)
                    logging.warning(f"Failed to install {source}")
                    return False
                """
                reg.add(
                    key="HKEY_CURRENT_USER\\Software\\Wine\\DllOverrides",
                    value=dll_name.split('.')[0],
                    data="native,builtin"
                )
                """
                return True

            if not self.prepare_uninstall(target, backup):
                return False

            temporary = None
            backup_used = False
            try:
                if os.path.exists(backup):
                    source = backup
                    if self.restore_builtin:
                        with open(backup, "rb") as stream:
                            header = stream.read(81)
                        if header[:2] == b"MZ" and header[64:81] == b"Wine builtin DLL\0":
                            source = (
                                self.__get_builtin_path(config, path, dll_name) or backup
                            )
                    fd, temporary = tempfile.mkstemp(dir=os.path.dirname(target))
                    os.close(fd)
                    shutil.copyfile(source, temporary)
                    os.replace(temporary, target)
                    backup_used = True
                else:
                    builtin = (
                        self.__get_builtin_path(config, path, dll_name)
                        if self.restore_builtin
                        else None
                    )
                    if builtin:
                        fd, temporary = tempfile.mkstemp(dir=os.path.dirname(target))
                        os.close(fd)
                        shutil.copyfile(builtin, temporary)
                        os.replace(temporary, target)
                    elif os.path.exists(target):
                        os.remove(target)
                self.finish_uninstall(target, backup)
                if backup_used:
                    os.remove(backup)
                self.complete_uninstall(target, backup)
            except OSError:
                if temporary:
                    with contextlib.suppress(FileNotFoundError):
                        os.remove(temporary)
                logging.warning(f"Failed to uninstall {target}")
                return False
            """
            reg.remove(
                key="HKEY_CURRENT_USER\\Software\\Wine\\DllOverrides",
                value=dll_name.split('.')[0]
            )
            """
            return True

    def __uninstall_dll(self, config, path: str, dll: str):
        return self.__install_dll(config, path, dll, remove=True)
