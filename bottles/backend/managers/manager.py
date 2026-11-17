# manager.py
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

import fnmatch
import os
import shlex
import re
import shutil
import sqlite3
import subprocess
import time
import uuid
from copy import deepcopy
from datetime import datetime
from gettext import gettext as _
from glob import glob
from threading import Event, RLock
from typing import Any, Callable, ClassVar, Dict, List, Optional, Tuple

from bottles.backend.dlls.d7vk import D7VKComponent
from bottles.backend.dlls.dxvk import DXVKComponent
from bottles.backend.dlls.latencyflex import LatencyFleXComponent
from bottles.backend.dlls.nvapi import NVAPIComponent
from bottles.backend.dlls.vkd3d import VKD3DComponent
from bottles.backend.globals import Paths
from bottles.backend.logger import Logger
from bottles.backend.managers.component import ComponentManager
from bottles.backend.managers.data import DataManager, UserDataKeys
from bottles.backend.managers.storage import BottleIndex, bottle_directory, bottle_operation
from bottles.backend.managers.dependency import DependencyManager
from bottles.backend.managers.epicgamesstore import EpicGamesStoreManager
from bottles.backend.managers.importer import ImportManager
from bottles.backend.managers.installer import InstallerManager
from bottles.backend.managers.library import LibraryManager
from bottles.backend.managers.playtime import ProcessSessionTracker
from bottles.backend.managers.registry_rule import RegistryRuleManager
from bottles.backend.managers.repository import RepositoryManager
from bottles.backend.managers.steam import SteamManager
from bottles.backend.managers.template import TemplateManager
from bottles.backend.managers.ubisoftconnect import UbisoftConnectManager
from bottles.backend.managers.versioning import VersioningManager
from bottles.backend.models.config import BottleConfig
from bottles.backend.models.result import Result
from bottles.backend.models.samples import Samples
from bottles.backend.state import (
    EventManager,
    Events,
    Notification,
    SignalManager,
    Signals,
)
from bottles.backend.utils import yaml
from bottles.backend.utils.connection import ConnectionUtils
from bottles.backend.utils.file import FileUtils
from bottles.backend.utils.generic import is_ntsync_available, sort_by_version
from bottles.backend.utils.gpu import GPUUtils, GPUVendors
from bottles.backend.utils.gsettings_stub import GSettingsStub
from bottles.backend.utils.lnk import LnkUtils
from bottles.backend.utils.manager import ManagerUtils
from bottles.backend.utils.runners import (
    RunnerRegistry,
    SYSTEM_WINE,
    system_runner_guidance,
)
from bottles.backend.utils.singleton import Singleton
from bottles.backend.utils.steam import SteamUtils
from bottles.backend.utils.threading import RunAsync
from bottles.backend.utils.wine import WineUtils
from bottles.backend.wine.drives import Drives
from bottles.backend.wine.reg import Reg
from bottles.backend.wine.regkeys import RegKeys
from bottles.backend.wine.uninstaller import Uninstaller
from bottles.backend.wine.wineboot import WineBoot
from bottles.backend.wine.winepath import WinePath
from bottles.backend.wine.wineserver import WineServer

logging = Logger()


