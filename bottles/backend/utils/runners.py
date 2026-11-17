"""Local runner discovery. Package managers own system runners; users own imports."""

import os
import shutil
import subprocess
from dataclasses import dataclass, replace
from pathlib import Path

from bottles.backend.logger import Logger

SYSTEM_WINE = "system-wine"
SYSTEM_RUNNER_PREFIX = "system:"
logging = Logger()


@dataclass(frozen=True)
class RunnerInfo:
    identifier: str
    source: str
    name: str
    root: str
    wine: str
    wineserver: str
    version: str = ""

    def wine_for_arch(self, arch: str) -> str:
        wine64 = f"{self.wine}64"
        if arch == "win64" and os.path.isfile(wine64) and os.access(wine64, os.X_OK):
            return wine64
        return self.wine


class RunnerRegistry:
    entries: dict[str, RunnerInfo] = {}

    @classmethod
    def name(cls, identifier: str) -> str:
        info = cls.entries.get(identifier)
        return info.name if info else identifier

    @staticmethod
    def inspect(identifier: str, root: str, source: str = "user", *, name: str | None = None) -> RunnerInfo:
        root = os.path.abspath(root)
        if os.path.isfile(os.path.join(root, "proton")) or os.path.isfile(os.path.join(root, "toolmanifest.vdf")):
            raise ValueError("Proton compatibility tools are not supported; select a Wine runner.")
        wine = os.path.join(root, "bin", "wine")
        server = os.path.join(root, "bin", "wineserver")
        for executable in (wine, server):
            if not os.path.isfile(executable) or not os.access(executable, os.X_OK):
                raise ValueError(f"Missing executable: {executable}")
        return RunnerInfo(
            identifier, source, name or os.path.basename(root), root, wine, server
        )

    @staticmethod
    def system() -> RunnerInfo | None:
        # A PATH Wine is another system runner in the current environment.
        # Resolve its matching server rather than searching PATH separately.
        wine = shutil.which("wine")
        if not wine:
            return None
        wine = os.path.abspath(wine)
        server = os.path.join(os.path.dirname(wine), "wineserver")
        if not os.path.isfile(server) or not os.access(server, os.X_OK):
            return None
        try:
            result = subprocess.run(
                [wine, "--version"], capture_output=True, text=True, timeout=5
            )
        except (OSError, subprocess.TimeoutExpired):
            return None
        if result.returncode or not result.stdout.strip():
            return None
        return RunnerInfo(
            SYSTEM_WINE, "system", "Wine", os.path.dirname(os.path.dirname(wine)),
            wine, server, result.stdout.strip(),
        )

    @classmethod
    def packaged(cls, directories: tuple[str, ...]) -> dict[str, RunnerInfo]:
        """Discover mounted extensions/native packages without a catalog or PATH."""
        entries = {}
        for directory in directories:
            try:
                roots = sorted(Path(directory).iterdir())
            except OSError:
                continue
            for root in roots:
                if not root.is_dir():
                    continue
                identifier = SYSTEM_RUNNER_PREFIX + root.name
                if identifier in entries:
                    continue
                try:
                    info = cls.inspect(identifier, str(root), "system")
                    result = subprocess.run(
                        [info.wine, "--version"], capture_output=True,
                        text=True, timeout=5,
                    )
                    if result.returncode or not result.stdout.strip():
                        continue
                    entries[identifier] = replace(info, version=result.stdout.strip())
                except (OSError, ValueError, subprocess.TimeoutExpired) as error:
                    logging.warning(f"Ignoring unavailable system runner {root}: {error}")
        return entries

    @classmethod
    def require(cls, identifier: str) -> RunnerInfo:
        info = cls.entries.get(identifier)
        if info is None:
            raise FileNotFoundError(f"Runner is unavailable: {identifier}")
        for executable in (info.wine, info.wineserver):
            if not os.path.isfile(executable) or not os.access(executable, os.X_OK):
                raise FileNotFoundError(f"Runner executable is unavailable: {executable}")
        return info


def system_runner_guidance() -> str:
    from gettext import gettext as _

    return _(
        "Install a system runner using your package manager, "
        "or add a local user runner in Preferences, then check again."
    )
