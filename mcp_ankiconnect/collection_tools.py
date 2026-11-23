"""MCP tools that bring the server to parity with other Anki MCP servers.

Covers batch creation, deletion, tags, decks, sync, review analytics, media
read-back and GUI context. They register against the shared FastMCP instance
in `mcp_ankiconnect.server`; import this module to install them.
"""

from __future__ import annotations

import base64
import binascii
import json
import logging
from datetime import date, datetime, timedelta
from pathlib import PurePosixPath
from typing import Any, NotRequired

from mcp.server.fastmcp import Image
from typing_extensions import TypedDict

from mcp_ankiconnect.ankiconnect_client import AnkiConnectClient
from mcp_ankiconnect.config import (
    ANKI_DAY_ROLLOVER_HOUR,
    MAX_BATCH_NOTES,
    MAX_STRUGGLING_SCAN,
)
from mcp_ankiconnect.server import (
    ADDITIVE,
    DESTRUCTIVE,
    EDIT,
    NETWORK,
    READ_ONLY,
    _build_note_payload,
    _card_header,
    _deck_clause,
    _ease,
    _format_note_clean,
    _front_preview,
    get_anki_client,
    handle_anki_connection_error,
    mcp,
)

logger = logging.getLogger(__name__)

_IMAGE_FORMATS = {
    "png": "png",
    "jpg": "jpeg",
    "jpeg": "jpeg",
    "gif": "gif",
    "webp": "webp",
}  # No SVG: model APIs reject image/svg+xml image blocks.


class NoteSpec(TypedDict):
    """One note for `add_notes`. Same shape as `add_note`'s arguments."""

    deckName: str
    modelName: str
    fields: dict[str, str]
    tags: NotRequired[list[str]]
    picture: NotRequired[list[dict[str, Any]]]


# --- Batch creation ---


def _missing_note_keys(notes: list[NoteSpec]) -> str | None:
    """Return an error naming the first malformed note, else None."""
    for i, note in enumerate(notes):
        missing = [k for k in ("deckName", "modelName", "fields") if not note.get(k)]
        if missing:
            return f"note at index {i} is missing {missing}"
    return None


@mcp.tool(annotations=ADDITIVE)
@handle_anki_connection_error
async def add_notes(notes: list[NoteSpec]) -> str:
    """Add up to 100 notes in one call. Prefer this over repeated `add_note`.

    Get the user's approval for the cards first, and look at `get_examples` so
    the new cards match their style. Field content gets the same conversions
    as `add_note`: `<math>` becomes MathJax, and backticks become `<code>`.

    Every note is added or rejected on its own, for example as a duplicate,
    so one bad card never sinks the batch.

    Args:
        notes: List of {deckName, modelName, fields, tags?, picture?}.

    Returns:
        JSON with counts and per-index results. Each result has status
        "added" with a noteId, or "failed" with a reason.
    """
    if not notes:
        return "SYSTEM_ERROR: `notes` must contain at least one note."
    if len(notes) > MAX_BATCH_NOTES:
        return (
            f"SYSTEM_ERROR: At most {MAX_BATCH_NOTES} notes per call "
            f"(got {len(notes)}). Split the batch."
        )
    malformed = _missing_note_keys(notes)
    if malformed is not None:
        return f"SYSTEM_ERROR: Invalid batch: {malformed}."

    payloads = [
        _build_note_payload(
            n["deckName"], n["modelName"], n["fields"], n.get("tags"), n.get("picture")
        )
        for n in notes
    ]

    async with get_anki_client() as anki:
        outcomes = await anki.add_notes_each(notes=payloads)

    results: list[dict[str, Any]] = []
    for i, (note_id, error) in enumerate(outcomes):
        if note_id:
            results.append({"index": i, "status": "added", "noteId": note_id})
        else:
            reason = error or "rejected by Anki"
            results.append({"index": i, "status": "failed", "reason": reason})

    counts = {s: sum(r["status"] == s for r in results) for s in ("added", "failed")}
    return json.dumps({**counts, "results": results}, ensure_ascii=False)


# --- Deletion ---


@mcp.tool(annotations=DESTRUCTIVE)
@handle_anki_connection_error
async def delete_notes(note_ids: list[int], confirm: bool = False) -> str:
    """Permanently delete notes and every card generated from them.

    This cannot be undone through this server. Only set `confirm=True` after
    the user has explicitly approved deleting these specific notes. To hide a
    card temporarily, use `set_suspended` instead.

    Args:
        note_ids: Note IDs (not card IDs) to delete.
        confirm: Must be True; guards against accidental deletion.
    """
    if not note_ids:
        return "SYSTEM_ERROR: `note_ids` must not be empty."
    if not confirm:
        return (
            "SYSTEM_ERROR: Deletion not performed. Ask the user to approve "
            f"deleting {len(note_ids)} note(s), then call again with confirm=True."
        )
    async with get_anki_client() as anki:
        await anki.delete_notes(notes=note_ids)
    return f"Deleted {len(note_ids)} note(s) and all their cards."


