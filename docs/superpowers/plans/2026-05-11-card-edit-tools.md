# Card Inspection & Edit Tools Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add six MCP tools — `inspect_cards`, `update_note_fields`, `update_note_tags`, `set_suspended`, `change_deck`, `reschedule_cards` — so an LLM can read per-card state and modify existing notes/cards via AnkiConnect.

**Architecture:** New `mcp_ankiconnect/edit_tools.py` registers tools against the existing FastMCP `mcp` instance from `server.py`. New `AnkiAction` enum members + thin async wrappers added to `ankiconnect_client.py`. `main.py` imports `edit_tools` so registration side-effects run before `mcp.run()`. Existing `server.py` is untouched.

**Tech Stack:** Python ≥3.10, FastMCP (`mcp.server.fastmcp`), `httpx`, `pydantic`, `pytest`/`pytest-asyncio` (`asyncio_mode=auto`).

**Spec reference:** `docs/superpowers/specs/2026-05-11-card-edit-tools-design.md`

**Refinement vs. spec:** The spec called for `inspect_cards` to return `days_until_due`. Computing this accurately requires AnkiConnect's collection-creation timestamp (since `cardsInfo`'s raw `due` is days-since-collection-creation for review cards and a position integer for new cards). Rather than wire that up, this plan returns the raw `due` field alongside `queue` and a derived `queue_label` (`"new"`, `"learn"`, `"review"`, `"day_learn"`, `"suspended"`, `"buried_user"`, `"buried_sched"`). The LLM can interpret. `last_review_iso` is still derived from `getReviewsOfCards` when `include_history=True`.

---

## File Structure

**Modified:**
- `mcp_ankiconnect/ankiconnect_client.py` — add 11 new `AnkiAction` enum members + thin async wrapper methods.
- `mcp_ankiconnect/main.py` — add an `import mcp_ankiconnect.edit_tools  # noqa: F401` so tool registration runs.
- `README.md` — list the 6 new tools.

**Created:**
- `mcp_ankiconnect/edit_tools.py` — `@mcp.tool` definitions for the 6 new tools + private helpers (queue-label mapping, review-entry formatting, note→card resolution).
- `tests/test_edit_tools.py` — unit tests for all 6 tools (happy path, validation error, API error, connection error).

**Untouched:** `server.py`, `config.py`, `server_prompts.py`, existing tests.

---

## Task 1: Extend AnkiConnect Client

**Files:**
- Modify: `mcp_ankiconnect/ankiconnect_client.py` (the `AnkiAction` enum near line 43; wrapper methods after line 241)
- Test: `tests/test_ankiconnect_client.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_ankiconnect_client.py`:

```python
import pytest
from unittest.mock import AsyncMock, patch

from mcp_ankiconnect.ankiconnect_client import AnkiAction, AnkiConnectClient


@pytest.fixture
def client_with_mocked_invoke():
    client = AnkiConnectClient(base_url="http://test")
    client.invoke = AsyncMock()
    return client


async def test_update_note_fields_wrapper(client_with_mocked_invoke):
    client_with_mocked_invoke.invoke.return_value = None
    note = {"id": 1, "fields": {"Front": "Q"}}
    await client_with_mocked_invoke.update_note_fields(note=note)
    client_with_mocked_invoke.invoke.assert_awaited_once_with(
        AnkiAction.UPDATE_NOTE_FIELDS, note=note
    )


async def test_add_tags_wrapper(client_with_mocked_invoke):
    client_with_mocked_invoke.invoke.return_value = None
    await client_with_mocked_invoke.add_tags(notes=[1, 2], tags="physics mechanics")
    client_with_mocked_invoke.invoke.assert_awaited_once_with(
        AnkiAction.ADD_TAGS, notes=[1, 2], tags="physics mechanics"
    )


async def test_remove_tags_wrapper(client_with_mocked_invoke):
    client_with_mocked_invoke.invoke.return_value = None
    await client_with_mocked_invoke.remove_tags(notes=[1, 2], tags="draft")
    client_with_mocked_invoke.invoke.assert_awaited_once_with(
        AnkiAction.REMOVE_TAGS, notes=[1, 2], tags="draft"
    )


async def test_suspend_wrapper(client_with_mocked_invoke):
    client_with_mocked_invoke.invoke.return_value = True
    await client_with_mocked_invoke.suspend(cards=[10, 11])
    client_with_mocked_invoke.invoke.assert_awaited_once_with(
        AnkiAction.SUSPEND, cards=[10, 11]
    )


async def test_unsuspend_wrapper(client_with_mocked_invoke):
    client_with_mocked_invoke.invoke.return_value = True
    await client_with_mocked_invoke.unsuspend(cards=[10, 11])
    client_with_mocked_invoke.invoke.assert_awaited_once_with(
        AnkiAction.UNSUSPEND, cards=[10, 11]
    )


async def test_are_suspended_wrapper(client_with_mocked_invoke):
    client_with_mocked_invoke.invoke.return_value = [True, False]
    result = await client_with_mocked_invoke.are_suspended(cards=[10, 11])
    client_with_mocked_invoke.invoke.assert_awaited_once_with(
        AnkiAction.ARE_SUSPENDED, cards=[10, 11]
    )
    assert result == [True, False]


async def test_change_deck_wrapper(client_with_mocked_invoke):
    client_with_mocked_invoke.invoke.return_value = None
    await client_with_mocked_invoke.change_deck(cards=[10, 11], deck="Spanish::Verbs")
    client_with_mocked_invoke.invoke.assert_awaited_once_with(
        AnkiAction.CHANGE_DECK, cards=[10, 11], deck="Spanish::Verbs"
    )


async def test_set_due_date_wrapper(client_with_mocked_invoke):
    client_with_mocked_invoke.invoke.return_value = True
    await client_with_mocked_invoke.set_due_date(cards=[10], days="1-7")
    client_with_mocked_invoke.invoke.assert_awaited_once_with(
        AnkiAction.SET_DUE_DATE, cards=[10], days="1-7"
    )


async def test_forget_cards_wrapper(client_with_mocked_invoke):
    client_with_mocked_invoke.invoke.return_value = None
    await client_with_mocked_invoke.forget_cards(cards=[10])
    client_with_mocked_invoke.invoke.assert_awaited_once_with(
        AnkiAction.FORGET_CARDS, cards=[10]
    )


async def test_relearn_cards_wrapper(client_with_mocked_invoke):
    client_with_mocked_invoke.invoke.return_value = None
    await client_with_mocked_invoke.relearn_cards(cards=[10])
    client_with_mocked_invoke.invoke.assert_awaited_once_with(
        AnkiAction.RELEARN_CARDS, cards=[10]
    )


async def test_get_reviews_of_cards_wrapper(client_with_mocked_invoke):
    client_with_mocked_invoke.invoke.return_value = {"10": []}
    result = await client_with_mocked_invoke.get_reviews_of_cards(cards=[10])
    client_with_mocked_invoke.invoke.assert_awaited_once_with(
        AnkiAction.GET_REVIEWS_OF_CARDS, cards=[10]
    )
    assert result == {"10": []}
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run --frozen pytest tests/test_ankiconnect_client.py -v -k "wrapper"`
Expected: All new wrapper tests fail with `AttributeError` on `AnkiAction.UPDATE_NOTE_FIELDS` (or whichever enum is referenced first).

