import pytest
from unittest.mock import AsyncMock, patch, MagicMock, call # Import MagicMock, call
from typing import List, Dict, Any # Keep if needed

# Use absolute imports for tests
from mcp_ankiconnect.server import (
    num_cards_due_today,
    list_decks_and_notes,
    get_examples,
    fetch_due_cards_for_review,
    submit_reviews,
    add_note,
    store_media_file,
    search_notes,
    mcp # Import the MCP instance if needed for registration checks
)
# Import the custom exception and the client (for spec)
from mcp_ankiconnect.ankiconnect_client import AnkiConnectionError, AnkiConnectClient
from mcp_ankiconnect.config import RATING_TO_EASE # Import if needed for tests

# --- Mock Anki Client Fixture ---
# This fixture provides a mocked AnkiConnectClient instance
@pytest.fixture
def mock_anki_client():
    mock_client = MagicMock(spec=AnkiConnectClient)
    # Make methods async mocks
    mock_client.deck_names = AsyncMock()
    mock_client.find_cards = AsyncMock()
    mock_client.cards_info = AsyncMock()
    mock_client.model_names = AsyncMock()
    mock_client.model_field_names = AsyncMock()
    mock_client.find_notes = AsyncMock()
    mock_client.notes_info = AsyncMock()
    mock_client.add_note = AsyncMock()
    mock_client.answer_cards = AsyncMock()
    mock_client.store_media_file = AsyncMock()
    mock_client.close = AsyncMock() # Mock close as well
    return mock_client

# --- Patch the Context Manager ---
# This fixture patches the 'get_anki_client' context manager used by the tools
# to yield our mocked client instance.
@pytest.fixture(autouse=True) # Apply automatically to all tests in this module
def patch_get_anki_client(mock_anki_client):
    # Patch the context manager within the server module
    with patch('mcp_ankiconnect.server.get_anki_client') as mock_context_manager:
        # Configure the __aenter__ method of the context manager's return value
        # to return the mock_anki_client
        mock_context_manager.return_value.__aenter__.return_value = mock_anki_client
        # Configure __aexit__ as well
        mock_context_manager.return_value.__aexit__ = AsyncMock(return_value=None)
        yield mock_context_manager # Yield the patch object if needed, otherwise just yield


# --- Tests for Tools ---

# Remove test_get_cards_by_due_and_deck as it's now a helper (_find_due_card_ids) tested implicitly

# --- num_cards_due_today ---
@pytest.mark.asyncio
async def test_num_cards_due_today_success(mock_anki_client):
    """Test num_cards_due_today success path."""
    mock_anki_client.find_cards.return_value = [101, 102, 103] # Simulate finding 3 cards

    # Test without deck
    result_all = await num_cards_due_today()
    mock_anki_client.find_cards.assert_called_with(query='is:due -is:suspended prop:due=0')
    assert result_all == "There are 3 cards due today across all decks."

    # Test with deck
    mock_anki_client.find_cards.reset_mock() # Reset mock for next call
    mock_anki_client.find_cards.return_value = [101] # Simulate finding 1 card
    result_deck = await num_cards_due_today(deck="TestDeck")
    mock_anki_client.find_cards.assert_called_with(query='is:due -is:suspended prop:due=0 "deck:TestDeck"')
    assert result_deck == "There are 1 cards due today in deck 'TestDeck'."


@pytest.mark.asyncio
async def test_num_cards_due_today_connection_error(mock_anki_client):
    """Test num_cards_due_today handles AnkiConnectionError via decorator."""
    # Configure the mock client method to raise the specific error
    error_message = "Connection refused"
    mock_anki_client.find_cards.side_effect = AnkiConnectionError(error_message)

    result = await num_cards_due_today(deck="TestDeck")

    # Assert client method was called
    mock_anki_client.find_cards.assert_called_once()
    # Assert the decorator caught the error and returned the specific SYSTEM_ERROR message
    assert "SYSTEM_ERROR: Cannot connect to Anki." in result
    assert "Please inform the user" in result
    assert error_message in result # Check that the original error detail is included

