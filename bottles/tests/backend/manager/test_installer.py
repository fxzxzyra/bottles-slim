import pytest

from bottles.backend.managers.installer import InstallerManager
from bottles.backend.models.config import BottleConfig
from bottles.backend.models.result import Result
from bottles.backend.repos.installer import InstallerRepo


@pytest.mark.parametrize(
    ("channel", "include_unstable", "expected"),
    [
        ("stable", False, True),
        ("rc", False, False),
        ("unstable", False, False),
        ("unstable", True, True),
    ],
)
def test_installer_respects_release_channel(channel, include_unstable, expected):
    installer = ("test", {"Channel": channel})

    assert InstallerManager.supports_channel(installer, include_unstable) is expected


@pytest.mark.parametrize("current_value", [True, False])
def test_installer_applies_window_decoration_parameter(mocker, current_value):
    registry = mocker.patch(
        "bottles.backend.managers.installer.RegKeys",
        autospec=True,
    )
    manager = mocker.Mock()
    installer = object.__new__(InstallerManager)
    installer._InstallerManager__manager = manager
    config = BottleConfig(Name="Test")
    config.Parameters.decorated = current_value

    installer._InstallerManager__set_parameters(config, {"decorated": False})

    registry.assert_called_once_with(config)
    registry.return_value.set_decorated.assert_called_once_with(False)
    manager.update_config.assert_called_once_with(
        config=config,
        key="decorated",
        value=False,
        scope="Parameters",
    )


def test_installer_preserves_file_associations_for_existing_program(
    mocker, monkeypatch, tmp_path
):
    manager = mocker.Mock()
    installer = object.__new__(InstallerManager)
    installer._InstallerManager__manager = manager
    config = BottleConfig(
        Name="Test",
        Path=str(tmp_path),
        External_Programs={
            "existing": {
                "name": "Editor",
                "path": "C:\\Program Files\\Editor\\editor.exe",
                "file_extensions": [".txt", ".json"],
            }
        },
    )
    manifest = {
        "Name": "Editor",
        "Executable": {
            "file": "editor.exe",
            "name": "Editor",
            "path": "Program Files/Editor/editor.exe",
            "icon": "editor.png",
        },
    }
    created = []

    monkeypatch.setattr(installer, "get_installer", lambda _name: manifest)
    monkeypatch.setattr(
        installer,
        "_InstallerManager__download_icon",
        lambda *_args: None,
    )
    monkeypatch.setattr(
        "bottles.backend.managers.installer.ManagerUtils.get_bottle_path",
        lambda _config: str(tmp_path),
    )
    monkeypatch.setattr(
        "bottles.backend.managers.installer.ManagerUtils.create_desktop_entry",
        lambda _config, program, *_args: created.append(program),
    )

    result = installer.install(config, ("editor",), lambda: None)

    assert result.status is True
    assert created[0]["file_extensions"] == [".txt", ".json"]
    assert next(iter(config.External_Programs.values()))["file_extensions"] == [
        ".txt",
        ".json",
    ]


def test_installer_registers_program_without_icon(mocker, monkeypatch, tmp_path):
    manager = mocker.Mock()
    installer = object.__new__(InstallerManager)
    installer._InstallerManager__manager = manager
    config = BottleConfig(Name="Test", Path=str(tmp_path))
    manifest = {
        "Name": "Editor",
        "Executable": {
            "file": "editor.exe",
            "name": "Editor",
            "path": "Program Files/Editor/editor.exe",
        },
    }

    monkeypatch.setattr(installer, "get_installer", lambda _name: manifest)
    monkeypatch.setattr(
        "bottles.backend.managers.installer.ManagerUtils.get_bottle_path",
        lambda _config: str(tmp_path),
    )
    desktop_entry = mocker.patch(
        "bottles.backend.managers.installer.ManagerUtils.create_desktop_entry"
    )

    result = installer.install(config, ("editor",), lambda: None)

    assert result.status is True
    desktop_entry.assert_called_once_with(
        config,
        mocker.ANY,
        False,
        "",
    )


def test_run_winecommand_waits_and_reports_failure(mocker):
    winecommand = mocker.patch(
        "bottles.backend.managers.installer.WineCommand",
        autospec=True,
    )
    winecommand.return_value.run.return_value = Result(False, message="failed")

    result = InstallerManager._InstallerManager__step_run_winecommand(
        BottleConfig(Name="Test"),
        {
            "commands": [
                {
                    "command": "reg",
                    "arguments": "query HKCU",
                    "minimal": True,
                    "wait": True,
                }
            ]
        },
    )

    assert result is False
    winecommand.assert_called_once_with(
        mocker.ANY,
        command="reg",
        arguments="query HKCU",
        minimal=True,
        communicate=True,
        capture_exit_code=False,
    )


