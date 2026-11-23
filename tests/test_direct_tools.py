"""Tools end to end while Anki is closed, on a real throwaway collection.

AnkiConnect is the only thing mocked: its probe says "nothing listening"
(or, for the switch-back tests, "listening" with `invoke` stubbed).
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from mcp.server.fastmcp import Image

from mcp_ankiconnect import collection_tools, edit_tools, server
from mcp_ankiconnect.ankiconnect_client import AnkiConnectClient
from mcp_ankiconnect.backend_mode import NOTICES, Mode, reset_announced_mode

CLOSED_NOTE = NOTICES[Mode.DIRECT]
OPEN_NOTE = NOTICES[Mode.ANKICONNECT]


@pytest.fixture(autouse=True)
def fresh_announcements():
    reset_announced_mode()
    yield
    reset_announced_mode()


@pytest.fixture
def listening():
    """Controls the AnkiConnect probe; starts with Anki closed."""
    with patch.object(
        server, "ankiconnect_listening", AsyncMock(return_value=False)
    ) as probe:
        yield probe


@pytest.fixture(autouse=True)
def closed_anki(collection_path: Path, listening, monkeypatch):
    monkeypatch.setenv("ANKI_COLLECTION_PATH", str(collection_path))
    monkeypatch.delenv("ANKI_DIRECT_FALLBACK", raising=False)
    return collection_path


def _body(result: str) -> str:
    """The result without a leading mode NOTE paragraph."""
    for note in (CLOSED_NOTE, OPEN_NOTE):
        if result.startswith(note):
            return result[len(note) :].lstrip("\n")
    return result


def _json(result: str) -> dict:
    return json.loads(_body(result))


async def _card_ids(query: str = "deck:Spanish") -> list[int]:
    result = _json(
        await edit_tools.inspect_cards(
            note_ids=await _note_ids(query), properties=["identity"]
        )
    )
    return sorted(c["cardId"] for c in result["cards"])


async def _note_ids(query: str) -> list[int]:
    result = _json(
        await server.search_notes(query=query, limit=100, return_card_content=False)
    )
    return [n["noteId"] for n in result["notes"]]


def _basic(front: str) -> dict:
    return {
        "deckName": "Spanish",
        "modelName": "Basic",
        "fields": {"Front": front, "Back": "x"},
        "tags": ["t"],
    }


# --- Mode notice ---


async def test_first_closed_call_says_so_once():
    first = await collection_tools.list_tags()
    assert first.startswith(CLOSED_NOTE)
    assert "spanish" in first
    second = await collection_tools.list_tags()
    assert not second.startswith("NOTE")


async def test_switching_back_to_ankiconnect_is_announced(listening):
    await collection_tools.list_tags()
    listening.return_value = True
    with patch.object(
        AnkiConnectClient, "invoke", AsyncMock(return_value=["from-ankiconnect"])
    ):
        back = await collection_tools.list_tags()
        again = await collection_tools.list_tags()
    assert back.startswith(OPEN_NOTE) and "from-ankiconnect" in back
    assert not again.startswith("NOTE")


async def test_open_from_the_start_has_no_note(listening):
    listening.return_value = True
    with patch.object(AnkiConnectClient, "invoke", AsyncMock(return_value=["a"])):
        assert not (await collection_tools.list_tags()).startswith("NOTE")


async def test_errors_do_not_consume_the_note(closed_anki: Path, open_col):
    col = open_col(closed_anki)  # Anki holds the file
    result = await collection_tools.list_tags()
    assert result.startswith("SYSTEM_ERROR") and "in use" in result
    col.close()
    assert (await collection_tools.list_tags()).startswith(CLOSED_NOTE)


async def test_images_defer_the_note(closed_anki: Path):
    media = closed_anki.parent / "collection.media"
    (media / "dot.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    image = await collection_tools.retrieve_media_file("dot.png")
    assert isinstance(image, Image)
    assert (await collection_tools.list_tags()).startswith(CLOSED_NOTE)


async def test_fallback_can_be_switched_off(listening, monkeypatch):
    monkeypatch.setenv("ANKI_DIRECT_FALLBACK", "0")
    with patch.object(AnkiConnectClient, "invoke", AsyncMock(return_value=[])):
        await collection_tools.list_tags()
    listening.assert_not_called()


async def test_schema_mismatch_reaches_the_user(closed_anki: Path):
    db = sqlite3.connect(closed_anki)
    db.execute("update col set ver = ver - 1")
    db.commit()
    db.close()
    result = await server.num_cards_due_today(deck=None)
    assert result.startswith("SYSTEM_ERROR") and "schema" in result


# --- Tools on the file ---


async def test_add_search_and_inspect():
    added = _json(await collection_tools.add_notes([_basic("uno"), _basic("hola")]))
    assert added["added"] == 1 and added["failed"] == 1
    assert "duplicate" in added["results"][1]["reason"]

    found = _json(
        await server.search_notes(query="uno", limit=5, return_card_content=True)
    )
    assert found["notes"][0]["fields"]["Front"] == "uno"

    nid = found["notes"][0]["noteId"]
    cards = _json(await edit_tools.inspect_cards(note_ids=[nid], properties=["all"]))
    [card] = cards["cards"]
    assert card["deck"] == "Spanish" and card["queue_label"] == "new"
    assert card["flag"] == "none" and card["reviews"] == []


async def test_add_note_and_listing():
    result = _body(
        await server.add_note(
            deckName="Spanish",
            modelName="Basic",
            fields={"Front": "dos", "Back": "two"},
        )
    )
    assert result.startswith("Successfully created note")
    listing = _body(await server.list_decks_and_notes())
    assert "Spanish" in listing and "Basic" in listing


async def test_edit_tools():
    [nid, _] = await _note_ids("deck:Spanish")
    assert "Updated note" in await edit_tools.update_note_fields(nid, {"Back": "`hi`"})
    await edit_tools.update_note_tags([nid], add=["extra"], remove=["spanish"])
    note = _json(
        await server.search_notes(query=f"nid:{nid}", limit=1, return_card_content=True)
    )["notes"][0]
    assert note["tags"] == ["extra"] and "<code>hi</code>" in note["fields"]["Back"]

    cids = await _card_ids()
    await edit_tools.set_suspended(cids[:1], suspended=True)
    flagged = _json(await edit_tools.set_card_flag(cids, "red"))
    assert flagged["set"] == 2
    await edit_tools.change_deck(cids[:1], "Spanish::Old")
    state = _json(await edit_tools.inspect_cards(card_ids=cids, properties=["all"]))
    first = state["cards"][0]
    assert first["suspended"] is True and first["flag"] == "red"
    assert first["deck"] == "Spanish::Old"


async def test_copy_scheduling_and_reschedule():
    source, target = await _card_ids()
    await edit_tools.reschedule_cards([source], mode="set_due", due="12!")
    result = _json(await edit_tools.copy_scheduling([target], source_card_id=source))
    assert result["copied"] == 1, result
    await edit_tools.reschedule_cards([target], mode="forget")
    await edit_tools.reschedule_cards([source], mode="relearn")
    cards = _json(await edit_tools.inspect_cards(card_ids=[source, target]))["cards"]
    assert cards[0]["type"] == 3 and cards[1]["queue_label"] == "new"


async def test_review_cycle():
    cids = await _card_ids()
    await edit_tools.reschedule_cards(cids, mode="set_due", due="0")
    due = _body(await server.num_cards_due_today(deck="Spanish"))
    assert due.startswith("There are 2 cards due today")
    prompt = _body(
        await server.fetch_due_cards_for_review(
            deck="Spanish", limit=5, today_only=True
        )
    )
    assert f'<card id="{cids[0]}">' in prompt and "hola" in prompt

    before = _json(await collection_tools.get_review_stats(days=7))["reviewed_today"]
    reviews = [
        {"card_id": cids[0], "rating": "good"},
        {"card_id": cids[1], "rating": "wrong"},
    ]
    summary = _body(await server.submit_reviews(reviews))
    assert summary.startswith("Review submission summary: 2 successful, 0 failed")

    # Like AnkiConnect, every revlog row counts, so the manual reschedule
    # above already logged one entry per card.
    stats = _json(await collection_tools.get_review_stats(days=7))
    assert stats["reviewed_today"] == before + 2
    history = _json(
        await edit_tools.inspect_cards(card_ids=cids[1:], properties=["history"])
    )["cards"][0]["reviews"]
    assert history[-1]["ease"] == "again"


async def test_struggling_and_examples():
    result = _body(await collection_tools.find_struggling_cards(min_lapses=0))
    assert json.loads(result)["total_matching"] == 2
    examples = _body(await server.get_examples(deck=None, limit=5, sample="recent"))
    assert "hola" in examples or "adiós" in examples


async def test_delete_and_create_deck():
    [nid, _] = await _note_ids("deck:Spanish")
    assert "Deleted 1" in await collection_tools.delete_notes([nid], confirm=True)
    assert len(await _note_ids("deck:Spanish")) == 1
    assert "is ready" in await collection_tools.create_deck("French")


async def test_media_round_trip(tmp_path: Path):
    png = tmp_path / "p.png"
    png.write_bytes(b"\x89PNG\r\n\x1a\nrest")
    stored = _body(await server.store_media_file(filename="p.png", path=str(png)))
    assert "Successfully stored media file as 'p.png'" in stored
    image = await collection_tools.retrieve_media_file("p.png")
    assert isinstance(image, Image) and image.data == png.read_bytes()
    missing = await collection_tools.retrieve_media_file("none.png")
    assert missing.startswith("SYSTEM_ERROR")


async def test_sync_and_gui_explain_anki_is_closed():
    synced = _body(await collection_tools.sync())
    assert "nothing was synced" in synced and "next time Anki syncs" in synced
    gui = _body(await collection_tools.get_gui_context())
    assert gui.startswith("Anki is closed")