# --- list_decks_and_notes ---
@pytest.mark.asyncio
async def test_list_decks_and_notes_success(mock_anki_client):
    """Test list_decks_and_notes success path."""
    mock_anki_client.deck_names.return_value = ["Default", "Test Deck", "AnKing::Step1"]
    mock_anki_client.model_names.return_value = ["Basic", "Cloze", "#AK_Step1_v12"]
    # Simulate different fields for different models
    mock_anki_client.model_field_names.side_effect = [
        ["Front", "Back"], # For Basic
        ["Text", "Back Extra"] # For Cloze
    ]

    result = await list_decks_and_notes()

    # Assertions
    assert "You have 2 filtered decks: Default, Test Deck" in result # Excludes AnKing
    assert "Your filtered note types and their fields are:" in result
    assert "- Basic: { \"Front\": \"string\", \"Back\": \"string\" }" in result
    assert "- Cloze: { \"Text\": \"string\", \"Back Extra\": \"string\" }" in result
    assert "#AK_Step1_v12" not in result # Excluded model

    # Check calls
    mock_anki_client.deck_names.assert_called_once()
    mock_anki_client.model_names.assert_called_once()
    assert mock_anki_client.model_field_names.call_count == 2 # Called for Basic and Cloze
    assert mock_anki_client.model_field_names.call_args_list == [
        call('Basic'),
        call('Cloze')
    ]

@pytest.mark.asyncio
async def test_list_decks_and_notes_connection_error(mock_anki_client):
    """Test list_decks_and_notes handles AnkiConnectionError."""
    error_message = "Network is unreachable"
    mock_anki_client.deck_names.side_effect = AnkiConnectionError(error_message)

    result = await list_decks_and_notes()

    mock_anki_client.deck_names.assert_called_once()
    mock_anki_client.model_names.assert_not_called() # Should not be called if deck_names failed

    assert "SYSTEM_ERROR: Cannot connect to Anki." in result
    assert error_message in result

# --- get_examples ---
@pytest.mark.asyncio
async def test_get_examples_success(mock_anki_client):
    """Test get_examples success path."""
    mock_anki_client.find_notes.return_value = [101, 102]
    mock_anki_client.notes_info.return_value = [
        {
            "noteId": 101, "modelName": "Basic", "tags": ["tag1"],
            "fields": {"Front": {"value": "Q1 <pre><code>code</code></pre>", "order": 0}, "Back": {"value": "A1", "order": 1}}
        },
        {
            "noteId": 102, "modelName": "Cloze", "tags": ["tag2"],
            "fields": {"Text": {"value": "Cloze {{c1::text}}", "order": 0}, "Extra": {"value": "Extra info", "order": 1}}
        }
    ]

    result = await get_examples(limit=2, sample="recent", deck="MyDeck")

    # Check query construction (adjust based on implementation)
    expected_query = '-is:suspended -note:*AnKing* -note:*#AK_* -note:*!AK_* "deck:MyDeck" added:7 sort:added rev' # Example query
    mock_anki_client.find_notes.assert_called_once_with(query=expected_query)
    mock_anki_client.notes_info.assert_called_once_with([101, 102])

    assert '"modelName": "Basic"' in result
    assert '"Front": "Q1 <code>code</code>"' in result # Check field processing
    assert '"Back": "A1"' in result
    assert '"modelName": "Cloze"' in result
    assert '"Text": "Cloze {{c1::text}}"' in result
    # Adjust assertion to account for json.dumps formatting with indentation
    assert '"tags": [\n      "tag1"\n    ]' in result

@pytest.mark.asyncio
async def test_get_examples_connection_error(mock_anki_client):
    """Test get_examples handles AnkiConnectionError."""
    error_message = "Failed to resolve host"
    mock_anki_client.find_notes.side_effect = AnkiConnectionError(error_message)

    result = await get_examples(limit=1)

    mock_anki_client.find_notes.assert_called_once()
    mock_anki_client.notes_info.assert_not_called()

    assert "SYSTEM_ERROR: Cannot connect to Anki." in result
    assert error_message in result