def test_run_winecommand_accepts_configured_exit_status(mocker):
    winecommand = mocker.patch(
        "bottles.backend.managers.installer.WineCommand",
        autospec=True,
    )
    winecommand.return_value.returncode = 49
    winecommand.return_value.run.return_value = Result(False, message="failed")

    result = InstallerManager._InstallerManager__step_run_winecommand(
        BottleConfig(Name="Test"),
        {
            "commands": [
                {
                    "command": "sc",
                    "arguments": "create TestService",
                    "wait": True,
                    "success_codes": [0, 49],
                }
            ]
        },
    )

    assert result is True


@pytest.mark.parametrize(
    ("installed", "expected_calls"),
    [
        (["WINWORD.EXE", "EXCEL.EXE"], 0),
        (["WINWORD.EXE"], 1),
    ],
)
def test_run_winecommand_skips_only_when_all_files_exist(
    mocker, monkeypatch, tmp_path, installed, expected_calls
):
    bottle = tmp_path / "Test"
    office = bottle / "drive_c" / "Program Files" / "Microsoft Office"
    office.mkdir(parents=True)
    for name in installed:
        (office / name).touch()
    monkeypatch.setattr(
        "bottles.backend.managers.installer.ManagerUtils.get_bottle_path",
        lambda _config: str(bottle),
    )
    winecommand = mocker.patch(
        "bottles.backend.managers.installer.WineCommand",
        autospec=True,
    )
    winecommand.return_value.run.return_value = Result(True)

    result = InstallerManager._InstallerManager__step_run_winecommand(
        BottleConfig(Name="Test"),
        {
            "commands": [
                {
                    "command": "setup.exe",
                    "wait": True,
                    "skip_if_files_exist": [
                        "Program Files/Microsoft Office/WINWORD.EXE",
                        "Program Files/Microsoft Office/EXCEL.EXE",
                    ],
                }
            ]
        },
    )

    assert result is True
    assert winecommand.call_count == expected_calls


def test_run_winecommand_does_not_skip_for_paths_outside_drive_c(
    mocker, monkeypatch, tmp_path
):
    bottle = tmp_path / "Test"
    drive_c = bottle / "drive_c"
    drive_c.mkdir(parents=True)
    (bottle / "outside.exe").touch()
    monkeypatch.setattr(
        "bottles.backend.managers.installer.ManagerUtils.get_bottle_path",
        lambda _config: str(bottle),
    )
    winecommand = mocker.patch(
        "bottles.backend.managers.installer.WineCommand",
        autospec=True,
    )
    winecommand.return_value.run.return_value = Result(True)

    result = InstallerManager._InstallerManager__step_run_winecommand(
        BottleConfig(Name="Test"),
        {
            "commands": [
                {
                    "command": "setup.exe",
                    "wait": True,
                    "skip_if_files_exist": ["../outside.exe"],
                }
            ]
        },
    )

    assert result is True
    winecommand.assert_called_once()


def test_installer_step_reports_failed_executable(mocker):
    manager = mocker.Mock()
    manager.component_manager.download.return_value = True
    installer = object.__new__(InstallerManager)
    installer._InstallerManager__component_manager = manager.component_manager
    executor = mocker.patch(
        "bottles.backend.managers.installer.WineExecutor",
        autospec=True,
    )
    executor.return_value.run.return_value = Result(False, message="failed")

    result = installer._InstallerManager__perform_steps(
        BottleConfig(Name="Test"),
        [
            {
                "action": "install_exe",
                "file_name": "setup.exe",
                "url": "https://example.invalid/setup.exe",
            }
        ],
    )

    assert result is False

def test_installer_refreshes_catalog_and_cached_manifests(mocker):
    repository = mocker.Mock()
    repository.catalog = {"old": {"Name": "Old"}}

    def refresh():
        repository.catalog = {"new": {"Name": "New"}}

    repository.refresh.side_effect = refresh
    installer = object.__new__(InstallerManager)
    installer._InstallerManager__repo = repository
    installer._InstallerManager__utils_conn = mocker.Mock(check_connection=lambda: True)

    installer._InstallerManager__manifests = {}

    assert installer.fetch_catalog() == {"old": {"Name": "Old"}}
    repository.get.return_value = {"Version": 1}
    assert installer.get_installer("office") == {"Version": 1}
    repository.get.return_value = {"Version": 2}
    assert installer.refresh_catalog() == {"new": {"Name": "New"}}
    assert installer.get_installer("office") == {"Version": 2}



def test_run_winecommand_accepts_truncated_configured_exit_status(mocker):
    winecommand = mocker.patch(
        "bottles.backend.managers.installer.WineCommand",
        autospec=True,
    )
    winecommand.return_value.returncode = 1073
    winecommand.return_value.run.return_value = Result(False, message="failed")

    result = InstallerManager._InstallerManager__step_run_winecommand(
        BottleConfig(Name="Test"),
        {
            "commands": [
                {
                    "command": "sc",
                    "arguments": "create TestService",
                    "wait": True,
                    "success_codes": [0, 49],
                }
            ]
        },
    )

    assert result is True



