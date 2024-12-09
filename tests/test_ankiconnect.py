import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from httpx import HTTPError

from mcp_ankiconnect.ankiconnect_client import AnkiConnectClient

@pytest.fixture
async def mocked_anki_client():
    client = AsyncMock(spec=AnkiConnectClient)
    yield client
    await client.close()

# Test AnkiConnectClient operations
async def test_deck_names(mocked_anki_client):
    mocked_anki_client.invoke.return_value = ["Default", "Test"]
    result = await mocked_anki_client.deck_names()
    assert result == ["Default", "Test"]
    mocked_anki_client.invoke.assert_called_once_with("deckNames")

async def test_find_cards(mocked_anki_client):
    mocked_anki_client.invoke.return_value = [1, 2, 3]
    result = await mocked_anki_client.find_cards("deck:Test")
    assert result == [1, 2, 3]
    mocked_anki_client.invoke.assert_called_once_with("findCards", query="deck:Test")

async def test_cards_info(mocked_anki_client):
    mock_cards = [{"cardId": 1, "fields": {}}, {"cardId": 2, "fields": {}}]
    mocked_anki_client.invoke.return_value = mock_cards
    result = await mocked_anki_client.cards_info([1, 2])
    assert result == mock_cards
    mocked_anki_client.invoke.assert_called_once_with("cardsInfo", cards=[1, 2])

async def test_answer_cards(mocked_anki_client):
    mock_answers = [{"cardId": 1, "ease": 3}, {"cardId": 2, "ease": 4}]
    mocked_anki_client.invoke.return_value = [True, True]
    result = await mocked_anki_client.answer_cards(mock_answers)
    assert result == [True, True]
    mocked_anki_client.invoke.assert_called_once_with("answerCards", answers=mock_answers)

async def test_model_names(mocked_anki_client):
    mock_models = ["Basic", "Cloze"]
    mocked_anki_client.invoke.return_value = mock_models
    result = await mocked_anki_client.model_names()
    assert result == mock_models
    mocked_anki_client.invoke.assert_called_once_with("modelNames")

async def test_model_field_names(mocked_anki_client):
    mock_fields = ["Front", "Back"]
    mocked_anki_client.invoke.return_value = mock_fields
    result = await mocked_anki_client.model_field_names("Basic")
    assert result == mock_fields
    mocked_anki_client.invoke.assert_called_once_with("modelFieldNames", modelName="Basic")

async def test_add_note(mocked_anki_client):
    mock_note = {
        "deckName": "Test",
        "modelName": "Basic",
        "fields": {"Front": "Q", "Back": "A"},
        "tags": ["test"]
    }
    mocked_anki_client.invoke.return_value = 12345  # Note ID
    result = await mocked_anki_client.add_note(mock_note)
    assert result == 12345
    mocked_anki_client.invoke.assert_called_once_with("addNote", note=mock_note)

# Test review card operations
async def test_fetch_due_cards_for_review_no_args(anki_server, mocked_anki_client):
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
    result = await anki_server.fetch_due_cards_for_review()

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

async def test_invoke_http_error():
    with patch('httpx.AsyncClient') as mock_client_class:
        mock_client = AsyncMock()
        mock_client_class.return_value = mock_client
        client = AnkiConnectClient()

        mock_client.post.side_effect = HTTPError("Connection failed")
        with pytest.raises(RuntimeError) as exc_info:
            await client.invoke("deckNames")
        assert "Failed to communicate with AnkiConnect" in str(exc_info.value)
        assert "Connection failed" in str(exc_info.value)

        await client.close()

async def test_invoke_anki_error():
    with patch('httpx.AsyncClient') as mock_client_class:
        mock_client = AsyncMock()
        mock_client_class.return_value = mock_client
        client = AnkiConnectClient()

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "error": "AnkiConnect error message",
            "result": None
        }
        mock_response.raise_for_status = MagicMock()
        mock_client.post.return_value = mock_response

        with pytest.raises(ValueError) as exc_info:
            await client.invoke("deckNames")
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
