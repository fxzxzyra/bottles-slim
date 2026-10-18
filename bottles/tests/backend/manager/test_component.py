import pytest
from types import SimpleNamespace

from bottles.backend.managers.component import ComponentManager
from bottles.backend.repos.component import ComponentRepo


@pytest.mark.parametrize("kind", ["runner", "runner:proton"])
def test_runner_archives_cannot_be_installed_or_extracted(kind, mocker, tmp_path):
    components = object.__new__(ComponentManager)
    fetch = mocker.patch.object(components, "get_component")

    result = components.install(kind, "some-runner")

    assert not result.ok
    fetch.assert_not_called()
    assert not ComponentManager.extract("some-runner", kind, "absent.tar.xz")


def test_runner_manifest_is_never_requested(mocker):
    repo = object.__new__(ComponentRepo)
    repo.catalog = {
        "remote-wine": {"Category": "runners", "Sub-category": "wine"},
    }
    fetch = mocker.patch.object(repo, "get_manifest")
    assert repo.get("remote-wine") is False
    assert repo.get("remote-wine", plain=True) is False
    fetch.assert_not_called()


@pytest.mark.parametrize("plain", [False, True])
def test_component_manifest_retries_failed_fetch(plain):
    manifest = "File: []\n" if plain else {"File": []}
    responses = iter([False, manifest])
    calls = []

    def fetch(name, requested_plain=False):
        calls.append((name, requested_plain))
        return next(responses)

    repo = SimpleNamespace(get=fetch)
    manager = SimpleNamespace(
        is_cli=True,
        repository_manager=SimpleNamespace(get_repo=lambda *a, **kw: repo),
    )
    components = ComponentManager(manager)

    assert components.get_component("runner", plain) is False
    assert components.get_component("runner", plain=plain) == manifest
    assert components.get_component("runner", plain) == manifest
    assert calls == [("runner", plain), ("runner", plain)]


def test_component_manifest_cache_keeps_parsed_and_plain_separate():
    calls = []
    manifest = {"File": []}

    def fetch(name, plain=False):
        calls.append((name, plain))
        return "File: []\n" if plain else manifest

    manager = SimpleNamespace(
        is_cli=True,
        repository_manager=SimpleNamespace(
            get_repo=lambda *a, **kw: SimpleNamespace(get=fetch)
        ),
    )
    components = ComponentManager(manager)

    assert components.get_component("runner") == manifest
    assert components.get_component("runner", False) == manifest
    assert components.get_component("runner", plain=True) == "File: []\n"
    assert components.get_component("runner", True) == "File: []\n"
    assert calls == [("runner", False), ("runner", True)]
