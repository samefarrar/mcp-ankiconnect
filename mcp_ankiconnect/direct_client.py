"""Use the collection file directly, through Anki's own engine, when Anki is closed.

`DirectAnkiClient` has the same `invoke` surface as `AnkiConnectClient`, so
every typed method and every tool works unchanged; `direct_actions` emulates
the AnkiConnect actions this server uses, with AnkiConnect's return shapes.

Safety rules, because this is the user's real collection:

- The collection is opened for one action (or one `multi` batch) and closed
  straight after, so Anki can open it whenever the user launches it.
- If Anki holds the file, the open fails and we report it; we never wait for
  or fight over the lock.
- Schema guard: `Collection()` silently upgrades an older schema and keeps it
  upgraded on close, and refuses a newer one. So the schema version is read
  first, without locking or writing, and the file is only opened when it
  already has exactly the schema this `anki` package writes. Then opening
  changes nothing the desktop app could fail to read.
"""

from __future__ import annotations

import asyncio
import functools
import logging
import sqlite3
import tempfile
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any

from mcp_ankiconnect.ankiconnect_client import (
    AnkiAction,
    AnkiConnectClient,
    DirectBackendError,
)

if TYPE_CHECKING:
    from anki.collection import Collection

logger = logging.getLogger(__name__)

# One open collection per process at a time. Why: clients run tool calls
# concurrently, and a second `Collection()` on the same file fails exactly
# like a running Anki would, which would be misreported as "in use".
_OPEN_LOCK = threading.Lock()


def read_schema_version(path: Path) -> int:
    """The collection's schema version (`col.ver`), read without side effects.

    Why `immutable=1`: a normal read-only open of a WAL database leaves
    `-wal`/`-shm` files beside the collection and takes a shared lock; the
    immutable open does neither. `ver` only changes during upgrades, so the
    uncommitted-WAL caveat of immutable reads does not matter here.
    """
    if not path.is_file():
        raise DirectBackendError(f"Anki collection not found at {path}.")
    try:
        db = sqlite3.connect(f"{path.as_uri()}?mode=ro&immutable=1", uri=True)
        try:
            return int(db.execute("select ver from col").fetchone()[0])
        finally:
            db.close()
    except (sqlite3.Error, TypeError) as e:
        raise DirectBackendError(
            f"Could not read the Anki collection at {path}: {e}"
        ) from e


@functools.cache
def supported_schema_version() -> int:
    """The schema version this `anki` package creates and upgrades to.

    Learned by creating a scratch collection once per process, so the guard
    follows the installed package instead of a hard-coded table.
    """
    from anki.collection import Collection

    with tempfile.TemporaryDirectory() as tmp:
        col = Collection(str(Path(tmp) / "probe.anki2"))
        col.close()
        return read_schema_version(Path(tmp) / "probe.anki2")


def check_schema(path: Path) -> None:
    """Refuse a collection whose schema opening would change or cannot read."""
    found, supported = read_schema_version(path), supported_schema_version()
    if found == supported:
        return
    if found < supported:
        advice = (
            "Opening it here would upgrade it, and an older Anki might then "
            "refuse it. Open Anki once (updating it if needed) so it is "
            "upgraded by Anki itself, or install an `anki` package matching "
            "your Anki version."
        )
    else:
        advice = (
            "It was written by a newer Anki than this server's `anki` package "
            "understands. Update the server's dependencies (`uv lock "
            "--upgrade-package anki`)."
        )
    raise DirectBackendError(
        f"Not opening the collection while Anki is closed: its schema version "
        f"is {found}, this server's Anki engine uses {supported}. {advice}"
    )


def _locked_error(path: Path) -> DirectBackendError:
    return DirectBackendError(
        f"The collection at {path} is in use, so Anki is probably running "
        "(or still starting) while AnkiConnect is not answering. Ask the user "
        "to wait for Anki to finish loading, or check that the AnkiConnect "
        "add-on is enabled. The file was not touched."
    )


@contextmanager
def open_collection(path: Path) -> Iterator[Collection]:
    """Open the collection for one action and always close it afterwards."""
    from anki.collection import Collection
    from anki.errors import DBError

    check_schema(path)
    try:
        col = Collection(str(path))
    except DBError as e:
        if "already open" in str(e):
            raise _locked_error(path) from e
        raise DirectBackendError(f"Could not open the collection: {e}") from e
    try:
        if not col.v3_scheduler():
            raise DirectBackendError(
                "This collection does not use Anki's v3 scheduler. Open it in "
                "Anki once so Anki can update it."
            )
        yield col
    finally:
        col.close()


class DirectAnkiClient(AnkiConnectClient):
    """AnkiConnect-compatible client that works on the collection file.

    Subclasses `AnkiConnectClient` only to inherit the typed wrapper methods;
    it opens no HTTP connection.
    """

    backend_mode = "direct"

    def __init__(self, collection_path: Path):
        self.collection_path = Path(collection_path)
        self.base_url = self.collection_path.as_uri()

    async def invoke(self, action: AnkiAction, **params: Any) -> Any:
        """Run one action in a worker thread, inside its own open/close.

        Errors from Anki become ValueError, as AnkiConnect's error replies do;
        DirectBackendError (lock, schema, missing file) passes through.
        """
        return await asyncio.to_thread(self._invoke_sync, action, params)

    def _invoke_sync(self, action: AnkiAction, params: dict[str, Any]) -> Any:
        from mcp_ankiconnect.direct_actions import run_action

        with _OPEN_LOCK, open_collection(self.collection_path) as col:
            try:
                return run_action(col, action.value, params)
            except DirectBackendError:
                raise
            except Exception as e:
                logger.info(f"Direct action {action.value} failed: {e}")
                raise ValueError(f"Anki error: {e}") from e

    async def close(self) -> None:
        """Nothing to release: the collection is closed after every action."""
