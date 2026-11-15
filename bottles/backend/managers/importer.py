# importer.py
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
import sqlite3
import shutil
from datetime import datetime
from glob import glob

from bottles.backend.globals import TrdyPaths
from bottles.backend.logger import Logger
from bottles.backend.models.config import BottleConfig
from bottles.backend.models.result import Result
from bottles.backend.managers.storage import BottleIndex, bottle_directory, bottle_operation, copy_bottle_contents

logging = Logger()


class ImportManager:
    def __init__(self, manager):
        self.manager = manager

    @staticmethod
    def search_wineprefixes(selected_paths=None) -> Result:
        """Look and return all 3rd party available wine prefixes"""
        importer_wineprefixes = []

        # search wine prefixes in external managers paths
        results = [(path, "Legacy Wine") for path in glob(TrdyPaths.wine)]
        results += [(path, "Lutris") for path in glob(f"{TrdyPaths.lutris}/*/")]
        results += [
            (path, "PlayOnLinux") for path in glob(f"{TrdyPaths.playonlinux}/*/")
        ]

        for selected_path in selected_paths or []:
            selected_path = os.path.normpath(selected_path)
            if os.path.isdir(os.path.join(selected_path, "drive_c")):
                results.append((selected_path, "Manual"))
            else:
                try:
                    with os.scandir(selected_path) as entries:
                        results += [
                            (entry.path, "Manual")
                            for entry in entries
                            if entry.is_dir()
                        ]
                except OSError:
                    pass

        seen = set()
        for wineprefix, wineprefix_manager in results:
            wineprefix = os.path.normpath(wineprefix)
            if wineprefix in seen:
                continue
            seen.add(wineprefix)
            wineprefix_name = os.path.basename(wineprefix)

            # check the drive_c path exists
            if os.path.isdir(os.path.join(wineprefix, "drive_c")):
                wineprefix_lock = os.path.isfile(
                    os.path.join(wineprefix, "bottle.lock")
                )
                importer_wineprefixes.append(
                    {
                        "Name": wineprefix_name,
                        "Manager": wineprefix_manager,
                        "Path": wineprefix,
                        "Lock": wineprefix_lock,
                    }
                )

        logging.info(f"Found {len(importer_wineprefixes)} wine prefixes…")

        return Result(status=True, data={"wineprefixes": importer_wineprefixes})

    def import_bottle(self, path: str) -> Result:
        """Register a current-format bottle in place without running Wine."""
        try:
            path = bottle_directory(path)
            with bottle_operation(path):
                config = BottleIndex().register(path)
            self.manager.update_bottles(silent=True)
            return Result(True, data={"config": config})
        except (OSError, ValueError, RuntimeError, sqlite3.IntegrityError) as error:
            return Result(False, message=str(error))

    def import_wineprefix(self, wineprefix: dict, destination: str) -> Result:
        """Copy a foreign prefix to an explicitly selected empty directory."""
        try:
            source = wineprefix["Path"]
            if os.path.isfile(os.path.join(source, "bottle.yml")):
                raise ValueError("This is an existing Bottles bottle; import it in place.")
            if not os.path.isdir(os.path.join(source, "drive_c")):
                raise ValueError("The source is not a Wine prefix.")
            destination = bottle_directory(destination, empty=True)
            with bottle_operation(destination):
                bottle_directory(destination, empty=True)
                os.chmod(destination, 0o700)
                copy_bottle_contents(wineprefix["Path"], destination)
                new_config = BottleConfig(
                    Name=wineprefix["Name"], Path=destination,
                    Runner=self.manager.get_default_runner(), Environment="Custom",
                    Creation_Date=str(datetime.now()), Update_Date=str(datetime.now()),
                )
                saved = new_config.dump(os.path.join(destination, "bottle.yml"))
                if not saved.ok:
                    return saved
                BottleIndex().register(destination)
            self.manager.update_bottles(silent=True)
            return Result(True)
        except (OSError, ValueError, RuntimeError, sqlite3.IntegrityError, shutil.Error) as error:
            return Result(False, message=str(error))
