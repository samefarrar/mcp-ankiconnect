import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from typing import List, Any, Optional
from httpx import HTTPError

from mcp.types import TextContent
from mcp_ankiconnect.server import AnkiServer, AnkiAction, AnkiConnectClient

@pytest.fixture
def mocked_anki_client():
    client = AsyncMock(spec=AnkiConnectClient)
    return client

@pytest.fixture
def anki_server(mocked_anki_client):
    server = AnkiServer()
    server.anki = mocked_anki_client
    return server

# Test deck operations
async def test_get_cards_accesses_deck_names_and_find_cards(anki_server, mocked_anki_client):
    # Setup mock responses
    mocked_anki_client.deck_names.return_value = ["Default", "Test"]
    mocked_anki_client.find_cards.return_value = [1, 2, 3]  # Mock card IDs

    # Call function
    result = await anki_server.get_cards_due()

    mocked_anki_client.deck_names.assert_called_once()

    # Verify correct query construction
    mocked_anki_client.find_cards.assert_called_once_with(
        query="is:due prop:due=0"
    )

    assert result == [1, 2, 3]

async def test_get_cards_due_with_deck(anki_server, mocked_anki_client):
    # Setup mock responses
    mocked_anki_client.deck_names.return_value = ["Default", "Test"]
    mocked_anki_client.find_cards.return_value = [4, 5, 6]

    # Call function
    result = await anki_server.get_cards_due(deck = "Test")

    # Verify correct query construction with deck
    mocked_anki_client.find_cards.assert_called_once_with(
        query='is:due prop:due=0 deck:Test'
    )

    assert result == [4, 5, 6]

async def test_get_cards_due_invalid_deck(anki_server, mocked_anki_client):
    # Setup mock responses
    mocked_anki_client.deck_names.return_value = ["Default", "Test"]

    # Call function and verify it raises error
    with pytest.raises(ValueError, match="Deck 'Invalid' does not exist"):
        await anki_server.get_cards_due("Invalid")

# Test tool operations
async def test_num_cards_due_today_counts_accurately_without_deck(anki_server, mocked_anki_client):
    # Setup mock responses
    mocked_anki_client.deck_names.return_value = ["Default"]
    mocked_anki_client.find_cards.return_value = [1, 2, 3]

    # Call function
    result = await anki_server.num_cards_due_today()

    assert len(result) == 1
    assert result[0].type == "text"
    assert result[0].text == "There are 3 cards due across all decks"

async def test_num_cards_due_today_with_deck(anki_server, mocked_anki_client):
    # Setup mock responses
    mocked_anki_client.deck_names.return_value = ["Test"]
    mocked_anki_client.find_cards.return_value = [1, 2]

    # Call function
    result = await anki_server.num_cards_due_today(arguments = {"deck":"Test"})

    assert len(result) == 1
    assert result[0].type == "text"
    assert result[0].text == "There are 2 cards due in deck 'Test'"

# Test review card operations
async def test_review_cards_no_args(anki_server, mocked_anki_client):
    # Setup mock responses
    mocked_anki_client.deck_names.return_value = ["Default"]
    mocked_anki_client.find_cards.return_value = [1, 2]
    mocked_anki_client.cards_info.return_value = [
        {
            "cardId": 1,
            "fields": {
                "Front": {"value": "Question 1", "order": 0},
                "Back": {"value": "Answer 1", "order": 1}
            },
            "fieldOrder": 0
        },
        {
            "cardId": 2,
            "fields": {
                "Front": {"value": "Question 2", "order": 0},
                "Back": {"value": "Answer 2", "order": 1}
            },
            "fieldOrder": 0
        }
    ]

    # Call function
    result = await anki_server.get_due_cards(None)

    # Verify the correct format of returned content
    assert len(result) == 1
    assert result[0].type == "text"
    assert '<card id="1">' in result[0].text
    assert "<question><front>Question 1</front></question>" in result[0].text
    assert "<answer><back>Answer 1</back></answer>" in result[0].text
    assert "<question><front>Question 2</front></question>" in result[0].text
    assert "<answer><back>Answer 2</back></answer>" in result[0].text

