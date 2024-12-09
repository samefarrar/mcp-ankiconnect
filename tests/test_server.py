import pytest
from pytest_mock import MockerFixture
from typing import List, Dict, Any

from mcp_ankiconnect.server import (
    get_cards_by_due_and_deck,
    num_cards_due_today,
    list_decks_and_notes,
    get_examples,
    fetch_due_cards_for_review,
    submit_reviews
)

@pytest.fixture
def mock_anki(mocker: MockerFixture):
    # Mock the AnkiConnectClient instance
    mock_client = mocker.patch('mcp_ankiconnect.server.anki')
    
    # Setup default return values
    mock_client.deck_names = mocker.AsyncMock(return_value=["Default", "Test Deck"])
    mock_client.find_cards = mocker.AsyncMock(return_value=[1, 2, 3])
    mock_client.cards_info = mocker.AsyncMock(return_value=[
        {"cardId": 1, "deck": "Default"},
        {"cardId": 2, "deck": "Default"},
        {"cardId": 3, "deck": "Default"}
    ])
    
    return mock_client

@pytest.mark.asyncio
async def test_get_cards_by_due_and_deck(mock_anki):
    # Test with no parameters
    cards = await get_cards_by_due_and_deck()
    mock_anki.find_cards.assert_called_with(query="is:due prop:due=0")
    assert cards == [1, 2, 3]

    # Test with deck filter
    cards = await get_cards_by_due_and_deck(deck="Default")
    mock_anki.find_cards.assert_called_with(query="is:due prop:due=0 deck:Default")
    
    # Test with day parameter
    cards = await get_cards_by_due_and_deck(day=1)
    mock_anki.find_cards.assert_called_with(query="is:due prop:due<2")

@pytest.mark.asyncio
async def test_num_cards_due_today(mock_anki):
    result = await num_cards_due_today()
    assert "There are 3 cards due across all decks" in result

    result = await num_cards_due_today(deck="Default")
    assert "There are 3 cards due in deck 'Default'" in result

@pytest.mark.asyncio
async def test_list_decks_and_notes(mock_anki):
    mock_anki.model_names = mocker.AsyncMock(return_value=["Basic", "Cloze"])
    mock_anki.model_field_names = mocker.AsyncMock(return_value=["Front", "Back"])
    
    result = await list_decks_and_notes()
    assert "Default" in result
    assert "Test Deck" in result
    assert "Basic" in result
    assert "Cloze" in result

@pytest.mark.asyncio
async def test_get_examples(mock_anki, mocker: MockerFixture):
    mock_anki.find_notes = mocker.AsyncMock(return_value=[1, 2])
    mock_anki.notes_info = mocker.AsyncMock(return_value=[
        {
            "noteId": 1,
            "tags": ["test"],
            "modelName": "Basic",
            "fields": {
                "Front": {"value": "Question 1", "order": 0},
                "Back": {"value": "Answer 1", "order": 1}
            }
        }
    ])
    
    result = await get_examples(limit=1)
    assert "Question 1" in result
    assert "Answer 1" in result

@pytest.mark.asyncio
async def test_fetch_due_cards_for_review(mock_anki):
    mock_anki.cards_info.return_value = [
        {
            "cardId": 1,
            "fields": {
                "Front": {"value": "Question", "order": 0},
                "Back": {"value": "Answer", "order": 1}
            },
            "fieldOrder": 0
        }
    ]
    
    result = await fetch_due_cards_for_review(limit=1)
    assert "<card id=\"1\">" in result
    assert "<question>" in result
    assert "<answer>" in result

@pytest.mark.asyncio
async def test_submit_reviews(mock_anki):
    mock_anki.answer_cards = mocker.AsyncMock(return_value=[True])
    
    class Review:
        def __init__(self, card_id, rating):
            self.card_id = card_id
            self.rating = rating
    
    reviews = [Review(1, "good")]
    result = await submit_reviews(reviews)
    assert "successfully" in result
    assert "Card 1" in result
