# library.py
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

import filecmp
from copy import deepcopy
import os
import shutil
import uuid
import tempfile
from pathlib import Path

import gi

from bottles.backend.logger import Logger
from bottles.backend.managers.steamgriddb import SteamGridDBManager
from bottles.backend.models.config import BottleConfig
from bottles.backend.managers.storage import BottleIndex, bottle_directory
from bottles.backend.utils import yaml
from bottles.backend.utils.manager import ManagerUtils

gi.require_version("GdkPixbuf", "2.0")
# ruff: noqa: E402
from gi.repository import GdkPixbuf

logging = Logger()

LibraryKey = tuple[str, str]

LOCAL_COVER_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp")


class LibraryManager:
    """
    The LibraryManager class is used to store and retrieve data
    from each registered bottle's library.yml file.
    """

    __library: dict[LibraryKey, dict]

    def __init__(self):
        self.load_library(silent=True)

    def load_library(self, silent=False):
        """
        Loads data from the library.yml file.
        """
        self.__library = {}
        self._bottle_libraries = {}
        self._stored = {}
        for bottle_id, path, name in BottleIndex().records():
            try:
                bottle_directory(path)
            except OSError:
                continue
            file = os.path.join(path, "library.yml")
            entries = {}
            if os.path.isfile(file):
                with open(file) as stream:
                    entries = yaml.load(stream)
                if not isinstance(entries, dict):
                    raise ValueError("Invalid library: " + file)
            self._stored[file] = deepcopy(entries)
            self._bottle_libraries[bottle_id] = file
            self.__library.update({
                (bottle_id, key): dict(value, bottle={"id": bottle_id, "name": name, "path": path})
                for key, value in entries.items()
            })

    def add_to_library(self, data: dict, config: BottleConfig):
        """
        Adds a new entry to the library.yml file.
        """
        path = ManagerUtils.get_bottle_path(config)
        data = dict(data, bottle={"id": config.Id, "name": config.Name, "path": path})
        if self.__already_in_library(data):
            logging.warning(f"Entry already in library, nothing to add: {data}")
            return

        key = (config.Id, str(uuid.uuid4()))
        logging.info(f"Adding new entry to library: {key}")

        if not data.get("thumbnail"):
            for cover in self.__get_local_covers(data, config):
                data["thumbnail"] = self.import_thumbnail(cover, config)
                if data["thumbnail"]:
                    break

        if not data.get("thumbnail"):
            try:
                data["thumbnail"] = SteamGridDBManager.get_game_grid(
                    data["name"], config
                )
            except Exception as e:
                logging.warning(f"Could not fetch thumbnail: {e}")

        self._bottle_libraries[config.Id] = os.path.join(path, "library.yml")
        self.__library[key] = data
        self.save_library()
        return key

    @staticmethod
    def __get_local_covers(data: dict, config: BottleConfig):
        program = config.External_Programs.get(data["id"], {})
        program_path = program.get("path")

        if program_path:
            executable = program_path.replace("\\", "/").rsplit("/", 1)[-1]
            folder = Path(ManagerUtils.get_exe_parent_dir(config, program_path))
            try:
                candidates = sorted(folder.iterdir(), key=lambda path: path.name)
            except OSError:
                candidates = []
            for extension in LOCAL_COVER_EXTENSIONS:
                for candidate in candidates:
                    if candidate.suffix.casefold() != extension:
                        continue
                    if candidate.name[: -len(candidate.suffix)] != executable:
                        continue
                    yield candidate

        yield os.path.join(ManagerUtils.get_bottle_path(config), "library.png")

    @staticmethod
    def import_thumbnail(source_path, config: BottleConfig):
        source_path = os.fspath(source_path)
        if not os.path.isfile(source_path):
            return None

        image_format, width, height = GdkPixbuf.Pixbuf.get_file_info(source_path)
        if image_format is None or width <= 0 or height <= 0:
            logging.warning(f"Invalid library thumbnail: {source_path}")
            return None

        extension = os.path.splitext(source_path)[1].lower()
        grids_path = os.path.join(ManagerUtils.get_bottle_path(config), "grids")
        filename = f"{uuid.uuid4()}{extension}"
        destination = os.path.join(grids_path, filename)

        try:
            os.makedirs(grids_path, exist_ok=True)
            for name in os.listdir(grids_path):
                candidate = os.path.join(grids_path, name)
                if os.path.isfile(candidate) and filecmp.cmp(source_path, candidate, shallow=False):
                    return f"grid:{name}"
            shutil.copy2(source_path, destination)
        except OSError as error:
            logging.warning(f"Could not import library thumbnail: {error}")
            return None

        return f"grid:{filename}"

    def set_thumbnail(self, key: LibraryKey, source_path, config: BottleConfig):
        if config is not None and key[0] != config.Id:
            raise ValueError("Library entry belongs to a different bottle.")
        entry = self.__library.get(key)
        if entry is None:
            logging.warning(f"Entry not found in library, can't set thumbnail: {key}")
            return False

        thumbnail = self.import_thumbnail(source_path, config)
        if thumbnail is None:
            return False

        old_thumbnail = entry.get("thumbnail")
        entry["thumbnail"] = thumbnail
        self.save_library()

        thumbnail_is_shared = any(
            other_key != key and other_key[0] == key[0] and item.get("thumbnail") == old_thumbnail
            for other_key, item in self.__library.items()
        )
        if (
            old_thumbnail
            and old_thumbnail != thumbnail
            and old_thumbnail.startswith("grid:")
            and not thumbnail_is_shared
        ):
            old_filename = old_thumbnail.removeprefix("grid:")
            if os.path.basename(old_filename) == old_filename:
                old_path = os.path.join(
                    ManagerUtils.get_bottle_path(config), "grids", old_filename
                )
                try:
                    os.remove(old_path)
                except FileNotFoundError:
                    pass

        return True

    def download_thumbnail(self, key: LibraryKey, config: BottleConfig):
        if config is not None and key[0] != config.Id:
            raise ValueError("Library entry belongs to a different bottle.")
        if not self.__library.get(key):
            logging.warning(
                f"Entry not found in library, can't download thumbnail: {key}"
            )
            return False

        data = self.__library.get(key)
        value = SteamGridDBManager.get_game_grid(data["name"], config)

        if not value:
            return False

        self.__library[key]["thumbnail"] = value
        self.save_library()
        return True

    def __already_in_library(self, data: dict):
        """
        Checks if the entry UUID is already in the library.yml file.
        """
        for k, v in self.__library.items():
            if (v["id"], v["bottle"]["id"]) == (data["id"], data["bottle"]["id"]):
                return True

        return False

    def remove_from_library(self, key: LibraryKey, config: BottleConfig = None):
        """Remove an entry and its unshared managed cover, when its bottle is known."""
        if config is not None and key[0] != config.Id:
            raise ValueError("Library entry belongs to a different bottle.")
        entry = self.__library.get(key)
        if entry:
            thumbnail = entry.get("thumbnail")
            shared = any(
                other_key != key and other_key[0] == key[0] and item.get("thumbnail") == thumbnail
                for other_key, item in self.__library.items()
            )
            del self.__library[key]
            self.save_library()
            if config is not None and thumbnail and not shared and thumbnail.startswith("grid:"):
                filename = thumbnail.removeprefix("grid:")
                if filename and os.path.basename(filename) == filename:
                    try:
                        os.remove(os.path.join(ManagerUtils.get_bottle_path(config), "grids", filename))
                    except FileNotFoundError:
                        pass
            return
        logging.warning(f"Entry not found in library, nothing to remove: {key}")

    def save_library(self, silent=False):
        """
        Saves the library.yml file.
        """
        files = {file: {} for file in self._bottle_libraries.values()}
        for key, entry in self.__library.items():
            entry = dict(entry)
            file = self._bottle_libraries[key[0]]
            entry.pop("bottle")
            files[file][key[1]] = entry
        for file, entries in files.items():
            if entries == self._stored.get(file, {}):
                continue
            bottle_directory(os.path.dirname(file))
            fd, temporary = tempfile.mkstemp(dir=os.path.dirname(file), prefix=".library-")
            try:
                with os.fdopen(fd, "w") as stream:
                    yaml.dump(entries, stream)
                os.replace(temporary, file)
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)
            self._stored[file] = deepcopy(entries)

    def get_library(self) -> dict[LibraryKey, dict]:
        """
        Returns the library.yml file.
        """
        return self.__library
