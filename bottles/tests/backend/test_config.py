from io import StringIO

import pytest

from bottles.backend.models.config import BottleConfig
from bottles.backend.models.samples import Samples
from bottles.backend.wine.winecommand import WineEnv


def _reload(config):
    stream = StringIO()
    assert config.dump(stream).status is True
    stream.seek(0)
    result = BottleConfig.load(stream)
    assert result.status is True
    return result.data


@pytest.mark.parametrize(
    "limit_environment,inherited",
    [
        (False, []),
        (True, ["DISPLAY"]),
        (True, ["DISPLAY", "CUSTOM_VARIABLE"]),
    ],
)
def test_load_preserves_custom_inherited_environment(limit_environment, inherited):
    config = BottleConfig(
        Limit_System_Environment=limit_environment,
        Inherited_Environment_Variables=inherited,
    )

    loaded = _reload(config)

    assert loaded.Inherited_Environment_Variables == inherited


def test_load_rejects_unknown_parameters():
    result = BottleConfig._fill_with({"Parameters": {"unknown_parameter": False}})
    assert not result.ok
    assert "unknown_parameter" in result.message


def test_bottle_configuration_moves_with_its_directory(tmp_path):
    import os
    from bottles.backend.utils import yaml
    old = tmp_path / "old"
    old.mkdir()
    config = BottleConfig(Name="Editor", Path=str(old), session_arguments="secret", run_in_terminal=True)
    assert config.dump(str(old / "bottle.yml")).ok
    saved = yaml.load((old / "bottle.yml").read_text())
    assert "Path" not in saved
    assert "session_arguments" not in saved
    assert "run_in_terminal" not in saved
    assert (old / "bottle.yml").stat().st_mode & 0o777 == 0o600
    new = tmp_path / "moved"
    os.rename(old, new)
    loaded = BottleConfig.load(str(new / "bottle.yml"))
    assert loaded.ok
    assert loaded.data.Path == str(new)
    assert loaded.data.Name == "Editor"
    assert loaded.data.Id == config.Id
    assert loaded.data.session_arguments == ""
    assert loaded.data.run_in_terminal is False
