"""Which backend answers a tool call, and telling the user when that changes.

Each tool call probes AnkiConnect with a short connect timeout. If nothing is
listening and the `direct` extra (the `anki` package) is installed, the call
works on the collection file instead. The user hears about it once per
switch: the first result after a flip starts with a one-line NOTE. The
server starts in AnkiConnect mode, so the usual case (Anki open) adds no
note at all.

The mode of the current call lives in a ContextVar set by `get_anki_client`
and read by the tool decorator, so no tool signature changes.
"""

from __future__ import annotations

import importlib.util
import logging
import os
from contextvars import ContextVar, Token
from enum import Enum
from typing import Any

import httpx

logger = logging.getLogger(__name__)

PROBE_CONNECT_TIMEOUT = 0.5  # seconds; localhost answers in well under this
PROBE_READ_TIMEOUT = 5.0  # a busy Anki is still "open": never take its file


class Mode(str, Enum):
    ANKICONNECT = "ankiconnect"
    DIRECT = "direct"


NOTICES = {
    Mode.DIRECT: (
        "NOTE: Anki is closed, so I'm working on your collection file "
        "directly. Changes reach AnkiWeb and your phone the next time Anki "
        "syncs."
    ),
    Mode.ANKICONNECT: "NOTE: Anki is open again; using AnkiConnect.",
}

_announced: Mode = Mode.ANKICONNECT
_call_mode: ContextVar[Mode | None] = ContextVar("anki_call_mode", default=None)


def direct_backend_enabled(env: dict[str, str] | None = None) -> bool:
    """True when the `anki` package is installed and not switched off.

    `ANKI_DIRECT_FALLBACK=0` restores the old behaviour (fail when Anki is
    closed). Without the extra, the probe is skipped entirely.
    """
    env = env if env is not None else dict(os.environ)
    if env.get("ANKI_DIRECT_FALLBACK", "").strip().lower() in {"0", "false", "no"}:
        return False
    return importlib.util.find_spec("anki") is not None


async def ankiconnect_listening(url: str) -> bool:
    """Whether anything answers at the AnkiConnect URL.

    Only a refused or timed-out *connection* counts as closed. A slow reply
    or an HTTP error means Anki is running, so the call goes to AnkiConnect
    and its own errors reach the user.
    """
    timeout = httpx.Timeout(PROBE_READ_TIMEOUT, connect=PROBE_CONNECT_TIMEOUT)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            await client.post(url, json={"action": "version", "version": 6})
    except (httpx.ConnectError, httpx.ConnectTimeout):
        return False
    except httpx.HTTPError as e:
        logger.info(f"AnkiConnect probe got a reply but failed: {e}")
    return True


def begin_call() -> Token:
    """Start tracking the mode of one tool call."""
    return _call_mode.set(None)


def end_call(token: Token) -> None:
    _call_mode.reset(token)


def record_mode(mode: Mode) -> None:
    """Note which backend this call uses (called by `get_anki_client`)."""
    _call_mode.set(mode)


def annotate(result: Any) -> Any:
    """Prepend the mode-change NOTE to a successful text result.

    Errors and non-text results (images) are returned unchanged and the
    switch stays unannounced, so the note appears on the next text result.
    """
    global _announced
    mode = _call_mode.get()
    if mode is None or mode == _announced:
        return result
    if not isinstance(result, str) or result.startswith("SYSTEM_ERROR"):
        return result
    _announced = mode
    return f"{NOTICES[mode]}\n\n{result}"


def reset_announced_mode() -> None:
    """Forget past announcements (tests; a fresh process starts here too)."""
    global _announced
    _announced = Mode.ANKICONNECT