# --- Tags, decks, sync ---


@mcp.tool(annotations=READ_ONLY)
@handle_anki_connection_error
async def list_tags(contains: str | None = None) -> str:
    """List the tags in the collection, so new cards reuse existing names.

    Args:
        contains: Optional case-insensitive substring filter
            (for example "spanish").
    """
    async with get_anki_client() as anki:
        tags = await anki.get_tags()
    if contains is not None:
        needle = contains.lower()
        tags = [t for t in tags if needle in t.lower()]
    if not tags:
        return "No tags found" + (f" containing '{contains}'." if contains else ".")
    return f"{len(tags)} tag(s): " + ", ".join(sorted(tags))


@mcp.tool(annotations=EDIT)
@handle_anki_connection_error
async def create_deck(deck: str) -> str:
    """Create a deck, or a nested deck such as "Spanish::Verbs".

    If the deck already exists, nothing changes and the call still succeeds.

    Args:
        deck: Full deck name; use "::" to separate subdecks.
    """
    name = deck.strip()
    if not name:
        return "SYSTEM_ERROR: `deck` must not be empty."
    async with get_anki_client() as anki:
        deck_id = await anki.create_deck(deck=name)
    return f"Deck '{name}' is ready (ID {deck_id})."


@mcp.tool(annotations=NETWORK)
@handle_anki_connection_error
async def sync() -> str:
    """Sync the collection with AnkiWeb.

    Call this before a review session, so cards reviewed on other devices are
    included, and again afterwards. The user must be logged in to AnkiWeb in
    Anki.
    """
    async with get_anki_client() as anki:
        await anki.sync()
    return "Sync with AnkiWeb complete."


# --- Review analytics ---


def _streak(active: set[date], today: date) -> int:
    """Count consecutive review days, ending today or yesterday.

    Why yesterday counts: an unreviewed today does not break the streak
    until the day is over.
    """
    day = today if today in active else today - timedelta(days=1)
    streak = 0
    while day in active:
        streak += 1
        day -= timedelta(days=1)
    return streak


def _anki_today(now: datetime, rollover_hour: int) -> date:
    """Anki's notion of today: the local date, shifted back by the rollover.

    Why: getNumCardsReviewedByDay buckets by Anki day, so at 1am with a 4am
    rollover the reviews just done belong to yesterday's calendar date.
    """
    return (now - timedelta(hours=rollover_hour)).date()


def _summarise_review_days(rows: list[list], today: date, days: int) -> dict:
    """Turn getNumCardsReviewedByDay rows into a compact summary.

    `today` is passed in, not read from the clock, so tests are deterministic.
    """
    counts = {date.fromisoformat(d): int(n) for d, n in rows if int(n) > 0}
    start = today - timedelta(days=days - 1)
    window = sorted((d, n) for d, n in counts.items() if start <= d <= today)
    total = sum(n for _, n in window)
    return {
        "window_days": days,
        "reviewed_today": counts.get(today, 0),
        "total_in_window": total,
        "average_per_day": round(total / days, 1),
        "active_days": len(window),
        "current_streak_days": _streak(set(counts), today),
        "daily": [{"date": d.isoformat(), "reviews": n} for d, n in window],
    }


@mcp.tool(annotations=READ_ONLY)
@handle_anki_connection_error
async def get_review_stats(days: int = 14) -> str:
    """Summarise recent review activity.

    Returns today's count, the total and average over the window, the number
    of active days, the current streak and a daily series. Use it to discuss
    progress or consistency.

    Args:
        days: Size of the window in days, counting back from today
            (default 14).
    """
    if days < 1:
        return "SYSTEM_ERROR: `days` must be at least 1."
    async with get_anki_client() as anki:
        rows = await anki.get_num_cards_reviewed_by_day()
    summary = _summarise_review_days(
        rows,
        today=_anki_today(datetime.now().astimezone(), ANKI_DAY_ROLLOVER_HOUR),
        days=days,
    )
    return json.dumps(summary)


def _struggling_entry(card: dict) -> dict:
    return {
        **_card_header(card),
        "lapses": card.get("lapses", 0),
        "ease": _ease(card),
        "interval": card.get("interval"),
        "preview": _front_preview(card),
    }


def _struggling_query(min_lapses: int, deck: str | None) -> str:
    query = f"prop:lapses>={min_lapses} -is:suspended"
    return f"{query} {_deck_clause(deck)}" if deck else query


