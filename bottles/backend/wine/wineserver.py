import os
import subprocess

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
        try:
            res.wait(timeout=0.5)
        except subprocess.TimeoutExpired:
            res.kill()
            res.wait()
            return True
        return False

    def _run(self, args):
        return subprocess.Popen(
            [self._server(), *args], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            cwd=ManagerUtils.get_bottle_path(self.config), env=self._server_environment(),
        )

    def _wait(self, args, timeout=None):
        process = self._run(args)
        try:
            return process.wait() if timeout is None else process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
            raise

    def wait(self, timeout=None):
        return self._wait(["-w"], timeout)

    def kill(self, signal: int = -1, timeout=None):
        args = "-k" if signal == -1 else f"-k{signal}"
        self.returncode = self._wait([args], timeout)

    def stop(self, timeout=30):
        if self.config.Parameters.sandbox:
            from bottles.backend.managers.sandbox import SandboxManager
            SandboxManager.terminate_prefix(ManagerUtils.get_bottle_path(self.config), timeout=timeout)
            return True
        self.kill(timeout=timeout)
        return self.returncode == 0 and self.wait(timeout=timeout) == 0

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
