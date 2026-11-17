from bottles.backend.utils.hidraw import list_hidraw_devices, normalize_hidraw_id


def test_list_hidraw_devices_reads_and_deduplicates_vid_pid(tmp_path):
    for index, name in ((0, "Flight Stick"), (1, "Duplicate Interface")):
        device = tmp_path / f"hidraw{index}" / "device"
        device.mkdir(parents=True)
        (device / "uevent").write_text(
            f"HID_ID=0003:0000044F:0000B10A\nHID_NAME={name}\n"
        )

    devices = list_hidraw_devices(tmp_path)

    assert len(devices) == 1
    assert devices[0].identifier == "0x044F/0xB10A"
    assert devices[0].name == "Flight Stick"


def test_list_hidraw_devices_ignores_malformed_entries(tmp_path):
    device = tmp_path / "hidraw0" / "device"
    device.mkdir(parents=True)
    (device / "uevent").write_text("HID_NAME=Missing identifier\n")

    assert list_hidraw_devices(tmp_path) == []


def test_normalize_hidraw_id_rejects_global_and_malformed_values():
    assert normalize_hidraw_id("0x044f/0xb10a") == "0x044F/0xB10A"
    assert normalize_hidraw_id("1") is None
    assert normalize_hidraw_id("0x044F") is None


def test_native_wine_hidraw_registry_uses_multi_string_vid_pid():
    from bottles.backend.utils.hidraw import hidraw_registry_bundle
    bundle = hidraw_registry_bundle(["0x044f/0xb10a", "0x231D/0x0200", "0x044F/0xB10A"])
    values = bundle[r"HKEY_LOCAL_MACHINE\System\CurrentControlSet\Services\winebus"]
    assert len(values) == 1
    assert values[0]["value"] == "EnableHidraw"
    assert values[0]["key_type"] == "hex(7)"
    encoded = bytes.fromhex(values[0]["data"].replace(",", " "))
    assert encoded.decode("utf-16le") == "044F:B10A\0" + "231D:0200\0\0"


def test_empty_hidraw_selection_clears_native_preference():
    from bottles.backend.utils.hidraw import hidraw_registry_bundle
    values = next(iter(hidraw_registry_bundle([]).values()))
    assert bytes.fromhex(values[0]["data"].replace(",", " ")) == b"\0\0\0\0"


def test_invalid_hidraw_selection_fails_instead_of_enabling_all_devices():
    import pytest
    from bottles.backend.utils.hidraw import hidraw_registry_bundle
    with pytest.raises(ValueError, match="Invalid HIDRAW"):
        hidraw_registry_bundle(["1"])


def test_hidraw_configuration_uses_wine_registry_and_propagates_failure(monkeypatch):
    from bottles.backend.models.result import Result
    from bottles.backend.utils.hidraw import configure_hidraw
    from bottles.backend.wine import reg
    calls = []
    config = object()
    failure = Result(False, message="Cannot import registry")
    class Registry:
        def __init__(self, received):
            assert received is config
        def import_bundle(self, bundle):
            calls.append(bundle)
            return failure
    monkeypatch.setattr(reg, "Reg", Registry)
    assert configure_hidraw(config, ["0x044F/0xB10A"]) is failure
    assert next(iter(calls[0].values()))[0]["value"] == "EnableHidraw"
