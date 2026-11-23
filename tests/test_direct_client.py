"""The direct backend answers AnkiConnect actions from the collection file.

Every test runs against a real throwaway collection (see conftest.py) and
checks the return shape the tools rely on, which is AnkiConnect's own.
"""

from __future__ import annotations

import base64
import sqlite3
import time
from pathlib import Path

import pytest

from mcp_ankiconnect.ankiconnect_client import AnkiAction, DirectBackendError
from mcp_ankiconnect.direct_client import DirectAnkiClient, supported_schema_version


@pytest.fixture
def client(collection_path: Path) -> DirectAnkiClient:
    return DirectAnkiClient(collection_path)


async def _card_ids(client: DirectAnkiClient) -> list[int]:
    return sorted(await client.find_cards("deck:Spanish"))


# --- Reading ---


async def test_find_and_info_shapes(client: DirectAnkiClient):
    note_ids = await client.find_notes("tag:spanish")
    assert len(note_ids) == 2 and all(isinstance(n, int) for n in note_ids)

    [note] = await client.notes_info([note_ids[0]])
    assert note["noteId"] == note_ids[0]
    assert note["modelName"] == "Basic"
    assert note["tags"] == ["spanish"]
    assert note["fields"]["Front"]["order"] == 0
    assert note["fields"]["Back"]["order"] == 1
    assert isinstance(note["cards"], list)

    cids = await _card_ids(client)
    [card] = await client.cards_info([cids[0]])
    expected = {
        "cardId",
        "note",
        "deckName",
        "modelName",
        "fields",
        "fieldOrder",
        "question",
        "answer",
        "ord",
        "type",
        "queue",
        "due",
        "interval",
        "factor",
        "reps",
        "lapses",
        "left",
        "mod",
        "flags",
    }
    assert expected <= set(card)
    assert card["deckName"] == "Spanish"
    assert card["queue"] == 0 and card["flags"] == 0


async def test_missing_ids_give_empty_dicts(client: DirectAnkiClient):
    """AnkiConnect keeps list positions aligned with `{}` for missing IDs."""
    assert await client.cards_info([123]) == [{}]
    assert await client.notes_info([123]) == [{}]
    assert await client.are_suspended([123]) == [None]


async def test_deck_model_and_tag_listing(client: DirectAnkiClient):
    assert "Spanish" in await client.deck_names()
    assert "Basic" in await client.model_names()
    assert await client.model_field_names("Basic") == ["Front", "Back"]
    assert await client.get_tags() == ["spanish"]
    with pytest.raises(ValueError, match="model was not found"):
        await client.model_field_names("Nope")


async def test_search_syntax_error_is_value_error(client: DirectAnkiClient):
    with pytest.raises(ValueError):
        await client.find_notes('"unbalanced')


# --- Adding ---


def _note(front: str, deck: str = "Spanish", **extra) -> dict:
    return {
        "deckName": deck,
        "modelName": "Basic",
        "fields": {"front": front, "Back": "b"},  # field names match any case
        "tags": ["new"],
        "options": {"allowDuplicate": False, "duplicateScope": "deck"},
        **extra,
    }


async def test_add_note_and_duplicate(client: DirectAnkiClient):
    nid = await client.add_note(_note("gato"))
    [info] = await client.notes_info([nid])
    assert info["fields"]["Front"]["value"] == "gato"
    with pytest.raises(ValueError, match="duplicate"):
        await client.add_note(_note("gato"))


async def test_duplicate_scope_is_the_deck(client: DirectAnkiClient):
    await client.create_deck("Other")
    assert await client.add_note(_note("hola", deck="Other"))


async def test_add_note_errors(client: DirectAnkiClient):
    with pytest.raises(ValueError, match="deck was not found"):
        await client.add_note(_note("x", deck="Missing"))
    with pytest.raises(ValueError, match="empty"):
        await client.add_note(_note(""))


async def test_add_notes_each_reports_per_note(client: DirectAnkiClient):
    outcomes = await client.add_notes_each([_note("perro"), _note("hola")])
    assert isinstance(outcomes[0][0], int) and outcomes[0][1] is None
    assert outcomes[1][0] is None and "duplicate" in outcomes[1][1]