async def test_review_cards_with_limit(anki_server, mocked_anki_client):
    # Setup mock responses
    mocked_anki_client.deck_names.return_value = ["Default"]
    mocked_anki_client.find_cards.return_value = [1, 2, 3, 4, 5, 6]
    mocked_anki_client.cards_info.return_value = [
        {
            "cardId": 1,
            "fields": {
                "Front": {"value": "Question 1", "order": 0},
                "Back": {"value": "Answer 1", "order": 1}
            },
            "fieldOrder": 0
        },
        {
            "cardId": 2,
            "fields": {
                "Front": {"value": "Question 2", "order": 0},
                "Back": {"value": "Answer 2", "order": 1}
            },
            "fieldOrder": 0
        }
    ]

    # Call function with limit
    result = await anki_server.get_due_cards({"limit": 2})

    # Verify cards_info was called with correct arguments
    mocked_anki_client.cards_info.assert_called_once_with(
        card_ids=[1, 2]
    )

    # Verify only one card is returned
    assert len(result) == 1
    assert result[0].type == "text"
    assert "<question><front>Question 1</front></question>" in result[0].text
    assert "<answer><back>Answer 1</back></answer>" in result[0].text
    assert "<question><front>Question 2</front></question>" in result[0].text
    assert "<answer><back>Answer 2</back></answer>" in result[0].text

async def test_review_cards_no_cards_found(anki_server, mocked_anki_client):
    # Setup mock responses
    mocked_anki_client.deck_names.return_value = ["Default"]
    mocked_anki_client.invoke.return_value = []

    # Call function
    result = await anki_server.get_due_cards(None)

    # Verify "no cards" message
    assert len(result) == 1
    assert result[0].type == "text"
    assert "No cards found to review" in result[0].text

@pytest.mark.asyncio
async def test_list_decks_and_notes(anki_server, mocked_anki_client):
    """Test listing decks and note types"""
    # Setup mock responses
    mocked_anki_client.deck_names.return_value = ["Default", "Test"]
    mocked_anki_client.invoke.side_effect = [
        ["Basic", "Cloze"],  # MODEL_NAMES response
        ["Front", "Back"],   # First MODEL_FIELD_NAMES response
        ["Text", "Back"]     # Second MODEL_FIELD_NAMES response
    ]
    
    # Call function
    result = await anki_server.list_decks_and_notes()
    
    # Verify response format
    assert len(result) == 1
    assert result[0].type == "text"
    
    # Parse JSON response
    data = json.loads(result[0].text)
    assert "decks" in data
    assert "note_types" in data
    assert data["decks"] == ["Default", "Test"]
    assert len(data["note_types"]) == 2
    assert data["note_types"][0]["name"] == "Basic"
    assert data["note_types"][0]["fields"] == ["Front", "Back"]
    assert data["note_types"][1]["name"] == "Cloze"
    assert data["note_types"][1]["fields"] == ["Text", "Back"]

async def test_invoke_error_handling():
    # Create AnkiConnectClient with mocked httpx client
    with patch('httpx.AsyncClient') as mock_client_class:
        mock_client = AsyncMock()
        mock_client_class.return_value = mock_client
        client = AnkiConnectClient()

        # Test HTTP error
        mock_client.post.side_effect = HTTPError("Connection failed")
        with pytest.raises(Exception) as exc_info:
            await client.invoke("deckNames")
        assert "Connection failed" in str(exc_info.value)

        # Test AnkiConnect error response
        mock_response = MagicMock()
        mock_response.json = lambda: {
            "error": "AnkiConnect error message",
            "result": None
        }
        mock_response.raise_for_status = AsyncMock()
        mock_client.post.side_effect = None
        mock_client.post.return_value = mock_response

        # We expect a RuntimeError wrapping the AnkiConnect error
        with pytest.raises(RuntimeError) as exc_info:
            await client.deck_names()
        assert "Error getting deck names" in str(exc_info.value)
        assert "AnkiConnect error: AnkiConnect error message" in str(exc_info.value)

        await client.close()

