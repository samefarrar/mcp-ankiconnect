"""Tests for the feature-parity tools in `mcp_ankiconnect.collection_tools`.

The AnkiConnect client is mocked, which keeps with the rest of the suite, so
no running Anki instance is needed.
"""

import base64
import json
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from mcp.server.fastmcp import Image

from mcp_ankiconnect.ankiconnect_client import AnkiConnectClient
from mcp_ankiconnect.collection_tools import (
    _summarise_review_days,
    add_notes,
    create_deck,
    delete_notes,
    find_struggling_cards,
    get_gui_context,
    get_review_stats,
    list_tags,
    retrieve_media_file,
    sync,
)


@pytest.fixture
def anki():
    mock = MagicMock(spec=AnkiConnectClient)
    for name in (
        "can_add_notes_with_error_detail",
        "add_notes",
        "delete_notes",
        "get_tags",
        "create_deck",
        "sync",
        "get_num_cards_reviewed_by_day",
        "find_cards",
        "cards_info",
        "retrieve_media_file",
        "gui_current_card",
        "gui_selected_notes",
    ):
        setattr(mock, name, AsyncMock())
    return mock


@pytest.fixture(autouse=True)
def patch_client(anki):
    with patch("mcp_ankiconnect.collection_tools.get_anki_client") as cm:
        cm.return_value.__aenter__.return_value = anki
        cm.return_value.__aexit__ = AsyncMock(return_value=None)
        yield cm


def _note(front: str, deck: str = "Default") -> dict:
    return {"deckName": deck, "modelName": "Basic", "fields": {"Front": front}}


# --- add_notes ---


async def test_add_notes_adds_valid_and_reports_skipped_duplicates(anki):
    anki.can_add_notes_with_error_detail.return_value = [
        {"canAdd": True},
        {"canAdd": False, "error": "cannot create note because it is a duplicate"},
        {"canAdd": True},
    ]
    anki.add_notes.return_value = [111, 333]

    result = json.loads(await add_notes([_note("a"), _note("b"), _note("c")]))

    sent = anki.add_notes.await_args.kwargs["notes"]
    assert [n["fields"]["Front"] for n in sent] == ["a", "c"]
    assert result["added"] == 2
    assert result["skipped"] == 1
    assert result["results"][0] == {"index": 0, "status": "added", "noteId": 111}
    assert result["results"][1]["status"] == "skipped"
    assert "duplicate" in result["results"][1]["reason"]
    assert result["results"][2] == {"index": 2, "status": "added", "noteId": 333}


async def test_add_notes_applies_same_field_processing_as_add_note(anki):
    anki.can_add_notes_with_error_detail.return_value = [{"canAdd": True}]
    anki.add_notes.return_value = [1]

    await add_notes([_note("<math>x^2</math> and `code`")])

    payload = anki.can_add_notes_with_error_detail.await_args.kwargs["notes"][0]
    assert payload["fields"]["Front"] == "\\(x^2\\) and <code>code</code>"
    assert payload["options"]["allowDuplicate"] is False
    assert payload["tags"] == []


async def test_add_notes_skips_addnotes_call_when_nothing_is_addable(anki):
    anki.can_add_notes_with_error_detail.return_value = [
        {"canAdd": False, "error": "duplicate"}
    ]

    result = json.loads(await add_notes([_note("a")]))

    anki.add_notes.assert_not_awaited()
    assert result["added"] == 0


async def test_add_notes_marks_null_ids_as_failed(anki):
    anki.can_add_notes_with_error_detail.return_value = [{"canAdd": True}]
    anki.add_notes.return_value = [None]

    result = json.loads(await add_notes([_note("a")]))

    assert result["results"][0]["status"] == "failed"
    assert result["failed"] == 1


async def test_add_notes_rejects_empty_and_oversized_batches(anki):
    assert (await add_notes([])).startswith("SYSTEM_ERROR:")
    too_many = [_note(str(i)) for i in range(101)]
    assert (await add_notes(too_many)).startswith("SYSTEM_ERROR:")
    anki.can_add_notes_with_error_detail.assert_not_awaited()


async def test_add_notes_rejects_note_missing_required_keys(anki):
    result = await add_notes([_note("a"), {"deckName": "D", "fields": {}}])
    assert result.startswith("SYSTEM_ERROR:")
    assert "index 1" in result
    anki.can_add_notes_with_error_detail.assert_not_awaited()