# --- fetch_due_cards_for_review ---
@pytest.mark.asyncio
async def test_fetch_due_cards_for_review_success(mock_anki_client):
    """Test fetch_due_cards_for_review success path."""
    mock_anki_client.find_cards.return_value = [201, 202] # Found 2 due cards
    mock_anki_client.cards_info.return_value = [
        {
            "cardId": 201, "note": 101, "deckName": "Default", "fieldOrder": 0, # fieldOrder indicates Question field index
            "fields": {
                "Front": {"value": "Question 1", "order": 0},
                "Back": {"value": "Answer 1", "order": 1},
                "Source": {"value": "Book A", "order": 2}
            }
        }
    ]

    result = await fetch_due_cards_for_review(limit=1, today_only=True)

    # Check find_cards call (for today, day=0)
    mock_anki_client.find_cards.assert_called_once_with(query='is:due -is:suspended prop:due=0')
    # Check cards_info call (limited to 1)
    mock_anki_client.cards_info.assert_called_once_with(card_ids=[201])

    assert "<card id=\"201\">" in result
    assert "<question><front>Question 1</front></question>" in result
    # Check that answer includes fields not matching fieldOrder, in order
    assert "<answer><back>Answer 1</back> <source>Book A</source></answer>" in result
    assert "{{flashcards}}" not in result # Placeholder should be replaced

@pytest.mark.asyncio
async def test_fetch_due_cards_for_review_connection_error(mock_anki_client):
    """Test fetch_due_cards_for_review handles AnkiConnectionError."""
    error_message = "Connection timed out"
    mock_anki_client.find_cards.side_effect = AnkiConnectionError(error_message)

    result = await fetch_due_cards_for_review(limit=1)

    mock_anki_client.find_cards.assert_called_once()
    mock_anki_client.cards_info.assert_not_called()

    assert "SYSTEM_ERROR: Cannot connect to Anki." in result
    assert error_message in result

# --- submit_reviews ---
@pytest.mark.asyncio
async def test_submit_reviews_success(mock_anki_client):
    """Test submit_reviews success path."""
    # Simulate AnkiConnect returning success for both reviews
    mock_anki_client.answer_cards.return_value = [True, True]

    reviews_payload = [
        {"card_id": 301, "rating": "good"},
        {"card_id": 302, "rating": "wrong"}
    ]

    result = await submit_reviews(reviews=reviews_payload)

    # Check that answer_cards was called with correct ease ratings
    expected_answers = [
        {"cardId": 301, "ease": RATING_TO_EASE["good"]}, # 3
        {"cardId": 302, "ease": RATING_TO_EASE["wrong"]} # 1
    ]
    mock_anki_client.answer_cards.assert_called_once_with(answers=expected_answers)

    assert "Review submission summary: 2 successful, 0 failed." in result
    assert "Card 301: Marked as 'good' successfully." in result
    assert "Card 302: Marked as 'wrong' successfully." in result

@pytest.mark.asyncio
async def test_submit_reviews_partial_failure(mock_anki_client):
    """Test submit_reviews when AnkiConnect reports partial failure."""
    # Simulate AnkiConnect returning success for first, failure for second
    mock_anki_client.answer_cards.return_value = [True, False]

    reviews_payload = [
        {"card_id": 301, "rating": "easy"},
        {"card_id": 302, "rating": "hard"}
    ]

    result = await submit_reviews(reviews=reviews_payload)

    expected_answers = [
        {"cardId": 301, "ease": RATING_TO_EASE["easy"]}, # 4
        {"cardId": 302, "ease": RATING_TO_EASE["hard"]} # 2
    ]
    mock_anki_client.answer_cards.assert_called_once_with(answers=expected_answers)

    assert "Review submission summary: 1 successful, 1 failed." in result
    assert "Card 301: Marked as 'easy' successfully." in result
    assert "Card 302: Failed to mark as 'hard'." in result


@pytest.mark.asyncio
async def test_submit_reviews_validation_error(mock_anki_client):
    """Test submit_reviews handles invalid input rating."""
    reviews_payload = [
        {"card_id": 301, "rating": "okay"} # Invalid rating
    ]

    result = await submit_reviews(reviews=reviews_payload)

    # Client should not be called if validation fails
    mock_anki_client.answer_cards.assert_not_called()

    assert "SYSTEM_ERROR: Could not submit reviews due to validation errors:" in result
    assert "Invalid rating 'okay' for card_id 301" in result

@pytest.mark.asyncio
async def test_submit_reviews_connection_error(mock_anki_client):
    """Test submit_reviews handles AnkiConnectionError."""
    error_message = "Connection reset by peer"
    mock_anki_client.answer_cards.side_effect = AnkiConnectionError(error_message)

    reviews_payload = [{"card_id": 301, "rating": "good"}]
    result = await submit_reviews(reviews=reviews_payload)

    mock_anki_client.answer_cards.assert_called_once()
    assert "SYSTEM_ERROR: Cannot connect to Anki." in result
    assert error_message in result