- [ ] **Step 3: Add `AnkiAction` enum members**

In `mcp_ankiconnect/ankiconnect_client.py`, in the `AnkiAction` enum block, add (preserving existing members):

```python
class AnkiAction(str, Enum):
    DECK_NAMES = "deckNames"
    FIND_CARDS = "findCards"
    CARDS_INFO = "cardsInfo"
    ANSWER_CARDS = "answerCards"
    MODEL_NAMES = "modelNames"
    MODEL_FIELD_NAMES = "modelFieldNames"
    ADD_NOTE = "addNote"
    FIND_NOTES = "findNotes"
    NOTES_INFO = "notesInfo"
    STORE_MEDIA_FILE = "storeMediaFile"
    # --- edit / inspect additions ---
    UPDATE_NOTE_FIELDS = "updateNoteFields"
    ADD_TAGS = "addTags"
    REMOVE_TAGS = "removeTags"
    SUSPEND = "suspend"
    UNSUSPEND = "unsuspend"
    ARE_SUSPENDED = "areSuspended"
    CHANGE_DECK = "changeDeck"
    SET_DUE_DATE = "setDueDate"
    FORGET_CARDS = "forgetCards"
    RELEARN_CARDS = "relearnCards"
    GET_REVIEWS_OF_CARDS = "getReviewsOfCards"
```

- [ ] **Step 4: Add wrapper methods**

In `mcp_ankiconnect/ankiconnect_client.py`, append before the `close()` method (i.e., after `store_media_file`):

```python
    # --- Edit / inspect wrappers ---
    async def update_note_fields(self, note: dict) -> None:
        """note must be {"id": int, "fields": {field_name: value, ...}}."""
        return await self.invoke(AnkiAction.UPDATE_NOTE_FIELDS, note=note)

    async def add_tags(self, notes: List[int], tags: str) -> None:
        """`tags` is a space-separated string (AnkiConnect's format)."""
        return await self.invoke(AnkiAction.ADD_TAGS, notes=notes, tags=tags)

    async def remove_tags(self, notes: List[int], tags: str) -> None:
        return await self.invoke(AnkiAction.REMOVE_TAGS, notes=notes, tags=tags)

    async def suspend(self, cards: List[int]) -> bool:
        return await self.invoke(AnkiAction.SUSPEND, cards=cards)

    async def unsuspend(self, cards: List[int]) -> bool:
        return await self.invoke(AnkiAction.UNSUSPEND, cards=cards)

    async def are_suspended(self, cards: List[int]) -> List[Optional[bool]]:
        return await self.invoke(AnkiAction.ARE_SUSPENDED, cards=cards)

    async def change_deck(self, cards: List[int], deck: str) -> None:
        return await self.invoke(AnkiAction.CHANGE_DECK, cards=cards, deck=deck)

    async def set_due_date(self, cards: List[int], days: str) -> bool:
        """`days` examples: "1" (1 day from now), "1-7" (random in range), "3!" (reset interval)."""
        return await self.invoke(AnkiAction.SET_DUE_DATE, cards=cards, days=days)

    async def forget_cards(self, cards: List[int]) -> None:
        return await self.invoke(AnkiAction.FORGET_CARDS, cards=cards)

    async def relearn_cards(self, cards: List[int]) -> None:
        return await self.invoke(AnkiAction.RELEARN_CARDS, cards=cards)

    async def get_reviews_of_cards(self, cards: List[int]) -> dict:
        """Returns {card_id_str: [review_entry_dict, ...]}."""
        return await self.invoke(AnkiAction.GET_REVIEWS_OF_CARDS, cards=cards)
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run --frozen pytest tests/test_ankiconnect_client.py -v`
Expected: All tests pass (existing + new wrappers).

- [ ] **Step 6: Run ruff to ensure clean formatting/lint**

Run: `uv run ruff check --fix mcp_ankiconnect/ankiconnect_client.py tests/test_ankiconnect_client.py && uv run ruff format mcp_ankiconnect/ankiconnect_client.py tests/test_ankiconnect_client.py`
Expected: No errors.

- [ ] **Step 7: Commit**

```bash
git add mcp_ankiconnect/ankiconnect_client.py tests/test_ankiconnect_client.py
git commit -m "feat: Add AnkiConnect client wrappers for note/card edit actions"
```

