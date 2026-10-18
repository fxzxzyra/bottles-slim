import struct
from types import SimpleNamespace

from bottles.backend.managers import eagle as eagle_module
from bottles.backend.managers.eagle import EagleManager
from bottles.backend.models.config import BottleConfig


def test_legacy_arm64_analysis_requires_a_matching_runner(monkeypatch, tmp_path):
    target = tmp_path / "arm64.exe"
    image = bytearray(1024)
    image[:2] = b"MZ"
    struct.pack_into("<I", image, 0x3C, 0x80)
    image[0x80:0x84] = b"PE\0\0"
    struct.pack_into("<HHIIIHH", image, 0x84, 0xAA64, 0, 1700000000, 0, 0, 240, 0x22)
    struct.pack_into("<H", image, 0x98, 0x20B)
    struct.pack_into("<Q", image, 0x98 + 24, 0x140000000)
    struct.pack_into("<II", image, 0x98 + 32, 4096, 512)
    struct.pack_into("<H", image, 0x98 + 40, 10)
    struct.pack_into("<II", image, 0x98 + 56, 4096, 512)
    struct.pack_into("<H", image, 0x98 + 68, 3)
    struct.pack_into("<I", image, 0x98 + 108, 16)
    target.write_bytes(image)
    manager = EagleManager.__new__(EagleManager)
    manager.config = BottleConfig(Runner="system-wine")
    manager._yara_rules = None
    steps = []
    events = []
    manager._send_step = lambda message, **_kwargs: steps.append(message)
    manager._send = lambda kind, result: events.append((kind, result))
    monkeypatch.setattr(eagle_module, "EagleIntel", lambda: SimpleNamespace(available=False))
    monkeypatch.setattr(eagle_module, "Gio", SimpleNamespace(
        Settings=SimpleNamespace(new=lambda _app: SimpleNamespace(get_int=lambda _key: 1))
    ))
    manager.analyze(str(target))

    assert len(events) == 1
    assert events[0][1].status
    warning, = events[0][1].data["details"]["Warning"]
    assert warning == {
        "name": "ARM64 binary",
        "description": "Requires an ARM64-capable Wine runner.",
        "severity": "warning",
        "source": "Main Executable",
    }
    assert "[!] ARM64 requires a matching Wine runner" in steps
    assert not any("will not work" in step for step in steps)

