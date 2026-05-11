# Card Inspection & Edit Tools — Design

**Status:** Draft, awaiting review
**Date:** 2026-05-11
**Scope:** Add MCP tools for inspecting card-level state and editing existing notes/cards. No deletion.

## Goal

The current MCP surface (`server.py`) lets an LLM *find* and *create* notes, and *review* cards, but offers nothing for inspecting per-card state (suspension, ease, scheduling, review history) or editing existing material. This change adds that capability so the LLM can answer "what's the state of this card?" and "change the tags / fields / deck / scheduling of these cards" without dropping the user into the Anki desktop UI.

## Non-goals

- Deleting notes or cards.
- Changing a note's model/note-type (rarely safe; out of scope).
- Bulk-edit UX beyond what AnkiConnect's batch endpoints already give us.
- Refactoring existing `server.py` tools.

## Tool surface

Six new MCP tools, each backed by AnkiConnect actions. All wrapped in the existing `@handle_anki_connection_error` decorator and returning `str` (JSON or human-readable summaries) to match the established pattern.

### 1. `inspect_cards`

Per-card detail for one or more cards.

- **Args:**
  - `card_ids: list[int] | None`
  - `note_ids: list[int] | None`
  - `include_history: bool = False`
- Exactly one of `card_ids` or `note_ids` must be provided. When `note_ids` is provided, the tool resolves to card IDs via an AnkiConnect `findCards` query of the form `nid:<id1>,<id2>,...` before fetching detail.
- **Backed by:** `cardsInfo` + `areSuspended` + (when `include_history`) `getReviewsOfCards`.
- **Returns:** JSON object with `cards: list[CardDetail]` where each `CardDetail` has:
  - `cardId`, `noteId`, `deck`, `modelName`
  - `suspended: bool`
  - `queue`, `type` (raw integers from AnkiConnect, plus a human-readable label like `"new"`, `"learn"`, `"review"`, `"suspended"`)
  - `ease: float` (factor / 1000)
  - `interval: int` (days)
  - `reps: int`, `lapses: int`
  - `days_until_due: int` (negative = overdue, 0 = today). Computed from AnkiConnect's `due` field and the card's queue, since AnkiConnect's raw `due` is a Julian day for review cards and a position for new cards. New cards get `null` for `days_until_due` and a separate `new_card_position` field.
  - `last_review_iso: str | None` (derived from the most recent review entry when `include_history=True`; otherwise `null` — adding it unconditionally would require a `getReviewsOfCards` call per card)
  - `reviews: list[ReviewEntry] | None` only when `include_history=True`, each entry:
    - `reviewed_at_iso: str`
    - `ease: Literal["again", "hard", "good", "easy"]`
    - `interval_days: int`
    - `time_taken_ms: int`

### 2. `update_note_fields`

Modify the text content of one note's fields.

- **Args:**
  - `note_id: int`
  - `fields: dict[str, str]` — only fields supplied are changed; others left untouched.
- Applies `_process_field_content` (existing helper) so MathJax/code formatting matches `add_note`.
- **Backed by:** `updateNoteFields`.
- **Returns:** Short summary listing the note ID and field names updated.

### 3. `update_note_tags`

Add and/or remove tags on one or more notes.

- **Args:**
  - `note_ids: list[int]`
  - `add: list[str] = []`
  - `remove: list[str] = []`
