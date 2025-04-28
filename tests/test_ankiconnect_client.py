import pytest
from pytest_mock import MockerFixture # Import MockerFixture
import httpx
import asyncio
from unittest.mock import AsyncMock, patch, call, MagicMock # Ensure call and MagicMock are imported
from typing import List # Keep List if used elsewhere, otherwise remove if unused

# Use absolute import based on project structure for tests
from mcp_ankiconnect.ankiconnect_client import (
    AnkiConnectClient,
    AnkiConnectionError, # Import custom exception
    AnkiAction,
    AnkiConnectRequest, # Import if needed for direct testing
    AnkiConnectResponse # Import if needed for direct testing
)
# Assuming TIMEOUTS config is accessible or mockable if needed by client init
# from mcp_ankiconnect.config import TIMEOUTS # If needed

# Fixture for the client (can be reused)
@pytest.fixture
async def client(): # Make the fixture async
    # Setup: Create the client instance
    instance = AnkiConnectClient(base_url="http://testhost:8765")
    yield instance
    # Teardown: Close the client's session after the test using it has finished
    await instance.close()

# Keep mock_response fixture if it's still used by older tests, otherwise remove.
# It seems less necessary with AsyncMock for httpx.post
@pytest.fixture
def mock_response(): # Keep if used
    class MockResponse:
        def __init__(self, data, status_code=200):
            self._data = data
            self.status_code = status_code

        def json(self): # Make json synchronous
            return self._data

        def raise_for_status(self): # Keep raise_for_status sync
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

# Note: test_error_handling is replaced by test_invoke_anki_api_error_raises_valueerror
# Note: test_connection_error is replaced by test_invoke_connect_error_raises_custom_exception etc.

# --- New Tests for Invoke Error Handling ---

@pytest.mark.asyncio
@patch('asyncio.sleep', return_value=None) # Mock sleep to speed up tests
async def test_invoke_connect_error_raises_custom_exception(mock_sleep, client: AnkiConnectClient, mocker):
    """Test that invoke raises AnkiConnectionError after retries on httpx.ConnectError."""
    # Mock the httpx client's post method within the AnkiConnectClient instance
    mock_post = AsyncMock(side_effect=httpx.ConnectError("Connection failed"))
    client.client.post = mock_post # Replace the method on the instance

    action = AnkiAction.DECK_NAMES
    params = {}

    with pytest.raises(AnkiConnectionError) as excinfo:
        await client.invoke(action, **params)

    # Assertions
    assert "Unable to connect to AnkiConnect" in str(excinfo.value)
    assert "Connection failed" in str(excinfo.value) # Check original error is mentioned
    assert mock_post.call_count == 3 # Check if it retried 3 times
    # Check sleep calls with exponential backoff (0 -> 1s, 1 -> 2s)
    assert mock_sleep.call_args_list == [call(1), call(2)] # 2**0, 2**1


@pytest.mark.asyncio
@patch('asyncio.sleep', return_value=None) # Mock sleep
async def test_invoke_timeout_error_raises_custom_exception(mock_sleep, client: AnkiConnectClient, mocker):
    """Test that invoke raises AnkiConnectionError after retries on httpx.TimeoutException."""
    mock_post = AsyncMock(side_effect=httpx.TimeoutException("Request timed out"))
    client.client.post = mock_post

    action = AnkiAction.FIND_CARDS
    params = {"query": "test"}

    with pytest.raises(AnkiConnectionError) as excinfo:
        await client.invoke(action, **params)

    assert "Unable to connect to AnkiConnect" in str(excinfo.value)
    assert "timed out" in str(excinfo.value) # Check original error is mentioned
    assert mock_post.call_count == 3
    assert mock_sleep.call_args_list == [call(1), call(2)]


