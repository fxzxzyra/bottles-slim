# runner.py
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

from typing import TYPE_CHECKING

from bottles.backend.logger import Logger
from bottles.backend.models.config import BottleConfig
from bottles.backend.models.result import Result
from bottles.backend.utils.manager import ManagerUtils
from bottles.backend.utils.runners import RunnerRegistry
from bottles.backend.utils.wine import WineUtils
from bottles.backend.wine.wineboot import WineBoot

if TYPE_CHECKING:
    from bottles.backend.managers.manager import Manager

logging = Logger()


class Runner:
    """
    This class handle everything related to the runner (Wine).
    It should not contain any manager logic (e.g. catalogs, checks, etc.) or
    any bottle related stuff (e.g. config handling, etc.), also DXVK, VKD3D,
    NVAPI handling should not performed from here.
    """

    @staticmethod
    def runner_update(
        config: BottleConfig, manager: "Manager", runner: str
    ) -> Result[dict]:
        """
        This method should be executed after changing the runner
        for a bottle. It does a prefix update and re-initialize the
        active DLLComponents (dxvk, dxvk-nvapi, vkd3d…) to re-create
        the overrides and fix broken registry keys.
        """
        logging.info(f"Doing runner update for bottle: {config.Name}")
        wineboot = WineBoot(config)

        try:
            RunnerRegistry.require(runner)
        except FileNotFoundError as error:
            return Result(False, data={"config": config}, message=str(error))

        # kill wineserver after update
        wineboot.kill(force_if_stalled=True)

        bottle_path = ManagerUtils.get_bottle_path(config)
        existing_profiles = WineUtils.get_user_profile_ids(bottle_path)
        if existing_profiles is None:
            logging.error("Could not inspect the bottle user profiles.")
            return Result(status=False, data={"config": config})

        # update bottle config
        up_config = manager.update_config(
            config=config, key="Runner", value=runner
        ).data["config"]

        # perform a prefix update
        wineboot.update()
        if not WineUtils.unlink_user_profile_links(bottle_path, existing_profiles):
            logging.error("Could not unlink the new bottle user profile.")
            return Result(status=False, data={"config": up_config})

        # Registry overrides refer to the installed DLLs, never the download cache.
        for component, enabled in (
            ("d7vk", config.Parameters.d7vk),
            ("dxvk", config.Parameters.dxvk),
            ("nvapi", config.Parameters.dxvk_nvapi),
            ("vkd3d", config.Parameters.vkd3d),
            ("latencyflex", config.Parameters.latencyflex),
        ):
            if enabled:
                result = manager.install_dll_component(config, component, overrides_only=True)
                if not result.ok:
                    return result

        return Result(status=True, data={"config": up_config})
