"""Explicit, private bottle directories and the current user's path index."""

import fcntl
import os
import shutil
import sqlite3
import stat
from contextlib import closing, contextmanager

from bottles.backend.globals import Paths
from bottles.backend.models.config import BottleConfig


def bottle_directory(path: str, *, empty: bool = False) -> str:
    if not path or not os.path.isabs(path):
        raise ValueError("Select an absolute bottle directory.")
    path = os.path.realpath(path)
    info = os.stat(path)
    if not stat.S_ISDIR(info.st_mode):
        raise ValueError("The bottle path must be a directory.")
    if info.st_uid != os.getuid():
        raise PermissionError("The bottle directory must belong to the current user.")
    if not os.access(path, os.R_OK | os.W_OK | os.X_OK):
        raise PermissionError("The bottle directory must be readable and writable.")
    if empty:
        with os.scandir(path) as entries:
            if next(entries, None) is not None:
                raise ValueError("Select an empty directory for the new bottle.")
    elif stat.S_IMODE(info.st_mode) & 0o077:
        raise PermissionError("The bottle directory must be private (mode 0700).")
    return path


@contextmanager
def bottle_operation(path: str):
    """Serialize Bottles operations without leaving lock files in an empty target."""
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise RuntimeError("Another Bottles operation is using this directory.") from error
        yield
    finally:
        os.close(fd)


def copy_bottle_contents(source: str, destination: str, *, exclude=()):
    """Copy contents without importing the source root's permissions."""
    source = os.path.realpath(source)
    if os.path.commonpath((source, destination)) == source:
        raise ValueError("The destination must be outside the source bottle.")
    for entry in os.scandir(source):
        if entry.name in exclude:
            continue
        target = os.path.join(destination, entry.name)
        if entry.is_dir(follow_symlinks=False):
            shutil.copytree(entry.path, target, symlinks=True)
        else:
            shutil.copy2(entry.path, target, follow_symlinks=False)


class BottleIndex:
    """Only locations and display names live here; bottle contents stay in place."""

    @contextmanager
    def _database(self, *, write=False):
        path = Paths.bottle_index
        if not write and not os.path.exists(path):
            yield None
            return
        if write:
            os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
            fd = os.open(path, os.O_CREAT | os.O_WRONLY, 0o600)
            os.close(fd)
        with closing(sqlite3.connect(path)) as db, db:
            if write:
                db.execute("CREATE TABLE IF NOT EXISTS bottles (id TEXT PRIMARY KEY NOT NULL, path TEXT UNIQUE NOT NULL, name TEXT UNIQUE NOT NULL)")
            yield db

    def records(self) -> list[tuple[str, str, str]]:
        """Return registered (UUID, path, display name), including unavailable bottles."""
        with self._database() as db:
            return list(db.execute("SELECT id, path, name FROM bottles ORDER BY name")) if db else []

    def entries(self) -> dict[str, str]:
        return {path: name for _identifier, path, name in self.records()}

    def register(self, path: str) -> BottleConfig:
        path = bottle_directory(path)
        loaded = BottleConfig.load(os.path.join(path, "bottle.yml"))
        if not loaded.ok:
            raise ValueError(loaded.message)
        config = loaded.data
        if not isinstance(config.Name, str) or not config.Name.strip():
            raise ValueError("The bottle configuration must contain a name.")
        if not os.path.isdir(os.path.join(path, "drive_c")):
            raise ValueError("The directory does not contain a Wine prefix.")
        with self._database(write=True) as db:
            db.execute("INSERT INTO bottles(path, name, id) VALUES (?, ?, ?)", (path, config.Name, config.Id))
        return config

    def forget(self, identifier: str):
        with self._database(write=True) as db:
            db.execute("DELETE FROM bottles WHERE id=?", (identifier,))

    def rename(self, identifier: str, name: str):
        with self._database(write=True) as db:
            db.execute("UPDATE bottles SET name=? WHERE id=?", (name, identifier))