async def test_add_note_with_picture(client: DirectAnkiClient, tmp_path: Path):
    image = tmp_path / "cat.png"
    image.write_bytes(b"\x89PNG fake")
    picture = [{"path": str(image), "filename": "cat.png", "fields": ["Back"]}]
    nid = await client.add_note(_note("gata", picture=picture))
    [info] = await client.notes_info([nid])
    assert info["fields"]["Back"]["value"] == 'b<img src="cat.png">'
    stored = await client.retrieve_media_file("cat.png")
    assert base64.b64decode(stored) == b"\x89PNG fake"


# --- Editing ---


async def test_update_fields_and_tags(client: DirectAnkiClient):
    nid = (await client.find_notes("hola"))[0]
    assert (
        await client.update_note_fields({"id": nid, "fields": {"Back": "hi"}}) is None
    )
    await client.add_tags([nid], "a b")
    await client.remove_tags([nid], "spanish")
    [info] = await client.notes_info([nid])
    assert info["fields"]["Back"]["value"] == "hi"
    assert sorted(info["tags"]) == ["a", "b"]
    with pytest.raises(ValueError, match="not found"):
        await client.update_note_fields({"id": 1, "fields": {"Back": "x"}})


async def test_suspend_round_trip(client: DirectAnkiClient):
    cids = await _card_ids(client)
    assert await client.suspend(cids[:1]) is True
    assert await client.suspend(cids[:1]) is False  # nothing left to change
    assert await client.are_suspended(cids) == [True, False]
    assert await client.unsuspend(cids[:1]) is True
    assert await client.are_suspended(cids) == [False, False]


async def test_change_deck_creates_target(client: DirectAnkiClient):
    cids = await _card_ids(client)
    assert await client.change_deck(cids[:1], "Spanish::Verbs") is None
    [card] = await client.cards_info(cids[:1])
    assert card["deckName"] == "Spanish::Verbs"


async def test_flags_ivl_and_factor(client: DirectAnkiClient):
    cids = await _card_ids(client)
    errors = await client.set_card_values({cids[0]: {"flags": 1}})
    assert errors == {cids[0]: None}
    await client.set_due_date(cids[:1], "3!")
    errors = await client.set_card_values(
        {cids[0]: {"ivl": 40, "factor": 2300}}, warning_check=True
    )
    assert errors == {cids[0]: None}
    [card] = await client.cards_info(cids[:1])
    assert (card["flags"], card["interval"], card["factor"]) == (1, 40, 2300)
    assert card["type"] == 2


async def test_card_value_guards_match_ankiconnect(client: DirectAnkiClient):
    cid = (await _card_ids(client))[0]
    # ivl without warning_check: AnkiConnect answers a bare False.
    assert await client.set_card_values({cid: {"ivl": 5}}) == {cid: "invalid request"}
    # A key this server never writes is refused rather than set raw.
    errors = await client.set_card_values({cid: {"odue": 5}}, warning_check=True)
    assert "not supported" in errors[cid]


async def test_forget_and_relearn(client: DirectAnkiClient):
    cids = await _card_ids(client)
    await client.set_due_date(cids, "5!")
    await client.forget_cards(cids[:1])
    await client.relearn_cards(cids[1:])
    new, relearn = await client.cards_info(cids)
    assert (new["type"], new["queue"]) == (0, 0)
    assert (relearn["type"], relearn["queue"]) == (3, 1)


async def test_delete_notes(client: DirectAnkiClient):
    nid = (await client.find_notes("hola"))[0]
    assert await client.delete_notes([nid]) is None
    assert await client.find_notes("hola") == []


# --- Scheduling and history ---


async def test_answer_cards_uses_the_v3_scheduler(client: DirectAnkiClient):
    cids = await _card_ids(client)
    before = time.time() * 1000
    result = await client.answer_cards(
        [{"cardId": cids[0], "ease": 3}, {"cardId": 99, "ease": 3}]
    )
    assert result == [True, False]
    reviews = await client.get_reviews_of_cards(cids)
    assert set(reviews) == {str(c) for c in cids}  # JSON object keys
    [entry] = reviews[str(cids[0])]
    assert set(entry) == {
        "id",
        "usn",
        "ease",
        "ivl",
        "lastIvl",
        "factor",
        "time",
        "type",
    }
    assert entry["ease"] == 3 and entry["id"] >= before
    assert reviews[str(cids[1])] == []
    [card] = await client.cards_info(cids[:1])
    assert card["reps"] == 1 and card["queue"] in (1, 3)


