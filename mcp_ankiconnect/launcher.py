"""Open Anki in the background when nothing is listening on AnkiConnect's port.

The interface is one call, `AnkiLauncher.recover(base_url)`, which the client
makes after a *refused* connection (never after a timeout: a busy Anki is
running and must not be launched again). It returns once AnkiConnect answers,
returns False when launching cannot help (a remote AnkiConnect), or raises
`AnkiLaunchError` with a message ready for the user. Everything else (platform
commands, polling, the single-flight lock, backoff after a failure) is hidden
here, so the client and the tools stay unaware of launching.

A successful launch is recorded as a NOTE line through `capture_notes`, which
the tool decorator in `server.py` prepends to the tool's result so the user
learns that Anki was opened for them.
"""

import asyncio
import contextvars
import logging
import os
import subprocess
import sys
import time
from collections.abc import Awaitable, Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import urlparse

import httpx

from .ankiconnect_client import AnkiConnectionError

logger = logging.getLogger(__name__)

FALSE_STRINGS = frozenset({"0", "false", "no", "off"})
TRUE_STRINGS = frozenset({"1", "true", "yes", "on"})
LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1", "0.0.0.0"})
DEFAULT_TIMEOUT = 30.0
POLL_INTERVAL = 0.5
PROBE_TIMEOUT = 2.0
FAILURE_BACKOFF = 60.0
ENABLE_HINT = (
    "To let me open Anki for you, remove ANKI_AUTO_LAUNCH=false from the "
    "server's environment (auto-launch is on by default)."
)


class AnkiLaunchError(AnkiConnectionError):
    """Anki is closed and could not (or may not) be opened. The message is
    complete and user-facing, so the tool decorator shows it verbatim."""


class LaunchedProcess(Protocol):
    """The part of `subprocess.Popen` the launcher needs."""

    def poll(self) -> int | None: ...


Spawn = Callable[[list[str]], LaunchedProcess]
Probe = Callable[[str], Awaitable[bool]]


def parse_bool(raw: str | None, default: bool) -> bool:
    """Read an on/off env var ("true"/"false", "1"/"0", "yes"/"no", "on"/"off").
    An unset, empty or unexpanded `${...}` value keeps the default, so a client
    config that passes a placeholder through does not disable the feature."""
    if raw is None:
        return default
    value = raw.strip().lower()
    if value in FALSE_STRINGS:
        return False
    if value in TRUE_STRINGS:
        return True
    return default


def _parse_seconds(raw: str | None, default: float) -> float:
    """A positive number of seconds, else the default."""
    if raw is None:
        return default
    try:
        seconds = float(raw)
    except ValueError:
        return default
    return seconds if seconds > 0 else default


@dataclass(frozen=True)
class LaunchSettings:
    enabled: bool = True
    app: str | None = None  # ANKI_APP_PATH: app name/path or executable
    timeout: float = DEFAULT_TIMEOUT
    platform: str = sys.platform

    @classmethod
    def from_env(cls) -> "LaunchSettings":
        return cls(
            enabled=parse_bool(os.getenv("ANKI_AUTO_LAUNCH"), default=True),
            app=os.getenv("ANKI_APP_PATH") or None,
            timeout=_parse_seconds(os.getenv("ANKI_LAUNCH_TIMEOUT"), DEFAULT_TIMEOUT),
        )


def launch_command(settings: LaunchSettings) -> list[str]:
    """The command that starts Anki without stealing focus.

    macOS `open -g` launches in the background and exits at once; elsewhere
    the Anki executable itself is started detached.
    """
    if settings.platform == "darwin":
        return ["open", "-g", "-a", settings.app or "Anki"]
    if settings.platform == "win32":
        default = os.path.join(
            os.getenv("LOCALAPPDATA", r"C:\Users\Default\AppData\Local"),
            "Programs", "Anki", "anki.exe",
        )
        return [settings.app or default]
    return [settings.app or "anki"]


def spawn_detached(command: list[str]) -> subprocess.Popen:
    """Start the command in its own session with no stdio, so Anki outlives
    this server and cannot write into the MCP stdio stream. Popen returns
    as soon as the process exists, so this does not block the event loop."""
    kwargs: dict[str, Any] = {
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
    }
    if sys.platform == "win32":
        kwargs["creationflags"] = (
            subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
        )
    else:
        kwargs["start_new_session"] = True
    return subprocess.Popen(command, **kwargs)


async def probe_version(base_url: str) -> bool:
    """True when AnkiConnect answers its `version` action."""
    payload = {"action": "version", "version": 6}
    try:
        async with httpx.AsyncClient(timeout=PROBE_TIMEOUT) as client:
            response = await client.post(base_url, json=payload)
            return response.status_code == 200
    except httpx.HTTPError:
        return False


def is_local(base_url: str) -> bool:
    """Only an AnkiConnect on this machine can be fixed by opening Anki."""
    host = urlparse(base_url).hostname
    return host is not None and host.lower() in LOCAL_HOSTS


# --- Telling the user ------------------------------------------------------