class Manager(metaclass=Singleton):
    """
    This is the core of Bottles, everything starts from here. There should
    be only one instance of this class, as it checks for the existence of
    the bottles' directories and creates them if they don't exist. Also
    check for components, dependencies, and installers so this check should
    not be performed every time the manager is initialized.
    """

    # component lists
    runtimes_available = []
    winebridge_available = []
    runners_available = []
    d7vk_available: ClassVar[list] = []
    dxvk_available = []
    vkd3d_available = []
    nvapi_available = []
    latencyflex_available = []
    local_bottles: Dict[str, BottleConfig] = {}
    _programs_cache: Dict[str, List[dict]] = {}
    supported_runtimes = {}
    supported_winebridge = {}
    supported_d7vk: ClassVar[dict] = {}
    supported_dxvk = {}
    supported_vkd3d = {}
    supported_nvapi = {}
    supported_latencyflex = {}
    supported_dependencies = {}
    supported_installers = {}
    _playtime_signals_connected: bool = False

    def __init__(
        self,
        g_settings: Any = None,
        check_connection: bool = True,
        is_cli: bool = False,
        **kwargs,
    ):
        super().__init__(**kwargs)

        times = {"start": time.time()}

        # common variables
        self.is_cli = is_cli
        self.settings = g_settings or GSettingsStub
        # The CLI used to be wired offline unconditionally, which left the
        # component catalog empty and made bottle creation fail when nothing was
        # cached locally. Honor the actual force-offline setting instead, so the
        # CLI can fetch and install components just like the GUI.
        self.utils_conn = ConnectionUtils(
            force_offline=self.settings.get_boolean("force-offline")
        )
        self.data_mgr = DataManager()
        _offline = True

        if check_connection and not self.utils_conn.force_offline:
            _offline = not self.utils_conn.check_connection()

        # sub-managers
        self.repository_manager = RepositoryManager(get_index=not _offline)
        if self.repository_manager.aborted_connections > 0:
            self.utils_conn.status = False
            _offline = True

        times["RepositoryManager"] = time.time()
        self.versioning_manager = VersioningManager(self)
        times["VersioningManager"] = time.time()
        self.component_manager = ComponentManager(self, _offline)
        self.installer_manager = InstallerManager(self, _offline)
        self.dependency_manager = DependencyManager(self, _offline)
        self.import_manager = ImportManager(self)
        times["ImportManager"] = time.time()
        self.steam_manager = SteamManager()
        times["SteamManager"] = time.time()

        # Initialize playtime tracker
        self._playtime_trackers = {}
        self._playtime_lock = RLock()
        self._launch_to_session = {}
        times["PlaytimeTracker"] = time.time()

        # React to runtime changes in playtime preference when available
        if hasattr(self.settings, "connect"):
            try:
                self.settings.connect(
                    "changed::playtime-enabled", self._on_playtime_enabled_changed
                )
            except Exception:
                pass

        # Subscribe to playtime signals (connect once per process)
        if not Manager._playtime_signals_connected:
            SignalManager.connect(Signals.ProgramStarted, self._on_program_started)
            SignalManager.connect(Signals.ProgramFinished, self._on_program_finished)
            Manager._playtime_signals_connected = True

        if not self.is_cli:
            times.update(self.checks(install_latest=False, first_run=True).data)
        else:
            logging.set_silent()
            self.check_app_dirs()
            self.check_runners()

        if "BOOT_TIME" in os.environ:
            _temp_times = times.copy()
            last = 0
            times_str = "Boot times:"
            for f, t in _temp_times.items():
                if last == 0:
                    last = int(round(t))
                    continue
                t = int(round(t))
                times_str += f"\n\t - {f} took: {t - last}s"
                last = t
            logging.info(times_str)

    def checks(
        self,
        install_latest=False,
        first_run=False,
        progress_callback: Optional[Callable[..., None]] = None,
    ) -> Result:
        logging.info("Performing Bottles checks…")

        rv = Result(status=True, data={})

        steps: List[Tuple[Optional[str], str, Callable[[], bool | None]]] = [
            ("check_app_dirs", _("Preparing folders…"), self.check_app_dirs),
            (
                "check_d7vk",
                _("Setting up D7VK..."),
                lambda: self.check_d7vk(install_latest),
            ),
            (
                "check_dxvk",
                _("Setting up DXVK…"),
                lambda: self.check_dxvk(install_latest),
            ),
            (
                "check_vkd3d",
                _("Setting up VKD3D…"),
                lambda: self.check_vkd3d(install_latest),
            ),
            (
                "check_nvapi",
                _("Setting up NVAPI…"),
                lambda: self.check_nvapi(install_latest),
            ),
            (
                "check_latencyflex",
                _("Setting up LatencyFleX…"),
                lambda: self.check_latencyflex(install_latest),
            ),
            (
                "check_runtimes",
                _("Preparing runtimes…"),
                lambda: self.check_runtimes(install_latest),
            ),
            (
                "check_winebridge",
                _("Preparing WineBridge…"),
                lambda: self.check_winebridge(install_latest),
            ),
            (
                "check_runners",
                _("Preparing runners…"),
                self.check_runners,
            ),
        ]

        if first_run:
            steps.extend(
                [
                    (
                        None,
                        _("Organizing components…"),
                        self.organize_components,
                    ),
                    (
                        None,
                        _("Cleaning temporary files…"),
                        self.__clear_temp,
                    ),
                ]
            )

        steps.extend(
            [
                (
                    None,
                    _("Organizing dependencies…"),
                    self.organize_dependencies,
                ),
                (
                    None,
                    _("Organizing installers…"),
                    self.organize_installers,
                ),
                ("check_bottles", _("Loading containers…"), self.check_bottles),
            ]
        )

        total_steps = len(steps)

        for index, (data_key, description, func) in enumerate(steps, start=1):
            if progress_callback:
                try:
                    progress_callback(
                        description=description,
                        current_step=index,
                        total_steps=total_steps,
                        completed=False,
                    )
                except Exception as error:  # pragma: no cover - defensive
                    logging.debug(f"Progress callback start failed: {error}")

            result = func()

            if result is False:
                rv.set_status(False)

            if progress_callback:
                try:
                    progress_callback(
                        description=description,
                        current_step=index,
                        total_steps=total_steps,
                        completed=True,
                    )
                except Exception as error:  # pragma: no cover - defensive
                    logging.debug(f"Progress callback end failed: {error}")

            if data_key:
                rv.data[data_key] = time.time()

        return rv

    def __del__(self):
        for tracker in getattr(self, "_playtime_trackers", {}).values():
            tracker.shutdown()

    def get_playtime_tracker(self, bottle_id: str) -> ProcessSessionTracker:
        config = self.local_bottles[bottle_id]
        path = bottle_directory(ManagerUtils.get_bottle_path(config))
        with self._playtime_lock:
            db_path = os.path.join(path, "process_metrics.sqlite")
            existing = self._playtime_trackers.get(config.Id)
            if existing is not None and existing.db_path != db_path:
                existing.shutdown()
                del self._playtime_trackers[config.Id]
            if config.Id not in self._playtime_trackers:
                tracker = ProcessSessionTracker(
                    db_path=db_path,
                    enabled=self.settings.get_boolean("playtime-enabled"),
                    heartbeat_interval=self.settings.get_int("playtime-heartbeat-interval") or 60,
                )
                if not self.is_cli and tracker.has_open_sessions() and not WineServer(config).is_alive():
                    tracker.recover_open_sessions()
                self._playtime_trackers[config.Id] = tracker
            return self._playtime_trackers[config.Id]

    def _on_playtime_enabled_changed(self, _settings, _key) -> None:
        for tracker in self._playtime_trackers.values():
            tracker.shutdown()
        self._playtime_trackers.clear()
        self._launch_to_session = {key: (config, None) for key, (config, _sid) in self._launch_to_session.items()}

    # Playtime signal handlers
    _launch_to_session: Dict[str, tuple[BottleConfig, Optional[int]]] = {}

    # Public Playtime API (wrap tracker with Result)
    def playtime_start(
        self,
        *,
        bottle_id: str,
        bottle_name: str,
        bottle_path: str,
        program_name: str,
        program_path: str,
    ) -> Result[int]:
        try:
            sid = self.get_playtime_tracker(bottle_id).start_session(
                bottle_id=bottle_id,
                bottle_name=bottle_name,
                bottle_path=bottle_path,
                program_name=program_name,
                program_path=program_path,
            )
            return Result(True, data=sid)
        except Exception as e:
            logging.exception(e)
            return Result(False, message=str(e))

    def playtime_finish(
        self,
        session_id: int,
        *,
        bottle_id: str,
        status: str = "success",
        ended_at: Optional[int] = None,
    ) -> Result[None]:
        try:
            if status == "success":
                self.get_playtime_tracker(bottle_id).mark_exit(
                    session_id, status="success", ended_at=ended_at
                )
            else:
                self.get_playtime_tracker(bottle_id).mark_failure(session_id, status=status)
            return Result(True)
        except Exception as e:
            logging.exception(e)
            return Result(False, message=str(e))

    def _on_program_started(self, data: Optional[Result] = None) -> None:
        if not data or not data.data:
            return
        payload = data.data
        config = self.local_bottles[payload.bottle_id]
        RegistryRuleManager.apply_rules(config, trigger="start_program")
        sid = None
        if self.settings.get_boolean("playtime-enabled"):
            result = self.playtime_start(
                bottle_id=payload.bottle_id,
                bottle_name=payload.bottle_name,
                bottle_path=payload.bottle_path,
                program_name=payload.program_name,
                program_path=payload.program_path,
            )
            if result.ok:
                sid = result.data
        self._launch_to_session[payload.launch_id] = (config, sid)

    def _on_program_finished(self, data: Optional[Result] = None) -> None:
        if not data or not data.data:
            return
        payload = data.data
        session = self._launch_to_session.pop(payload.launch_id, None)
        if session is None:
            return
        config, sid = session
        if sid is not None:
            self.playtime_finish(sid, bottle_id=config.identifier, status=payload.status,
                                 ended_at=int(payload.ended_at or time.time()))
        RegistryRuleManager.apply_rules(config, trigger="stop_program")

    def __clear_temp(self, force: bool = False):
        """Clears the temp directory if user setting allows it. Use the force
        parameter to force clearing the directory.
        """
        if self.settings.get_boolean("temp") or force:
            try:
                shutil.rmtree(Paths.temp)
                os.makedirs(Paths.temp, exist_ok=True)
                logging.info("Temp directory cleaned successfully!")
            except FileNotFoundError:
                self.check_app_dirs()

    def get_cache_details(self) -> dict:
        self.check_app_dirs()
        file_utils = FileUtils()

        temp_size_bytes = file_utils.get_path_size(Paths.temp, human=False)
        templates = []
        templates_size_bytes = 0

        for template in TemplateManager.get_templates():
            template_uuid = template.get("uuid", "")
            template_path = os.path.join(Paths.templates, template_uuid)

            size_bytes = file_utils.get_path_size(template_path, human=False)
            templates_size_bytes += size_bytes

            templates.append(
                {
                    "uuid": template_uuid,
                    "env": template.get("env", ""),
                    "created": template.get("created", ""),
                    "size": file_utils.get_human_size(size_bytes),
                    "size_bytes": size_bytes,
                }
            )

        total_size_bytes = temp_size_bytes + templates_size_bytes

        return {
            "temp": {
                "path": Paths.temp,
                "size": file_utils.get_human_size(temp_size_bytes),
                "size_bytes": temp_size_bytes,
            },
            "templates": templates,
            "templates_size": file_utils.get_human_size(templates_size_bytes),
            "templates_size_bytes": templates_size_bytes,
            "total_size": file_utils.get_human_size(total_size_bytes),
            "total_size_bytes": total_size_bytes,
        }

    def clear_temp_cache(self) -> Result[None]:
        try:
            self.__clear_temp(force=True)
        except Exception as ex:
            logging.error(f"Failed to clear temp cache: {ex}")
            return Result(False, message=str(ex))

        return Result(True)

    def clear_template_cache(self, template_uuid: str) -> Result[None]:
        self.check_app_dirs()
        try:
            TemplateManager.delete_template(template_uuid)
        except Exception as ex:
            logging.error(f"Failed to clear template cache: {ex}")
            return Result(False, message=str(ex))

        return Result(True)

    def clear_templates_cache(self) -> Result[None]:
        self.check_app_dirs()
        try:
            for template in TemplateManager.get_templates():
                TemplateManager.delete_template(template.get("uuid", ""))
        except Exception as ex:
            logging.error(f"Failed to clear templates cache: {ex}")
            return Result(False, message=str(ex))

        return Result(True)

    def clear_all_caches(self) -> Result[None]:
        temp_result = self.clear_temp_cache()
        if not temp_result.ok:
            return temp_result

        templates_result = self.clear_templates_cache()
        if not templates_result.ok:
            return templates_result

        return Result(True)

    def update_bottles(self, silent: bool = False):
        """Checks for new bottles and update the list view."""
        self.check_bottles(silent)
        SignalManager.send(Signals.ManagerLocalBottlesLoaded)

    def check_app_dirs(self):
        """
        Checks for the existence of the bottles' directories, and creates them
        if they don't exist.
        """
        if not os.path.isdir(Paths.runtimes):
            logging.info("Runtimes path doesn't exist, creating now.")
            os.makedirs(Paths.runtimes, exist_ok=True)

        if not os.path.isdir(Paths.winebridge):
            logging.info("WineBridge path doesn't exist, creating now.")
            os.makedirs(Paths.winebridge, exist_ok=True)

        if not os.path.isdir(Paths.dxvk):
            logging.info("Dxvk path doesn't exist, creating now.")
            os.makedirs(Paths.dxvk, exist_ok=True)

        if not os.path.isdir(Paths.d7vk):
            logging.info("D7VK path doesn't exist, creating now.")
            os.makedirs(Paths.d7vk, exist_ok=True)

        if not os.path.isdir(Paths.vkd3d):
            logging.info("Vkd3d path doesn't exist, creating now.")
            os.makedirs(Paths.vkd3d, exist_ok=True)

        if not os.path.isdir(Paths.nvapi):
            logging.info("Nvapi path doesn't exist, creating now.")
            os.makedirs(Paths.nvapi, exist_ok=True)

        if not os.path.isdir(Paths.templates):
            logging.info("Templates path doesn't exist, creating now.")
            os.makedirs(Paths.templates, exist_ok=True)

        if not os.path.isdir(Paths.temp):
            logging.info("Temp path doesn't exist, creating now.")
            os.makedirs(Paths.temp, exist_ok=True)

        if not os.path.isdir(Paths.latencyflex):
            logging.info("LatencyFleX path doesn't exist, creating now.")
            os.makedirs(Paths.latencyflex, exist_ok=True)

    @RunAsync.run_async
    def organize_components(self):
        """Get components catalog and organizes into supported_ lists."""
        EventManager.wait(Events.ComponentsFetching)
        catalog = self.component_manager.fetch_catalog()
        if len(catalog) == 0:
            EventManager.done(Events.ComponentsOrganizing)
            logging.info("No components found.")
            return

        self.supported_runtimes = catalog["runtimes"]
        self.supported_winebridge = catalog["winebridge"]
        self.supported_d7vk = catalog["d7vk"]
        self.supported_dxvk = catalog["dxvk"]
        self.supported_vkd3d = catalog["vkd3d"]
        self.supported_nvapi = catalog["nvapi"]
        self.supported_latencyflex = catalog["latencyflex"]
        EventManager.done(Events.ComponentsOrganizing)

    @RunAsync.run_async
    def organize_dependencies(self):
        """Organizes dependencies into supported_dependencies."""
        EventManager.wait(Events.DependenciesFetching)
        catalog = self.dependency_manager.fetch_catalog()
        if len(catalog) == 0:
            EventManager.done(Events.DependenciesOrganizing)
            logging.info("No dependencies found!")
            return

        self.supported_dependencies = catalog
        EventManager.done(Events.DependenciesOrganizing)

    @RunAsync.run_async
    def organize_installers(self):
        """Organizes installers into supported_installers."""
        EventManager.wait(Events.InstallersFetching)
        catalog = self.installer_manager.fetch_catalog()
        if len(catalog) == 0:
            EventManager.done(Events.InstallersOrganizing)
            logging.info("No installers found!")
            return

        self.supported_installers = catalog
        EventManager.done(Events.InstallersOrganizing)

    def remove_dependency(self, config: BottleConfig, dependency: list):
        """Uninstall a dependency and remove it from the bottle config."""
        dependency = dependency[0]
        logging.info(f"Removing {dependency} dependency from {config.Name}")
        uninstallers = config.Uninstallers

        names = Uninstaller.get_names(uninstallers.get(dependency))
        if not names:
            return Result(
                status=False,
                message=f"No uninstaller is available for {dependency}.",
            )

        uninstaller = Uninstaller(config)
        for name in names:
            result = uninstaller.from_name(name)
            if not result.ok:
                return Result(
                    False,
                    message=result.message or f"Failed to uninstall {name}.",
                )

        # remove dependency from bottle configuration
        if dependency in config.Installed_Dependencies:
            config.Installed_Dependencies.remove(dependency)

        self.update_config(
            config, key="Installed_Dependencies", value=config.Installed_Dependencies
        )
        self.update_config(
            config,
            key=dependency,
            value=None,
            scope="Uninstallers",
            remove=True,
        )
        return Result(status=True, data={"removed": True})

    def check_runners(self) -> bool:
        """Discover usable local runners, with package-supplied Wine first."""
        entries = RunnerRegistry.packaged(Paths.system_runners)
        # PATH is relative to the current execution environment, including
        # the sandbox when packaged. It does not access the host's Wine.
        system = RunnerRegistry.system()
        if system:
            entries[system.identifier] = system

        registrations = self.data_mgr.get(UserDataKeys.UserRunners) or {}
        for identifier, registration in registrations.items():
            try:
                entries[identifier] = RunnerRegistry.inspect(
                    identifier, registration["path"], name=registration["name"],
                )
            except (OSError, ValueError) as error:
                logging.warning(f"Unavailable registered runner {registration['name']}: {error}")

        RunnerRegistry.entries = entries
        self.runners_available = list(entries)
        return bool(entries)

    def register_user_runner(self, name: str, path: str, identifier: str | None = None) -> Result:
        """Register or edit a named Wine installation in place; never change its files."""
        name = name.strip()
        if not name:
            return Result(False, message=_("Enter a runner name."))
        if not os.path.isabs(path):
            return Result(False, message=_("Select an absolute runner directory."))
        if "/run/user/" in path and "/doc/" in path:
            return Result(False, message=_("Select a permanent runner directory, not a document portal path."))
        path = os.path.realpath(path)
        registrations = dict(self.data_mgr.get(UserDataKeys.UserRunners) or {})
        if identifier is not None and identifier not in registrations:
            return Result(False, message=_("This runner registration no longer exists."))
        for key, registration in registrations.items():
            if key == identifier:
                continue
            if registration["name"].casefold() == name.casefold():
                return Result(False, message=_("A runner with this name is already registered."))
            if os.path.realpath(registration["path"]) == path:
                return Result(False, message=_("This runner is already registered."))
        if any(info.source == "system" and os.path.realpath(info.root) == path
               for info in RunnerRegistry.entries.values()):
            return Result(False, message=_("This runner is already provided by the system."))
        identifier = identifier or f"user-{uuid.uuid4().hex}"
        try:
            RunnerRegistry.inspect(identifier, path, name=name)
        except (OSError, ValueError) as error:
            return Result(False, message=str(error))
        registrations[identifier] = {"name": name, "path": path}
        self.data_mgr.set(UserDataKeys.UserRunners, registrations)
        self.check_runners()
        return Result(True, data={"runner": identifier})

    def remove_user_runner(self, identifier: str) -> Result:
        """Forget an explicit import; never delete the user's runner directory."""
        if any(config.Runner == identifier for config in self.local_bottles.values()):
            return Result(False, message=_("This runner is used by a container."))
        registrations = dict(self.data_mgr.get(UserDataKeys.UserRunners) or {})
        if identifier not in registrations:
            return Result(False, message=_("This runner is managed outside Bottles."))
        del registrations[identifier]
        self.data_mgr.set(UserDataKeys.UserRunners, registrations)
        self.check_runners()
        return Result(True)

    def check_runtimes(self, install_latest: bool = True) -> bool:
        self.runtimes_available = []
        if "FLATPAK_ID" in os.environ:
            self.runtimes_available = ["flatpak-managed"]
            return True

        runtimes = os.listdir(Paths.runtimes)

        if len(runtimes) == 0:
            if install_latest and self.utils_conn.check_connection():
                logging.warning("No runtime found.")
                try:
                    version = next(iter(self.supported_runtimes))
                    return self.component_manager.install("runtime", version)
                except StopIteration:
                    return False
            return False

        runtime = runtimes[0]  # runtimes cannot be more than one
        manifest = os.path.join(Paths.runtimes, runtime, "manifest.yml")

        if os.path.exists(manifest):
            with open(manifest, "r") as f:
                data = yaml.load(f)
                version = data.get("version")
                if version:
                    version = f"runtime-{version}"
                    self.runtimes_available = [version]
                    return True
        return False

    def __winebridge_status(self) -> tuple[Optional[str], Optional[str], bool]:
        def _is_newer(candidate: str, current: str) -> bool:
            versions = [candidate, current]
            try:
                sorted_versions = sort_by_version(list(versions))
            except ValueError:
                sorted_versions = sorted(versions, reverse=True)
            return sorted_versions[0] == candidate and candidate != current

        self.winebridge_available = []
        winebridge = os.listdir(Paths.winebridge)
        latest_supported = None

        if self.supported_winebridge:
            try:
                latest_supported = sort_by_version(
                    list(self.supported_winebridge.keys())
                )[0]
            except ValueError:
                latest_supported = sorted(
                    list(self.supported_winebridge.keys()), reverse=True
                )[0]

        version_file = os.path.join(Paths.winebridge, "VERSION")
        installed_identifier = None
        if os.path.exists(version_file):
            with open(version_file, "r") as f:
                version = f.read().strip()
                if version:
                    installed_identifier = f"winebridge-{version}"
                    self.winebridge_available = [installed_identifier]

        missing_installation = len(winebridge) == 0 or not installed_identifier
        needs_latest = False
        if latest_supported:
            needs_latest = missing_installation or _is_newer(
                latest_supported, installed_identifier
            )

        return latest_supported, installed_identifier, needs_latest

    def winebridge_update_status(self) -> dict:
        latest_supported, installed_identifier, needs_latest = (
            self.__winebridge_status()
        )
        return {
            "latest_supported": latest_supported,
            "installed_identifier": installed_identifier,
            "needs_latest": needs_latest,
            "missing": not installed_identifier,
        }

    def check_winebridge(
        self, install_latest: bool = True, update: bool = False
    ) -> bool:
        latest_supported, installed_identifier, needs_latest = (
            self.__winebridge_status()
        )

        can_install = install_latest or update
        if can_install and needs_latest and latest_supported:
            if not self.utils_conn.check_connection():
                return False
            logging.warning("WineBridge installation/update required.")
            res = self.component_manager.install("winebridge", latest_supported)
            if res.ok:
                self.winebridge_available = [latest_supported]
                return True
            return False

        if needs_latest and not can_install:
            return False

        return bool(self.winebridge_available)

    def check_dxvk(self, install_latest: bool = True) -> bool:
        res = self.__check_component("dxvk", install_latest)
        if res:
            self.dxvk_available = res
        return res is not False

    def check_d7vk(self, install_latest: bool = True) -> bool:
        res = self.__check_component("d7vk", install_latest)
        self.d7vk_available = res if isinstance(res, list) else []
        return res is not False

    def check_vkd3d(self, install_latest: bool = True) -> bool:
        res = self.__check_component("vkd3d", install_latest)
        if res:
            self.vkd3d_available = res
        return res is not False

    def check_nvapi(self, install_latest: bool = True) -> bool:
        res = self.__check_component("nvapi", install_latest)
        if res:
            self.nvapi_available = res
        return res is not False

    def check_latencyflex(self, install_latest: bool = True) -> bool:
        res = self.__check_component("latencyflex", install_latest)
        if res:
            self.latencyflex_available = res
        return res is not False

    def get_offline_components(
        self, component_type: str, extra_name_check: str = ""
    ) -> list:
        components = {
            "d7vk": {
                "available": self.d7vk_available,
                "supported": self.supported_d7vk,
            },
            "dxvk": {
                "available": self.dxvk_available,
                "supported": self.supported_dxvk,
            },
            "vkd3d": {
                "available": self.vkd3d_available,
                "supported": self.supported_vkd3d,
            },
            "nvapi": {
                "available": self.nvapi_available,
                "supported": self.supported_nvapi,
            },
            "latencyflex": {
                "available": self.latencyflex_available,
                "supported": self.supported_latencyflex,
            },
        }
        if component_type not in components:
            logging.warning(f"Unknown component type found: {component_type}")
            raise ValueError("Component type not supported.")

        component_list = components[component_type]
        offline_components = list(
            set(component_list["available"]).difference(
                component_list["supported"].keys()
            )
        )

        if (
            extra_name_check
            and extra_name_check not in component_list["available"]
            and extra_name_check not in component_list["supported"]
        ):
            offline_components.append(extra_name_check)

        try:
            return sort_by_version(offline_components)
        except ValueError:
            return sorted(offline_components, reverse=True)

    def __check_component(
        self, component_type: str, install_latest: bool = True
    ) -> bool | list:
        components = {
            "d7vk": {
                "available": self.d7vk_available,
                "supported": self.supported_d7vk,
                "path": Paths.d7vk,
            },
            "dxvk": {
                "available": self.dxvk_available,
                "supported": self.supported_dxvk,
                "path": Paths.dxvk,
            },
            "vkd3d": {
                "available": self.vkd3d_available,
                "supported": self.supported_vkd3d,
                "path": Paths.vkd3d,
            },
            "nvapi": {
                "available": self.nvapi_available,
                "supported": self.supported_nvapi,
                "path": Paths.nvapi,
            },
            "latencyflex": {
                "available": self.latencyflex_available,
                "supported": self.supported_latencyflex,
                "path": Paths.latencyflex,
            },
            "runtime": {
                "available": self.runtimes_available,
                "supported": self.supported_runtimes,
                "path": Paths.runtimes,
            },
        }

        if component_type not in components:
            logging.warning(f"Unknown component type found: {component_type}")
            raise ValueError("Component type not supported.")

        component = components[component_type]
        component["available"] = os.listdir(component["path"])
        if component_type == "d7vk":
            component["available"] = [
                version
                for version in component["available"]
                if D7VKComponent(version).checked_dlls
            ]

        if len(component["available"]) > 0:
            logging.info(
                "{0}s found:\n - {1}".format(
                    component_type.capitalize(), "\n - ".join(component["available"])
                )
            )

        if len(component["available"]) == 0 and install_latest:
            logging.warning(f"No {component_type} found.")

            if self.utils_conn.check_connection():
                # if connected, install the latest component from repository
                try:
                    if not self.settings.get_boolean("release-candidate"):
                        tmp_components = []
                        for cpnt in component["supported"].items():
                            if cpnt[1]["Channel"] not in ["rc", "unstable"]:
                                tmp_components.append(cpnt)
                                break
                        component_version = next(iter(tmp_components))[0]
                    else:
                        tmp_components = component["supported"]
                        component_version = next(iter(tmp_components))
                    installed = self.component_manager.install(
                        component_type, component_version
                    )
                    if not installed.ok:
                        return False
                    component["available"] = [component_version]
                except StopIteration:
                    return False
            else:
                return False

        try:
            return sort_by_version(component["available"])
        except ValueError:
            return sorted(component["available"], reverse=True)

    def get_programs(
        self, config: BottleConfig, force_update: bool = False
    ) -> List[dict]:
        """
        Get the list of programs (both from the drive and the user defined
        in the bottle configuration file).
        """
        if config is None:
            return []

        cache_key = config.Id
        if not force_update and cache_key in self._programs_cache:
            return self._programs_cache[cache_key]

        bottle = ManagerUtils.get_bottle_path(config)
        winepath = WinePath(config)
        results = glob(f"{bottle}/drive_c/users/*/Desktop/*.lnk", recursive=True)
        results += glob(
            f"{bottle}/drive_c/users/*/Start Menu/Programs/**/*.lnk", recursive=True
        )
        results += glob(
            f"{bottle}/drive_c/ProgramData/Microsoft/Windows/Start Menu/Programs/**/*.lnk",
            recursive=True,
        )
        results += glob(
            f"{bottle}/drive_c/users/*/AppData/Roaming/Microsoft/Windows/Start Menu/Programs/**/*.lnk",
            recursive=True,
        )
        installed_programs = []
        ignored_patterns = [
            "*installer*",
            "*unins*",
            "*setup*",
            "*debug*",
            "*report*",
            "*crash*",
            "*err*",
            "_*",
            "start",
            "OriginEr",
            "*website*",
            "*web site*",
            "*user_manual*",
        ]
        found = []
        ext_programs = config.External_Programs

        """
        Process External_Programs
        """
        for _, _program in ext_programs.items():
            found.append(_program["executable"])
            if winepath.is_windows(_program["path"]):
                program_folder = ManagerUtils.get_exe_parent_dir(
                    config, _program["path"]
                )
            else:
                program_folder = os.path.dirname(_program["path"])
            installed_programs.append(
                {
                    "executable": _program.get("executable"),
                    "arguments": _program.get("arguments"),
                    "arguments_enabled": _program.get("arguments_enabled", True),
                    "environment": _program.get("environment"),
                    "name": _program.get("name"),
                    "path": _program.get("path"),
                    "icon": "com.usebottles.bottles-program",
                    "pre_script": _program.get("pre_script"),
                    "pre_script_args": _program.get("pre_script_args"),
                    "post_script": _program.get("post_script"),
                    "post_script_args": _program.get("post_script_args"),
                    "folder": _program.get("folder", program_folder),
                    "d7vk": _program.get("d7vk"),
                    "dxvk": _program.get("dxvk"),
                    "vkd3d": _program.get("vkd3d"),
                    "dxvk_nvapi": _program.get("dxvk_nvapi"),
                    "gamescope": _program.get("gamescope"),
                    "discrete_gpu": _program.get("discrete_gpu"),
                    "fsr": _program.get("fsr"),
                    "gamemode": _program.get("gamemode"),
                    "latencyflex": _program.get("latencyflex"),
                    "sync": _program.get("sync"),
                    "pulseaudio_latency": _program.get("pulseaudio_latency"),
                    "virtual_desktop": _program.get("virtual_desktop"),
                    "winebridge": _program.get("winebridge"),
                    "hide_console": _program.get("hide_console"),
                    "autostart": _program.get("autostart", False),
                    "file_extensions": _program.get("file_extensions", []),
                    "automatic_backup": _program.get("automatic_backup"),
                    "removed": _program.get("removed"),
                    "id": _program.get("id"),
                }
            )

        for program in results:
            """
            for each .lnk file, try to get the executable path and
            append it to the installed_programs list with its icon,
            skip if the path contains the "Uninstall" word.
            """
            executable_path = LnkUtils.get_data(program)
            if executable_path in [None, ""]:
                continue
            executable_name = executable_path.split("\\")[-1]
            program_folder = ManagerUtils.get_exe_parent_dir(config, executable_path)
            stop = False

            for pattern in ignored_patterns:
                try:
                    if fnmatch.fnmatch(executable_name.lower(), pattern):
                        stop = True
                        break
                except:  # safe to ignore
                    pass
            if stop:
                continue

            path_check = os.path.join(
                bottle, executable_path.replace("C:\\", "drive_c\\").replace("\\", "/")
            )
            if os.path.exists(path_check):
                if executable_name not in found:
                    installed_programs.append(
                        {
                            "executable": executable_name,
                            "arguments": "",
                            "name": executable_name.rsplit(".", 1)[0],
                            "path": executable_path,
                            "folder": program_folder,
                            "icon": "com.usebottles.bottles-program",
                            "id": str(uuid.uuid4()),
                            "auto_discovered": True,
                        }
                    )
                    found.append(executable_name)

        win_steam_manager = SteamManager(config, is_windows=True)

        if (
            self.settings.get_boolean("steam-programs")
            and win_steam_manager.is_steam_supported
        ):
            programs_names = [p.get("name", "") for p in installed_programs]
            for app in win_steam_manager.get_installed_apps_as_programs():
                if app["name"] not in programs_names:
                    installed_programs.append(app)

        if self.settings.get_boolean(
            "epic-games"
        ) and EpicGamesStoreManager.is_epic_supported(config):
            programs_names = {p.get("name", "") for p in installed_programs}
            program_launches = {
                (
                    p.get("path"),
                    p.get("arguments") if p.get("arguments_enabled", True) else None,
                )
                for p in installed_programs
            }
            for app in EpicGamesStoreManager.get_installed_games(config):
                launch = (app.get("path"), app.get("arguments"))
                if app["name"] in programs_names or launch in program_launches:
                    continue
                installed_programs.append(app)
                programs_names.add(app["name"])
                program_launches.add(launch)

        if self.settings.get_boolean(
            "ubisoft-connect"
        ) and UbisoftConnectManager.is_uconnect_supported(config):
            programs_names = [p.get("name", "") for p in installed_programs]
            for app in UbisoftConnectManager.get_installed_games(config):
                if app["name"] not in programs_names:
                    installed_programs.append(app)

        self._programs_cache[cache_key] = installed_programs
        return installed_programs

    def check_bottles(self, silent: bool = False):
        """
        Check for local bottles and update the local_bottles list.
        Will also mark the broken ones if the configuration file is missing
        """
        self.local_bottles = {}
        self._programs_cache = {}
        self.unavailable_bottles = {}
        for bottle_id, path, name in BottleIndex().records():
            try:
                bottle_directory(path)
                loaded = BottleConfig.load(os.path.join(path, "bottle.yml"))
                if not loaded.ok:
                    raise ValueError(loaded.message)
                config = loaded.data
                if config.Id != bottle_id:
                    raise ValueError("The bottle UUID differs from its registration.")
                self.local_bottles[config.Id] = config
            except (OSError, ValueError) as error:
                self.unavailable_bottles[bottle_id] = (path, str(error))
                logging.warning(f"Bottle {name} at {path} is unavailable: {error}")
        if self.unavailable_bottles and not silent and not self.is_cli:
            SignalManager.send(
                Signals.GNotification,
                Result(True, Notification(
                    title="Bottles",
                    text=_("Some registered containers are unavailable:") + "\n" + "\n".join(
                        f"{path}: {error}" for path, error in self.unavailable_bottles.values()
                    ),
                    image="drive-harddisk-symbolic",
                )),
            )

    # Update parameters in bottle config
    def update_config(
        self,
        config: BottleConfig,
        key: str,
        value: Any,
        scope: str = "",
        remove: bool = False,
        fallback: bool = False,
    ) -> Result[dict]:
        """
        Update parameters in bottle config. Use the scope argument to
        update the parameters in the specified scope (e.g. Parameters).
        A new key will be created if another already exists and fallback
        is set to True.
        TODO: move to bottle.py (Bottle manager)
        """
        _name = config.Name
        logging.info(f"Setting Key {key}={value} for bottle {_name}…")

        _config = config.copy()
        wineboot = WineBoot(_config)
        wineserver = WineServer(_config)
        bottle_path = ManagerUtils.get_bottle_path(config)

        if key == "sync":
            """
            Workaround <https://github.com/bottlesdevs/Bottles/issues/916>
            Sync type change requires wineserver restart or wine will fail
            to execute any command.
            """
            wineboot.kill()
            wineserver.wait()

        if scope:
            if remove:
                del config[scope][key]
            elif config[scope].get(key) and fallback:
                config[scope][f"{key}-{uuid.uuid4()}"] = value
            else:
                config[scope][key] = value
        else:
            if remove:
                del config[key]
            elif config.get(key) and fallback:
                config[f"{key}-{uuid.uuid4()}"] = value
            else:
                config[key] = value

        result = config.dump(os.path.join(bottle_path, "bottle.yml"))
        if not result.status:
            return Result(False, data={"config": config}, message=result.message)

        if key == "Name" and not scope:
            BottleIndex().rename(config.Id, config.Name)

        config.Update_Date = str(datetime.now())

        if scope == "External_Programs":
            self._programs_cache.pop(config.Id, None)


        component_keys = {
            "Runner",
            "D7VK",
            "DXVK",
            "VKD3D",
            "NVAPI",
            "LatencyFleX",
            "LatencyFleX_Activated",
        }

        if key in component_keys or scope in component_keys:
            RegistryRuleManager.apply_rules(config, trigger="components")

        return Result(status=True, data={"config": config})

    def apply_audio_driver(self, driver: str) -> Result[None]:
        """Apply the configured audio driver override to every bottle."""

        logging.info(f"Applying audio driver '{driver}' to local bottles…")
        try:
            for config in self.local_bottles.values():
                if not isinstance(config, BottleConfig):
                    continue
                RegKeys(config).set_audio_driver(driver)
        except ValueError as exc:
            logging.error(str(exc))
            return Result(False, message=str(exc))

        return Result(True)

    def create_bottle_from_config(self, config: BottleConfig, path: str) -> bool:
        """Create a bottle from a config object."""
        logging.info(f"Creating new {config.Name} bottle from config…")

        config = deepcopy(config)
        config.Id = uuid.uuid4().hex
        result = self.create_bottle(
            name=config.Name,
            path=path,
            environment=config.Environment or "Custom",
            runner=config.Runner,
            d7vk=config.D7VK if config.Parameters.d7vk else False,
            dxvk=config.DXVK,
            vkd3d=config.VKD3D,
            nvapi=config.NVAPI,
            latencyflex=config.LatencyFleX,
            versioning=config.Versioning,
            sandbox=config.Parameters.sandbox,
            arch=config.Arch,
            configuration=config,
        )
        if not result.ok:
            return False

        restored = result.data["config"]
        logging.info(f"New bottle from config created: {restored.Path}")
        self.update_bottles(silent=True)
        return True

    def create_bottle(
        self,
        name,
        environment: str,
        path: str,
        runner: str = False,
        d7vk: bool = False,
        dxvk: bool = False,
        vkd3d: bool = False,
        nvapi: bool = False,
        latencyflex: bool = False,
        versioning: bool = False,
        sandbox: bool = False,
        fn_logger: callable = None,
        arch: str = "win64",
        custom_environment: Optional[str] = None,
        cancel_event: Optional[Event] = None,
        configuration: Optional[BottleConfig] = None,
    ) -> Result[dict]:
        """
        Create a new bottle from the given arguments.
        TODO: will be replaced by the BottleBuilder class.
        """

        try:
            path = bottle_directory(path, empty=True)
            if name in BottleIndex().entries().values():
                raise ValueError("A bottle with this name is already registered.")
            if not name.strip():
                raise ValueError("Bottle name cannot be empty.")
        except (OSError, ValueError) as error:
            return Result(False, message=str(error))
        try:
            with bottle_operation(path):
                bottle_directory(path, empty=True)
                result = self._create_bottle(
                    name, environment, path, runner, d7vk, dxvk, vkd3d, nvapi,
                    latencyflex, versioning, sandbox, fn_logger, arch,
                    custom_environment, cancel_event, configuration,
                )
                if not result.ok:
                    if os.path.isdir(os.path.join(path, "drive_c")):
                        cleanup = BottleConfig(Path=path, Runner=runner or self.get_default_runner())
                        cleanup.Parameters.sandbox = sandbox
                        WineServer(cleanup).force_kill()
                    for item in os.scandir(path):
                        if item.is_dir(follow_symlinks=False):
                            shutil.rmtree(item.path)
                        else:
                            os.unlink(item.path)
                return result
        except (OSError, ValueError, RuntimeError, sqlite3.IntegrityError, yaml.YAMLError) as error:
            return Result(False, message=str(error))

    def _create_bottle(
        self, name, environment, path, runner, d7vk, dxvk, vkd3d, nvapi,
        latencyflex, versioning, sandbox, fn_logger, arch,
        custom_environment, cancel_event, configuration,
    ) -> Result[dict]:
        d7vk_requested = bool(d7vk)

        def log_update(message):
            if fn_logger:
                fn_logger(message)

        cancellation_announced = False

        cleanup_config = BottleConfig()
        cleanup_config.Name = name
        cleanup_config.Environment = environment.capitalize()

        def is_cancelled() -> bool:
            return cancel_event is not None and cancel_event.is_set()

        def abort_build(message: Optional[str] = None) -> Result[dict]:
            nonlocal cancellation_announced

            if not cancellation_announced:
                log_update(
                    message
                    or _("Cancellation requested. Stopping after the current step…")
                )
                cancellation_announced = True

            return Result(False, data={"config": cleanup_config}, message="cancelled")

        def check_cancel(message: Optional[str] = None) -> Optional[Result[dict]]:
            if not is_cancelled():
                return None
            return abort_build(message)

        cancel_result = check_cancel()
        if cancel_result is not None:
            return cancel_result

        runner = runner or self.get_default_runner()
        try:
            RunnerRegistry.require(runner)
        except FileNotFoundError as error:
            message = f"{error}. {system_runner_guidance()}"
            log_update(message)
            return Result(False, message=message)

        if arch == "win32" and not WineUtils.supports_win32_prefix(
            ManagerUtils.get_runner_path(runner)
        ):
            message = _("This runner cannot create a 32-bit prefix. Select a 64-bit container.")
            log_update(message)
            return Result(False, message=message)

        if configuration is not None:
            env = {
                "Parameters": {}, "Installed_Dependencies": configuration.Installed_Dependencies,
            }
            parameters = configuration.Parameters
        elif custom_environment:
            with open(custom_environment, encoding="utf-8") as stream:
                env = yaml.load(stream)
            if not isinstance(env, dict) or not isinstance(env.get("Parameters", {}), dict):
                raise ValueError("Invalid environment recipe.")
            parameters = env.get("Parameters", {})
        else:
            if environment.lower() not in ("custom", "application", "gaming"):
                raise ValueError("Unknown bottle environment: " + environment)
            env = deepcopy(Samples.environments.get(environment.lower()))
            if env and env.get("Parameters", {}).get("sync") == "ntsync":
                info = RunnerRegistry.require(runner)
                if not is_ntsync_available(shlex.quote(info.wine_for_arch(arch))):
                    env["Parameters"]["sync"] = "fsync"
            parameters = env.get("Parameters", {}) if env else {}

        requested = {
            "d7vk": bool(d7vk_requested or parameters.get("d7vk")),
            "dxvk": bool(parameters.get("dxvk")),
            "vkd3d": bool(parameters.get("vkd3d")),
            "nvapi": bool(parameters.get("dxvk_nvapi")),
            "latencyflex": bool(parameters.get("latencyflex")),
        }
        for component, needed in requested.items():
            if needed and not getattr(self, component + "_available"):
                if not getattr(self, "check_" + component)(True):
                    return Result(False, message=f"Required component is unavailable: {component}")
        if d7vk and isinstance(d7vk, str) and d7vk not in self.d7vk_available:
            installed = self.component_manager.install("d7vk", d7vk)
            if not installed.ok:
                return installed

        cancel_result = check_cancel()
        if cancel_result is not None:
            return cancel_result

        # default components versions if not specified
        runner_name = runner

        if not dxvk:
            # if no dxvk is specified, use the first one from available
            dxvk = self.dxvk_available[0] if self.dxvk_available else ""
        dxvk_name = dxvk

        if not d7vk:
            d7vk = self.d7vk_available[0] if self.d7vk_available else ""
        d7vk_name = d7vk

        if not vkd3d:
            # if no vkd3d is specified, use the first one from available
            vkd3d = self.vkd3d_available[0] if self.vkd3d_available else ""
        vkd3d_name = vkd3d

        if not nvapi:
            # if no nvapi is specified, use the first one from available
            nvapi = self.nvapi_available[0] if self.nvapi_available else ""
        nvapi_name = nvapi

        if not latencyflex:
            # if no latencyflex is specified, use the first one from available
            latencyflex = (
                self.latencyflex_available[0] if self.latencyflex_available else ""
            )
        latencyflex_name = latencyflex

        bottle_name = name
        bottle_complete_path = path
        cleanup_config.Path = path
        cancel_result = check_cancel()
        if cancel_result is not None:
            return cancel_result

        # define registers that should be awaited
        reg_files = [
            os.path.join(bottle_complete_path, "system.reg"),
            os.path.join(bottle_complete_path, "user.reg"),
        ]
        prefix_files = reg_files + [
            os.path.join(
                bottle_complete_path,
                "drive_c",
                "windows",
                "system32",
                "kernel32.dll",
            )
        ]

        # create the bottle directory
        try:
            bottle_directory(bottle_complete_path, empty=True)
            # Pre-create drive_c directory and set the case-fold flag
            bottle_drive_c = os.path.join(bottle_complete_path, "drive_c")
            os.makedirs(bottle_drive_c)
            FileUtils.chattr_f(bottle_drive_c)
        except OSError:
            logging.error(
                f"Failed to create bottle directory: {bottle_complete_path}", jn=True
            )
            log_update(_("Failed to create container directory."))
            return Result(False)

        cancel_result = check_cancel()
        if cancel_result is not None:
            return cancel_result

        # generate bottle configuration
        logging.info("Generating bottle configuration…")
        log_update(_("Generating container configuration…"))
        config = (
            deepcopy(configuration) if configuration is not None else BottleConfig()
        )
        config.Name = bottle_name
        config.Arch = arch
        config.Runner = runner_name
        config.D7VK = d7vk_name
        config.DXVK = dxvk_name
        config.VKD3D = vkd3d_name
        config.NVAPI = nvapi_name
        config.LatencyFleX = latencyflex_name
        config.Path = bottle_complete_path
        config.Environment = environment.capitalize()
        config.Creation_Date = str(datetime.now())
        config.Update_Date = str(datetime.now())
        config.Parameters.sandbox = sandbox
        if versioning:
            config.Versioning = True
        if configuration is None:
            config.Limit_System_Environment = True
            config.Inherited_Environment_Variables = (
                Samples.default_inherited_environment.copy()
            )

        cleanup_config = config

        cancel_result = check_cancel()
        if cancel_result is not None:
            return cancel_result

        # get template
        template = (
            None
            if configuration is not None or custom_environment
            else TemplateManager.get_env_template(environment)
        )
        template_updated = False
        if template:
            log_update(_("Template found, applying…"))
            if TemplateManager.unpack_template(template, config):
                config.Installed_Dependencies = template["config"][
                    "Installed_Dependencies"
                ]
                config.Uninstallers = template["config"]["Uninstallers"]
            else:
                template = None
                try:
                    shutil.rmtree(bottle_drive_c)
                    os.makedirs(bottle_drive_c)
                    FileUtils.chattr_f(bottle_drive_c)
                except OSError:
                    logging.error(
                        f"Failed to restore bottle directory: {bottle_complete_path}",
                        jn=True,
                    )
                    log_update(_("Failed to create container directory."))
                    return Result(False)

        cancel_result = check_cancel()
        if cancel_result is not None:
            return cancel_result

        if not WineUtils.ensure_user_profile_alias(bottle_complete_path):
            logging.error("Failed to prepare the bottle user profile.")
            return Result(False, message="Failed to prepare the bottle user profile.")

        # initialize wineprefix
        reg = Reg(config)
        rk = RegKeys(config)
        wineboot = WineBoot(config)
        wineserver = WineServer(config)

        # execute wineboot on the bottle path
        log_update(_("The Wine config is being updated…"))
        initialized = wineboot.init()
        if not initialized.ok:
            message = _("Failed to initialize the Wine prefix.")
            if initialized.message:
                message = f"{message} {initialized.message}"
            logging.error(message, jn=True)
            log_update(message)
            return Result(False, data={"config": config}, message=message)
        cancel_result = check_cancel()
        if cancel_result is not None:
            return cancel_result
        if not FileUtils.wait_for_files(prefix_files, timeout=5):
            logging.error("Wine prefix initialization failed.", jn=True)
            message = _("Failed to initialize the Wine prefix.")
            log_update(message)
            return Result(False, data={"config": config}, message=message)
        log_update(_("Wine config updated!"))

        cancel_result = check_cancel()
        if cancel_result is not None:
            return cancel_result

        if not WineUtils.unlink_user_profile_links(bottle_complete_path):
            logging.error("Could not sandbox the bottle user directory.", jn=True)
            message = _("Failed to sandbox the container user directory.")
            log_update(message)
            return Result(False, data={"config": config}, message=message)

        cancel_result = check_cancel()
        if cancel_result is not None:
            return cancel_result

        # wait for registry files to be created
        FileUtils.wait_for_files(reg_files)

        cancel_result = check_cancel()
        if cancel_result is not None:
            return cancel_result

        # apply Windows version
        if not template and not custom_environment:
            cancel_result = check_cancel()
            if cancel_result is not None:
                return cancel_result

            logging.info("Setting Windows version…")
            log_update(_("Setting Windows version…"))
            try:
                rk.lg_set_windows(config.Windows)
            except ValueError as e:
                logging.warning(str(e))
            wineboot.update()

            FileUtils.wait_for_files(reg_files)

            # apply CMD settings
            logging.info("Setting CMD default settings…")
            log_update(_("Apply CMD default settings…"))
            rk.apply_cmd_settings()
            wineboot.update()

            FileUtils.wait_for_files(reg_files)

            logging.info("Enabling font smoothing…")
            log_update(_("Enabling font smoothing…"))
            rk.apply_font_smoothing()

            audio_driver = self.settings.get_string("audio-driver")
            if audio_driver not in ("", "default"):
                logging.info("Configuring audio driver…")
                log_update(_("Configuring audio driver…"))
                try:
                    rk.set_audio_driver(audio_driver)
                except ValueError as exc:
                    logging.warning(str(exc))

            wineboot.update()

            FileUtils.wait_for_files(reg_files)

            # blacklisting processes
            logging.info("Optimizing environment…")
            log_update(_("Optimizing environment…"))
            _blacklist_dll = ["winemenubuilder.exe"]
            for _dll in _blacklist_dll:
                reg.add(
                    key="HKEY_CURRENT_USER\\Software\\Wine\\DllOverrides",
                    value=_dll,
                    data="",
                )

        if configuration is not None:
            parameters = config.Parameters
            rk.toggle_virtual_desktop(
                parameters.virtual_desktop,
                parameters.virtual_desktop_res,
            )
            rk.toggle_wayland_driver(parameters.wayland)
            rk.set_renderer(parameters.renderer)
            rk.set_dpi(parameters.custom_dpi)
            if parameters.dpi_scaling != "default":
                result = rk.set_dpi_scaling(parameters.dpi_scaling)
                if not result.ok:
                    raise ValueError(result.message)
            rk.set_grab_fullscreen(parameters.fullscreen_capture)
            rk.set_take_focus(parameters.take_focus)
            rk.set_decorated(parameters.decorated)
            rk.set_mouse_warp(int(parameters.mouse_warp))
            wineboot.update()

        # apply environment configuration
        logging.info(f"Applying environment: [{environment}]…")
        log_update(_("Applying environment: {0}…").format(environment))
        cancel_result = check_cancel()
        if cancel_result is not None:
            return cancel_result
        if custom_environment:
            wineboot.kill()

        if self.settings.get_boolean("disable-home-drive"):
            Drives(config).remove_drive("Z")

        if env:
            while wineserver.is_alive():
                cancel_result = check_cancel()
                if cancel_result is not None:
                    return cancel_result
                time.sleep(1)

            for prm in config.Parameters:
                if prm in env.get("Parameters", {}):
                    config.Parameters[prm] = env["Parameters"][prm]

            cancel_result = check_cancel()
            if cancel_result is not None:
                return cancel_result

            if (not template and config.Parameters.dxvk) or (
                template and template["config"]["DXVK"] != dxvk
            ):
                cancel_result = check_cancel()
                if cancel_result is not None:
                    return cancel_result

                # perform dxvk installation if configured
                logging.info("Installing DXVK…")
                log_update(_("Installing DXVK…"))
                self.install_dll_component(config, "dxvk", version=dxvk_name)
                template_updated = True

            if (
                not template
                and config.Parameters.vkd3d
                or (template and template["config"]["VKD3D"] != vkd3d)
            ):
                cancel_result = check_cancel()
                if cancel_result is not None:
                    return cancel_result

                # perform vkd3d installation if configured
                logging.info("Installing VKD3D…")
                log_update(_("Installing VKD3D…"))
                self.install_dll_component(config, "vkd3d", version=vkd3d_name)
                template_updated = True

            if (
                not template
                and config.Parameters.dxvk_nvapi
                or (template and template["config"]["NVAPI"] != nvapi)
            ):
                if GPUUtils.is_gpu(GPUVendors.NVIDIA):
                    cancel_result = check_cancel()
                    if cancel_result is not None:
                        return cancel_result

                    # perform nvapi installation if configured
                    logging.info("Installing DXVK-NVAPI…")
                    log_update(_("Installing DXVK-NVAPI…"))
                    self.install_dll_component(config, "nvapi", version=nvapi_name)
                    template_updated = True

            for dep in env.get("Installed_Dependencies", []):
                if template and dep in template["config"]["Installed_Dependencies"]:
                    continue
                if dep in self.supported_dependencies:
                    cancel_result = check_cancel()
                    if cancel_result is not None:
                        return cancel_result

                    _dep = self.supported_dependencies[dep]
                    log_update(
                        _("Installing dependency: %s …")
                        % _dep.get("Description", "n/a")
                    )
                    res = self.dependency_manager.install(config, [dep, _dep])
                    if not res.ok:
                        logging.error(
                            _("Failed to install dependency: %s")
                            % _dep.get("Description", "n/a"),
                            jn=True,
                        )
                        log_update(
                            _("Failed to install dependency: %s")
                            % _dep.get("Description", "n/a")
                        )
                        if res.message:
                            log_update(res.message)
                        return res
                    template_updated = True

        if d7vk_requested:
            config.Parameters.d7vk = True

        template_has_d7vk = bool(
            template
            and template["config"].get("Parameters", {}).get("d7vk")
            and template["config"].get("D7VK") == d7vk_name
        )
        if config.Parameters.d7vk and not template_has_d7vk:
            cancel_result = check_cancel()
            if cancel_result is not None:
                return cancel_result

            logging.info("Installing D7VK...")
            log_update(_("Installing D7VK..."))
            result = self.install_dll_component(config, "d7vk", version=d7vk_name)
            if not result.ok:
                return result
            template_updated = True

        # save bottle config
        cancel_result = check_cancel()
        if cancel_result is not None:
            return cancel_result

        saved = config.dump(f"{bottle_complete_path}/bottle.yml")
        if not saved.ok:
            return saved

        if versioning:
            # create first state if versioning enabled
            cancel_result = check_cancel()
            if cancel_result is not None:
                return cancel_result

            logging.info("Creating versioning state 0…")
            log_update(_("Creating versioning state 0…"))
            self.versioning_manager.create_state(config=config, message="First boot")

        # set status created and UI usability
        logging.info(f"New bottle created: {bottle_name}", jn=True)
        log_update(_("Finalizing…"))

        # wait for all registry changes to be applied
        FileUtils.wait_for_files(reg_files)

        cancel_result = check_cancel()
        if cancel_result is not None:
            return cancel_result

        # perform wineboot
        wineboot.update()

        cancel_result = check_cancel()
        if cancel_result is not None:
            return cancel_result

        if self.settings.get_boolean("disable-home-drive"):
            Drives(config).remove_drive("Z")

        # caching template
        if configuration is None and not custom_environment and (not template or template_updated):
            logging.info("Caching template…")
            log_update(_("Caching template…"))
            TemplateManager.new(environment, config)

        BottleIndex().register(bottle_complete_path)
        return Result(status=True, data={"config": config})

    def get_default_runner(self) -> str:
        """The discovered system runner is first; local imports are the fallback."""
        return self.runners_available[0] if self.runners_available else ""

    # Config version key for each DLL component that supports upgrades.
    __dll_component_keys = {
        "d7vk": "D7VK",
        "dxvk": "DXVK",
        "vkd3d": "VKD3D",
        "nvapi": "NVAPI",
        "latencyflex": "LatencyFleX",
    }

    def get_component_updates(self, config: BottleConfig) -> list:
        """
        Return the components of a bottle that can be upgraded to a newer
        version available in the online catalog. Each entry is a dict with
        id, title, current, latest and (for runners) component_type. Steam
        bottles are skipped, since they manage their own runner.
        """
        updates = []

        if not self.settings.get_boolean("show-component-updates"):
            return updates

        component_meta = {
            "d7vk": {
                "title": _("D7VK"),
                "enabled": config.Parameters.d7vk,
                "current": config.D7VK,
                "supported": self.supported_d7vk,
            },
            "dxvk": {
                "title": _("DXVK"),
                "enabled": config.Parameters.dxvk,
                "current": config.DXVK,
                "supported": self.supported_dxvk,
            },
            "vkd3d": {
                "title": _("VKD3D"),
                "enabled": config.Parameters.vkd3d,
                "current": config.VKD3D,
                "supported": self.supported_vkd3d,
            },
            "nvapi": {
                "title": _("NVAPI"),
                "enabled": config.Parameters.dxvk_nvapi,
                "current": config.NVAPI,
                "supported": self.supported_nvapi,
            },
            "latencyflex": {
                "title": _("LatencyFleX"),
                "enabled": config.Parameters.latencyflex,
                "current": config.LatencyFleX,
                "supported": self.supported_latencyflex,
            },
        }

        for component, meta in component_meta.items():
            if not meta["enabled"] or not meta["current"] or not meta["supported"]:
                continue
            latest = self.__get_latest_supported(meta["supported"])
            if not latest or not self.__is_version_newer(latest, meta["current"]):
                continue
            updates.append(
                {
                    "id": component,
                    "title": meta["title"],
                    "current": meta["current"],
                    "latest": latest,
                }
            )

        winebridge_update = self.__collect_winebridge_update(config)
        if winebridge_update:
            updates.append(winebridge_update)

        return updates

    def apply_component_update(self, config: BottleConfig, update: dict) -> Result:
        """Apply a single update entry returned by get_component_updates,
        downloading the target version first if it is not installed yet."""
        component = update["id"]

        if component == "winebridge":
            return self.__update_winebridge_component(config, update["latest"])
        if component not in self.__dll_component_keys:
            return Result(False, message="Unknown component type.")
        return self.__update_dll_component(config, component, update["latest"])

    def __collect_winebridge_update(self, config: BottleConfig) -> Optional[dict]:
        if not config.Parameters.winebridge:
            return None

        latest = self.__get_latest_supported(self.supported_winebridge)
        installed = self.winebridge_available[0] if self.winebridge_available else None
        if not latest or not self.__is_version_newer(latest, installed):
            return None

        return {
            "id": "winebridge",
            "title": _("WineBridge"),
            "current": installed or _("Not installed"),
            "latest": latest,
        }

    def __filter_update_catalog(self, catalog: dict) -> dict:
        if self.settings.get_boolean("release-candidate"):
            return catalog
        return {
            name: component
            for name, component in catalog.items()
            if component.get("Channel") not in ("rc", "unstable")
        }

    def __get_latest_supported(self, supported_dict: dict) -> Optional[str]:
        supported_dict = self.__filter_update_catalog(supported_dict)
        if not supported_dict:
            return None
        keys = list(supported_dict.keys())
        try:
            return sort_by_version(keys)[0]
        except ValueError:
            return sorted(keys, reverse=True)[0]

    @staticmethod
    def __is_version_newer(latest: str, current: Optional[str]) -> bool:
        if not latest:
            return False
        if not current:
            return True
        versions = [latest, current]
        try:
            ordered = sort_by_version(versions.copy())
        except ValueError:
            ordered = sorted(versions, reverse=True)
        return ordered[0] == latest and latest != current

    def __ensure_component_available(self, component: str, version: str) -> Result:
        availability_attrs = {
            "d7vk": "d7vk_available",
            "dxvk": "dxvk_available",
            "vkd3d": "vkd3d_available",
            "nvapi": "nvapi_available",
            "latencyflex": "latencyflex_available",
        }
        available = getattr(self, availability_attrs[component], [])
        if version in available:
            return Result(True)
        return self.component_manager.install(component, version)

    def __update_dll_component(
        self, config: BottleConfig, component: str, version: str
    ) -> Result:
        ensure = self.__ensure_component_available(component, version)
        if not ensure.ok:
            return ensure

        if component == "d7vk":
            return self.set_d7vk(config, True, version)

        remove_res = self.install_dll_component(
            config=config, component=component, remove=True
        )
        if not remove_res.ok:
            return remove_res

        update_res = self.update_config(
            config=config, key=self.__dll_component_keys[component], value=version
        )
        if not update_res.ok:
            return update_res
        updated_config = update_res.data["config"]

        install_res = self.install_dll_component(
            config=updated_config, component=component, version=version
        )
        if not install_res.ok:
            return install_res

        return Result(True, data={"config": updated_config})

    def set_graphics_component(
        self,
        config: BottleConfig,
        component: str,
        enabled: bool,
        version: str | None = None,
    ) -> Result:
        if component not in ("dxvk", "vkd3d"):
            return Result(False, message=_("Invalid graphics component."))

        previous = deepcopy(config)
        candidate = deepcopy(config)
        selected = version or getattr(config, component.upper())
        if enabled and not selected:
            available = getattr(self, f"{component}_available")
            selected = available[0] if available else ""
        if enabled and not selected:
            return Result(False, message=_("No graphics component version available."))
        if enabled:
            setattr(candidate, component.upper(), selected)
        setattr(candidate.Parameters, component, enabled)
        components = [component]
        if component == "dxvk" and not enabled and previous.Parameters.vkd3d:
            candidate.Parameters.vkd3d = False
            components.insert(0, "vkd3d")
        elif component == "vkd3d" and enabled and not previous.Parameters.dxvk:
            candidate.DXVK = previous.DXVK or (
                self.dxvk_available[0] if self.dxvk_available else ""
            )
            if not candidate.DXVK:
                return Result(False, message=_("No DXVK version available."))
            candidate.Parameters.dxvk = True
            components.insert(0, "dxvk")

        changed = []

        def rollback(failure):
            restored = True
            for name in reversed(changed):
                result = self.install_dll_component(
                    previous,
                    name,
                    remove=not getattr(previous.Parameters, name),
                    version=getattr(previous, name.upper()),
                )
                restored = result.ok and restored
            if not restored:
                return Result(
                    False, message=_("Failed to restore graphics components.")
                )
            return failure

        for name in components:
            changed.append(name)
            result = self.install_dll_component(
                candidate,
                name,
                remove=not getattr(candidate.Parameters, name),
                version=getattr(candidate, name.upper()),
            )
            if not result.ok:
                return rollback(result)

        current = deepcopy(config)
        for name in components:
            setattr(current, name.upper(), getattr(candidate, name.upper()))
            setattr(current.Parameters, name, getattr(candidate.Parameters, name))
        candidate = current
        candidate.Update_Date = str(datetime.now().astimezone().replace(tzinfo=None))
        bottle_path = ManagerUtils.get_bottle_path(candidate)
        result = candidate.dump(os.path.join(bottle_path, "bottle.yml"))
        if not result.ok:
            return rollback(result)

        config.DXVK = candidate.DXVK
        config.VKD3D = candidate.VKD3D
        config.Parameters.dxvk = candidate.Parameters.dxvk
        config.Parameters.vkd3d = candidate.Parameters.vkd3d
        config.Update_Date = candidate.Update_Date
        if config.Id in self.local_bottles:
            self.local_bottles[config.Id] = config
        RegistryRuleManager.apply_rules(config, trigger="components")
        return Result(True, data={"config": config})

    def set_d7vk(
        self, config: BottleConfig, enabled: bool, version: str | None = None
    ) -> Result:
        previous = deepcopy(config)

        if not enabled:
            result = self.install_dll_component(config, "d7vk", remove=True)
            if not result.ok:
                return self.__rollback_d7vk(previous, result)
            persisted = self.__persist_d7vk_config(config, False, config.D7VK)
            if persisted.ok:
                return persisted
            return self.__rollback_d7vk(previous, persisted)

        selected = version or config.D7VK
        if not selected:
            selected = self.d7vk_available[0] if self.d7vk_available else ""
        if not selected:
            return Result(False, message=_("No D7VK version available."))

        result = self.install_dll_component(config, "d7vk", version=selected)
        if not result.ok:
            return self.__rollback_d7vk(previous, result)

        persisted = self.__persist_d7vk_config(config, True, selected)
        if persisted.ok:
            return persisted
        return self.__rollback_d7vk(previous, persisted)

    def __persist_d7vk_config(
        self, config: BottleConfig, enabled: bool, version: str
    ) -> Result:
        candidate = deepcopy(config)
        candidate.D7VK = version
        candidate.Parameters.d7vk = enabled
        candidate.Update_Date = str(datetime.now().astimezone().replace(tzinfo=None))

        bottle_path = ManagerUtils.get_bottle_path(candidate)
        saved = candidate.dump(os.path.join(bottle_path, "bottle.yml"))
        if not saved.ok:
            return Result(False, message=saved.message)

        config.D7VK = candidate.D7VK
        config.Parameters.d7vk = candidate.Parameters.d7vk
        config.Update_Date = candidate.Update_Date
        if candidate.Id in self.local_bottles:
            self.local_bottles[candidate.Id] = config
        RegistryRuleManager.apply_rules(config, trigger="components")
        return Result(True, data={"config": config})

    def __rollback_d7vk(self, previous: BottleConfig, failure: Result) -> Result:
        if not self.reconcile_d7vk(previous):
            return Result(
                False,
                message=_("Failed to save and roll back the D7VK configuration."),
            )
        return failure

    def reconcile_d7vk(self, config: BottleConfig) -> bool:
        if not config.Parameters.d7vk and not D7VKComponent.has_managed_install(config):
            return True

        component = D7VKComponent(config.D7VK or "d7vk")
        if config.Parameters.d7vk:
            if not config.D7VK or not component.checked_dlls:
                return False
            if component.is_installed(config):
                return True
            return component.install(config)

        if component.has_managed_install(config):
            return component.uninstall(config)
        return True

    def __update_winebridge_component(
        self, config: BottleConfig, version: str
    ) -> Result:
        if version in self.winebridge_available:
            return Result(True)
        return self.component_manager.install("winebridge", version)

    def delete_bottle(self, config: BottleConfig) -> bool:
        """
        Perform wineserver shutdown and delete the bottle.
        TODO: will be replaced by the BottlesManager class.
        """
        try:
            path = bottle_directory(ManagerUtils.get_bottle_path(config))
            if not any(identifier == config.Id and registered == path
                       for identifier, registered, _name in BottleIndex().records()):
                raise ValueError("Only a registered bottle can be deleted.")
            with bottle_operation(path):
                return self._delete_bottle(config, path)
        except (OSError, ValueError, RuntimeError, sqlite3.IntegrityError, yaml.YAMLError) as error:
            logging.error(str(error))
            return False

    def forget_bottle(self, config: BottleConfig) -> bool:
        path = ManagerUtils.get_bottle_path(config)
        tracker = self._playtime_trackers.pop(config.Id, None)
        if tracker:
            tracker.shutdown()
        BottleIndex().forget(config.Id)
        self.check_bottles(silent=True)
        return True

    def _delete_bottle(self, config: BottleConfig, path: str) -> bool:
        logging.info("Stopping bottle…")
        wineserver = WineServer(config)

        if config.Parameters.sandbox:
            wineserver.force_kill()
        else:
            WineBoot(config).kill(True)
            wineserver.wait()

        if not config.Path:
            logging.error("Empty path found. Disasters unavoidable.")
            return False

        logging.info("Removing applications installed with the bottle…")
        for program in config.External_Programs.values():
            ManagerUtils.remove_desktop_entry(config, program)

        logging.info("Removing library entries associated with this bottle…")
        library_manager = LibraryManager()
        entries = library_manager.get_library().copy()
        for _uuid, entry in entries.items():
            if _uuid[0] == config.Id:
                library_manager.remove_from_library(_uuid)

        tracker = self._playtime_trackers.pop(config.Id, None)
        if tracker:
            tracker.shutdown()
        shutil.rmtree(path)
        BottleIndex().forget(config.Id)

        # The UI invokes delete_bottle in a worker thread. Refresh only the
        # backend state here; its RunAsync callback rebuilds the GTK list on
        # the main loop.
        self.check_bottles(silent=True)

        logging.info(f"Deleted the bottle in: {path}")
        return True

    def repair_bottle(self, config: BottleConfig) -> bool:
        """
        This function tries to repair a broken bottle, creating a
        new bottle configuration with the latest runner. Each fixed
        bottle will use the Custom environment.
        TODO: will be replaced by the BottlesManager class.
        """
        logging.info(f"Trying to repair the bottle: [{config.Name}]…")

        wineboot = WineBoot(config)
        bottle_path = ManagerUtils.get_bottle_path(config)

        # create new config with path as name and Custom environment
        new_config = BottleConfig(Id=config.Id)
        new_config.Name = config.Name
        new_config.Runner = self.get_default_runner()
        new_config.Path = bottle_path
        new_config.Environment = "Custom"
        new_config.Creation_Date = str(datetime.now())
        new_config.Update_Date = str(datetime.now())

        saved = new_config.dump(os.path.join(bottle_path, "bottle.yml"))
        if not saved.status:
            return False

        # Execute wineboot in bottle to generate missing files
        wineboot.init()

        # Update bottles
        self.update_bottles()
        return True

    def install_dll_component(
        self,
        config: BottleConfig,
        component: str,
        remove: bool = False,
        version: str = False,
        overrides_only: bool = False,
        exclude: list = None,
    ) -> Result:
        if exclude is None:
            exclude = []

        # D7VK, DXVK, VKD3D and NVAPI require Vulkan to be present on the host.
        if not remove and component in ("d7vk", "dxvk", "vkd3d", "nvapi"):
            from bottles.backend.utils.vulkan import VulkanUtils

            if not VulkanUtils.check_support():
                logging.warning(
                    f"Skipping {component} installation: Vulkan is not available on this system."
                )
                return Result(
                    status=False,
                    message=_(
                        "{0} requires Vulkan, which is not available on this system."
                    ).format(component.upper()),
                )

        if component == "d7vk":
            _version = (
                version
                or config.D7VK
                or (self.d7vk_available[0] if self.d7vk_available else "")
            )
            if remove and not _version:
                _version = "d7vk"
            if not _version:
                return Result(status=False, message=_("No D7VK version available."))
            manager = D7VKComponent(_version)
        elif component == "dxvk":
            _version = (
                version
                or config.DXVK
                or (self.dxvk_available[0] if self.dxvk_available else "")
            )
            if not _version:
                return Result(status=False, message=_("No DXVK version available."))
            manager = DXVKComponent(_version)
        elif component == "vkd3d":
            _version = (
                version
                or config.VKD3D
                or (self.vkd3d_available[0] if self.vkd3d_available else "")
            )
            if not _version:
                return Result(status=False, message=_("No VKD3D version available."))
            manager = VKD3DComponent(_version)
        elif component == "nvapi":
            _version = (
                version
                or config.NVAPI
                or (self.nvapi_available[0] if self.nvapi_available else "")
            )
            if not _version:
                return Result(status=False, message=_("No NVAPI version available."))
            manager = NVAPIComponent(_version)
        elif component == "latencyflex":
            _version = version or config.LatencyFleX
            if not _version:
                if len(self.latencyflex_available) == 0:
                    self.check_latencyflex(install_latest=True)
                _version = (
                    self.latencyflex_available[0] if self.latencyflex_available else ""
                )
            if not _version:
                return Result(
                    status=False, message=_("No LatencyFleX version available.")
                )
            manager = LatencyFleXComponent(_version)
        else:
            return Result(
                status=False, data={"message": f"Invalid component: {component}"}
            )

        if (
            not remove
            and component in ("d7vk", "dxvk", "vkd3d")
            and not manager.checked_dlls
        ):
            return Result(
                status=False,
                message=_("The selected {0} installation is incomplete.").format(
                    component.upper()
                ),
            )

        if remove:
            success = manager.uninstall(config, exclude)
        else:
            success = manager.install(config, overrides_only, exclude)

        if not success:
            message = (
                _("Failed to remove {0}.") if remove else _("Failed to install {0}.")
            )
            return Result(
                status=False,
                message=message.format(component.upper()),
            )
        return Result(status=True)

    def shutdown(self):
        """Cleanup only truly orphaned or stuck bottles."""
        logging.info("Starting shutdown cleanup …")

        known_prefixes = {ManagerUtils.get_bottle_path(config) for config in self.local_bottles.values()}
        active_bottle_ids = []
        for tracker in self._playtime_trackers.values():
            with tracker._lock:
                active_bottle_ids.extend(session.bottle_id for session in tracker._tracked.values())
            tracker.shutdown()
        self._playtime_trackers.clear()

        protected_prefixes = set()
        for b_id in active_bottle_ids:
            if b_id in self.local_bottles:
                protected_prefixes.add(
                    ManagerUtils.get_bottle_path(self.local_bottles[b_id])
                )

        from bottles.backend.utils.proc import ProcUtils

        procs = ProcUtils.get_procs()
        prefix_to_procs = {}

        for proc in procs:
            env = proc.get_env()
            if "WINEPREFIX=" in env:
                for var in env.split("\x00"):
                    if var.startswith("WINEPREFIX="):
                        prefix = var.split("=", 1)[1]
                        if prefix not in known_prefixes:
                            continue
                        if prefix not in prefix_to_procs:
                            prefix_to_procs[prefix] = []
                        prefix_to_procs[prefix].append(proc)

        for prefix, p_list in prefix_to_procs.items():
            if prefix in protected_prefixes:
                continue

            for p in p_list:
                name = p.get_name().lower()
                state = p.get_state()

                if name != "wineserver" and state != "Z":
                    logging.info(
                        f"Prefix {prefix} is active (e.g. {name}), protecting."
                    )
                    protected_prefixes.add(prefix)
                    break

        for prefix, p_list in prefix_to_procs.items():
            if prefix in protected_prefixes:
                continue

            logging.info(f"Cleaning up orphaned/stuck bottle at {prefix} …")
            for proc in p_list:
                proc.kill(9)
