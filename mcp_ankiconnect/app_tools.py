"""MCP Apps spike: a card-review page rendered inside the Claude conversation.

Why: the redesign pipeline needs a human verdict on many cards at once, and a
page with buttons is quicker than typing "1 ok, 2 reject: …" in chat. Hosts
that support MCP Apps (SEP-1865) render `ui://` HTML resources linked from a
tool's `_meta.ui.resourceUri`; other hosts just see the tool's text result.

The page only records decisions; it never writes to Anki. Applying them stays
with the model, after it reads the log, so the existing approval-then-apply
safeguards in the skills still hold.

The page speaks the MCP Apps postMessage protocol (spec 2026-01-26) by hand,
so it needs no SDK upgrade or external scripts. To check it without a real
host, load it in an iframe whose parent answers `ui/initialize`, then sends
`ui/notifications/tool-result`, and replies to `tools/call` and `ui/message`.
"""

from __future__ import annotations

import json
import os
from collections import Counter
from datetime import UTC, datetime
from importlib.resources import files
from pathlib import Path
from typing import Any, Literal, NotRequired

from typing_extensions import TypedDict

from mcp_ankiconnect.server import (
    ADDITIVE,
    READ_ONLY,
    _format_note_clean,
    get_anki_client,
    handle_anki_connection_error,
    mcp,
)

APP_MIME_TYPE = "text/html;profile=mcp-app"
CARD_REVIEW_URI = "ui://ankiconnect/card-review.html"
DEFAULT_DECISIONS_FILE = Path.home() / ".mcp-ankiconnect" / "decisions.jsonl"
MAX_REVIEW_NOTES = 50

Verdict = Literal["approve", "reject", "skip"]
_VERDICTS: frozenset[str] = frozenset({"approve", "reject", "skip"})


class CardDecision(TypedDict):
    """One verdict from the review page."""

    note_id: int
    decision: Verdict
    comment: NotRequired[str]


def _decisions_path() -> Path:
    """Where verdicts go; ANKI_DECISIONS_FILE lets an overlay choose the log."""
    override = os.getenv("ANKI_DECISIONS_FILE")
    return Path(override).expanduser() if override else DEFAULT_DECISIONS_FILE


@mcp.resource(
    CARD_REVIEW_URI,
    name="card-review",
    title="Card review",
    description="Interactive page for approving or rejecting Anki notes.",
    mime_type=APP_MIME_TYPE,
)
def card_review_page() -> str:
    """Serve the self-contained review page (no external scripts, for CSP)."""
    return files("mcp_ankiconnect").joinpath("ui/card_review.html").read_text()


@mcp.tool(
    annotations=READ_ONLY,
    meta={"ui": {"resourceUri": CARD_REVIEW_URI, "visibility": ["model", "app"]}},
)
@handle_anki_connection_error
async def open_card_review(
    note_ids: list[int], context: dict[str, str] | None = None
) -> dict[str, Any]:
    """Show notes on an approve/reject page, in hosts that render MCP Apps.

    The user's verdicts are written to the decisions log (not to Anki), and the
    page posts a summary message into the conversation when they submit. In a
    host without MCP Apps support, present the notes in chat instead.

    Args:
        note_ids: Notes to review, in display order (at most 50).
        context: Optional note ID (as a string) -> text shown under the card,
            e.g. the triage reason or a proposed redesign.
    """
    if not note_ids:
        return {"error": "SYSTEM_ERROR: `note_ids` must not be empty."}
    if len(note_ids) > MAX_REVIEW_NOTES:
        return {"error": f"SYSTEM_ERROR: at most {MAX_REVIEW_NOTES} notes per page."}

    async with get_anki_client() as anki:
        found = {n["noteId"]: n for n in await anki.notes_info(note_ids) if n}
    notes = [
        {**_format_note_clean(found[nid]), "context": (context or {}).get(str(nid))}
        for nid in note_ids
        if nid in found
    ]
    return {"notes": notes, "missing": [n for n in note_ids if n not in found]}


@mcp.tool(annotations=ADDITIVE, meta={"ui": {"visibility": ["app"]}})
@handle_anki_connection_error
async def record_card_decisions(decisions: list[CardDecision]) -> str:
    """Append the review page's verdicts to the decisions log (JSONL).

    App-only: hosts hide it from the model, so a verdict in the log always
    came from a human click. Nothing in Anki changes.

    Args:
        decisions: One entry per note: note_id, decision
            (approve/reject/skip) and an optional comment.
    """
    bad = [d for d in decisions if d.get("decision") not in _VERDICTS]
    if bad:
        return f"SYSTEM_ERROR: unknown decision(s) {bad}; use {sorted(_VERDICTS)}."

    path = _decisions_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).isoformat(timespec="seconds")
    with path.open("a", encoding="utf-8") as log:
        for d in decisions:
            log.write(json.dumps({**d, "recorded_at": stamp}) + "\n")

    counts = Counter(d["decision"] for d in decisions)
    tally = ", ".join(f"{n} {verdict}" for verdict, n in sorted(counts.items()))
    return f"Recorded {len(decisions)} decisions ({tally}) in {path}."