# --- add_note ---
@pytest.mark.asyncio
async def test_add_note_success(mock_anki_client):
    """Test add_note success path with field processing."""
    mock_anki_client.add_note.return_value = 1234567890 # Simulate successful note addition

    deck = "MyDeck"
    model = "Basic"
    fields = {
        "Front": "Question `code` here",
        "Back": "Answer <math>e=mc^2</math>",
        "Code": "```python\ndef hello():\n  print('hi')\n```"
        }
    tags = ["test", "math", "code"]

    result = await add_note(deckName=deck, modelName=model, fields=fields, tags=tags)

    # Assert client method was called with processed fields
    expected_processed_fields = {
        "Front": "Question <code>code</code> here", # `code` -> <code>code</code>
        "Back": "Answer \\(e=mc^2\\)",      # <math> -> \( \)
        "Code": '<pre><code class="language-python">def hello():\n  print(\'hi\')\n</code></pre>' # ```python...``` -> <pre><code class="language-python">...</code></pre>
    }
    expected_payload = {
        "deckName": deck,
        "modelName": model,
        "fields": expected_processed_fields,
        "tags": tags,
        "options": {"allowDuplicate": False, "duplicateScope": "deck"}
    }
    mock_anki_client.add_note.assert_called_once_with(note=expected_payload)
    # Assert the tool returned the success message
    assert result == f"Successfully created note with ID: 1234567890 in deck '{deck}'."

@pytest.mark.asyncio
async def test_add_note_connection_error(mock_anki_client):
    """Test add_note handles AnkiConnectionError via decorator."""
    error_message = "Timeout connecting"
    mock_anki_client.add_note.side_effect = AnkiConnectionError(error_message)

    deck = "MyDeck"
    model = "Basic"
    fields = {"Front": "Q", "Back": "A"}

    result = await add_note(deckName=deck, modelName=model, fields=fields)

    # The mock *is* called, but the decorator catches the raised exception.
    mock_anki_client.add_note.assert_called_once()
    assert "SYSTEM_ERROR: Cannot connect to Anki." in result
    assert error_message in result

@pytest.mark.asyncio
async def test_add_note_api_error(mock_anki_client):
    """Test add_note handles Anki API errors (ValueError) via decorator."""
    # Simulate an error raised from invoke due to Anki API response
    error_message = "AnkiConnect error: Model not found"
    mock_anki_client.add_note.side_effect = ValueError(error_message)

    deck = "MyDeck"
    model = "NonExistentModel"
    fields = {"Front": "Q", "Back": "A"}

    result = await add_note(deckName=deck, modelName=model, fields=fields)

    # The mock *is* called, but the decorator catches the raised exception.
    mock_anki_client.add_note.assert_called_once()
    # Assert the decorator caught the ValueError and returned the specific SYSTEM_ERROR message
    assert "SYSTEM_ERROR: An error occurred communicating with Anki:" in result
    assert error_message in result


@pytest.mark.asyncio
async def test_add_note_with_picture_url(mock_anki_client):
    """Test add_note with a picture attachment via URL."""
    mock_anki_client.add_note.return_value = 9876543210

    deck = "MyDeck"
    model = "Basic"
    fields = {"Front": "What animal is this?", "Back": "A cat"}
    tags = ["animals"]
    pictures = [
        {
            "url": "https://example.com/cat.jpg",
            "filename": "cat.jpg",
            "fields": ["Back"],
        }
    ]

    result = await add_note(
        deckName=deck, modelName=model, fields=fields, tags=tags, picture=pictures
    )

    # Verify the note payload includes the picture
    call_kwargs = mock_anki_client.add_note.call_args[1]
    note_payload = call_kwargs["note"]
    assert note_payload["picture"] == pictures
    assert note_payload["deckName"] == deck
    assert note_payload["fields"]["Front"] == "What animal is this?"

    assert "Successfully created note with ID: 9876543210" in result
    assert "1 image(s) attached" in result


