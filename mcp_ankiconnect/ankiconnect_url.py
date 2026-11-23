"""Work out where AnkiConnect listens, from the add-on's own settings.

Why: the plugin can't ask for settings (the Claude desktop app refuses to
start a plugin server that needs them), so a user who moved AnkiConnect off
port 8765 would get no connection at all. Anki
keeps every add-on's settings on disk, readable even while Anki is closed:
defaults in `addons21/<addon>/config.json`, the user's changes merged over
them from `meta.json` under "config". An explicit ANKI_CONNECT_URL still
wins; a blank or unexpanded one means "detect".
"""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

DEFAULT_URL = "http://localhost:8765"
ANKIWEB_ADDON_ID = "2055492159"
_WILDCARD_HOSTS = {"0.0.0.0", "::", ""}


def resolve_ankiconnect_url(
    env: Mapping[str, str] | None = None, base: Path | None = None
) -> str:
    """Return the AnkiConnect URL: explicit setting, else detected, else default."""
    env = os.environ if env is None else env
    explicit = (env.get("ANKI_CONNECT_URL") or "").strip()
    if explicit and not explicit.startswith("${"):
        return explicit
    settings = _ankiconnect_settings(base if base is not None else anki_base_dir(env))
    if settings is None:
        return DEFAULT_URL
    return _url_from_settings(settings) or DEFAULT_URL


def anki_base_dir(
    env: Mapping[str, str] | None = None,
    platform: str = sys.platform,
    home: Path | None = None,
) -> Path:
    """Anki's data folder (holds profiles and addons21), per platform."""
    env = os.environ if env is None else env
    home = Path.home() if home is None else home
    if env.get("ANKI_BASE"):
        return Path(env["ANKI_BASE"])
    if platform == "darwin":
        return home / "Library" / "Application Support" / "Anki2"
    if platform == "win32":
        return home / env.get("APPDATA", "AppData/Roaming") / "Anki2"
    return home / env.get("XDG_DATA_HOME", ".local/share") / "Anki2"


def _ankiconnect_settings(base: Path) -> dict[str, Any] | None:
    """AnkiConnect's effective settings: AnkiWeb folder first, then any match."""
    addons = base / "addons21"
    preferred = addons / ANKIWEB_ADDON_ID
    others = sorted(p for p in addons.glob("*") if p.is_dir() and p != preferred)
    for folder in [preferred, *others]:
        settings = _merged_config(folder)
        if settings is not None and "webBindPort" in settings:
            return settings
    return None


def _merged_config(folder: Path) -> dict[str, Any] | None:
    """Defaults from config.json with the user's meta.json changes on top."""
    defaults = _read_json(folder / "config.json")
    if not isinstance(defaults, dict):
        return None
    meta = _read_json(folder / "meta.json")
    user = meta.get("config") if isinstance(meta, dict) else None
    return {**defaults, **user} if isinstance(user, dict) else defaults


def _url_from_settings(settings: Mapping[str, Any]) -> str | None:
    """Build the URL; None if the port is unusable (corrupt settings)."""
    port = settings.get("webBindPort")
    if not isinstance(port, int) or not 0 < port < 65536:
        return None
    host = str(settings.get("webBindAddress", "localhost")).strip()
    host = "localhost" if host in _WILDCARD_HOSTS else host
    return f"http://{host}:{port}"


def _read_json(path: Path) -> Any:
    """Parsed JSON, or None for a missing or unreadable file."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