async def test_invoke_error_propagation(anki_server):
    # Replace the anki_server's client with our mocked one
    with patch('httpx.AsyncClient') as mock_client_class:
        mock_client = AsyncMock()
        mock_client_class.return_value = mock_client

        # Create a new AnkiConnectClient with our mocked HTTP client
        anki_server.anki = AnkiConnectClient()  # This will use our mocked httpx.AsyncClient

        # Make HTTP request fail
        mock_client.post.side_effect = HTTPError("Connection failed")

        # This should propagate through deck_names() -> invoke()
        with pytest.raises(RuntimeError) as exc_info:
            await anki_server.get_cards_due()
        assert "Error getting deck names" in str(exc_info.value)
        assert "Connection failed" in str(exc_info.value)

# Test cleanup
async def test_cleanup(anki_server, mocked_anki_client):
    await anki_server.cleanup()
    mocked_anki_client.close.assert_called_once()

# Integration-style tests
@pytest.mark.integration
async def test_submit_reviews_success(anki_server, mocked_anki_client):
    # Test each valid rating
    for rating in ["wrong", "hard", "good", "easy"]:
        # Setup test
        card_id = 123
        reviews = [{"card_id": card_id, "rating": rating}]
        args = {"reviews": reviews}

        # Get expected ease value
        ease_map = {"wrong": 1, "hard": 2, "good": 3, "easy": 4}
        expected_ease = ease_map[rating]

        # Setup mock response
        mocked_anki_client.answer_cards.return_value = [True]

        # Execute review
        result = await anki_server.submit_reviews(args)

        # Verify answer_cards was called with correct parameters
        expected_answers = [{"cardId": card_id, "ease": expected_ease}]
        mocked_anki_client.answer_cards.assert_called_with(expected_answers)

        # Verify response format
        assert len(result) == 1
        assert result[0].type == "text"
        assert result[0].text == f"Card {card_id} successfully marked as {rating}"

async def test_submit_reviews_missing_arguments(anki_server, mocked_anki_client):
    # Test with no arguments
    with pytest.raises(ValueError, match="Arguments required for submitting reviews"):
        await anki_server.submit_reviews(None)

async def test_submit_reviews_error_handling(anki_server, mocked_anki_client):
    # Setup test with error condition
    reviews = [{"card_id": 123, "rating": "good"}]
    args = {"reviews": reviews}
    mocked_anki_client.answer_cards.side_effect = RuntimeError("Failed to answer card")

    # Execute review and verify error propagation
    with pytest.raises(RuntimeError, match="Failed to answer card"):
        await anki_server.submit_reviews(args)

async def test_full_review_workflow(anki_server, mocked_anki_client):
    # Setup mock responses for a full workflow
    mocked_anki_client.deck_names.return_value = ["Test Deck"]
    mocked_anki_client.invoke.side_effect = [
        # First call - get due cards
        [1, 2],
        # Second call - find cards
        [1, 2]
    ]
    mocked_anki_client.cards_info.return_value = [
        {
            "cardId": 1,
            "fields": {
                "Front": {"value": "Test Question 1", "order": 0},
                "Back": {"value": "Test Answer 1", "order": 1}
            },
            "fieldOrder": 0
        },
        {
            "cardId": 2,
            "fields": {
                "Front": {"value": "Test Question 2", "order": 0},
                "Back": {"value": "Test Answer 2", "order": 1}
            },
            "fieldOrder": 0
        }
    ]

    # Execute review workflow
    args = {"deck": "Test Deck", "limit": 2, "today_only": True}
    result = await anki_server.get_due_cards(args)

    # Verify the full workflow results
    assert len(result) == 1
    assert result[0].type == "text"
    assert all(x in result[0].text for x in [
        "Test Question 1",
        "Test Answer 1",
        "Test Question 2",
        "Test Answer 2"
    ])
