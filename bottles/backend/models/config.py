import contextlib
import logging
import os
import tempfile
import uuid
from dataclasses import asdict, dataclass, field, replace
from io import IOBase
from typing import IO, Container, Dict, ItemsView, List, Optional

from bottles.backend.models.result import Result
from bottles.backend.utils import yaml

# class name prefix "Bottle" is a workaround for:
# https://github.com/python/cpython/issues/90104


# noinspection PyDataclass
class DictCompatMixIn:
    @staticmethod
    def yaml_serialize_handler(dumper, data):
        dict_repr = data.to_dict()
        return dumper.represent_dict(dict_repr)

    @staticmethod
    def json_serialize_handler(data):
        return data.to_dict()

    def keys(self):
        return self.__dict__.keys()

    def get(self, key, __default=None):
        return getattr(self, key, __default)

    def copy(self):
        return replace(self)

    def to_dict(self) -> dict:
        return asdict(self)

    def items(self) -> ItemsView[str, Container]:
        return self.to_dict().items()

    def __iter__(self):
        """handle `for x in obj` syntax"""
        return iter(self.__dict__)

    def __getitem__(self, item):
        """handle `obj[x]` syntax"""
        return getattr(self, item)

    def __delitem__(self, key):
        """handle `del obj[x]` syntax"""
        return delattr(self, key)

    def __setitem__(self, key, value):
        """handle `obj[x] = y` syntax"""
        return setattr(self, key, value)


@dataclass
class BottleSandboxParams(DictCompatMixIn):
    share_net: bool = False
    share_sound: bool = False
    share_input: bool = False
    share_usb: bool = False
    # share_host_ro: bool = True  # TODO: implement, requires the Bottles runtime (next) for a minimal sandbox
    # share_gpu: bool = True  # TODO: implement
    # share_paths_ro: List[str] = field(default_factory=lambda: [])  # TODO: implement
    # share_paths_rw: List[str] = field(default_factory=lambda: [])  # TODO: implement


@dataclass
class BottleParams(DictCompatMixIn):
    d7vk: bool = False
    dxvk: bool = False
    dxvk_nvapi: bool = False
    vkd3d: bool = False
    latencyflex: bool = False
    mangohud: bool = False
    mangohud_display_on_game_start: bool = True
    obsvkc: bool = False
    vkbasalt: bool = False
    lsfg_vk: bool = False
    lsfg_vk_multiplier: int = 2
    lsfg_vk_flow_scale: float = 1.0
    lsfg_vk_performance_mode: bool = False
    gamemode: bool = False
    gamescope: bool = False
    gamescope_game_width: int = 0
    gamescope_game_height: int = 0
    gamescope_window_width: int = 0
    gamescope_window_height: int = 0
    gamescope_fps: int = 0
    gamescope_fps_no_focus: int = 0
    gamescope_scaling: bool = False
    gamescope_borderless: bool = False
    gamescope_fullscreen: bool = True
    gamescope_custom_options: str = ""
    sync: str = "wine"
    frame_rate_limit: int = 0
    hidraw_devices: list[str] = field(default_factory=list)
    fsr: bool = False
    fsr_sharpening_strength: int = 8
    custom_dpi: int = 96
    dpi_scaling: str = "default"
    renderer: str = "gl"
    discrete_gpu: bool = False
    virtual_desktop: bool = False
    virtual_desktop_res: str = "1280x720"
    wayland: bool = False
    hdr: bool = False
    pulseaudio_latency: bool = False
    fullscreen_capture: bool = False
    take_focus: bool = False
    mouse_warp: bool = True
    decorated: bool = True
    fixme_logs: bool = False
    use_runtime: bool = False
    use_eac_runtime: bool = True
    use_be_runtime: bool = True
    use_steam_runtime: bool = False
    winebridge: bool = False
    sandbox: bool = False
    versioning_compression: bool = False
    versioning_automatic: bool = False
    versioning_exclusion_patterns: bool = False
    vmtouch: bool = False
    vmtouch_cache_cwd: bool = False


