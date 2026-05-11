"""MCP tools for inspecting and editing existing Anki notes/cards.

These tools register against the shared FastMCP instance defined in
`mcp_ankiconnect.server`. Import this module to install the tools.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Literal

from mcp_ankiconnect.server import (
    get_anki_client,
    handle_anki_connection_error,
    mcp,
)

logger = logging.getLogger(__name__)


# --- Helpers ---

_QUEUE_LABELS = {
    0: "new",
    1: "learn",
    2: "review",
    3: "day_learn",
    -1: "suspended",
    -2: "buried_sched",
    -3: "buried_user",
}

_EASE_LABELS = {1: "again", 2: "hard", 3: "good", 4: "easy"}


def _queue_label(queue: int) -> str:
    return _QUEUE_LABELS.get(queue, "unknown")


def _format_review_entry(entry: dict) -> dict:
    ts_ms = entry.get("id", 0)
    reviewed_at = datetime.fromtimestamp(ts_ms / 1000, tz=UTC).isoformat()
    return {
        "reviewed_at_iso": reviewed_at,
        "ease": _EASE_LABELS.get(entry.get("ease", 0), "unknown"),
        "interval_days": entry.get("ivl", 0),
        "time_taken_ms": entry.get("time", 0),
    }


# --- Tools ---


@mcp.tool()
@handle_anki_connection_error
async def inspect_cards(
    card_ids: list[int] | None = None,
    note_ids: list[int] | None = None,
    include_history: bool = False,
) -> str:
    """Inspect per-card state: deck, model, suspension, ease, scheduling, optional review history.

    Provide EXACTLY ONE of `card_ids` or `note_ids`. When `note_ids` is given, the tool
    resolves to all cards belonging to those notes via an `nid:` query.

    Returned JSON contains a `cards` array. Each entry includes raw `queue`, `type`, and
    `raw_due` from AnkiConnect (interpretation depends on queue), plus a derived
    `queue_label` ("new"/"learn"/"review"/"day_learn"/"suspended"/"buried_sched"/"buried_user").

    Set `include_history=True` to fetch each card's review log (extra AnkiConnect call).
    Each review entry has an ISO timestamp, an "again"/"hard"/"good"/"easy" rating,
    interval in days, and time taken in ms.

    Args:
        card_ids: List of card IDs to inspect.
        note_ids: List of note IDs; expands to every card on those notes.
        include_history: If True, attach per-card review history.
    """
    if (card_ids is None) == (note_ids is None):
        return (
            "SYSTEM_ERROR: Provide exactly one of `card_ids` or `note_ids` "
            "(not both, not neither)."
        )

    async with get_anki_client() as anki:
        if note_ids is not None:
            if not note_ids:
                return "SYSTEM_ERROR: `note_ids` must not be empty."
            nid_query = "nid:" + ",".join(str(n) for n in note_ids)
            resolved_card_ids = await anki.find_cards(query=nid_query)
            if not resolved_card_ids:
                return json.dumps({"cards": []}, indent=2)
        else:
            if not card_ids:
                return "SYSTEM_ERROR: `card_ids` must not be empty."
            resolved_card_ids = list(card_ids)

        cards_info = await anki.cards_info(card_ids=resolved_card_ids)
        suspended_flags = await anki.are_suspended(cards=resolved_card_ids)

        reviews_by_card: dict[str, list[dict]] = {}
        if include_history:
            reviews_by_card = await anki.get_reviews_of_cards(cards=resolved_card_ids)

        out_cards = []
        for card, suspended in zip(cards_info, suspended_flags, strict=False):
            cid = card.get("cardId")
            entry = {
                "cardId": cid,
                "noteId": card.get("note"),
                "deck": card.get("deckName"),
                "modelName": card.get("modelName"),
                "suspended": bool(suspended) if suspended is not None else None,
                "queue": card.get("queue"),
                "queue_label": _queue_label(card.get("queue", 0)),
                "type": card.get("type"),
                "ease": (card.get("factor", 0) or 0) / 1000.0,
                "interval": card.get("interval"),
                "reps": card.get("reps"),
                "lapses": card.get("lapses"),
                "raw_due": card.get("due"),
                "modified_iso": datetime.fromtimestamp(
                    card.get("mod", 0), tz=UTC
                ).isoformat()
                if card.get("mod")
                else None,
                "reviews": None,
                "last_review_iso": None,
            }
            if include_history:
                raw_reviews = reviews_by_card.get(str(cid), [])
                formatted = [_format_review_entry(r) for r in raw_reviews]
                entry["reviews"] = formatted
                entry["last_review_iso"] = (
                    formatted[-1]["reviewed_at_iso"] if formatted else None
                )
            out_cards.append(entry)

        return json.dumps({"cards": out_cards}, indent=2, ensure_ascii=False)


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