@pytest.mark.asyncio
async def test_add_note_with_picture_base64(mock_anki_client):
    """Test add_note with a picture attachment via base64 data."""
    mock_anki_client.add_note.return_value = 1111111111

    deck = "Science"
    model = "Basic"
    fields = {"Front": "What does this diagram show?", "Back": "Cell division"}
    pictures = [
        {
            "data": "iVBORw0KGgoAAAANSUhEUg==",
            "filename": "cell_division.png",
            "fields": ["Front"],
        }
    ]

    result = await add_note(
        deckName=deck, modelName=model, fields=fields, picture=pictures
    )

    call_kwargs = mock_anki_client.add_note.call_args[1]
    note_payload = call_kwargs["note"]
    assert note_payload["picture"] == pictures
    assert note_payload["tags"] == []  # No tags provided, should default to []

    assert "Successfully created note with ID: 1111111111" in result
    assert "1 image(s) attached" in result


@pytest.mark.asyncio
async def test_add_note_with_multiple_pictures(mock_anki_client):
    """Test add_note with multiple picture attachments."""
    mock_anki_client.add_note.return_value = 2222222222

    pictures = [
        {"url": "https://example.com/img1.jpg", "filename": "img1.jpg", "fields": ["Front"]},
        {"url": "https://example.com/img2.jpg", "filename": "img2.jpg", "fields": ["Back"]},
    ]

    result = await add_note(
        deckName="Deck", modelName="Basic",
        fields={"Front": "Q", "Back": "A"},
        picture=pictures,
    )

    call_kwargs = mock_anki_client.add_note.call_args[1]
    assert len(call_kwargs["note"]["picture"]) == 2
    assert "2 image(s) attached" in result


@pytest.mark.asyncio
async def test_add_note_without_picture(mock_anki_client):
    """Test add_note without picture parameter does not include picture key."""
    mock_anki_client.add_note.return_value = 3333333333

    result = await add_note(
        deckName="Deck", modelName="Basic",
        fields={"Front": "Q", "Back": "A"},
    )

    call_kwargs = mock_anki_client.add_note.call_args[1]
    assert "picture" not in call_kwargs["note"]
    assert "image(s) attached" not in result
    assert "Successfully created note" in result


# --- store_media_file ---
@pytest.mark.asyncio
async def test_store_media_file_with_url(mock_anki_client):
    """Test store_media_file with a URL source."""
    mock_anki_client.store_media_file.return_value = "cat_photo.jpg"

    result = await store_media_file(
        filename="cat_photo.jpg",
        url="https://example.com/cat.jpg",
    )

    mock_anki_client.store_media_file.assert_called_once_with(
        filename="cat_photo.jpg",
        url="https://example.com/cat.jpg",
        data=None,
    )
    assert "Successfully stored media file as 'cat_photo.jpg'" in result
    assert '<img src="cat_photo.jpg">' in result


@pytest.mark.asyncio
async def test_store_media_file_with_base64(mock_anki_client):
    """Test store_media_file with base64 data."""
    mock_anki_client.store_media_file.return_value = "diagram.png"

    result = await store_media_file(
        filename="diagram.png",
        data="iVBORw0KGgoAAAANSUhEUg==",
    )

    mock_anki_client.store_media_file.assert_called_once_with(
        filename="diagram.png",
        url=None,
        data="iVBORw0KGgoAAAANSUhEUg==",
    )
    assert "Successfully stored media file as 'diagram.png'" in result


@pytest.mark.asyncio
async def test_store_media_file_no_source(mock_anki_client):
    """Test store_media_file returns error when no source is provided."""
    result = await store_media_file(filename="orphan.jpg")

    mock_anki_client.store_media_file.assert_not_called()
    assert "SYSTEM_ERROR: Must provide either 'url' or 'data'" in result


@pytest.mark.asyncio
async def test_store_media_file_connection_error(mock_anki_client):
    """Test store_media_file handles AnkiConnectionError via decorator."""
    error_message = "Connection refused"
    mock_anki_client.store_media_file.side_effect = AnkiConnectionError(error_message)

    result = await store_media_file(
        filename="test.jpg",
        url="https://example.com/test.jpg",
    )

    mock_anki_client.store_media_file.assert_called_once()
    assert "SYSTEM_ERROR: Cannot connect to Anki." in result
    assert error_message in result


# --- Tests for Helper Functions ---

