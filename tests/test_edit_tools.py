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


# --- update_note_fields ---

from mcp_ankiconnect.edit_tools import update_note_fields  # noqa: E402


async def test_update_note_fields_empty_fields_dict_returns_error(mock_anki_client):
    result = await update_note_fields(note_id=200, fields={})
    assert result.startswith("SYSTEM_ERROR:")
    assert "fields" in result.lower()
    mock_anki_client.update_note_fields.assert_not_awaited()


async def test_update_note_fields_processes_content_and_invokes_client(
    mock_anki_client,
):
    mock_anki_client.update_note_fields.return_value = None
    result = await update_note_fields(
        note_id=200,
        fields={"Front": "What is `x`?", "Back": "<math>x = 1</math>"},
    )
    mock_anki_client.update_note_fields.assert_awaited_once()
    call_kwargs = mock_anki_client.update_note_fields.await_args.kwargs
    note = call_kwargs["note"]
    assert note["id"] == 200
    assert note["fields"]["Front"] == "What is <code>x</code>?"
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


# --- update_note_tags ---

from mcp_ankiconnect.edit_tools import update_note_tags  # noqa: E402


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
    mock_anki_client.add_tags.assert_awaited_once_with(notes=[1, 2, 3], tags="reviewed")
    mock_anki_client.remove_tags.assert_awaited_once_with(
        notes=[1, 2, 3], tags="draft todo"
    )
    assert "3 notes" in result


# --- set_suspended ---

from mcp_ankiconnect.edit_tools import set_suspended  # noqa: E402


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


# --- change_deck ---

from mcp_ankiconnect.edit_tools import change_deck  # noqa: E402


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