_notes: contextvars.ContextVar[list[str] | None] = contextvars.ContextVar(
    "anki_launch_notes", default=None
)


@contextmanager
def capture_notes() -> Iterator[list[str]]:
    """Collect NOTE lines recorded during one tool call.

    The list is shared by reference, so notes recorded in tasks spawned by
    the tool (which get a copy of the context) still land here.
    """
    notes: list[str] = []
    token = _notes.set(notes)
    try:
        yield notes
    finally:
        _notes.reset(token)


def record_note(note: str) -> None:
    """Attach a note to the current tool call, if one is capturing."""
    notes = _notes.get()
    if notes is not None:
        notes.append(note)


def with_notes(result: Any, notes: list[str]) -> Any:
    """Put the notes in front of a text result or in a dict's `note` field.

    Other results (an MCP Image) are returned unchanged: they have no place
    for text, and the next text result will not repeat the note.
    """
    if not notes:
        return result
    text = "\n".join(notes)
    if isinstance(result, str):
        return f"{text}\n{result}"
    if isinstance(result, dict):
        return {**result, "note": text}
    logger.info(f"Not attaching launch note to {type(result).__name__} result")
    return result


# --- The launcher ----------------------------------------------------------


class AnkiLauncher:
    def __init__(
        self,
        settings: LaunchSettings,
        spawn: Spawn = spawn_detached,
        probe: Probe = probe_version,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self.settings = settings
        self._spawn = spawn
        self._probe = probe
        self._clock = clock
        self._sleep = sleep
        self._lock = asyncio.Lock()
        self._failed_at: float | None = None
        self._failure = ""

    @classmethod
    def from_env(cls) -> "AnkiLauncher":
        return cls(LaunchSettings.from_env())

    capture_notes = staticmethod(capture_notes)

    async def recover(self, base_url: str) -> bool:
        """Make AnkiConnect at `base_url` answer after a refused connection.

        Returns True when it now answers (launched here or by a concurrent
        call), False when launching cannot help, and raises AnkiLaunchError
        when Anki stays unreachable.
        """
        if not is_local(base_url):
            return False
        if not self.settings.enabled:
            raise AnkiLaunchError(
                f"Anki is closed (nothing is listening at {base_url}). "
                f"Ask the user to open Anki. {ENABLE_HINT}"
            )
        async with self._lock:
            if await self._probe(base_url):
                return True  # a concurrent call already opened it
            self._check_backoff()
            try:
                elapsed = await self._launch_and_wait(base_url)
            except AnkiLaunchError as e:
                self._failed_at, self._failure = self._clock(), str(e)
                raise
            self._failed_at = None
        record_note(
            "NOTE: Anki was closed, so I opened it in the background "
            f"(took {elapsed:.0f} s)."
        )
        return True

    def _check_backoff(self) -> None:
        """Refuse to relaunch soon after a failed launch, so a stuck profile
        picker does not cost every tool call another full timeout."""
        if self._failed_at is None:
            return
        remaining = FAILURE_BACKOFF - (self._clock() - self._failed_at)
        if remaining > 0:
            raise AnkiLaunchError(
                f"{self._failure} I will not try to open Anki again for "
                f"{remaining:.0f} s; once the user has fixed this, retry."
            )

    async def _launch_and_wait(self, base_url: str) -> float:
        """Start Anki and poll `version`; return the seconds it took."""
        command = launch_command(self.settings)
        started = self._clock()
        logger.info(f"AnkiConnect refused; launching Anki with {command}")
        try:
            process = self._spawn(command)
        except OSError as e:
            raise AnkiLaunchError(
                f"Anki is closed and I could not open it with {command!r}: {e}. "
                "Set ANKI_APP_PATH to Anki's app name, .app path or executable."
            ) from e
        while self._clock() - started < self.settings.timeout:
            await self._sleep(POLL_INTERVAL)
            if await self._probe(base_url):
                return self._clock() - started
            self._check_exit(process, command)
        raise AnkiLaunchError(self._timeout_message(base_url))

    @staticmethod
    def _check_exit(process: LaunchedProcess, command: list[str]) -> None:
        """Fail fast when the launch command itself failed (`open` exits 0
        once the app starts, so only a non-zero code means trouble)."""
        code = process.poll()
        if code is not None and code != 0:
            raise AnkiLaunchError(
                f"Anki is closed and opening it failed: {command!r} exited "
                f"with code {code}. Is Anki installed? Set ANKI_APP_PATH if it "
                "lives somewhere unusual."
            )

    def _timeout_message(self, base_url: str) -> str:
        return (
            f"I opened Anki, but AnkiConnect at {base_url} did not answer "
            f"within {self.settings.timeout:.0f} s. Ask the user to check Anki: "
            "it is probably waiting at the profile picker (choose a profile), "
            "or the AnkiConnect add-on (code 2055492159) is missing or "
            "disabled, or AnkiConnect listens on a different port than "
            "ANKI_CONNECT_URL."
        )


LAUNCHER = AnkiLauncher.from_env()