# Test _process_field_content
@pytest.mark.parametrize("input_content, expected_output", [
    # Basic text
    ("Hello world", "Hello world"),
    # MathJax
    ("Equation: <math>e=mc^2</math>", "Equation: \\(e=mc^2\\)"),
    # Inline code
    ("Use `variable_name` here.", "Use <code>variable_name</code> here."),
    # Code block without language
    ("```\ncode line 1\ncode line 2\n```", "<pre><code>code line 1\ncode line 2\n</code></pre>"),
    # Code block with language
    ("```python\ndef test():\n  pass\n```", '<pre><code class="language-python">def test():\n  pass\n</code></pre>'),
    # Mixed content
    ("Text `code` and <math>math</math> and ```js\nconsole.log('hi');\n```", 'Text <code>code</code> and \\(math\\) and <pre><code class="language-js">console.log(\'hi\');\n</code></pre>'),
    # Non-string input (should return as-is)
    (123, 123),
    (None, None),
    (["list"], ["list"]),
])
def test__process_field_content(input_content, expected_output):
    """Test the _process_field_content helper for various transformations."""
    from mcp_ankiconnect.server import _process_field_content # Import locally for clarity
    assert _process_field_content(input_content) == expected_output

# Test _build_example_query
@pytest.mark.parametrize("deck, sample, expected_query_parts", [
    (None, "random", ["-is:suspended", "-note:*AnKing*", "-note:*#AK_*", "-note:*!AK_*", "is:review"]),
    ("MyDeck", "random", ["-is:suspended", "-note:*AnKing*", '-note:*#AK_*', '-note:*!AK_*', '"deck:MyDeck"', "is:review"]),
    (None, "recent", ["-is:suspended", "-note:*AnKing*", "-note:*#AK_*", "-note:*!AK_*", "added:7", "sort:added rev"]),
    ("Another Deck", "mature", ['-is:suspended', '-note:*AnKing*', '-note:*#AK_*', '-note:*!AK_*', '"deck:Another Deck"', 'prop:ivl>=21', '-is:learn', 'sort:ivl rev']),
    (None, "most_reviewed", ['-is:suspended', '-note:*AnKing*', '-note:*#AK_*', '-note:*!AK_*', 'prop:reps>10', 'sort:reps rev']),
    (None, "best_performance", ['-is:suspended', '-note:*AnKing*', '-note:*#AK_*', '-note:*!AK_*', 'prop:lapses<3', 'is:review', 'sort:lapses']),
    (None, "young", ['-is:suspended', '-note:*AnKing*', '-note:*#AK_*', '-note:*!AK_*', 'is:review', 'prop:ivl<=7', '-is:learn', 'sort:ivl']),
])
def test__build_example_query(deck, sample, expected_query_parts):
    """Test the _build_example_query helper for different inputs."""
    from mcp_ankiconnect.server import _build_example_query # Import locally
    # Check if all expected parts are present in the generated query
    # Order might vary slightly depending on implementation details, so check presence
    generated_query = _build_example_query(deck, sample)
    for part in expected_query_parts:
        assert part in generated_query
    # Check exclusion strings are present
    assert "-note:*AnKing*" in generated_query
    assert "-note:*#AK_*" in generated_query
    assert "-note:*!AK_*" in generated_query


# Test _format_example_notes
def test__format_example_notes():
    """Test the _format_example_notes helper."""
    from mcp_ankiconnect.server import _format_example_notes # Import locally
    notes_info = [
        {
            "noteId": 101, "modelName": "Basic", "tags": ["tag1"],
            "fields": {"Front": {"value": "Q1 <pre><code>code</code></pre>", "order": 0}, "Back": {"value": "A1", "order": 1}}
        },
        {
            "noteId": 102, "modelName": "Cloze", "tags": [],
            "fields": {"Text": {"value": "Cloze {{c1::text}}", "order": 0}, "Extra": {"value": "Extra info", "order": 1}}
        },
        { # Note with missing fields/modelName
            "noteId": 103, "tags": ["minimal"],
        }
    ]
    expected_output = [
        {
            "modelName": "Basic",
            "fields": {"Front": "Q1 <code>code</code>", "Back": "A1"}, # Check code simplification
            "tags": ["tag1"]
        },
        {
            "modelName": "Cloze",
            "fields": {"Text": "Cloze {{c1::text}}", "Extra": "Extra info"},
            "tags": []
        },
        {
            "modelName": "UnknownModel", # Default model name
            "fields": {}, # Empty fields dict
            "tags": ["minimal"]
        }
    ]
    assert _format_example_notes(notes_info) == expected_output