@pytest.mark.asyncio
@patch('asyncio.sleep', return_value=None)
async def test_invoke_success_after_retry(mock_sleep, client: AnkiConnectClient, mocker):
    """Test that invoke succeeds if a retry attempt is successful."""
    mock_response_data = {"result": ["Deck1", "Deck2"], "error": None}
    # Simulate failure on first attempt, success on second
    mock_post = AsyncMock(side_effect=[
        httpx.TimeoutException("Timeout on first try"),
        AsyncMock( # Mock successful response object for second try
            spec=httpx.Response,
            status_code=200,
            # Make json() a sync method returning the data
            json=MagicMock(return_value=mock_response_data),
            # raise_for_status is sync
            raise_for_status=MagicMock()
        )
    ])
    # No need for the separate successful_response_mock setup now

    # The side_effect list directly contains the exception and the configured AsyncMock
    # mock_post = AsyncMock(side_effect=[
    #     httpx.TimeoutException("Timeout on first try"),
    #     successful_response_mock # Return the configured mock on the second call
    # ])
    # Assign the mock_post with the side_effect directly


    client.client.post = mock_post

    action = AnkiAction.DECK_NAMES
    params = {}

    result = await client.invoke(action, **params)

    assert result == ["Deck1", "Deck2"]
    assert mock_post.call_count == 2 # Failed once, succeeded once
    assert mock_sleep.call_count == 1 # Slept after the first failure
    assert mock_sleep.call_args == call(1) # 2**0


@pytest.mark.asyncio
async def test_invoke_http_status_error_raises_runtimeerror(client: AnkiConnectClient, mocker):
    """Test that invoke raises RuntimeError for non-connection HTTP errors."""
    # Create a mock request object needed for HTTPStatusError
    mock_request = mocker.Mock(spec=httpx.Request)
    # Configure json() to be a sync method returning the expected dict structure
    def mock_json():
        return {"result": None, "error": "Server error occurred"}

    mock_response = MagicMock(spec=httpx.Response, status_code=500, text="Internal Server Error", request=mock_request)
    # Configure the mock response to raise HTTPStatusError when raise_for_status is called
    # raise_for_status is synchronous, so use MagicMock or configure directly
    http_error = httpx.HTTPStatusError(
        message="Server error", request=mock_request, response=mock_response # Pass the mock_response itself
    )
    # Configure raise_for_status directly on the mock_response instance
    mock_response.raise_for_status = MagicMock(side_effect=http_error)
    # Assign the synchronous mock_json function
    mock_response.json = mock_json


    mock_post = AsyncMock(return_value=mock_response)
    client.client.post = mock_post

    action = AnkiAction.ADD_NOTE
    params = {"note": {"deckName": "Test", "modelName": "Basic", "fields": {"Front": "Q", "Back": "A"}}}

    with pytest.raises(RuntimeError) as excinfo:
        await client.invoke(action, **params)

    assert "AnkiConnect request failed with status 500" in str(excinfo.value)
    assert "Internal Server Error" in str(excinfo.value)
    assert mock_post.call_count == 1 # No retries for HTTP status errors


@pytest.mark.asyncio
async def test_invoke_anki_api_error_raises_valueerror(client: AnkiConnectClient, mocker):
    """Test that invoke raises ValueError for errors reported by the AnkiConnect API."""
    mock_response_data = {"result": None, "error": "Deck not found"}
    # Make json synchronous
    mock_response = MagicMock(
        spec=httpx.Response,
        status_code=200,
        json=MagicMock(return_value=mock_response_data)
    )
    mock_response.raise_for_status = MagicMock() # No HTTP error, sync method

    mock_post = AsyncMock(return_value=mock_response)
    client.client.post = mock_post

    action = AnkiAction.ADD_NOTE
    params = {"note": {"deckName": "NonExistent", "modelName": "Basic", "fields": {"Front": "Q", "Back": "A"}}}

    with pytest.raises(ValueError) as excinfo:
        await client.invoke(action, **params)

    assert "AnkiConnect error: Deck not found" in str(excinfo.value)
    assert mock_post.call_count == 1


# --- Keep existing tests for client methods (like test_deck_names, test_add_note)
# They implicitly test the success path of invoke. Ensure they close the client. ---

@pytest.mark.asyncio
async def test_add_note(client: AnkiConnectClient, mocker: MockerFixture, mock_response): # Keep mock_response if used here
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