async def _scan_ids(
    anki: AnkiConnectClient, min_lapses: int, deck: str | None, limit: int
) -> tuple[int, list[int]]:
    """Return (total matches, card IDs to rank).

    The IDs are everything matching, or only the worst cards if too many.

    Why escalate: findCards cannot sort, so truncating a huge match to the
    first N IDs would rank an arbitrary subset. Raising the lapse threshold
    instead keeps exactly the cards that could make the top of the list.
    """
    ids = await anki.find_cards(query=_struggling_query(min_lapses, deck))
    total = len(ids)
    threshold = min_lapses
    while len(ids) > MAX_STRUGGLING_SCAN:
        threshold += 1
        narrower = await anki.find_cards(query=_struggling_query(threshold, deck))
        if len(narrower) < limit:
            # Too few at the next lapse count: keep those worst cards first,
            # then fill with ties at the current count (equal lapses).
            worst = set(narrower)
            ids = narrower + [i for i in ids if i not in worst]
            break
        ids = narrower
    return total, ids[:MAX_STRUGGLING_SCAN]


@mcp.tool(annotations=READ_ONLY)
@handle_anki_connection_error
async def find_struggling_cards(
    deck: str | None = None, min_lapses: int = 3, limit: int = 10
) -> str:
    """Find the cards the user keeps forgetting (leeches and near-leeches).

    Cards are ranked by lapses, most first, then by ease, lowest first.
    Suspended cards are excluded. Good next steps are to rewrite a card with
    `update_note_fields`, split it into simpler cards, or add mnemonics.
    `inspect_cards` gives the full review history.

    Args:
        deck: Optional deck to restrict to (includes subdecks).
        min_lapses: Minimum number of times forgotten (default 3).
        limit: Maximum number of cards to return (default 10).
    """
    min_lapses, limit = max(min_lapses, 0), max(limit, 1)
    async with get_anki_client() as anki:
        total, scan = await _scan_ids(anki, min_lapses, deck, limit)
        if not total:
            where = f" in deck '{deck}'" if deck else ""
            return f"No struggling cards with ≥{min_lapses} lapses{where}."
        cards = await anki.cards_info(card_ids=scan)

    ranked = sorted(cards, key=lambda c: (-c.get("lapses", 0), _ease(c)))
    payload = {
        "total_matching": total,
        "cards": [_struggling_entry(c) for c in ranked[:limit]],
    }
    return json.dumps(payload, ensure_ascii=False)


# --- Media read-back ---


@mcp.tool(annotations=READ_ONLY, structured_output=False)
@handle_anki_connection_error
async def retrieve_media_file(filename: str) -> Image | str:
    """Fetch a file from Anki's media folder. Images come back as images.

    Use this to look at an image on a card, for example `[image: x.png]` in
    `search_notes` output. Non-image files are only described.

    Args:
        filename: Media filename as referenced in the card (for example
            "diagram.png").
    """
    async with get_anki_client() as anki:
        encoded = await anki.retrieve_media_file(filename=filename)
    if not isinstance(encoded, str) or not encoded:
        return (
            f"SYSTEM_ERROR: Media file '{filename}' not found in Anki's media folder."
        )

    ext = PurePosixPath(filename).suffix.lstrip(".").lower()
    image_format = _IMAGE_FORMATS.get(ext)
    if image_format is None:
        # Size from base64 length: no need to decode a file we won't return.
        approx_bytes = len(encoded) * 3 // 4
        return f"'{filename}' exists (~{approx_bytes} bytes) but is not an image."
    try:
        return Image(data=base64.b64decode(encoded), format=image_format)
    except binascii.Error as e:
        return f"SYSTEM_ERROR: Could not decode media file '{filename}': {e}"


# --- GUI context ---


def _format_gui_card(card: dict) -> dict:
    clean = _format_note_clean(card)
    return {
        **_card_header(card),
        "modelName": clean["modelName"],
        "fields": clean["fields"],
    }


@mcp.tool(annotations=READ_ONLY)
@handle_anki_connection_error
async def get_gui_context() -> str:
    """See what the user has open in Anki right now.

    Returns the card shown in the reviewer, if any, and the note IDs selected
    in the Browse window, if any. Use this when the user says things like
    "fix this card" or "tag the ones I've selected".
    """
    # AnkiConnect already reports "nothing open" as None / [] rather than an
    # error, so genuine failures still surface through the decorator.
    async with get_anki_client() as anki:
        card = await anki.gui_current_card()
        selected = await anki.gui_selected_notes()
        if card:
            # guiCurrentCard omits the note ID, which edit tools need.
            [info] = await anki.cards_info(card_ids=[card["cardId"]])
            card = {**card, "note": info.get("note")}

    payload: dict[str, Any] = {
        "current_review_card": _format_gui_card(card) if card else None,
        "selected_note_ids": selected or [],
    }
    if card is None and not selected:
        payload["hint"] = (
            "Nothing open: ask the user to show the card in the reviewer or "
            "select notes in the Browse window."
        )
    return json.dumps(payload, ensure_ascii=False)