# Test _format_cards_for_llm
def test__format_cards_for_llm():
    """Test the _format_cards_for_llm helper."""
    from mcp_ankiconnect.server import _format_cards_for_llm # Import locally
    cards_info = [
        { # Basic card
            "cardId": 201, "note": 101, "deckName": "Default", "fieldOrder": 0, # Question is field 0 ('Front')
            "fields": {
                "Front": {"value": "Question 1", "order": 0},
                "Back": {"value": "Answer 1", "order": 1},
                "Source": {"value": "Book A", "order": 2}
            }
        },
        { # Cloze card (Question is field 0 - 'Text')
            "cardId": 202, "note": 102, "deckName": "Default", "fieldOrder": 0,
            "fields": {
                "Text": {"value": "Cloze {{c1::deletion}} here", "order": 0},
                "Extra": {"value": "Extra info", "order": 1}
            }
        },
        { # Card with different field order for question
            "cardId": 203, "note": 103, "deckName": "Default", "fieldOrder": 1, # Question is field 1 ('Back')
            "fields": {
                "Front": {"value": "Context", "order": 0},
                "Back": {"value": "Term", "order": 1},
                "Definition": {"value": "The definition", "order": 2}
            }
        },
        { # Card with missing fields
            "cardId": 204, "note": 104, "deckName": "Default", "fieldOrder": 0,
            "fields": {}
        }
    ]

    expected_output = (
        '<card id="201">\n'
        '  <question><front>Question 1</front></question>\n'
        '  <answer><back>Answer 1</back> <source>Book A</source></answer>\n'
        '</card>\n\n'
        '<card id="202">\n'
        '  <question><text>Cloze {{c1::deletion}} here</text></question>\n'
        '  <answer><extra>Extra info</extra></answer>\n'
        '</card>\n\n'
        '<card id="203">\n'
        '  <question><back>Term</back></question>\n'
        '  <answer><front>Context</front> <definition>The definition</definition></answer>\n' # Note order based on field 'order'
        '</card>\n\n'
        '<card id="204">\n'
        '  <question><error>Question field not found</error></question>\n'
        '  <answer><error>Answer fields not found</error></answer>\n'
        '</card>'
    )

    assert _format_cards_for_llm(cards_info) == expected_output


# --- search_notes ---
@pytest.mark.asyncio
async def test_search_notes_success(mock_anki_client):
    """Test search_notes success path with results."""
    mock_anki_client.find_notes.return_value = [101, 102, 103]
    mock_anki_client.notes_info.return_value = [
        {
            "noteId": 101, "modelName": "Basic", "tags": ["spanish", "vocab"],
            "fields": {"Front": {"value": "hola", "order": 0}, "Back": {"value": "hello", "order": 1}}
        },
        {
            "noteId": 102, "modelName": "Basic", "tags": ["spanish"],
            "fields": {"Front": {"value": "adios", "order": 0}, "Back": {"value": "goodbye", "order": 1}}
        },
        {
            "noteId": 103, "modelName": "Cloze", "tags": [],
            "fields": {"Text": {"value": "{{c1::gracias}} means thanks", "order": 0}}
        }
    ]

    result = await search_notes(query="deck:Spanish", limit=10)

    mock_anki_client.find_notes.assert_called_once_with(query="deck:Spanish")
    mock_anki_client.notes_info.assert_called_once_with([101, 102, 103])

    # Check the JSON response structure
    import json
    result_data = json.loads(result)
    assert result_data["query"] == "deck:Spanish"
    assert result_data["total_found"] == 3
    assert result_data["returned"] == 3
    assert len(result_data["notes"]) == 3

    # Check first note structure
    first_note = result_data["notes"][0]
    assert first_note["noteId"] == 101
    assert first_note["modelName"] == "Basic"
    assert first_note["tags"] == ["spanish", "vocab"]
    assert first_note["fields"]["Front"] == "hola"
    assert first_note["fields"]["Back"] == "hello"


@pytest.mark.asyncio
async def test_search_notes_no_results(mock_anki_client):
    """Test search_notes when no notes match the query."""
    mock_anki_client.find_notes.return_value = []

    result = await search_notes(query="nonexistent:query")

    mock_anki_client.find_notes.assert_called_once_with(query="nonexistent:query")
    mock_anki_client.notes_info.assert_not_called()

    import json
    result_data = json.loads(result)
    assert result_data["query"] == "nonexistent:query"
    assert result_data["total_found"] == 0
    assert result_data["notes"] == []
    assert "No notes found" in result_data["message"]


