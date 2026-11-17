import os
import subprocess
import time

from bottles.backend.logger import Logger
from bottles.backend.utils.manager import ManagerUtils
from bottles.backend.utils.proc import ProcUtils
from bottles.backend.utils.runners import RunnerRegistry
from bottles.backend.wine.wineprogram import WineProgram

logging = Logger()


class WineServer(WineProgram):
    program = "Wine Server"
    command = "wineserver"

    def _server(self) -> str:
        return RunnerRegistry.require(self.config.Runner).wineserver

    def _server_environment(self) -> dict:
        env = os.environ.copy()
        env["WINEPREFIX"] = ManagerUtils.get_bottle_path(self.config)
        return env

    def is_alive(self):
        if not self.config.Runner:
            return False
        bottle = ManagerUtils.get_bottle_path(self.config)
        if not os.path.isdir(bottle):
            return False
        try:
            server = self._server()
            res = subprocess.Popen(
                [server, "-w"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                cwd=bottle, env=self._server_environment(),
            )
        except OSError:
            return False
        time.sleep(0.5)
        alive = res.poll() is None
        if alive:
            res.kill()
        res.wait()
        return alive

    def wait(self):
        bottle = ManagerUtils.get_bottle_path(self.config)
        if not os.path.isdir(bottle):
            return
        try:
            subprocess.Popen(
                [self._server(), "-w"], cwd=bottle, env=self._server_environment(),
            ).wait()
        except OSError as error:
            logging.warning(f"Cannot wait for the bottle's wineserver: {error}")

    def kill(self, signal: int = -1):
        args = "-k"
        if signal != -1:
            args += str(signal)

        try:
            subprocess.run(
                [self._server(), args], env=self._server_environment(), check=False,
            )
        except OSError as error:
            logging.warning(f"Cannot signal the bottle's wineserver: {error}")

    def force_kill(self):
        bottle = ManagerUtils.get_bottle_path(self.config)

        # Under a dedicated sandbox the processes are not visible on the host,
        # so kill the tracked sandbox launchers (their process groups) instead.
        if self.config.Parameters.sandbox:
            from bottles.backend.managers.sandbox import SandboxManager

            SandboxManager.terminate_prefix(bottle)
            return

        procs = ProcUtils.get_by_env(f"WINEPREFIX={bottle}")
        for proc in procs:
            proc.kill(9)

        self.kill(9)