async def test_reviews_by_day(client: DirectAnkiClient):
    cids = await _card_ids(client)
    await client.answer_cards([{"cardId": c, "ease": 4} for c in cids])
    [[day, count]] = await client.get_num_cards_reviewed_by_day()
    assert len(day) == 10 and count == 2


# --- Media, sync, GUI ---


async def test_store_and_retrieve_media(client: DirectAnkiClient, collection_path):
    data = base64.b64encode(b"one").decode()
    assert await client.store_media_file("x.txt", data=data) == "x.txt"
    # AnkiConnect replaces a same-named file instead of renaming the new one.
    again = base64.b64encode(b"two").decode()
    assert await client.store_media_file("x.txt", data=again) == "x.txt"
    assert base64.b64decode(await client.retrieve_media_file("x.txt")) == b"two"
    assert (collection_path.parent / "collection.media" / "x.txt").is_file()
    assert await client.retrieve_media_file("nope.png") is False


async def test_sync_and_gui_never_leave_the_machine(client: DirectAnkiClient):
    assert await client.sync() is None
    assert await client.gui_current_card() is None
    assert await client.gui_selected_notes() == []


async def test_multi_isolates_errors(client: DirectAnkiClient):
    replies = await client.invoke(
        AnkiAction.MULTI,
        actions=[
            {"action": "deckNames", "version": 6, "params": {}},
            {"action": "modelFieldNames", "params": {"modelName": "Nope"}},
        ],
    )
    assert replies[0]["error"] is None and "Spanish" in replies[0]["result"]
    assert replies[1]["result"] is None and "model was not found" in replies[1]["error"]


# --- Safety ---


async def test_collection_is_closed_between_calls(
    client: DirectAnkiClient, collection_path: Path, open_col
):
    """After any call, Anki (here: a second opener) can take the file."""
    await client.deck_names()
    col = open_col(collection_path)
    assert col.decks.by_name("Spanish") is not None


async def test_locked_collection_is_refused(
    client: DirectAnkiClient, collection_path: Path, open_col
):
    open_col(collection_path)  # stands in for a running Anki
    with pytest.raises(DirectBackendError, match="in use"):
        await client.deck_names()


def _set_schema(path: Path, ver: int) -> None:
    db = sqlite3.connect(path)
    db.execute("update col set ver = ?", (ver,))
    db.commit()
    db.close()


def _schema(path: Path) -> int:
    db = sqlite3.connect(f"{path.as_uri()}?immutable=1", uri=True)
    try:
        return db.execute("select ver from col").fetchone()[0]
    finally:
        db.close()


@pytest.mark.parametrize("offset", [-1, 1])
async def test_schema_mismatch_is_refused_untouched(
    client: DirectAnkiClient, collection_path: Path, offset: int
):
    """An older schema would be upgraded on open, a newer one is unreadable.

    Either way the file is left exactly as it was.
    """
    ver = supported_schema_version() + offset
    _set_schema(collection_path, ver)
    with pytest.raises(DirectBackendError, match="schema"):
        await client.deck_names()
    assert _schema(collection_path) == ver


def test_supported_schema_version_is_current():
    pytest.importorskip("anki")
    assert supported_schema_version() >= 18


async def test_missing_collection(tmp_path: Path, anki_collection):
    client = DirectAnkiClient(tmp_path / "nope.anki2")
    with pytest.raises(DirectBackendError, match="not found"):
        await client.deck_names()
    assert not (tmp_path / "nope.anki2").exists()


async def test_parallel_calls_do_not_lock_each_other_out(client: DirectAnkiClient):
    """Clients may run tool calls concurrently; only Anki should mean "in use"."""
    import asyncio

    results = await asyncio.gather(*(client.deck_names() for _ in range(8)))
    assert all("Spanish" in r for r in results)
