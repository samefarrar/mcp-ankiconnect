"""Tests for finding AnkiConnect's URL from the add-on's own settings.

Why: hosts such as Cowork never prompt for plugin options, so a user who
moved AnkiConnect off port 8765 would otherwise get no connection at all.
These use real files in a temporary Anki folder rather than mocks.
"""

import json
from pathlib import Path

import pytest

from mcp_ankiconnect.ankiconnect_url import (
    DEFAULT_URL,
    anki_base_dir,
    resolve_ankiconnect_url,
)

ADDON_ID = "2055492159"


def _addon(base: Path, folder: str, defaults: dict, user: dict | None = None):
    """Write an add-on folder the way Anki stores it: defaults + meta.json."""
    path = base / "addons21" / folder
    path.mkdir(parents=True)
    (path / "config.json").write_text(json.dumps(defaults))
    if user is not None:
        (path / "meta.json").write_text(json.dumps({"config": user, "mod": 1}))


@pytest.fixture
def base(tmp_path) -> Path:
    return tmp_path / "Anki2"


def test_explicit_url_wins(base):
    _addon(base, ADDON_ID, {"webBindPort": 8765}, {"webBindPort": 8999})
    env = {"ANKI_CONNECT_URL": "http://example.lan:1234"}
    assert resolve_ankiconnect_url(env, base) == "http://example.lan:1234"


@pytest.mark.parametrize("unset", ["", "   ", "${user_config.ankiconnect_url}"])
def test_blank_or_unexpanded_url_means_detect(base, unset):
    _addon(base, ADDON_ID, {"webBindPort": 8765}, {"webBindPort": 8999})
    env = {"ANKI_CONNECT_URL": unset}
    assert resolve_ankiconnect_url(env, base) == "http://localhost:8999"


def test_user_port_in_meta_overrides_default(base):
    _addon(base, ADDON_ID, {"webBindPort": 8765}, {"webBindPort": 8999})
    assert resolve_ankiconnect_url({}, base) == "http://localhost:8999"


def test_default_port_from_config_json_when_user_never_changed_it(base):
    _addon(base, ADDON_ID, {"webBindAddress": "127.0.0.1", "webBindPort": 8770})
    assert resolve_ankiconnect_url({}, base) == "http://127.0.0.1:8770"


def test_wildcard_bind_address_is_reached_on_localhost(base):
    _addon(base, ADDON_ID, {"webBindPort": 8765}, {"webBindAddress": "0.0.0.0"})
    assert resolve_ankiconnect_url({}, base) == "http://localhost:8765"


def test_addon_installed_under_another_folder_name(base):
    # Installed from source rather than AnkiWeb: folder isn't the AnkiWeb id.
    _addon(base, "some-other-addon", {"colour": "blue"})
    _addon(base, "AnkiConnect", {"webBindPort": 8765}, {"webBindPort": 9001})
    assert resolve_ankiconnect_url({}, base) == "http://localhost:9001"


def test_falls_back_to_default_without_anki(base):
    assert resolve_ankiconnect_url({}, base) == DEFAULT_URL


def test_corrupt_settings_fall_back_to_default(base):
    path = base / "addons21" / ADDON_ID
    path.mkdir(parents=True)
    (path / "config.json").write_text("{not json")
    (path / "meta.json").write_text(json.dumps({"config": {"webBindPort": "x"}}))
    assert resolve_ankiconnect_url({}, base) == DEFAULT_URL


def test_base_dir_respects_anki_base_override(tmp_path):
    env = {"ANKI_BASE": str(tmp_path / "custom")}
    assert anki_base_dir(env, "darwin", tmp_path) == tmp_path / "custom"


@pytest.mark.parametrize(
    ("platform", "env", "expected"),
    [
        ("darwin", {}, "Library/Application Support/Anki2"),
        ("linux", {}, ".local/share/Anki2"),
        ("linux", {"XDG_DATA_HOME": "/xdg"}, "/xdg/Anki2"),
        ("win32", {"APPDATA": "/appdata"}, "/appdata/Anki2"),
    ],
)
def test_base_dir_per_platform(tmp_path, platform, env, expected):
    assert anki_base_dir(env, platform, tmp_path) == tmp_path / expected