async def test_add_notes_precheck_omits_picture_but_add_keeps_it(anki):
    """The pre-check ignores media; sending image data twice is pure waste."""
    anki.can_add_notes_with_error_detail.return_value = [{"canAdd": True}]
    anki.add_notes.return_value = [1]
    pic = [{"filename": "a.png", "data": "AAAA", "fields": ["Back"]}]

    await add_notes([{**_note("a"), "picture": pic}])

    checked = anki.can_add_notes_with_error_detail.await_args.kwargs["notes"][0]
    added = anki.add_notes.await_args.kwargs["notes"][0]
    assert "picture" not in checked
    assert added["picture"] == pic


# --- delete_notes ---


async def test_delete_notes_requires_explicit_confirmation(anki):
    result = await delete_notes([1, 2])
    assert result.startswith("SYSTEM_ERROR:")
    assert "confirm" in result
    anki.delete_notes.assert_not_awaited()


async def test_delete_notes_deletes_when_confirmed(anki):
    result = await delete_notes([1, 2], confirm=True)
    anki.delete_notes.assert_awaited_once_with(notes=[1, 2])
    assert "2 note(s)" in result


async def test_delete_notes_rejects_empty_list(anki):
    assert (await delete_notes([], confirm=True)).startswith("SYSTEM_ERROR:")


# --- list_tags / create_deck / sync ---


async def test_list_tags_filters_case_insensitively(anki):
    anki.get_tags.return_value = ["Spanish::verbs", "french", "spanish::nouns"]
    result = await list_tags(contains="SPANISH")
    assert "Spanish::verbs" in result
    assert "spanish::nouns" in result
    assert "french" not in result


async def test_list_tags_reports_when_none_match(anki):
    anki.get_tags.return_value = ["a"]
    assert "No tags" in await list_tags(contains="zzz")


async def test_create_deck_returns_deck_id(anki):
    anki.create_deck.return_value = 1234
    result = await create_deck("Spanish::Verbs")
    anki.create_deck.assert_awaited_once_with(deck="Spanish::Verbs")
    assert "1234" in result


async def test_create_deck_rejects_blank_name(anki):
    assert (await create_deck("  ")).startswith("SYSTEM_ERROR:")


async def test_sync_invokes_anki_sync(anki):
    result = await sync()
    anki.sync.assert_awaited_once_with()
    assert "Sync" in result


# --- review stats ---


def test_summarise_review_days_counts_window_and_streak():
    rows = [
        ["2026-11-23", 40],
        ["2026-11-22", 20],
        ["2026-11-21", 10],
        ["2026-11-19", 5],
        ["2026-10-01", 99],  # outside a 7-day window
    ]
    out = _summarise_review_days(rows, today=date(2026, 11, 23), days=7)
    assert out["reviewed_today"] == 40
    assert out["total_in_window"] == 75
    assert out["active_days"] == 4
    assert out["current_streak_days"] == 3
    assert out["daily"][0] == {"date": "2026-11-19", "reviews": 5}
    assert out["daily"][-1] == {"date": "2026-11-23", "reviews": 40}


def test_summarise_review_days_streak_survives_until_today_is_reviewed():
    """A streak ending yesterday is still live: today isn't over yet."""
    rows = [["2026-11-22", 3], ["2026-11-21", 3]]
    out = _summarise_review_days(rows, today=date(2026, 11, 23), days=14)
    assert out["reviewed_today"] == 0
    assert out["current_streak_days"] == 2


def test_summarise_review_days_broken_streak_is_zero():
    rows = [["2026-11-20", 3]]
    out = _summarise_review_days(rows, today=date(2026, 11, 23), days=14)
    assert out["current_streak_days"] == 0


async def test_get_review_stats_returns_json_summary(anki):
    anki.get_num_cards_reviewed_by_day.return_value = []
    payload = json.loads(await get_review_stats(days=7))
    assert payload["window_days"] == 7
    assert payload["total_in_window"] == 0


async def test_get_review_stats_rejects_non_positive_window(anki):
    assert (await get_review_stats(days=0)).startswith("SYSTEM_ERROR:")


# --- find_struggling_cards ---


def _card(cid: int, lapses: int, factor: int, front: str = "Q") -> dict:
    return {
        "cardId": cid,
        "note": cid * 10,
        "deckName": "Default",
        "modelName": "Basic",
        "lapses": lapses,
        "factor": factor,
        "interval": 2,
        "fields": {
            "Front": {"value": f"<div>{front}</div>", "order": 0},
            "Back": {"value": "A", "order": 1},
        },
    }