@dataclass
class BottleConfig(DictCompatMixIn):
    Id: str = field(default_factory=lambda: uuid.uuid4().hex)
    Name: str = ""
    Notes: str = ""
    Arch: str = "win64"  # Enum, Use bottles.backend.models.enum.Arch
    Windows: str = "win10"
    Runner: str = ""  # stable local runner identifier
    WorkingDir: str = ""
    D7VK: str = ""
    DXVK: str = ""
    NVAPI: str = ""
    VKD3D: str = ""
    LatencyFleX: str = ""
    Path: str = ""
    Environment: str = ""
    Creation_Date: str = ""
    Update_Date: str = ""
    Versioning: bool = False
    Versioning_Exclusion_Patterns: list = field(default_factory=list)
    State: int = 0
    Parameters: BottleParams = field(default_factory=BottleParams)
    Sandbox: BottleSandboxParams = field(default_factory=BottleSandboxParams)
    Limit_System_Environment: bool = False
    Environment_Variables: dict = field(default_factory=dict)
    Inherited_Environment_Variables: List[str] = field(default_factory=list)
    Installed_Dependencies: List[str] = field(default_factory=list)
    DLL_Overrides: dict = field(default_factory=dict)
    External_Programs: Dict[str, dict] = field(default_factory=dict)
    Uninstallers: dict = field(default_factory=dict)
    Registry_Rules: list = field(default_factory=list)
    session_arguments: str = ""
    run_in_terminal: bool = False
    Language: str = "sys"  # "sys", "any valid language code"
    Winebridge: bool = False

    # Section - Not Existed in Sample Config but used in code
    data: dict = field(default_factory=dict)  # possible keys: "config", ...
    RunnerPath: str = ""

    @property
    def identifier(self) -> str:
        return self.Id

    def to_dict(self) -> dict:
        data = asdict(self)
        for key in ("Path", "session_arguments", "run_in_terminal", "RunnerPath"):
            data.pop(key)
        return data

    def dump(self, file: str | IO, mode="w", encoding=None, indent=4) -> Result:
        """
        Dump config to file

        :param file: filepath str or IO-like object.
        :param mode: when param 'file' is filepath, use this mode to open file, otherwise ignored.
               default is 'w'
        :param encoding: file content encoding, default is None(Decide by Python IO)
        :param indent: file indent width, default is 4
        """
        try:
            self.Id = uuid.UUID(self.Id).hex
            if isinstance(file, IOBase):
                yaml.dump(self.to_dict(), file, indent=indent, encoding=encoding)
            else:
                directory = os.path.dirname(os.path.abspath(file))
                fd, tmp_path = tempfile.mkstemp(
                    dir=directory, prefix=".bottle-", suffix=".tmp"
                )
                try:
                    with os.fdopen(fd, mode=mode) as f:
                        yaml.dump(
                            self.to_dict(), f, indent=indent, encoding=encoding
                        )
                        f.flush()
                        os.fsync(f.fileno())
                    os.replace(tmp_path, file)
                except BaseException:
                    with contextlib.suppress(OSError):
                        os.remove(tmp_path)
                    raise
            return Result(True)
        except Exception as e:
            logging.exception(e)
            return Result(False, message=str(e))

    @classmethod
    def load(cls, file: str | IO, mode="r") -> Result[Optional["BottleConfig"]]:
        """
        Load config from file

        :param file: filepath str or IO-like object.
        :param mode: when param 'file' is filepath, use this mode to open file, otherwise ignored.
               default is 'r'
        """
        try:
            if isinstance(file, IOBase):
                data = yaml.load(file)
            else:
                if not os.path.exists(file):
                    logging.info("Config file %s not found, skipping load", file)
                    return Result(False, message="Config file not exists")

                with open(file, mode=mode) as f:
                    data = yaml.load(f)
            if not isinstance(data, dict):
                raise TypeError(
                    "Config data should be dict type, but it was %s" % type(data)
                )

            if not isinstance(data.get("Id"), str) or not data["Id"]:
                raise ValueError("Bottle configuration has no Id.")
            data["Id"] = uuid.UUID(data["Id"]).hex
            filled = cls._fill_with(data)
            if not filled.status:
                raise ValueError("Invalid Config data (%s)" % filled.message)

            if not isinstance(file, IOBase):
                filled.data.Path = os.path.dirname(os.path.abspath(file))
            return Result(True, data=filled.data)
        except Exception as e:
            logging.exception(e)
            return Result(False, message=str(e))

    @classmethod
    def _fill_with(cls, data: dict) -> Result[Optional["BottleConfig"]]:
        """fill with dict"""
        try:
            data = data.copy()

            params = BottleParams(**data.pop("Parameters", {}))
            sandbox_param = BottleSandboxParams(**data.pop("Sandbox", {}))

            return Result(
                True,
                data=BottleConfig(Parameters=params, Sandbox=sandbox_param, **data),
            )
        except Exception as e:
            logging.exception(e)
            return Result(False, message=repr(e))

# Register custom YAML serializer for BottleConfig
yaml.register_serializer(BottleConfig)
