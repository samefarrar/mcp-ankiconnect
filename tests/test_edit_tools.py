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


# --- inspect_cards ---

import json  # noqa: E402

from mcp_ankiconnect.edit_tools import (  # noqa: E402
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
    assert out["reviewed_at_iso"].startswith("2024")


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
    card = payload["cards"][0]
    assert card["cardId"] == 100
    assert card["noteId"] == 200
    assert card["deck"] == "Default"
    assert card["suspended"] is False
    assert card["queue_label"] == "review"
    assert card["ease"] == 2.5
    assert card["interval"] == 14
    assert card["reps"] == 20
    assert card["lapses"] == 1
    assert card["raw_due"] == 365
    assert card["reviews"] is None
    assert card["last_review_iso"] is None
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
    assert card["last_review_iso"] == card["reviews"][1]["reviewed_at_iso"]
    assert card["reviews"][1]["ease"] == "easy"


async def test_inspect_cards_connection_error(mock_anki_client):
    mock_anki_client.cards_info.side_effect = AnkiConnectionError("nope")
    result = await inspect_cards(card_ids=[100])
    assert result.startswith("SYSTEM_ERROR: Cannot connect to Anki")