@pytest.mark.parametrize("connected", [True, False])
def test_installer_uses_loaded_catalog_without_network(mocker, connected):
    installer = object.__new__(InstallerManager)
    installer._InstallerManager__repo = mocker.Mock(
        catalog={"z": {"Name": "Last"}, "office": {"Name": "Office"}}
    )
    installer._InstallerManager__utils_conn = mocker.Mock()
    installer._InstallerManager__utils_conn.check_connection.return_value = connected

    assert list(installer.fetch_catalog()) == ["office", "z"]


@pytest.mark.parametrize("initial_catalog", [None, {}])
def test_installer_catalog_recovers_when_repository_becomes_ready(mocker, initial_catalog):
    repository = mocker.Mock(catalog=initial_catalog)
    installer = object.__new__(InstallerManager)
    installer._InstallerManager__repo = repository
    installer._InstallerManager__utils_conn = mocker.Mock(check_connection=lambda: True)

    assert installer.fetch_catalog() == {}
    repository.catalog = {"office": {"Name": "Office"}}
    assert installer.fetch_catalog() == {"office": {"Name": "Office"}}


def test_installer_catalog_loaded_from_repository_cache(monkeypatch, tmp_path):
    monkeypatch.setattr("bottles.backend.repos.repo.Paths.temp", str(tmp_path))
    repository = InstallerRepo(
        "https://repo.example.test/",
        "",
        catalog_data=b"office:\n  Name: Office\n  Category: Office\n",
    )
    repository.offline = True
    repository.catalog = None
    repository.refresh()
    installer = object.__new__(InstallerManager)
    installer._InstallerManager__repo = repository

    assert installer.fetch_catalog() == {
        "office": {"Name": "Office", "Category": "Office"}
    }



def test_installer_retries_missing_manifest_and_caches_success(mocker):
    manager = mocker.Mock()
    repository = manager.repository_manager.get_repo.return_value
    repository.get.side_effect = [False, {"Name": "Office"}]
    installer = InstallerManager(manager)

    assert installer.get_installer("office") is False
    assert installer.get_installer("office") == {"Name": "Office"}
    assert installer.get_installer("office") == {"Name": "Office"}
    assert repository.get.call_count == 2


def test_installer_reports_missing_manifest_without_starting(mocker):
    manager = mocker.Mock()
    manager.repository_manager.get_repo.return_value.get.return_value = False
    installer = InstallerManager(manager)
    executor = mocker.patch("bottles.backend.managers.installer.WineExecutor")
    step = mocker.Mock()

    assert installer.has_local_resources(("office",)) == []
    assert installer.count_steps(("office",)) == {"total": 0, "sections": []}
    result = installer.install(BottleConfig(Name="Test"), ("office",), step)

    assert result.ok is False
    assert result.data["message"] == "Cannot find manifest for office."
    step.assert_not_called()
    executor.assert_not_called()





@pytest.mark.parametrize(
    ("failure", "message"),
    [
        (
            Result(False, message="Cannot find manifest for office-runtime."),
            "Failed to install office-runtime. Cannot find manifest for office-runtime.",
        ),
        (
            Result(False, data={"message": "Download failed."}),
            "Failed to install office-runtime. Download failed.",
        ),
        (Result(False), "Failed to install office-runtime."),
    ],
)
def test_installer_keeps_dependency_failure_details(mocker, failure, message):
    manager = mocker.Mock()
    manifest = {
        "Name": "Editor",
        "Executable": {"file": "editor.exe", "name": "Editor"},
        "Dependencies": ["office-runtime", "next-runtime"],
    }
    manager.repository_manager.get_repo.return_value.get.return_value = manifest
    manager.supported_dependencies = {"office-runtime": {"Category": "Essentials"}}
    manager.dependency_manager.install.return_value = failure
    installer = InstallerManager(manager)
    config = BottleConfig(Name="Test")
    executor = mocker.patch("bottles.backend.managers.installer.WineExecutor")
    logs = []

    result = installer.install(config, ("editor",), lambda *_args: None)

    assert result.ok is False
    assert result.message == message
    assert result.data["message"] == message
    manager.dependency_manager.install.assert_called_once_with(
        config, ["office-runtime", {"Category": "Essentials"}]
    )
    executor.assert_not_called()


def test_installer_skips_installed_dependencies(mocker):
    manager = mocker.Mock()
    installer = InstallerManager(manager)
    config = BottleConfig(Name="Test", Installed_Dependencies=["runtime"])

    installer._InstallerManager__install_dependencies(
        config, ["runtime"], lambda *_args: None
    )

    manager.dependency_manager.install.assert_not_called()