- At least one of `add` or `remove` must be non-empty.
- The same tag MUST NOT appear in both `add` and `remove` (validation error).
- **Backed by:** `addTags` and/or `removeTags`. Tags joined with single spaces under the hood (AnkiConnect's expected format).
- **Returns:** Summary like `"Updated tags on 3 notes — added: [physics, mechanics]; removed: [draft]"`.

### 4. `set_suspended`

Suspend or unsuspend one or more cards.

- **Args:**
  - `card_ids: list[int]`
  - `suspended: bool`
- **Backed by:** `suspend` when `suspended=True`, otherwise `unsuspend`.
- **Returns:** Summary like `"Suspended 5 cards"` / `"Unsuspended 5 cards"`.

### 5. `change_deck`

Move cards to a different deck.

- **Args:**
  - `card_ids: list[int]`
  - `deck: str`
- Operates on card IDs (mirrors AnkiConnect). The tool description tells the LLM to call `inspect_cards(note_ids=...)` first if it only has note IDs, since a single note's cards can live in different decks.
- **Backed by:** `changeDeck`.
- **Returns:** Summary like `"Moved 4 cards to deck 'Spanish::Verbs'"`.

### 6. `reschedule_cards`

Manipulate scheduling on cards.

- **Args:**
  - `card_ids: list[int]`
  - `mode: Literal["set_due", "forget", "relearn"]`
  - `due: str | None = None` — required when `mode="set_due"`. AnkiConnect's `setDueDate` "days" spec: `"1"` (1 day from now), `"1-7"` (random in range), `"3!"` (reset interval). Documented in the tool docstring.
- **Backed by:** `setDueDate`, `forgetCards`, or `relearnCards` depending on `mode`.
- **Returns:** Summary describing the action taken and affected card count.

## Client additions (`ankiconnect_client.py`)

New `AnkiAction` enum members:

```python
UPDATE_NOTE_FIELDS   = "updateNoteFields"
ADD_TAGS             = "addTags"
REMOVE_TAGS          = "removeTags"
SUSPEND              = "suspend"
UNSUSPEND            = "unsuspend"
ARE_SUSPENDED        = "areSuspended"
CHANGE_DECK          = "changeDeck"
SET_DUE_DATE         = "setDueDate"
FORGET_CARDS         = "forgetCards"
RELEARN_CARDS        = "relearnCards"
GET_REVIEWS_OF_CARDS = "getReviewsOfCards"
```

Thin async wrappers mirror existing style (`update_note_fields(note: dict)`, `add_tags(notes: list[int], tags: str)`, etc.). No defensive try/except — `invoke()` handles connection/API errors.

## File layout

```
mcp_ankiconnect/
  edit_tools.py        ← new: 6 @mcp.tool definitions + private helpers
  server.py            ← unchanged; the `mcp` instance is re-exported as today
  main.py              ← imports edit_tools so the registration side-effects run
tests/
  test_edit_tools.py   ← new
```

`edit_tools.py` imports `mcp` from `mcp_ankiconnect.server` and registers its tools against the same FastMCP instance. `main.py` adds an `import mcp_ankiconnect.edit_tools  # noqa: F401` after `from mcp_ankiconnect.server import mcp` to ensure registration runs before `mcp.run()`.

## Error handling

- All tools wrapped with `@handle_anki_connection_error` (existing decorator).
- Tool-level validation errors (e.g., empty `card_ids`, conflicting `add`/`remove` tags, missing `due` when `mode="set_due"`, both `card_ids` and `note_ids` supplied to `inspect_cards`, neither supplied) return a `SYSTEM_ERROR: ...` string. This matches `submit_reviews` precedent — tools never raise.
- AnkiConnect-level errors (note doesn't exist, deck doesn't exist, etc.) surface as `ValueError` from `invoke()` and are caught by the decorator and rendered as `SYSTEM_ERROR: ...`.

## Output conventions

- `inspect_cards` returns JSON (`json.dumps(..., indent=2, ensure_ascii=False)`), like `search_notes`.
- All edit tools return short human-readable summaries containing the affected IDs so the user can verify outcomes.
- Failures always begin with `SYSTEM_ERROR:` so the LLM can detect them programmatically.

## Testing

`tests/test_edit_tools.py`, mirroring existing tests' use of `monkeypatch` / `AsyncMock` to stub `AnkiConnectClient.invoke`.

Per tool:

- Happy path (the tool calls `invoke` with the expected action and params, returns expected summary/JSON).
- Validation error (returns `SYSTEM_ERROR: ...`, does NOT call `invoke`).
- AnkiConnect API error (`invoke` raises `ValueError` → decorator returns `SYSTEM_ERROR: ...`).
- Connection error (`invoke` raises `AnkiConnectionError` → decorator returns `SYSTEM_ERROR: Cannot connect to Anki`).

Plus one integration-style test for `inspect_cards` exercising the `note_ids → card_ids` resolution path (mocks `findCards`, `cardsInfo`, `areSuspended`).

## Open questions

None. All decisions resolved in brainstorming:

- Granularity → several focused tools.
- Safety → trust the LLM; no dry-run.
- Scope → inspect + update_fields + update_tags + set_suspended + change_deck + reschedule_cards. No deletion.
- File layout → new `edit_tools.py`, existing `server.py` untouched.
- `change_deck` takes card IDs (mirrors AnkiConnect; no hidden note→card resolution).
- `reschedule_cards` is a single tool with a `mode` enum.

## Implementation order (suggested for the plan phase)

1. Add `AnkiAction` enum members + client wrappers.
2. Add `edit_tools.py` with `inspect_cards` (the read-only one, unblocks all the edit flows).
3. Add the five edit tools.
4. Tests alongside each step.
5. Update `README.md` to list the new tools.
