"""Tests for flag and scheduling-transfer tools in `mcp_ankiconnect.edit_tools`.

The theme of these tests is that no write can report success unseen: each tool
re-reads the cards, so a silent AnkiConnect no-op shows up as `unchanged` or
`mismatch` instead of a false success.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mcp_ankiconnect.ankiconnect_client import AnkiConnectClient
from mcp_ankiconnect.edit_tools import copy_scheduling, inspect_cards, set_card_flag


@pytest.fixture
def anki():
    mock = MagicMock(spec=AnkiConnectClient)
    for name in (
        "set_card_values",
        "cards_info",
        "find_cards",
        "set_due_date",
        "are_suspended",
    ):
        setattr(mock, name, AsyncMock())
    mock.set_card_values.side_effect = lambda values, **_: dict.fromkeys(values)
    return mock


@pytest.fixture(autouse=True)
def patch_client(anki):
    with patch("mcp_ankiconnect.edit_tools.get_anki_client") as cm:
        cm.return_value.__aenter__.return_value = anki
        cm.return_value.__aexit__ = AsyncMock(return_value=None)
        yield cm


def _card(cid: int, **kw) -> dict:
    base = {"cardId": cid, "note": cid * 10, "interval": 0, "factor": 0, "reps": 0}
    return {**base, **kw}


# --- set_card_flag ---


async def test_set_card_flag_writes_flag_number_as_int(anki):
    anki.cards_info.return_value = [_card(1, flags=1), _card(2, flags=1)]

    await set_card_flag([1, 2], "red")

    values = anki.set_card_values.await_args.args[0]
    assert values == {1: {"flags": 1}, 2: {"flags": 1}}
    assert all(type(v["flags"]) is int for v in values.values())


async def test_set_card_flag_reports_silent_no_op_as_unchanged(anki):
    """Regression guard: AnkiConnect can accept a write and change nothing."""
    anki.cards_info.return_value = [_card(1, flags=3), _card(2, flags=0)]

    payload = json.loads(await set_card_flag([1, 2], "green"))

    assert payload["results"][0] == {"cardId": 1, "status": "set"}
    assert payload["results"][1] == {
        "cardId": 2,
        "status": "unchanged",
        "current_flag": "none",
    }
    assert payload["set"] == 1


async def test_set_card_flag_reports_missing_cards(anki):
    anki.cards_info.return_value = [_card(1, flags=2), {}]

    payload = json.loads(await set_card_flag([1, 999], "orange"))

    assert payload["results"][1] == {"cardId": 999, "status": "missing"}


async def test_set_card_flag_marks_unverified_when_anki_omits_flags(anki):
    anki.cards_info.return_value = [_card(1)]  # older AnkiConnect: no "flags"

    payload = json.loads(await set_card_flag([1], "red"))

    assert payload["results"][0]["status"] == "unverified"


async def test_set_card_flag_includes_write_error(anki):
    anki.set_card_values.side_effect = None
    anki.set_card_values.return_value = {1: "card was not found"}
    anki.cards_info.return_value = [{}]

    payload = json.loads(await set_card_flag([1], "red"))

    assert payload["results"][0]["error"] == "card was not found"


async def test_set_card_flag_rejects_empty_and_unknown(anki):
    assert (await set_card_flag([], "red")).startswith("SYSTEM_ERROR:")
    assert (await set_card_flag([1], "magenta")).startswith("SYSTEM_ERROR:")  # type: ignore[arg-type]
    anki.set_card_values.assert_not_awaited()


# --- flags in inspect_cards ---


async def test_inspect_cards_state_includes_flag_name(anki):
    anki.cards_info.return_value = [_card(1, flags=1, queue=2, type=2)]
    anki.are_suspended.return_value = [False]

    card = json.loads(await inspect_cards(card_ids=[1], properties=["state"]))["cards"][
        0
    ]

    assert card["flag"] == "red"


async def test_inspect_cards_omits_flag_when_anki_does_not_report_it(anki):
    anki.cards_info.return_value = [_card(1, queue=2, type=2)]
    anki.are_suspended.return_value = [False]

    card = json.loads(await inspect_cards(card_ids=[1], properties=["state"]))["cards"][
        0
    ]

    assert "flag" not in card


# --- copy_scheduling ---


SOURCE = _card(100, interval=34, factor=2300, reps=12)


async def test_copy_scheduling_sets_due_then_ivl_and_factor_as_ints(anki):
    anki.cards_info.side_effect = [
        [SOURCE],  # source
        [_card(1), _card(2)],  # targets before
        [
            _card(1, interval=34, factor=2300, type=2),
            _card(2, interval=34, factor=2300, type=2),
        ],
    ]

    payload = json.loads(await copy_scheduling([1, 2], source_card_id=100))

    anki.set_due_date.assert_awaited_once_with(cards=[1, 2], days="0-6")
    values = anki.set_card_values.await_args.args[0]
    assert values == {
        1: {"ivl": 34, "factor": 2300},
        2: {"ivl": 34, "factor": 2300},
    }
    assert anki.set_card_values.await_args.kwargs["warning_check"] is True
    assert payload["copied"] == 2
    assert payload["source"] == {"cardId": 100, "interval": 34, "factor": 2300}


async def test_copy_scheduling_reports_mismatch_on_silent_no_op(anki):
    """Regression guard for the skill's gotcha: string values no-op silently.

    Whatever the cause, a target that re-reads wrong must not count as copied.
    """
    anki.cards_info.side_effect = [
        [SOURCE],
        [_card(1)],
        [_card(1, interval=3, factor=2500)],
    ]

    payload = json.loads(await copy_scheduling([1], source_card_id=100))

    result = payload["results"][0]
    assert result["status"] == "mismatch"
    assert result["expected"] == {
        "interval": 34,
        "factor": 2300,
        "review_card": True,
    }
    assert result["actual"] == {"interval": 3, "factor": 2500, "review_card": False}
    assert payload["copied"] == 0


async def test_copy_scheduling_from_note_uses_longest_interval_card(anki):
    anki.find_cards.return_value = [100, 101]
    anki.cards_info.side_effect = [
        [_card(101, interval=5, factor=2500, reps=3), SOURCE],
        [_card(1)],
        [_card(1, interval=34, factor=2300, type=2)],
    ]

    payload = json.loads(await copy_scheduling([1], source_note_id=1000))

    assert anki.find_cards.await_args.kwargs["query"] == "nid:1000"
    assert payload["source"]["cardId"] == 100


async def test_copy_scheduling_refuses_unreviewed_source(anki):
    anki.cards_info.return_value = [_card(100)]

    result = await copy_scheduling([1], source_card_id=100)

    assert result.startswith("SYSTEM_ERROR:")
    assert "never been reviewed" in result
    anki.set_due_date.assert_not_awaited()


async def test_copy_scheduling_protects_targets_with_history(anki):
    anki.cards_info.side_effect = [[SOURCE], [_card(1), _card(2, reps=8)]]

    result = await copy_scheduling([1, 2], source_card_id=100)

    assert result.startswith("SYSTEM_ERROR:")
    assert "2" in result and "overwrite_history" in result
    anki.set_due_date.assert_not_awaited()
    anki.set_card_values.assert_not_awaited()


async def test_copy_scheduling_overwrites_history_when_asked(anki):
    anki.cards_info.side_effect = [
        [SOURCE],
        [_card(2, reps=8)],
        [_card(2, interval=34, factor=2300, type=2)],
    ]

    payload = json.loads(
        await copy_scheduling([2], source_card_id=100, overwrite_history=True)
    )

    assert payload["copied"] == 1


async def test_copy_scheduling_validates_arguments(anki):
    both = await copy_scheduling([1], source_card_id=1, source_note_id=2)
    neither = await copy_scheduling([1])
    empty = await copy_scheduling([], source_card_id=1)
    self_copy = await copy_scheduling([100], source_card_id=100)
    for result in (both, neither, empty, self_copy):
        assert result.startswith("SYSTEM_ERROR:")
    anki.cards_info.assert_not_awaited()


async def test_copy_scheduling_reports_missing_targets(anki):
    anki.cards_info.side_effect = [[SOURCE], [_card(1), {}]]

    result = await copy_scheduling([1, 999], source_card_id=100)

    assert result.startswith("SYSTEM_ERROR:")
    assert "999" in result
    anki.set_due_date.assert_not_awaited()


# --- fresh-eyes regressions ---


async def test_copy_scheduling_flags_targets_that_stayed_new(anki):
    """Regression: if setDueDate is silently ignored the target stays a new
    card holding the copied numbers; that must not count as copied."""
    anki.cards_info.side_effect = [
        [SOURCE],
        [_card(1, type=0)],
        [_card(1, interval=34, factor=2300, type=0)],
    ]

    payload = json.loads(await copy_scheduling([1], source_card_id=100))

    result = payload["results"][0]
    assert result["status"] == "mismatch"
    assert result["actual"]["review_card"] is False


async def test_copy_scheduling_reports_per_card_when_value_write_fails_whole(anki):
    """Regression: setDueDate already changed the cards, so a failed value
    write must still produce the per-card report, not a bare error."""
    anki.set_card_values.side_effect = RuntimeError("multi failed")
    anki.cards_info.side_effect = [
        [SOURCE],
        [_card(1)],
        [_card(1, interval=2, factor=2500, type=2)],
    ]

    payload = json.loads(await copy_scheduling([1], source_card_id=100))

    result = payload["results"][0]
    assert result["status"] == "mismatch"
    assert "multi failed" in result["error"]


async def test_copy_scheduling_rejects_note_source_that_is_also_a_target(anki):
    """Regression: the self-copy guard must hold for source_note_id too."""
    anki.find_cards.return_value = [100]
    # Enough data for the whole write path, so only the guard can stop it.
    anki.cards_info.side_effect = [[SOURCE], [SOURCE], [SOURCE]]

    result = await copy_scheduling([100], source_note_id=1000, overwrite_history=True)

    assert result.startswith("SYSTEM_ERROR:")
    assert "target" in result
    anki.set_due_date.assert_not_awaited()
