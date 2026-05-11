"""MCP tools for inspecting and editing existing Anki notes/cards.

These tools register against the shared FastMCP instance defined in
`mcp_ankiconnect.server`. Import this module to install the tools.
"""

from __future__ import annotations

import logging
from typing import Literal

from mcp_ankiconnect.server import (
    get_anki_client,  # noqa: F401  # re-exported for test patching; consumed by tools added in later tasks
    handle_anki_connection_error,
    mcp,
)

logger = logging.getLogger(__name__)


# --- Stubs (implementations land in later tasks) ---


@mcp.tool()
@handle_anki_connection_error
async def inspect_cards(
    card_ids: list[int] | None = None,
    note_ids: list[int] | None = None,
    include_history: bool = False,
) -> str:
    """Stub — implemented in a later task."""
    return "SYSTEM_ERROR: inspect_cards not yet implemented."


@mcp.tool()
@handle_anki_connection_error
async def update_note_fields(note_id: int, fields: dict[str, str]) -> str:
    """Stub — implemented in a later task."""
    return "SYSTEM_ERROR: update_note_fields not yet implemented."


@mcp.tool()
@handle_anki_connection_error
async def update_note_tags(
    note_ids: list[int],
    add: list[str] | None = None,
    remove: list[str] | None = None,
) -> str:
    """Stub — implemented in a later task."""
    return "SYSTEM_ERROR: update_note_tags not yet implemented."


@mcp.tool()
@handle_anki_connection_error
async def set_suspended(card_ids: list[int], suspended: bool) -> str:
    """Stub — implemented in a later task."""
    return "SYSTEM_ERROR: set_suspended not yet implemented."


@mcp.tool()
@handle_anki_connection_error
async def change_deck(card_ids: list[int], deck: str) -> str:
    """Stub — implemented in a later task."""
    return "SYSTEM_ERROR: change_deck not yet implemented."


@mcp.tool()
@handle_anki_connection_error
async def reschedule_cards(
    card_ids: list[int],
    mode: Literal["set_due", "forget", "relearn"],
    due: str | None = None,
) -> str:
    """Stub — implemented in a later task."""
    return "SYSTEM_ERROR: reschedule_cards not yet implemented."