---

## Task 2: Scaffold `edit_tools.py` and register import

**Files:**
- Create: `mcp_ankiconnect/edit_tools.py`
- Modify: `mcp_ankiconnect/main.py`
- Test: `tests/test_edit_tools.py`

- [ ] **Step 1: Write a failing smoke test that imports the module**

Create `tests/test_edit_tools.py` with:

```python
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mcp_ankiconnect.ankiconnect_client import (
    AnkiConnectClient,
    AnkiConnectionError,
)


@pytest.fixture
def mock_anki_client():
    mock = MagicMock(spec=AnkiConnectClient)
    mock.find_cards = AsyncMock()
    mock.cards_info = AsyncMock()
    mock.are_suspended = AsyncMock()
    mock.get_reviews_of_cards = AsyncMock()
    mock.update_note_fields = AsyncMock()
    mock.add_tags = AsyncMock()
    mock.remove_tags = AsyncMock()
    mock.suspend = AsyncMock()
    mock.unsuspend = AsyncMock()
    mock.change_deck = AsyncMock()
    mock.set_due_date = AsyncMock()
    mock.forget_cards = AsyncMock()
    mock.relearn_cards = AsyncMock()
    mock.close = AsyncMock()
    return mock


@pytest.fixture(autouse=True)
def patch_get_anki_client(mock_anki_client):
    with patch("mcp_ankiconnect.edit_tools.get_anki_client") as cm:
        cm.return_value.__aenter__.return_value = mock_anki_client
        cm.return_value.__aexit__ = AsyncMock(return_value=None)
        yield cm


def test_module_imports_and_registers_tools():
    """edit_tools must import cleanly and contribute its tools to the shared FastMCP instance."""
    import mcp_ankiconnect.edit_tools  # noqa: F401
    from mcp_ankiconnect.edit_tools import (
        change_deck,
        inspect_cards,
        reschedule_cards,
        set_suspended,
        update_note_fields,
        update_note_tags,
    )
    # Existence is enough at this stage.
    assert all(
        callable(t)
        for t in (
            inspect_cards,
            update_note_fields,
            update_note_tags,
            set_suspended,
            change_deck,
            reschedule_cards,
        )
    )
```

- [ ] **Step 2: Run the smoke test to verify it fails**

Run: `uv run --frozen pytest tests/test_edit_tools.py::test_module_imports_and_registers_tools -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'mcp_ankiconnect.edit_tools'`.

- [ ] **Step 3: Create the scaffold**

Create `mcp_ankiconnect/edit_tools.py`:

```python
"""MCP tools for inspecting and editing existing Anki notes/cards.

These tools register against the shared FastMCP instance defined in
`mcp_ankiconnect.server`. Import this module to install the tools.
"""

from __future__ import annotations

import logging
from typing import Literal

from mcp_ankiconnect.server import (
    get_anki_client,
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
```

- [ ] **Step 4: Wire registration into `main.py`**

Modify `mcp_ankiconnect/main.py` to:

```python
import logging

from mcp_ankiconnect.server import mcp
import mcp_ankiconnect.edit_tools  # noqa: F401  # registers edit/inspect tools

logger = logging.getLogger(__name__)


def main():
    """Main entry point for the package."""
    logger.info("Starting MCP-AnkiConnect server")
    mcp.run()


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Run the smoke test to verify it passes**

Run: `uv run --frozen pytest tests/test_edit_tools.py::test_module_imports_and_registers_tools -v`
Expected: PASS.

- [ ] **Step 6: Run lint/format**

Run: `uv run ruff check --fix mcp_ankiconnect/edit_tools.py mcp_ankiconnect/main.py tests/test_edit_tools.py && uv run ruff format mcp_ankiconnect/edit_tools.py mcp_ankiconnect/main.py tests/test_edit_tools.py`
Expected: No errors.

- [ ] **Step 7: Commit**

```bash
git add mcp_ankiconnect/edit_tools.py mcp_ankiconnect/main.py tests/test_edit_tools.py
git commit -m "feat: Scaffold edit_tools module with stub tool registrations"
```

---

## Task 3: Implement `inspect_cards`

**Files:**
- Modify: `mcp_ankiconnect/edit_tools.py`
- Test: `tests/test_edit_tools.py`

`cardsInfo` reference (AnkiConnect, version 6) returns a list of dicts per card, each with fields like:

```python
{
    "cardId": 1498938915662,
    "fields": {"Front": {"value": "...", "order": 0}, "Back": {...}},
    "fieldOrder": 0,
    "question": "...",
    "answer": "...",
    "modelName": "Basic",
    "deckName": "Default",
    "css": "...",
    "factor": 2500,        # ease × 1000 (0 for new cards)
    "interval": 14,        # days
    "type": 2,             # 0=new, 1=learn, 2=review, 3=relearn
    "queue": 2,            # 0=new, 1=(daily)learn, 2=review, 3=day-learn, -1=suspended, -2=buried(sched), -3=buried(user)
    "due": 365,            # raw scheduler "due" (meaning depends on queue/type)
    "reps": 20,
    "lapses": 1,
    "mod": 1730481234,     # last modification, unix seconds
    "note": 1498938915001,
}
```

`getReviewsOfCards` (version 6) returns `{card_id_string: [review_entry_dict, ...]}`. Each review entry:

```python
{
    "id": 1730481234567,     # review timestamp in ms (becomes the timestamp)
    "usn": 12,
    "ease": 3,               # 1=again, 2=hard, 3=good, 4=easy
    "ivl": 14,               # interval after this review (negative => seconds when learning)
    "lastIvl": 7,
    "factor": 2500,
    "time": 4200,            # time taken to answer in ms
    "type": 1,               # 0=learn, 1=review, 2=relearn, 3=cram
}
```

- [ ] **Step 1: Write failing tests for the helpers and the tool**

Append to `tests/test_edit_tools.py`:

```python
import json

