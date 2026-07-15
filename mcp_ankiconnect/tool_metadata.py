"""Shared MCP metadata used by the server and every registered tool."""

from mcp.types import ToolAnnotations


SERVER_INSTRUCTIONS = (
    "Use these tools to inspect and modify the user's Anki collection. Before "
    "adding notes, identify the target deck, note type, and required fields; "
    "call list_decks_and_notes when unknown. When creating flashcards from "
    "supplied material, draft concise cards, check likely duplicates with "
    "search_notes, and save with add_note. Use get_examples to match existing "
    "style. Before editing, use search_notes to find note IDs, then call "
    "inspect_cards(note_ids=...) to resolve card IDs and state. Report successes "
    "and failures, including returned note IDs. "
    "For review sessions, call fetch_due_cards_for_review before submit_reviews "
    "and submit only ratings supplied or confirmed by the user."
)


READ_ONLY = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=False,
)

ADDITIVE_WRITE = ToolAnnotations(
    readOnlyHint=False,
    destructiveHint=False,
    idempotentHint=False,
    openWorldHint=False,
)

DESTRUCTIVE_WRITE = ToolAnnotations(
    readOnlyHint=False,
    destructiveHint=True,
    idempotentHint=False,
    openWorldHint=False,
)

DESTRUCTIVE_IDEMPOTENT_WRITE = ToolAnnotations(
    readOnlyHint=False,
    destructiveHint=True,
    idempotentHint=True,
    openWorldHint=False,
)

# Media inputs can read arbitrary URLs or local paths. These tools can also
# replace an existing Anki media file when given the same filename.
DESTRUCTIVE_OPEN_WORLD_WRITE = ToolAnnotations(
    readOnlyHint=False,
    destructiveHint=True,
    idempotentHint=False,
    openWorldHint=True,
)
