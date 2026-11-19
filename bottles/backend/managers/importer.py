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

import sqlite3

from bottles.backend.models.result import Result
from bottles.backend.managers.storage import BottleIndex, bottle_directory, bottle_operation


class ImportManager:
    def __init__(self, manager):
        self.manager = manager

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