from mcp_ankiconnect.edit_tools import (
    _format_review_entry,
    _queue_label,
    inspect_cards,
)


def test_queue_label_known_values():
    assert _queue_label(0) == "new"
    assert _queue_label(1) == "learn"
    assert _queue_label(2) == "review"
    assert _queue_label(3) == "day_learn"
    assert _queue_label(-1) == "suspended"
    assert _queue_label(-2) == "buried_sched"
    assert _queue_label(-3) == "buried_user"
    assert _queue_label(999) == "unknown"


def test_format_review_entry_translates_ease_and_timestamp():
    raw = {
        "id": 1730481234567,
        "ease": 3,
        "ivl": 14,
        "time": 4200,
    }
    out = _format_review_entry(raw)
    assert out["ease"] == "good"
    assert out["interval_days"] == 14
    assert out["time_taken_ms"] == 4200
    assert out["reviewed_at_iso"].startswith("2024")  # 2024-11-01-ish — sanity


async def test_inspect_cards_requires_exactly_one_of_card_ids_or_note_ids(
    mock_anki_client,
):
    result = await inspect_cards()
    assert result.startswith("SYSTEM_ERROR:")
    assert "card_ids" in result and "note_ids" in result
    mock_anki_client.cards_info.assert_not_awaited()

    result_both = await inspect_cards(card_ids=[1], note_ids=[2])
    assert result_both.startswith("SYSTEM_ERROR:")


async def test_inspect_cards_by_card_ids_happy_path(mock_anki_client):
    mock_anki_client.cards_info.return_value = [
        {
            "cardId": 100,
            "note": 200,
            "deckName": "Default",
            "modelName": "Basic",
            "queue": 2,
            "type": 2,
            "factor": 2500,
            "interval": 14,
            "reps": 20,
            "lapses": 1,
            "due": 365,
            "mod": 1730481234,
        }
    ]
    mock_anki_client.are_suspended.return_value = [False]

    result = await inspect_cards(card_ids=[100])
    payload = json.loads(result)
    assert payload["cards"][0]["cardId"] == 100
    assert payload["cards"][0]["noteId"] == 200
    assert payload["cards"][0]["deck"] == "Default"
    assert payload["cards"][0]["suspended"] is False
    assert payload["cards"][0]["queue_label"] == "review"
    assert payload["cards"][0]["ease"] == 2.5
    assert payload["cards"][0]["interval"] == 14
    assert payload["cards"][0]["reps"] == 20
    assert payload["cards"][0]["lapses"] == 1
    assert payload["cards"][0]["raw_due"] == 365
    # No history requested
    assert payload["cards"][0]["reviews"] is None
    assert payload["cards"][0]["last_review_iso"] is None
    mock_anki_client.get_reviews_of_cards.assert_not_awaited()


async def test_inspect_cards_by_note_ids_resolves_via_find_cards(mock_anki_client):
    mock_anki_client.find_cards.return_value = [100, 101]
    mock_anki_client.cards_info.return_value = [
        {
            "cardId": 100,
            "note": 200,
            "deckName": "D",
            "modelName": "M",
            "queue": 0,
            "type": 0,
            "factor": 0,
            "interval": 0,
            "reps": 0,
            "lapses": 0,
            "due": 5,
            "mod": 1730481234,
        },
        {
            "cardId": 101,
            "note": 200,
            "deckName": "D",
            "modelName": "M",
            "queue": 0,
            "type": 0,
            "factor": 0,
            "interval": 0,
            "reps": 0,
            "lapses": 0,
            "due": 6,
            "mod": 1730481234,
        },
    ]
    mock_anki_client.are_suspended.return_value = [False, False]

    await inspect_cards(note_ids=[200])
    mock_anki_client.find_cards.assert_awaited_once_with(query="nid:200")
    mock_anki_client.cards_info.assert_awaited_once_with(card_ids=[100, 101])


async def test_inspect_cards_with_history(mock_anki_client):
    mock_anki_client.cards_info.return_value = [
        {
            "cardId": 100,
            "note": 200,
            "deckName": "D",
            "modelName": "M",
            "queue": 2,
            "type": 2,
            "factor": 2500,
            "interval": 14,
            "reps": 2,
            "lapses": 0,
            "due": 365,
            "mod": 1730481234,
        }
    ]
    mock_anki_client.are_suspended.return_value = [False]
    mock_anki_client.get_reviews_of_cards.return_value = {
        "100": [
            {"id": 1730000000000, "ease": 3, "ivl": 7, "time": 4000},
            {"id": 1730481234567, "ease": 4, "ivl": 14, "time": 3000},
        ]
    }

    result = await inspect_cards(card_ids=[100], include_history=True)
    payload = json.loads(result)
    card = payload["cards"][0]
    assert card["reviews"] is not None
    assert len(card["reviews"]) == 2
    # Last review = most recent by timestamp
    assert card["last_review_iso"] == card["reviews"][1]["reviewed_at_iso"]
    assert card["reviews"][1]["ease"] == "easy"


async def test_inspect_cards_connection_error(mock_anki_client):
    mock_anki_client.cards_info.side_effect = AnkiConnectionError("nope")
    result = await inspect_cards(card_ids=[100])
    assert result.startswith("SYSTEM_ERROR: Cannot connect to Anki")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run --frozen pytest tests/test_edit_tools.py -v -k "inspect or queue_label or format_review"`
Expected: All fail — `_queue_label`, `_format_review_entry` don't exist; `inspect_cards` returns the stub error.

- [ ] **Step 3: Implement helpers and `inspect_cards`**

Add the following imports to the top of `mcp_ankiconnect/edit_tools.py` (alongside the existing imports added in Task 2):

```python
import json
from datetime import datetime, timezone
```

Then replace the stub `inspect_cards` with the helpers and full implementation:

```python
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
    reviewed_at = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).isoformat()
    return {
        "reviewed_at_iso": reviewed_at,
        "ease": _EASE_LABELS.get(entry.get("ease", 0), "unknown"),
        "interval_days": entry.get("ivl", 0),
        "time_taken_ms": entry.get("time", 0),
    }


