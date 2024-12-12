import pytest
from pytest_mock import MockerFixture
import httpx
from typing import List

from mcp_ankiconnect.ankiconnect_client import AnkiConnectClient, AnkiAction

@pytest.fixture
async def client():
    client = AnkiConnectClient()
    yield client
    await client.close()

@pytest.fixture
def mock_response():
    class MockResponse:
        def __init__(self, data, status_code=200):
            self._data = data
            self.status_code = status_code

        def json(self):
            return self._data

        def raise_for_status(self):
            if self.status_code >= 400:
                raise httpx.HTTPStatusError("Error", request=None, response=self)

    return MockResponse

@pytest.mark.asyncio
async def test_deck_names(client: AnkiConnectClient, mocker: MockerFixture, mock_response):
    expected_decks = ["Default", "Test Deck"]
    mock_post = mocker.patch.object(
        client.client, 
        "post",
        return_value=mock_response({"result": expected_decks, "error": None})
    )

    result = await client.deck_names()

    assert result == expected_decks
    mock_post.assert_called_once()
    call_args = mock_post.call_args[1]
    assert call_args["json"]["action"] == AnkiAction.DECK_NAMES

@pytest.mark.asyncio
async def test_cards_info(client: AnkiConnectClient, mocker: MockerFixture, mock_response):
    card_ids = [1, 2, 3]
    expected_info = [
        {"cardId": 1, "deck": "Default"},
        {"cardId": 2, "deck": "Default"},
        {"cardId": 3, "deck": "Default"},
    ]
    mock_post = mocker.patch.object(
        client.client,
        "post",
        return_value=mock_response({"result": expected_info, "error": None})
    )

    result = await client.cards_info(card_ids)

    assert result == expected_info
    mock_post.assert_called_once()
    call_args = mock_post.call_args[1]
    assert call_args["json"]["action"] == AnkiAction.CARDS_INFO
    assert call_args["json"]["params"]["cards"] == card_ids

@pytest.mark.asyncio
async def test_error_handling(client: AnkiConnectClient, mocker: MockerFixture, mock_response):
    error_message = "Test error"
    mock_post = mocker.patch.object(
        client.client,
        "post",
        return_value=mock_response({"result": None, "error": error_message})
    )

    with pytest.raises(RuntimeError, match=f"Error getting deck names: AnkiConnect error: {error_message}"):
        await client.deck_names()

@pytest.mark.asyncio
async def test_connection_error(client: AnkiConnectClient, mocker: MockerFixture):
    mocker.patch.object(
        client.client,
        "post",
        side_effect=httpx.TimeoutException("Connection timeout")
    )

    with pytest.raises(RuntimeError, match="Unable to connect to Anki after 3 attempts"):
        await client.deck_names()

@pytest.mark.asyncio
async def test_add_note(client: AnkiConnectClient, mocker: MockerFixture, mock_response):
    note = {
        "deckName": "Default",
        "modelName": "Basic",
        "fields": {
            "Front": "Test front",
            "Back": "Test back"
        }
    }
    expected_id = 1234
    mock_post = mocker.patch.object(
        client.client,
        "post",
        return_value=mock_response({"result": expected_id, "error": None})
    )

    result = await client.add_note(note)

    assert result == expected_id
    mock_post.assert_called_once()
    call_args = mock_post.call_args[1]
    assert call_args["json"]["action"] == AnkiAction.ADD_NOTE
    assert call_args["json"]["params"]["note"] == note
