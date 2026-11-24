"""Tests for the MCP Apps card-review spike in `mcp_ankiconnect.app_tools`.

The page's JavaScript is checked by hand in a fake host (see the module
docstring in `app_tools.py`); these tests pin the server side: tool metadata that links the page, the structured payload it
renders, and the app-only decision log.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mcp_ankiconnect.ankiconnect_client import AnkiConnectClient
from mcp_ankiconnect.app_tools import (
    APP_MIME_TYPE,
    CARD_REVIEW_URI,
    open_card_review,
    record_card_decisions,
)


@pytest.fixture
def anki():
    mock = MagicMock(spec=AnkiConnectClient)
    mock.notes_info = AsyncMock()
    return mock


@pytest.fixture(autouse=True)
def patch_client(anki):
    with patch("mcp_ankiconnect.app_tools.get_anki_client") as cm:
        cm.return_value.__aenter__.return_value = anki
        cm.return_value.__aexit__ = AsyncMock(return_value=None)
        yield cm


@pytest.fixture
def decisions_file(tmp_path, monkeypatch):
    path = tmp_path / "decisions.jsonl"
    monkeypatch.setenv("ANKI_DECISIONS_FILE", str(path))
    return path


async def _tools():
    import mcp_ankiconnect.main  # noqa: F401  # registers every tool module
    from mcp_ankiconnect.server import mcp

    return {t.name: t for t in await mcp.list_tools()}


async def test_open_card_review_links_the_page():
    tool = (await _tools())["open_card_review"]
    assert tool.meta["ui"]["resourceUri"] == CARD_REVIEW_URI
    assert "model" in tool.meta["ui"]["visibility"]


async def test_record_decisions_is_app_only():
    # Hidden from the model, so only a human click can record a verdict.
    tool = (await _tools())["record_card_decisions"]
    assert tool.meta["ui"]["visibility"] == ["app"]


async def test_page_resource_is_registered_as_mcp_app_html():
    from mcp_ankiconnect.server import mcp

    resources = {str(r.uri): r for r in await mcp.list_resources()}
    assert resources[CARD_REVIEW_URI].mimeType == APP_MIME_TYPE
    contents = list(await mcp.read_resource(CARD_REVIEW_URI))
    assert "ui/initialize" in contents[0].content


async def test_open_card_review_returns_clean_notes_in_order(anki):
    anki.notes_info.return_value = [
        {"noteId": 2, "modelName": "Basic", "tags": ["t"],
         "fields": {"Front": {"value": "<b>Q2</b>"}, "Back": {"value": "A2"}}},
        {"noteId": 1, "modelName": "Basic", "tags": [],
         "fields": {"Front": {"value": "Q1"}, "Back": {"value": ""}}},
    ]
    result = await open_card_review(note_ids=[1, 2], context={"2": "leaks c1"})

    assert [n["noteId"] for n in result["notes"]] == [1, 2]
    assert result["notes"][0]["fields"] == {"Front": "Q1"}
    # The shared cleaner keeps light formatting; the page strips it for display.
    assert result["notes"][1]["fields"]["Front"] == "<b>Q2</b>"
    assert result["notes"][1]["context"] == "leaks c1"
    assert result["missing"] == []


async def test_open_card_review_reports_missing_notes(anki):
    anki.notes_info.return_value = [{}]  # AnkiConnect's shape for an unknown id
    result = await open_card_review(note_ids=[99])
    assert result["notes"] == []
    assert result["missing"] == [99]


async def test_open_card_review_rejects_empty_input():
    result = await open_card_review(note_ids=[])
    assert result["error"].startswith("SYSTEM_ERROR")


async def test_record_decisions_appends_jsonl(decisions_file):
    out = await record_card_decisions(
        decisions=[
            {"note_id": 1, "decision": "approve"},
            {"note_id": 2, "decision": "reject", "comment": "hint gives it away"},
        ]
    )
    await record_card_decisions(decisions=[{"note_id": 3, "decision": "skip"}])

    lines = [json.loads(x) for x in decisions_file.read_text().splitlines()]
    assert [x["note_id"] for x in lines] == [1, 2, 3]
    assert lines[1]["comment"] == "hint gives it away"
    assert all("recorded_at" in x for x in lines)
    assert "2 decisions" in out and "1 approve" in out and "1 reject" in out


async def test_record_decisions_refuses_unknown_verdicts(decisions_file):
    out = await record_card_decisions(decisions=[{"note_id": 1, "decision": "maybe"}])
    assert out.startswith("SYSTEM_ERROR")
    assert not decisions_file.exists()


# --- Does the connected app say it can display the page? ---

from mcp.types import ClientCapabilities, Implementation, InitializeRequestParams  # noqa: E402

from mcp_ankiconnect.app_tools import host_page_support  # noqa: E402


def _params(capabilities: dict, name: str = "claude-desktop") -> InitializeRequestParams:
    return InitializeRequestParams(
        protocolVersion="2025-06-18",
        capabilities=ClientCapabilities.model_validate(capabilities),
        clientInfo=Implementation(name=name, version="1"),
    )


def test_host_that_advertises_mcp_apps_is_supported():
    caps = {"extensions": {"io.modelcontextprotocol/ui": {"mimeTypes": [APP_MIME_TYPE]}}}
    assert host_page_support(_params(caps)) == (True, "claude-desktop")


@pytest.mark.parametrize(
    "caps",
    [
        {},
        {"extensions": {}},
        {"extensions": {"io.modelcontextprotocol/ui": {"mimeTypes": ["text/plain"]}}},
        {"extensions": {"io.modelcontextprotocol/ui": "yes"}},
    ],
)
def test_host_without_the_extension_is_not_supported(caps):
    assert host_page_support(_params(caps, "cowork"))[0] is False


def test_unknown_host_is_not_supported():
    # Called outside a client session (e.g. directly in tests).
    assert host_page_support(None) == (False, "unknown")


async def test_open_card_review_reports_page_support(anki):
    # Regression: the skill guessed "no page" from getting JSON back, but the
    # model always gets JSON; only the host's capabilities say if it rendered.
    anki.notes_info.return_value = [
        {"noteId": 1, "modelName": "Basic", "tags": [], "fields": {"Front": {"value": "Q"}}}
    ]
    result = await open_card_review(note_ids=[1])
    assert result["page_supported"] is False
    assert result["host"] == "unknown"