@mcp.tool()
@handle_anki_connection_error
async def inspect_cards(
    card_ids: list[int] | None = None,
    note_ids: list[int] | None = None,
    include_history: bool = False,
) -> str:
    """Inspect per-card state: deck, model, suspension, ease, scheduling, optional review history.

    Provide EXACTLY ONE of `card_ids` or `note_ids`. When `note_ids` is given, the tool
    resolves to all cards belonging to those notes via `nid:` query.

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
            "SYSTEM_ERROR: Provide exactly one of `card_ids` or `note_ids` (not both, not neither)."
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
                    card.get("mod", 0), tz=timezone.utc
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
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run --frozen pytest tests/test_edit_tools.py -v -k "inspect or queue_label or format_review"`
Expected: PASS.

- [ ] **Step 5: Run lint/format and the full test suite**

Run: `uv run ruff check --fix mcp_ankiconnect/edit_tools.py tests/test_edit_tools.py && uv run ruff format mcp_ankiconnect/edit_tools.py tests/test_edit_tools.py && uv run --frozen pytest`
Expected: All green.

- [ ] **Step 6: Commit**

```bash
git add mcp_ankiconnect/edit_tools.py tests/test_edit_tools.py
git commit -m "feat: Add inspect_cards MCP tool for per-card state and review history"
```

---

## Task 4: Implement `update_note_fields`

**Files:**
- Modify: `mcp_ankiconnect/edit_tools.py`
- Test: `tests/test_edit_tools.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_edit_tools.py`:

```python
from mcp_ankiconnect.edit_tools import update_note_fields


async def test_update_note_fields_empty_fields_dict_returns_error(mock_anki_client):
    result = await update_note_fields(note_id=200, fields={})
    assert result.startswith("SYSTEM_ERROR:")
    assert "fields" in result.lower()
    mock_anki_client.update_note_fields.assert_not_awaited()


async def test_update_note_fields_processes_content_and_invokes_client(mock_anki_client):
    mock_anki_client.update_note_fields.return_value = None
    result = await update_note_fields(
        note_id=200,
        fields={"Front": "What is `x`?", "Back": "<math>x = 1</math>"},
    )
    mock_anki_client.update_note_fields.assert_awaited_once()
    call_kwargs = mock_anki_client.update_note_fields.await_args.kwargs
    note = call_kwargs["note"]
    assert note["id"] == 200
    # Inline code transformed
    assert note["fields"]["Front"] == "What is <code>x</code>?"
    # MathJax transformed
    assert note["fields"]["Back"] == "\\(x = 1\\)"
    assert "200" in result
    assert "Front" in result and "Back" in result


async def test_update_note_fields_api_error(mock_anki_client):
    mock_anki_client.update_note_fields.side_effect = ValueError(
        "AnkiConnect error: note was not found"
    )
    result = await update_note_fields(note_id=999, fields={"Front": "hi"})
    assert result.startswith("SYSTEM_ERROR:")
    assert "note was not found" in result
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run --frozen pytest tests/test_edit_tools.py -v -k "update_note_fields"`
Expected: All three fail (stub returns the not-implemented error).

- [ ] **Step 3: Implement `update_note_fields`**

Add this import to the top of `mcp_ankiconnect/edit_tools.py` (in the existing block that imports from `mcp_ankiconnect.server`):

```python
from mcp_ankiconnect.server import (
    get_anki_client,
    handle_anki_connection_error,
    mcp,
    _process_field_content,
)
```

(I.e., add `_process_field_content` to that already-existing import list.)

Replace the stub `update_note_fields` with:

```python
@mcp.tool()
@handle_anki_connection_error
async def update_note_fields(
    note_id: int,
    fields: dict[str, str],
) -> str:
    """Update the text content of one or more fields on an existing note.

    Only fields you pass in are changed; omitted fields are left alone. MathJax
    (`<math>...</math>`) and code blocks/inline code are auto-converted to the
    same HTML representations used by `add_note`.

    Args:
        note_id: Anki note ID (not a card ID).
        fields: Mapping of field name -> new value.
    """
    if not fields:
        return "SYSTEM_ERROR: `fields` must contain at least one field to update."

    processed = {name: _process_field_content(value) for name, value in fields.items()}
    payload = {"id": note_id, "fields": processed}

    async with get_anki_client() as anki:
        await anki.update_note_fields(note=payload)
        field_list = ", ".join(sorted(fields.keys()))
        return f"Updated note {note_id}. Fields modified: {field_list}."
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run --frozen pytest tests/test_edit_tools.py -v -k "update_note_fields"`
Expected: PASS.

- [ ] **Step 5: Lint/format and run full suite**

Run: `uv run ruff check --fix mcp_ankiconnect/edit_tools.py tests/test_edit_tools.py && uv run ruff format mcp_ankiconnect/edit_tools.py tests/test_edit_tools.py && uv run --frozen pytest`
Expected: All green.

- [ ] **Step 6: Commit**

```bash
git add mcp_ankiconnect/edit_tools.py tests/test_edit_tools.py
git commit -m "feat: Add update_note_fields MCP tool"
```

---

## Task 5: Implement `update_note_tags`

**Files:**
- Modify: `mcp_ankiconnect/edit_tools.py`
- Test: `tests/test_edit_tools.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_edit_tools.py`:

```python
from mcp_ankiconnect.edit_tools import update_note_tags


async def test_update_note_tags_requires_add_or_remove(mock_anki_client):
    result = await update_note_tags(note_ids=[1, 2])
    assert result.startswith("SYSTEM_ERROR:")
    mock_anki_client.add_tags.assert_not_awaited()
    mock_anki_client.remove_tags.assert_not_awaited()


async def test_update_note_tags_empty_note_ids(mock_anki_client):
    result = await update_note_tags(note_ids=[], add=["x"])
    assert result.startswith("SYSTEM_ERROR:")
    mock_anki_client.add_tags.assert_not_awaited()


async def test_update_note_tags_rejects_overlap(mock_anki_client):
    result = await update_note_tags(note_ids=[1], add=["draft"], remove=["draft"])
    assert result.startswith("SYSTEM_ERROR:")
    assert "draft" in result
    mock_anki_client.add_tags.assert_not_awaited()
    mock_anki_client.remove_tags.assert_not_awaited()


async def test_update_note_tags_add_only(mock_anki_client):
    mock_anki_client.add_tags.return_value = None
    result = await update_note_tags(note_ids=[1, 2], add=["physics", "mechanics"])
    mock_anki_client.add_tags.assert_awaited_once_with(
        notes=[1, 2], tags="physics mechanics"
    )
    mock_anki_client.remove_tags.assert_not_awaited()
    assert "2 notes" in result
    assert "physics" in result and "mechanics" in result


async def test_update_note_tags_remove_only(mock_anki_client):
    mock_anki_client.remove_tags.return_value = None
    result = await update_note_tags(note_ids=[1], remove=["draft"])
    mock_anki_client.remove_tags.assert_awaited_once_with(notes=[1], tags="draft")
    mock_anki_client.add_tags.assert_not_awaited()
    assert "draft" in result


async def test_update_note_tags_add_and_remove(mock_anki_client):
    mock_anki_client.add_tags.return_value = None
    mock_anki_client.remove_tags.return_value = None
    result = await update_note_tags(
        note_ids=[1, 2, 3],
        add=["reviewed"],
        remove=["draft", "todo"],
    )
    mock_anki_client.add_tags.assert_awaited_once_with(
        notes=[1, 2, 3], tags="reviewed"
    )
    mock_anki_client.remove_tags.assert_awaited_once_with(
        notes=[1, 2, 3], tags="draft todo"
    )
    assert "3 notes" in result
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run --frozen pytest tests/test_edit_tools.py -v -k "update_note_tags"`
Expected: All fail.

- [ ] **Step 3: Implement `update_note_tags`**

Replace the stub `update_note_tags` in `mcp_ankiconnect/edit_tools.py` with:

```python
@mcp.tool()
@handle_anki_connection_error
async def update_note_tags(
    note_ids: list[int],
    add: list[str] | None = None,
    remove: list[str] | None = None,
) -> str:
    """Add and/or remove tags on one or more notes.

    Tags MUST NOT appear in both `add` and `remove`. At least one of the two lists
    must be non-empty.

    Args:
        note_ids: Note IDs to modify.
        add: Tags to add (each tag should not contain spaces).
        remove: Tags to remove.
    """
    add = add or []
    remove = remove or []

    if not note_ids:
        return "SYSTEM_ERROR: `note_ids` must not be empty."
    if not add and not remove:
        return "SYSTEM_ERROR: Provide at least one of `add` or `remove`."

    overlap = set(add) & set(remove)
    if overlap:
        joined = ", ".join(sorted(overlap))
        return f"SYSTEM_ERROR: Tags appear in both `add` and `remove`: {joined}."

    async with get_anki_client() as anki:
        if add:
            await anki.add_tags(notes=list(note_ids), tags=" ".join(add))
        if remove:
            await anki.remove_tags(notes=list(note_ids), tags=" ".join(remove))

    parts = [f"Updated tags on {len(note_ids)} notes"]
    if add:
        parts.append(f"added: [{', '.join(add)}]")
    if remove:
        parts.append(f"removed: [{', '.join(remove)}]")
    return " — ".join([parts[0], "; ".join(parts[1:])]) + "."
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run --frozen pytest tests/test_edit_tools.py -v -k "update_note_tags"`
Expected: PASS.

- [ ] **Step 5: Lint/format and run full suite**

Run: `uv run ruff check --fix mcp_ankiconnect/edit_tools.py tests/test_edit_tools.py && uv run ruff format mcp_ankiconnect/edit_tools.py tests/test_edit_tools.py && uv run --frozen pytest`
Expected: All green.

- [ ] **Step 6: Commit**

```bash
git add mcp_ankiconnect/edit_tools.py tests/test_edit_tools.py
git commit -m "feat: Add update_note_tags MCP tool"
```

---

## Task 6: Implement `set_suspended`

**Files:**
- Modify: `mcp_ankiconnect/edit_tools.py`
- Test: `tests/test_edit_tools.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_edit_tools.py`:

```python
from mcp_ankiconnect.edit_tools import set_suspended


async def test_set_suspended_empty_card_ids(mock_anki_client):
    result = await set_suspended(card_ids=[], suspended=True)
    assert result.startswith("SYSTEM_ERROR:")
    mock_anki_client.suspend.assert_not_awaited()


async def test_set_suspended_true_calls_suspend(mock_anki_client):
    mock_anki_client.suspend.return_value = True
    result = await set_suspended(card_ids=[10, 11, 12], suspended=True)
    mock_anki_client.suspend.assert_awaited_once_with(cards=[10, 11, 12])
    mock_anki_client.unsuspend.assert_not_awaited()
    assert "Suspended 3" in result


async def test_set_suspended_false_calls_unsuspend(mock_anki_client):
    mock_anki_client.unsuspend.return_value = True
    result = await set_suspended(card_ids=[10], suspended=False)
    mock_anki_client.unsuspend.assert_awaited_once_with(cards=[10])
    mock_anki_client.suspend.assert_not_awaited()
    assert "Unsuspended 1" in result


async def test_set_suspended_connection_error(mock_anki_client):
    mock_anki_client.suspend.side_effect = AnkiConnectionError("nope")
    result = await set_suspended(card_ids=[10], suspended=True)
    assert result.startswith("SYSTEM_ERROR: Cannot connect to Anki")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run --frozen pytest tests/test_edit_tools.py -v -k "set_suspended"`
Expected: All fail.

- [ ] **Step 3: Implement `set_suspended`**

Replace the stub `set_suspended` in `mcp_ankiconnect/edit_tools.py` with:

```python
@mcp.tool()
@handle_anki_connection_error
async def set_suspended(card_ids: list[int], suspended: bool) -> str:
    """Suspend or unsuspend one or more cards.

    Args:
        card_ids: Card IDs to act on (not note IDs).
        suspended: True to suspend, False to unsuspend.
    """
    if not card_ids:
        return "SYSTEM_ERROR: `card_ids` must not be empty."

    async with get_anki_client() as anki:
        if suspended:
            await anki.suspend(cards=list(card_ids))
            verb = "Suspended"
        else:
            await anki.unsuspend(cards=list(card_ids))
            verb = "Unsuspended"
    return f"{verb} {len(card_ids)} card(s)."
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run --frozen pytest tests/test_edit_tools.py -v -k "set_suspended"`
Expected: PASS.

- [ ] **Step 5: Lint/format and run full suite**

Run: `uv run ruff check --fix mcp_ankiconnect/edit_tools.py tests/test_edit_tools.py && uv run ruff format mcp_ankiconnect/edit_tools.py tests/test_edit_tools.py && uv run --frozen pytest`
Expected: All green.

- [ ] **Step 6: Commit**

```bash
git add mcp_ankiconnect/edit_tools.py tests/test_edit_tools.py
git commit -m "feat: Add set_suspended MCP tool"
```

---

## Task 7: Implement `change_deck`

**Files:**
- Modify: `mcp_ankiconnect/edit_tools.py`
- Test: `tests/test_edit_tools.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_edit_tools.py`:

```python
from mcp_ankiconnect.edit_tools import change_deck


async def test_change_deck_empty_card_ids(mock_anki_client):
    result = await change_deck(card_ids=[], deck="Spanish")
    assert result.startswith("SYSTEM_ERROR:")
    mock_anki_client.change_deck.assert_not_awaited()


async def test_change_deck_empty_deck_name(mock_anki_client):
    result = await change_deck(card_ids=[10], deck="")
    assert result.startswith("SYSTEM_ERROR:")
    mock_anki_client.change_deck.assert_not_awaited()


async def test_change_deck_happy_path(mock_anki_client):
    mock_anki_client.change_deck.return_value = None
    result = await change_deck(card_ids=[10, 11], deck="Spanish::Verbs")
    mock_anki_client.change_deck.assert_awaited_once_with(
        cards=[10, 11], deck="Spanish::Verbs"
    )
    assert "2" in result
    assert "Spanish::Verbs" in result
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run --frozen pytest tests/test_edit_tools.py -v -k "change_deck"`
Expected: All fail.

- [ ] **Step 3: Implement `change_deck`**

Replace the stub `change_deck` in `mcp_ankiconnect/edit_tools.py` with:

```python
@mcp.tool()
@handle_anki_connection_error
async def change_deck(card_ids: list[int], deck: str) -> str:
    """Move cards into a different deck.

    Operates on card IDs (AnkiConnect's `changeDeck` is card-scoped). If you only have
    note IDs, call `inspect_cards(note_ids=...)` first — a single note's cards can
    legitimately live in different decks, so this tool never silently expands notes
    into cards.

    Args:
        card_ids: Card IDs to move.
        deck: Target deck name (e.g. "Spanish::Verbs"). Must already exist in Anki;
            AnkiConnect will create missing decks but this tool does not promise that
            behaviour.
    """
    if not card_ids:
        return "SYSTEM_ERROR: `card_ids` must not be empty."
    if not deck:
        return "SYSTEM_ERROR: `deck` must not be empty."

    async with get_anki_client() as anki:
        await anki.change_deck(cards=list(card_ids), deck=deck)
    return f"Moved {len(card_ids)} card(s) to deck '{deck}'."
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run --frozen pytest tests/test_edit_tools.py -v -k "change_deck"`
Expected: PASS.

- [ ] **Step 5: Lint/format and run full suite**

Run: `uv run ruff check --fix mcp_ankiconnect/edit_tools.py tests/test_edit_tools.py && uv run ruff format mcp_ankiconnect/edit_tools.py tests/test_edit_tools.py && uv run --frozen pytest`
Expected: All green.

- [ ] **Step 6: Commit**

```bash
git add mcp_ankiconnect/edit_tools.py tests/test_edit_tools.py
git commit -m "feat: Add change_deck MCP tool"
```

---

## Task 8: Implement `reschedule_cards`

**Files:**
- Modify: `mcp_ankiconnect/edit_tools.py`
- Test: `tests/test_edit_tools.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_edit_tools.py`:

```python
from mcp_ankiconnect.edit_tools import reschedule_cards


async def test_reschedule_empty_card_ids(mock_anki_client):
    result = await reschedule_cards(card_ids=[], mode="forget")
    assert result.startswith("SYSTEM_ERROR:")
    mock_anki_client.forget_cards.assert_not_awaited()


async def test_reschedule_set_due_requires_due_arg(mock_anki_client):
    result = await reschedule_cards(card_ids=[10], mode="set_due")
    assert result.startswith("SYSTEM_ERROR:")
    assert "due" in result.lower()
    mock_anki_client.set_due_date.assert_not_awaited()


async def test_reschedule_set_due_happy_path(mock_anki_client):
    mock_anki_client.set_due_date.return_value = True
    result = await reschedule_cards(card_ids=[10, 11], mode="set_due", due="1-7")
    mock_anki_client.set_due_date.assert_awaited_once_with(
        cards=[10, 11], days="1-7"
    )
    assert "1-7" in result
    assert "2" in result


async def test_reschedule_forget_happy_path(mock_anki_client):
    mock_anki_client.forget_cards.return_value = None
    result = await reschedule_cards(card_ids=[10], mode="forget")
    mock_anki_client.forget_cards.assert_awaited_once_with(cards=[10])
    mock_anki_client.set_due_date.assert_not_awaited()
    mock_anki_client.relearn_cards.assert_not_awaited()
    assert "Forgot" in result or "forget" in result.lower()


async def test_reschedule_relearn_happy_path(mock_anki_client):
    mock_anki_client.relearn_cards.return_value = None
    result = await reschedule_cards(card_ids=[10], mode="relearn")
    mock_anki_client.relearn_cards.assert_awaited_once_with(cards=[10])
    mock_anki_client.forget_cards.assert_not_awaited()
    assert "relearn" in result.lower()


async def test_reschedule_ignores_due_for_non_set_due_mode(mock_anki_client):
    mock_anki_client.forget_cards.return_value = None
    result = await reschedule_cards(card_ids=[10], mode="forget", due="1")
    mock_anki_client.forget_cards.assert_awaited_once_with(cards=[10])
    mock_anki_client.set_due_date.assert_not_awaited()
    assert not result.startswith("SYSTEM_ERROR:")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run --frozen pytest tests/test_edit_tools.py -v -k "reschedule"`
Expected: All fail.

- [ ] **Step 3: Implement `reschedule_cards`**

Replace the stub `reschedule_cards` in `mcp_ankiconnect/edit_tools.py` with:

```python
@mcp.tool()
@handle_anki_connection_error
async def reschedule_cards(
    card_ids: list[int],
    mode: Literal["set_due", "forget", "relearn"],
    due: str | None = None,
) -> str:
    """Manipulate the scheduling state of one or more cards.

    Modes:
    - `set_due`: Set the cards' due date. Requires `due`. Accepts AnkiConnect's
      `setDueDate` spec:
        * "1"   → due 1 day from now
        * "1-7" → randomly due between 1 and 7 days from now
        * "3!"  → due in 3 days AND reset interval to 3
    - `forget`: Reset cards to the "new" queue (re-enters the learning pipeline).
    - `relearn`: Move cards into the relearning queue.

    Args:
        card_ids: Card IDs to reschedule.
        mode: One of "set_due", "forget", "relearn".
        due: Required for `mode="set_due"`; ignored otherwise.
    """
    if not card_ids:
        return "SYSTEM_ERROR: `card_ids` must not be empty."

    cards = list(card_ids)
    async with get_anki_client() as anki:
        if mode == "set_due":
            if not due:
                return (
                    "SYSTEM_ERROR: `due` is required when mode='set_due' "
                    "(e.g. '1', '1-7', '3!')."
                )
            await anki.set_due_date(cards=cards, days=due)
            return f"Set due date '{due}' on {len(cards)} card(s)."
        if mode == "forget":
            await anki.forget_cards(cards=cards)
            return f"Forgot (reset to new) {len(cards)} card(s)."
        if mode == "relearn":
            await anki.relearn_cards(cards=cards)
            return f"Moved {len(cards)} card(s) into the relearn queue."

    # The Literal type prevents this in well-typed callers, but defensive
    # for any LLM that passes an unexpected string.
    return f"SYSTEM_ERROR: Unknown mode '{mode}'. Expected one of: set_due, forget, relearn."
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run --frozen pytest tests/test_edit_tools.py -v -k "reschedule"`
Expected: PASS.

- [ ] **Step 5: Lint/format and run full suite**

Run: `uv run ruff check --fix mcp_ankiconnect/edit_tools.py tests/test_edit_tools.py && uv run ruff format mcp_ankiconnect/edit_tools.py tests/test_edit_tools.py && uv run --frozen pytest`
Expected: All green.

- [ ] **Step 6: Commit**

```bash
git add mcp_ankiconnect/edit_tools.py tests/test_edit_tools.py
git commit -m "feat: Add reschedule_cards MCP tool"
```

---

## Task 9: Update README

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Locate the tools list in `README.md`**

Run: `grep -n "search_notes\|store_media_file\|add_note" README.md`
Expected: A line (or block) listing the existing MCP tools.

- [ ] **Step 2: Add the six new tools to the same section**

Edit the section that enumerates tools (the one matching the grep). Add the following bullets in the same style as existing entries:

```
- `inspect_cards`: View per-card state (suspension, ease, interval, scheduling, optional review history) for given card IDs or note IDs.
- `update_note_fields`: Modify the text content of one note's fields. Uses the same MathJax/code conversions as `add_note`.
- `update_note_tags`: Add and/or remove tags on one or more notes.
- `set_suspended`: Suspend or unsuspend one or more cards.
- `change_deck`: Move cards (by card ID) into a different deck.
- `reschedule_cards`: Set due date, forget, or relearn one or more cards.
```

- [ ] **Step 3: Run the full suite one final time**

Run: `uv run --frozen pytest`
Expected: All green.

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs: Document inspect/edit MCP tools in README"
```

---

## Final Verification

- [ ] **Run full test suite:** `uv run --frozen pytest`
- [ ] **Run type/lint checks:** `uv run ruff check . && uv run ruff format --check .`
- [ ] **Manual smoke (optional, requires running Anki):** start the server with `uv run mcp-ankiconnect` or `uv run mcp dev mcp_ankiconnect/server.py`, list tools, and confirm all six new ones are registered.
- [ ] **Update CLAUDE.md (only if a workflow gotcha was discovered):** if you found something non-obvious during implementation, add it under "## Gotchas" in `CLAUDE.md`.
