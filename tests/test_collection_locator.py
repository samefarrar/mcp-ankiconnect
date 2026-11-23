"""Finding the user's collection file when Anki is closed.

Pure filesystem logic: no `anki` package needed. Each test builds a fake
Anki base folder (profile folders with a `collection.anki2`, optionally a
`prefs21.db`) in a tmp dir.
"""

import pickle
import sqlite3
from pathlib import Path

import pytest

from mcp_ankiconnect.ankiconnect_client import DirectBackendError
from mcp_ankiconnect.collection_locator import (
    default_base_dir,
    locate_collection,
)


def _profile(base: Path, name: str) -> Path:
    path = base / name / "collection.anki2"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"")
    return path


def _prefs(base: Path, meta: dict) -> None:
    """Write prefs21.db the way Anki does: a pickled dict in the _global row."""
    db = sqlite3.connect(base / "prefs21.db")
    db.execute("create table profiles (name text primary key, data blob not null)")
    db.execute("insert into profiles values ('_global', ?)", (pickle.dumps(meta),))
    db.commit()
    db.close()


@pytest.fixture
def base(tmp_path: Path) -> Path:
    (tmp_path / "addons21").mkdir()  # not a profile: has no collection
    return tmp_path


def test_explicit_path_wins(base: Path, tmp_path: Path):
    path = _profile(base, "User 1")
    env = {"ANKI_COLLECTION_PATH": str(path), "ANKI_PROFILE": "Nope"}
    assert locate_collection(env=env, base_dir=base) == path


def test_explicit_path_must_exist(base: Path):
    env = {"ANKI_COLLECTION_PATH": str(base / "missing.anki2")}
    with pytest.raises(DirectBackendError, match="ANKI_COLLECTION_PATH"):
        locate_collection(env=env, base_dir=base)


def test_empty_env_values_are_ignored(base: Path):
    """The plugin passes unset userConfig options as empty strings."""
    path = _profile(base, "User 1")
    env = {"ANKI_COLLECTION_PATH": "", "ANKI_PROFILE": ""}
    assert locate_collection(env=env, base_dir=base) == path


def test_single_profile_is_used(base: Path):
    path = _profile(base, "User 1")
    assert locate_collection(env={}, base_dir=base) == path


def test_named_profile(base: Path):
    _profile(base, "User 1")
    sam = _profile(base, "Sam")
    assert locate_collection(env={"ANKI_PROFILE": "Sam"}, base_dir=base) == sam


def test_unknown_named_profile_lists_profiles(base: Path):
    _profile(base, "User 1")
    with pytest.raises(DirectBackendError, match="User 1"):
        locate_collection(env={"ANKI_PROFILE": "Sam"}, base_dir=base)


def test_last_used_profile_from_prefs(base: Path):
    _profile(base, "User 1")
    sam = _profile(base, "Sam")
    _prefs(base, {"last_loaded_profile_name": "Sam", "created": 1})
    assert locate_collection(env={}, base_dir=base) == sam


def test_ambiguous_profiles_list_choices(base: Path):
    _profile(base, "User 1")
    _profile(base, "Sam")
    with pytest.raises(DirectBackendError) as err:
        locate_collection(env={}, base_dir=base)
    assert "Sam" in str(err.value) and "User 1" in str(err.value)
    assert "ANKI_PROFILE" in str(err.value)


def test_unreadable_prefs_fall_back(base: Path):
    path = _profile(base, "User 1")
    (base / "prefs21.db").write_bytes(b"not a database")
    assert locate_collection(env={}, base_dir=base) == path


def test_prefs_pickle_with_classes_is_not_loaded(base: Path):
    """The prefs pickle is only read when it holds plain values.

    Why: unpickling a class reference can run code, so anything beyond
    builtins is refused and the other rules decide.
    """
    _profile(base, "User 1")
    _profile(base, "Sam")
    _prefs(base, {"last_loaded_profile_name": "Sam", "path": Path("/x")})
    with pytest.raises(DirectBackendError, match="profiles"):
        locate_collection(env={}, base_dir=base)


def test_no_profiles(base: Path):
    with pytest.raises(DirectBackendError, match="No Anki profile"):
        locate_collection(env={}, base_dir=base)


def test_missing_base_dir(tmp_path: Path):
    with pytest.raises(DirectBackendError, match="No Anki profile"):
        locate_collection(env={}, base_dir=tmp_path / "nowhere")


@pytest.mark.parametrize(
    ("platform", "env", "expected"),
    [
        ("darwin", {}, "/home/u/Library/Application Support/Anki2"),
        ("linux", {}, "/home/u/.local/share/Anki2"),
        ("linux", {"XDG_DATA_HOME": "/xdg"}, "/xdg/Anki2"),
        (
            "win32",
            {"APPDATA": "C:/Users/u/AppData/Roaming"},
            "C:/Users/u/AppData/Roaming/Anki2",
        ),
        ("darwin", {"ANKI_BASE": "/custom"}, "/custom"),
    ],
)
def test_default_base_dir(platform: str, env: dict, expected: str):
    got = default_base_dir(platform=platform, env=env, home=Path("/home/u"))
    assert got == Path(expected)
