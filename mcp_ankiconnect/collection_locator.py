"""Find the user's `collection.anki2` when Anki is closed.

Resolution order: `ANKI_COLLECTION_PATH`, then a profile folder under Anki's
base folder chosen by `ANKI_PROFILE`, the last-used profile recorded in
`prefs21.db`, or the only profile. Anything ambiguous raises
`DirectBackendError` listing the choices, because guessing the wrong
profile would edit the wrong collection.

Reads only: `prefs21.db` is opened immutable, so nothing is created next to
it and Anki's own lock is never touched.
"""

from __future__ import annotations

import io
import os
import pickle
import sqlite3
import sys
from collections.abc import Mapping
from pathlib import Path

from mcp_ankiconnect.ankiconnect_client import DirectBackendError

COLLECTION_FILE = "collection.anki2"


def default_base_dir(
    platform: str = sys.platform,
    env: Mapping[str, str] = os.environ,
    home: Path | None = None,
) -> Path:
    """Anki's base folder (the one holding profile folders) on this OS.

    `ANKI_BASE` is honoured because Anki itself uses it to relocate data.
    """
    if env.get("ANKI_BASE"):
        return Path(env["ANKI_BASE"])
    home = home if home is not None else Path.home()
    if platform == "darwin":
        return home / "Library" / "Application Support" / "Anki2"
    if platform == "win32":
        appdata = env.get("APPDATA") or str(home / "AppData" / "Roaming")
        return Path(appdata) / "Anki2"
    xdg = env.get("XDG_DATA_HOME") or str(home / ".local" / "share")
    return Path(xdg) / "Anki2"


def locate_collection(
    env: Mapping[str, str] = os.environ, base_dir: Path | None = None
) -> Path:
    """Path of the collection to open, or DirectBackendError explaining why not."""
    explicit = env.get("ANKI_COLLECTION_PATH") or ""
    if explicit:
        path = Path(explicit).expanduser()
        if not path.is_file():
            raise DirectBackendError(
                f"ANKI_COLLECTION_PATH points to {path}, which does not exist."
            )
        return path
    base = base_dir if base_dir is not None else default_base_dir(env=env)
    profiles = _profiles(base)
    return base / _choose_profile(base, profiles, env) / COLLECTION_FILE


def _profiles(base: Path) -> list[str]:
    """Profile folder names: subfolders that hold a collection file."""
    if not base.is_dir():
        return []
    return sorted(p.name for p in base.iterdir() if (p / COLLECTION_FILE).is_file())


def _choose_profile(base: Path, profiles: list[str], env: Mapping[str, str]) -> str:
    if not profiles:
        raise DirectBackendError(
            f"No Anki profile found in {base}. Set ANKI_COLLECTION_PATH to the "
            "full path of your collection.anki2."
        )
    wanted = env.get("ANKI_PROFILE") or ""
    if wanted:
        if wanted in profiles:
            return wanted
        raise DirectBackendError(
            f"Anki profile '{wanted}' not found in {base}. "
            f"Profiles: {', '.join(profiles)}."
        )
    last = _last_used_profile(base)
    if last is not None and last in profiles:
        return last
    if len(profiles) == 1:
        return profiles[0]
    raise DirectBackendError(
        f"Several Anki profiles found ({', '.join(profiles)}) and no last-used "
        "profile could be read. Set ANKI_PROFILE (the plugin's Anki profile "
        "option) to the one to use."
    )


class _PlainUnpickler(pickle.Unpickler):
    """Unpickler that refuses every class, so loading cannot run code."""

    def find_class(self, module: str, name: str):
        raise pickle.UnpicklingError(f"refusing {module}.{name}")


def _last_used_profile(base: Path) -> str | None:
    """Anki's `last_loaded_profile_name` from prefs21.db, or None if unreadable."""
    prefs = base / "prefs21.db"
    if not prefs.is_file():
        return None
    try:
        db = sqlite3.connect(f"{prefs.as_uri()}?mode=ro&immutable=1", uri=True)
        try:
            row = db.execute(
                "select data from profiles where name = '_global'"
            ).fetchone()
        finally:
            db.close()
        if row is None:
            return None
        meta = _PlainUnpickler(io.BytesIO(row[0])).load()
    except (sqlite3.Error, pickle.UnpicklingError, EOFError, ValueError, TypeError):
        return None
    name = meta.get("last_loaded_profile_name") if isinstance(meta, dict) else None
    return name if isinstance(name, str) else None
