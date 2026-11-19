import contextlib
import dataclasses
import os
import shlex
import uuid
from typing import List, Optional

from bottles.backend.logger import Logger
from bottles.backend.models.result import Result
from bottles.backend.utils.manager import ManagerUtils
from bottles.backend.wine.winedbg import WineDbg
from bottles.backend.wine.wineprogram import WineProgram

logging = Logger()


@dataclasses.dataclass
class RegItem:
    key: str
    value: str
    value_type: str
    data: str


class Reg(WineProgram):
    program = "Wine Registry CLI"
    command = "reg"

    def bulk_add(self, regs: List[RegItem]) -> Result:
        """Use the same Unicode serializer and per-bottle temporary file as bundles."""
        bundle = {}
        for item in regs:
            value = {"value": item.value, "data": item.data}
            if item.value_type:
                value["key_type"] = item.value_type
            bundle.setdefault(item.key, []).append(value)
        return self.import_bundle(bundle)

    def add(self, key: str, value: str, data: str, value_type: Optional[str] = None):
        config = self.config
        logging.info(
            f"Adding Key: [{key}] with Value: [{value}] and "
            f"Data: [{data}] in {config.Name} registry"
        )
        winedbg = WineDbg(config)
        args = "add '%s' /v '%s' /d '%s' /f" % (key, value, data)

        if value_type is not None:
            args = "add '%s' /v '%s' /t %s /d '%s' /f" % (key, value, value_type, data)

        # avoid conflicts when executing async
        winedbg.wait_for_process("reg.exe")

        res = self.launch(args, communicate=True, minimal=True, action_name="add")
        logging.info(res.data)
        return res

    def remove(self, key: str, value: str):
        """Remove a key from the registry"""
        config = self.config
        logging.info(
            f"Removing Value: [{key}] from Key: [{value}] in " f"{config.Name} registry"
        )
        winedbg = WineDbg(config)
        args = "delete '%s' /v %s /f" % (key, value)

        # avoid conflicts when executing async
        winedbg.wait_for_process("reg.exe")

        res = self.launch(args, communicate=True, minimal=True, action_name="remove")
        logging.info(res.data)
        return res

    def import_bundle(self, bundle: dict) -> Result:
        """Import a bundle of keys into the registry"""
        config = self.config
        logging.info(f"Importing bundle to {config.Name} registry")
        winedbg = WineDbg(config)
        reg_file = ManagerUtils.get_temp_path(f"{uuid.uuid4()}.reg", config)

        try:
            # prepare reg file
            fd = os.open(reg_file, os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w", encoding="utf-16") as f:
                f.write("Windows Registry Editor Version 5.00\n\n")

                for key in bundle:
                    f.write(f"[{key}]\n")

                    for value in bundle[key]:
                        if value["data"] == "-":
                            f.write(f'"{value["value"]}"=-\n')
                        elif "key_type" in value:
                            f.write(
                                f'"{value["value"]}"={value["key_type"]}:{value["data"]}\n'
                            )
                        else:
                            f.write(f'"{value["value"]}"="{value["data"]}"\n')

                    f.write("\n")

            args = "import " + shlex.quote(reg_file)

            # avoid conflicts when executing async
            winedbg.wait_for_process("reg.exe")

            res = self.launch(
                args, communicate=True, minimal=True, action_name="import_bundle"
            )
            logging.info(f"Import bundle result: '{res.data}'")
            return res
        except OSError as error:
            logging.warning(f"Failed to import registry bundle: {error}")
            return Result(False, message=str(error))
        finally:
            with contextlib.suppress(FileNotFoundError):
                os.remove(reg_file)