async def test_find_struggling_cards_sorts_by_lapses_then_ease(anki):
    anki.find_cards.return_value = [1, 2, 3]
    anki.cards_info.return_value = [
        _card(1, lapses=4, factor=2500),
        _card(2, lapses=8, factor=2500),
        _card(3, lapses=4, factor=1300, front="hardest"),
    ]

    payload = json.loads(await find_struggling_cards(min_lapses=3, limit=2))

    query = anki.find_cards.await_args.kwargs["query"]
    assert "prop:lapses>=3" in query
    assert "-is:suspended" in query
    ids = [c["cardId"] for c in payload["cards"]]
    assert ids == [2, 3]
    assert payload["cards"][1]["preview"] == "hardest"
    assert payload["cards"][1]["ease"] == 1.3
    assert payload["total_matching"] == 3


async def test_find_struggling_cards_raises_threshold_instead_of_truncating(
    anki,
):
    """Above the scan cap, truncating by ID would rank an arbitrary subset."""
    from mcp_ankiconnect.config import MAX_STRUGGLING_SCAN

    huge = list(range(MAX_STRUGGLING_SCAN + 100))
    anki.find_cards.side_effect = [huge, [7, 8, 9]]
    anki.cards_info.return_value = [_card(7, 9, 2500), _card(8, 5, 2500)]

    payload = json.loads(await find_struggling_cards(min_lapses=3, limit=2))

    second_query = anki.find_cards.await_args_list[1].kwargs["query"]
    assert "prop:lapses>=4" in second_query
    anki.cards_info.assert_awaited_once_with(card_ids=[7, 8, 9])
    assert payload["total_matching"] == len(huge)
    assert [c["cardId"] for c in payload["cards"]] == [7, 8]


async def test_find_struggling_cards_filters_by_deck(anki):
    anki.find_cards.return_value = []
    result = await find_struggling_cards(deck="Spanish")
    assert '"deck:Spanish"' in anki.find_cards.await_args.kwargs["query"]
    assert "No struggling cards" in result
    anki.cards_info.assert_not_awaited()


# --- retrieve_media_file ---


async def test_retrieve_media_file_returns_image_content(anki):
    raw = b"\x89PNG\r\n\x1a\nfake"
    anki.retrieve_media_file.return_value = base64.b64encode(raw).decode()

    result = await retrieve_media_file("diagram.png")

    assert isinstance(result, Image)
    assert result.data == raw
    assert result._mime_type == "image/png"


async def test_retrieve_media_file_reports_missing_file(anki):
    anki.retrieve_media_file.return_value = False
    result = await retrieve_media_file("nope.png")
    assert isinstance(result, str)
    assert result.startswith("SYSTEM_ERROR:")


async def test_retrieve_media_file_describes_non_image_files(anki):
    anki.retrieve_media_file.return_value = base64.b64encode(b"ID3audio").decode()
    result = await retrieve_media_file("word.mp3")
    assert isinstance(result, str)
    assert "not an image" in result


# --- get_gui_context ---


async def test_get_gui_context_returns_current_card_and_selection(anki):
    anki.gui_current_card.return_value = _card(5, lapses=0, factor=2500)
    anki.gui_selected_notes.return_value = [10, 20]

    payload = json.loads(await get_gui_context())

    assert payload["current_review_card"]["cardId"] == 5
    assert payload["current_review_card"]["noteId"] == 50
    assert payload["current_review_card"]["fields"] == {"Front": "Q", "Back": "A"}
    assert payload["selected_note_ids"] == [10, 20]


async def test_get_gui_context_tolerates_inactive_reviewer_and_browser(anki):
    # AnkiConnect's own "nothing open" responses: null card, empty selection.
    anki.gui_current_card.return_value = None
    anki.gui_selected_notes.return_value = []

    payload = json.loads(await get_gui_context())

    assert payload["current_review_card"] is None
    assert payload["selected_note_ids"] == []
    assert "hint" in payload


# --- discoverability: annotations, instructions, resource ---


async def test_every_tool_declares_annotations():
    import mcp_ankiconnect.main  # noqa: F401  # registers every tool module
    from mcp_ankiconnect.server import mcp

    tools = {t.name: t for t in await mcp.list_tools()}
    missing = [n for n, t in tools.items() if t.annotations is None]
    assert missing == []

    assert tools["search_notes"].annotations.readOnlyHint is True
    assert tools["delete_notes"].annotations.destructiveHint is True
    assert tools["add_notes"].annotations.readOnlyHint is False
    assert tools["add_notes"].annotations.destructiveHint is False


def test_server_exposes_instructions():
    from mcp_ankiconnect.server import mcp

    assert mcp.instructions is not None
    assert "note ID" in mcp.instructions
    assert "card ID" in mcp.instructions


async def test_search_syntax_resource_is_readable():
    from mcp_ankiconnect.server import mcp

    contents = list(await mcp.read_resource("anki://docs/search-syntax"))
    text = contents[0].content
    assert "deck:" in text
    assert "prop:" in text