@pytest.mark.asyncio
async def test_search_notes_with_limit(mock_anki_client):
    """Test search_notes respects the limit parameter."""
    # Return more notes than the limit
    mock_anki_client.find_notes.return_value = [101, 102, 103, 104, 105]
    mock_anki_client.notes_info.return_value = [
        {"noteId": 101, "modelName": "Basic", "tags": [], "fields": {"Front": {"value": "Q1"}, "Back": {"value": "A1"}}},
        {"noteId": 102, "modelName": "Basic", "tags": [], "fields": {"Front": {"value": "Q2"}, "Back": {"value": "A2"}}},
    ]

    result = await search_notes(query="is:review", limit=2)

    mock_anki_client.find_notes.assert_called_once_with(query="is:review")
    # Should only fetch info for limited note IDs
    mock_anki_client.notes_info.assert_called_once_with([101, 102])

    import json
    result_data = json.loads(result)
    assert result_data["total_found"] == 5
    assert result_data["returned"] == 2
    assert len(result_data["notes"]) == 2
    assert "Showing 2 of 5" in result_data["message"]


@pytest.mark.asyncio
async def test_search_notes_connection_error(mock_anki_client):
    """Test search_notes handles AnkiConnectionError via decorator."""
    error_message = "Connection refused"
    mock_anki_client.find_notes.side_effect = AnkiConnectionError(error_message)

    result = await search_notes(query="deck:Test")

    mock_anki_client.find_notes.assert_called_once()
    mock_anki_client.notes_info.assert_not_called()

    assert "SYSTEM_ERROR: Cannot connect to Anki." in result
    assert error_message in result


@pytest.mark.asyncio
async def test_search_notes_complex_query(mock_anki_client):
    """Test search_notes with complex Anki query syntax."""
    mock_anki_client.find_notes.return_value = [101]
    mock_anki_client.notes_info.return_value = [
        {"noteId": 101, "modelName": "Basic", "tags": ["verb"], "fields": {"Front": {"value": "correr"}, "Back": {"value": "to run"}}}
    ]

    # Complex query with multiple filters
    complex_query = 'deck:Spanish tag:verb is:due prop:ivl>=7 -is:suspended'
    result = await search_notes(query=complex_query, limit=20)

    mock_anki_client.find_notes.assert_called_once_with(query=complex_query)
    mock_anki_client.notes_info.assert_called_once_with([101])

    import json
    result_data = json.loads(result)
    assert result_data["query"] == complex_query
    assert result_data["total_found"] == 1


# Test _format_search_results
def test__format_search_results():
    """Test the _format_search_results helper."""
    from mcp_ankiconnect.server import _format_search_results
    notes_info = [
        {
            "noteId": 101, "modelName": "Basic", "tags": ["tag1", "tag2"],
            "fields": {"Front": {"value": "Q1 <pre><code>code</code></pre>", "order": 0}, "Back": {"value": "A1", "order": 1}}
        },
        {
            "noteId": 102, "modelName": "Cloze", "tags": [],
            "fields": {"Text": {"value": "Cloze {{c1::text}}", "order": 0}}
        },
        {  # Note with missing fields/modelName
            "noteId": 103, "tags": ["minimal"],
        }
    ]
    expected_output = [
        {
            "noteId": 101,
            "modelName": "Basic",
            "fields": {"Front": "Q1 <code>code</code>", "Back": "A1"},  # Check code simplification
            "tags": ["tag1", "tag2"]
        },
        {
            "noteId": 102,
            "modelName": "Cloze",
            "fields": {"Text": "Cloze {{c1::text}}"},
            "tags": []
        },
        {
            "noteId": 103,
            "modelName": "UnknownModel",  # Default model name
            "fields": {},  # Empty fields dict
            "tags": ["minimal"]
        }
    ]
    assert _format_search_results(notes_info) == expected_output


def test__format_search_results_includes_note_ids():
    """Test that _format_search_results includes noteId for follow-up actions."""
    from mcp_ankiconnect.server import _format_search_results
    notes_info = [
        {"noteId": 12345, "modelName": "Basic", "tags": [], "fields": {"Front": {"value": "Q"}}}
    ]
    result = _format_search_results(notes_info)
    assert result[0]["noteId"] == 12345


# --- End Tests ---
