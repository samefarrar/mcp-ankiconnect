from typing import List, Optional, Literal, Dict, Union
from typing import List, Optional, Literal, Dict, Union, AsyncGenerator # Added AsyncGenerator
import json
import re
import random
import logging
import functools # Import functools
from contextlib import asynccontextmanager
from mcp.server.fastmcp import FastMCP

# Use relative imports within the package
from .ankiconnect_client import AnkiConnectClient, AnkiConnectionError # Import custom exception
from .config import EXCLUDE_STRINGS, RATING_TO_EASE, ANKI_CONNECT_URL, MAX_FUTURE_DAYS # Import necessary configs
from .server_prompts import flashcard_guidelines, claude_review_instructions

from pydantic import Field

logger = logging.getLogger(__name__)

logger.info("Initializing MCP-AnkiConnect server")
mcp = FastMCP("mcp-ankiconnect")
logger.debug("Created FastMCP instance")

# --- Context Manager for Client ---
@asynccontextmanager
async def get_anki_client() -> AsyncGenerator[AnkiConnectClient, None]: # Added type hint
    # Pass the configured URL to the client constructor
    client = AnkiConnectClient(base_url=ANKI_CONNECT_URL)
    try:
        yield client
    except Exception: # Log exceptions during client usage if needed
        logger.exception("Error occurred while using AnkiConnect client")
        raise # Re-raise the exception
    finally:
        logger.debug("Closing AnkiConnect client")
        await client.close()

# --- Decorator for Connection Error Handling ---
def handle_anki_connection_error(func):
    """Decorator to catch AnkiConnectionError and return a user-friendly message."""
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            # Call the original async tool function
            return await func(*args, **kwargs)
        except AnkiConnectionError as e:
            logger.error(f"Caught Anki connection error in tool '{func.__name__}': {e}")
            # Return the specific message intended for the LLM
            # Ensure the message clearly indicates it's an error for the LLM to handle
            return (
                "SYSTEM_ERROR: Cannot connect to Anki. "
                "Please inform the user that they need to start their Anki application "
                "and ensure the AnkiConnect add-on is installed and enabled before proceeding. "
                f"Details: {e}" # Include the error detail from the exception
            )
        except ValueError as e:
             # Catch Anki API errors (raised as ValueError from invoke)
             logger.error(f"Caught Anki API error in tool '{func.__name__}': {e}")
             return (
                 f"SYSTEM_ERROR: An error occurred communicating with Anki: {e}. "
                 "Please inform the user about the error."
             )
        except Exception as e:
            # Catch any other unexpected errors within the tool
            logger.exception(f"An unexpected error occurred in tool '{func.__name__}': {e}")
            # Provide a generic error message for the LLM
            return (
                f"SYSTEM_ERROR: An unexpected error occurred while executing the Anki tool '{func.__name__}'. "
                f"Details: {e}"
            )
    return wrapper
# --- End Decorator ---


# --- Helper Function (Refactored) ---
# This helper now requires the client to be passed in, making it testable
# and ensuring it runs within the context managed by the tool.
async def _find_due_card_ids(
    client: AnkiConnectClient,
    deck: Optional[str] = None,
    day: Optional[int] = 0
) -> List[int]:
    """Finds card IDs due on a specific day relative to today (0=today)."""
    if day < 0:
        raise ValueError("Day must be non-negative.")

    # Construct the search query
    # prop:due=0 means due today
    # prop:due=1 means due tomorrow (relative to review time)
    # prop:due<=N finds cards due today up to N days in the future.
    if day == 0:
        prop = "prop:due=0" # Due exactly today
    else:
        prop = f"prop:due<={day}"

    query = f"is:due -is:suspended {prop}"
    if deck:
        # Add deck to query, ensuring proper quoting for spaces
        query += f' "deck:{deck}"'

    logger.debug(f"Executing Anki card search query: {query}")
    card_ids = await client.find_cards(query=query)
    logger.info(f"Found {len(card_ids)} cards for query: {query}")
    return card_ids


def _build_example_query(deck: Optional[str], sample: str) -> str:
    """Builds the Anki query string for finding example notes."""
    query_parts = ["-is:suspended"]
    query_parts.extend([f"-note:*{ex}*" for ex in EXCLUDE_STRINGS])

    if deck:
        query_parts.append(f'"deck:{deck}"')

    sort_order = ""
    match sample:
        case "recent":
            query_parts.append("added:7")
            sort_order = "sort:added rev"
        case "most_reviewed":
            query_parts.append("prop:reps>10")
            sort_order = "sort:reps rev"
        case "best_performance":
            query_parts.append("prop:lapses<3 is:review")
            sort_order = "sort:lapses"
        case "mature":
            query_parts.append("prop:ivl>=21 -is:learn")
            sort_order = "sort:ivl rev"
        case "young":
            query_parts.append("is:review prop:ivl<=7 -is:learn")
            sort_order = "sort:ivl"
        case "random":
            query_parts.append("is:review") # Default filter for random

    query = " ".join(query_parts)
    if sort_order:
        query += f" {sort_order}"
    return query


def _format_example_notes(notes_info: List[dict]) -> List[dict]:
    """Formats note information into simplified dictionaries for examples."""
    examples = []
    for note in notes_info:
        processed_fields = {}
        for name, field_data in note.get("fields", {}).items():
            value = field_data.get("value", "")
            processed_value = value.replace("<pre><code>", "<code>").replace("</code></pre>", "</code>")
            processed_fields[name] = processed_value

        example = {
            "modelName": note.get("modelName", "UnknownModel"),
            "fields": processed_fields,
            "tags": note.get("tags", [])
        }
        examples.append(example)
    return examples


def _format_cards_for_llm(cards_info: List[dict]) -> str:
    """Formats card information into an XML-like string for the LLM."""
    formatted_cards = []
    for card in cards_info:
        card_id = card.get('cardId', 'UNKNOWN_ID')
        fields = card.get('fields', {})
        question_field_order = card.get('fieldOrder', 0)

        question_parts = []
        answer_parts = []
        sorted_field_items = sorted(fields.items(), key=lambda item: item[1].get('order', 0))

        for name, field_data in sorted_field_items:
            field_value = field_data.get('value', '')
            field_order = field_data.get('order', -1)
            tag_name = name.lower().replace(" ", "_")

            if field_order == question_field_order:
                question_parts.append(f"<{tag_name}>{field_value}</{tag_name}>")
            else:
                answer_parts.append(f"<{tag_name}>{field_value}</{tag_name}>")

        question_str = "".join(question_parts) if question_parts else "<error>Question field not found</error>"
        answer_str = " ".join(answer_parts) if answer_parts else "<error>Answer fields not found</error>"

        formatted_cards.append(
            f"<card id=\"{card_id}\">\n"
            f"  <question>{question_str}</question>\n"
            f"  <answer>{answer_str}</answer>\n"
            f"</card>"
        )
    return "\n\n".join(formatted_cards)


def _process_field_content(content: str) -> str:
    """Processes field content for MathJax and code blocks before sending to Anki."""
    if not isinstance(content, str):
        logger.warning(f"Field content is not a string (type: {type(content)}). Returning as-is.")
        return content # Return non-strings unmodified

    # 1. MathJax: <math>...</math> -> \(...\)
    processed_value = content.replace("<math>", "\\(").replace("</math>", "\\)")

    # 2. Code Blocks: ```lang\n...\n``` -> <pre><code class="language-lang">...</code></pre>
    processed_value = re.sub(
        r'```(\w+)?\s*\n?(.*?)```',
        lambda m: f'<pre><code class="language-{m.group(1)}">{m.group(2)}</code></pre>' if m.group(1) else f'<pre><code>{m.group(2)}</code></pre>',
        processed_value,
        flags=re.DOTALL
    )

    # 3. Inline Code: `...` -> <code>...</code>
    processed_value = re.sub(r'`([^`]+)`', r'<code>\1</code>', processed_value)

    return processed_value


# --- Tool Definitions ---

@mcp.tool()
@handle_anki_connection_error # Apply decorator
async def num_cards_due_today(deck: Optional[str] = None) -> str:
    """Get the number of cards due exactly today, with an optional deck filter."""
    async with get_anki_client() as anki:
        # Use the helper, specifying day=0 for today
        card_ids = await _find_due_card_ids(anki, deck, day=0)
        count = len(card_ids)
        deck_msg = f" in deck '{deck}'" if deck else " across all decks"
        return f"There are {count} cards due today{deck_msg}."

@mcp.tool()
@handle_anki_connection_error # Apply decorator
async def list_decks_and_notes() -> str:
    """Get all decks (excluding specified patterns) and note types with their fields."""
    async with get_anki_client() as anki:
        all_decks = await anki.deck_names()
        # Filter decks based on EXCLUDE_STRINGS
        decks = [d for d in all_decks if not any(ex.lower() in d.lower() for ex in EXCLUDE_STRINGS)]
        logger.info(f"Filtered decks: {decks}")

        all_model_names = await anki.model_names()
        note_types = []
        for model in all_model_names:
            if any(ex.lower() in model.lower() for ex in EXCLUDE_STRINGS):
                continue
            try:
                fields = await anki.model_field_names(model)
                note_types.append({"name": model, "fields": fields})
            except Exception as e:
                 logger.warning(f"Could not get fields for model '{model}': {e}. Skipping this model.")


        # Format the output string
        deck_list_str = f"You have {len(decks)} filtered decks: {', '.join(decks)}" if decks else "No filtered decks found."

        note_type_list = []
        if note_types:
             for note in note_types:
                 # Format fields as "FieldName": "type" (assuming string for simplicity)
                 field_str = ', '.join([f'"{field}": "string"' for field in note['fields']])
                 note_type_list.append(f"- {note['name']}: {{ {field_str} }}")
             note_types_str = f"Your filtered note types and their fields are:\n" + "\n".join(note_type_list)
        else:
             note_types_str = "No filtered note types found."

        return f"{deck_list_str}\n\n{note_types_str}"


@mcp.tool()
@handle_anki_connection_error # Apply decorator
async def get_examples(
    deck: Optional[str] = None,
    limit: int = Field(default = 5, ge = 1),
    sample: str = Field(
        default = "random",
        description="Sampling technique: random, recent (added last 7d), most_reviewed (>10 reps), best_performance (<3 lapses), mature (ivl>=21d), young (ivl<=7d)",
        pattern="^(random|recent|most_reviewed|best_performance|mature|young)$" # Keep pattern for validation
    ), # Close Field()
) -> str: # Close parameters list
        """Get example notes from Anki to guide your flashcard making. Limit the number of examples returned and provide a sampling technique:

            - random: Randomly sample notes
            - recent: Notes added in the last week
            - most_reviewed: Notes with more than 10 reviews
            - best_performance: Notes with less than 3 lapses
            - mature: Notes with interval greater than 21 days
            - young: Notes with interval less than 7 days

        Args:
            deck: Optional[str] - Filter by specific deck (use exact name).
            limit: int - Maximum number of examples to return (default 5).
            sample: str - Sampling technique (random, recent, most_reviewed, best_performance, mature, young).
        """
        async with get_anki_client() as anki:
            # Build the query using the helper function
            query = _build_example_query(deck, sample)
            logger.debug(f"Finding example notes with query: {query}")

            note_ids = await anki.find_notes(query=query)
            if not note_ids:
                return f"No example notes found matching criteria (Sample: {sample}, Deck: {deck or 'Any'})."

            # Apply sampling and limit
            if sample == "random" and len(note_ids) > limit:
                sampled_note_ids = random.sample(note_ids, limit)
            else:
                # For sorted queries, take the top results up to the limit
                sampled_note_ids = note_ids[:limit]

            if not sampled_note_ids:
                 return f"No example notes found after sampling/limiting (Sample: {sample}, Deck: {deck or 'Any'})."


            logger.debug(f"Fetching info for note IDs: {sampled_note_ids}")
            notes_info = await anki.notes_info(sampled_note_ids)

            # Format notes using the helper function
            formatted_examples = _format_example_notes(notes_info)

            # Combine guidelines with the JSON examples
            # Use json.dumps for clean formatting
            examples_json = json.dumps(formatted_examples, indent=2, ensure_ascii=False)
            result = f"{flashcard_guidelines}\n\nHere are some examples based on your criteria:\n{examples_json}"

            return result


@mcp.tool()
@handle_anki_connection_error # Apply decorator
async def fetch_due_cards_for_review(
    deck: Optional[str] = None,
    limit: int = Field(default=5, ge=1, description="Max cards to fetch."),
    today_only: bool = Field(default=True, description="True=only today's cards, False=cards due up to MAX_FUTURE_DAYS ahead."),
) -> str:
    """Fetch cards due for review, formatted for an LLM to present.

    Args:
        deck: Optional[str] - Filter by specific deck name.
        limit: int - Maximum number of cards to fetch (default 5).
        today_only: bool - If true, only fetch cards due today. If false, fetch cards due up to MAX_FUTURE_DAYS ahead (currently {MAX_FUTURE_DAYS}).
    """
    async with get_anki_client() as anki:
        # Determine the maximum relative day to check based on today_only flag
        # day=0 means today, day=MAX_FUTURE_DAYS means today up to MAX_FUTURE_DAYS from now
        max_day_to_check = 0 if today_only else MAX_FUTURE_DAYS

        # Use the helper function to find relevant card IDs
        card_ids = await _find_due_card_ids(anki, deck, day=max_day_to_check)

        # Limit the number of cards to fetch info for
        card_ids_to_fetch = card_ids[:limit]

        if not card_ids_to_fetch:
            deck_msg = f" in deck '{deck}'" if deck else ""
            when_msg = "today" if today_only else f"within the next {max_day_to_check} days"
            return f"No cards found due {when_msg}{deck_msg}."

        logger.debug(f"Fetching info for card IDs: {card_ids_to_fetch}")
        cards_info_list = await anki.cards_info(card_ids=card_ids_to_fetch)

        # Format cards using the helper function
        cards_text = _format_cards_for_llm(cards_info_list)

        # Inject the formatted cards into the review instructions prompt
        review_prompt = claude_review_instructions.replace("{{flashcards}}", cards_text)

        return review_prompt


@mcp.tool()
@handle_anki_connection_error # Apply decorator
async def submit_reviews(
    reviews: List[Dict[Literal["card_id", "rating"], Union[int, Literal["wrong", "hard", "good", "easy"]]]]
    ) -> str:
    """Submit multiple card reviews to Anki using ratings ('wrong', 'hard', 'good', 'easy').

    Args:
        reviews: List of review dictionaries, each with:
            - card_id (int): The ID of the card reviewed.
            - rating (str): 'wrong', 'hard', 'good', or 'easy'.
    """
    if not reviews:
        # Return a message instead of raising ValueError, handled by decorator now
        return "No reviews provided to submit."

    answers_to_submit = []
    validation_errors = []
    for review in reviews:
        card_id = review.get("card_id")
        rating = str(review.get("rating", "")).lower() # Ensure lowercase string

        if not isinstance(card_id, int):
            validation_errors.append(f"Invalid card_id '{card_id}' in review: {review}. Must be an integer.")
            continue # Skip this invalid review

        ease = RATING_TO_EASE.get(rating)
        if ease is None:
            valid_ratings = list(RATING_TO_EASE.keys())
            validation_errors.append(f"Invalid rating '{rating}' for card_id {card_id}. Must be one of: {valid_ratings}.")
            continue # Skip this invalid review

        answers_to_submit.append({"cardId": card_id, "ease": ease})

    if validation_errors:
        # Report validation errors back to the LLM/user
        errors_str = "\n".join(validation_errors)
        return f"SYSTEM_ERROR: Could not submit reviews due to validation errors:\n{errors_str}"

    if not answers_to_submit:
         return "No valid reviews found to submit after validation."


    async with get_anki_client() as anki:
        logger.info(f"Submitting {len(answers_to_submit)} reviews to Anki.")
        # The 'answerCards' action returns a list of booleans (or similar success indicators)
        # It might raise an error if the entire batch fails, handled by invoke/decorator
        results = await anki.answer_cards(answers=answers_to_submit)

        # Check if the result length matches the input length
        if len(results) != len(answers_to_submit):
             logger.warning(f"Anki response length mismatch: Expected {len(answers_to_submit)}, Got {len(results)}")
             # Handle potential mismatch - maybe return a generic success/fail message
             # For now, assume results correspond to input order if length matches

        # Generate response messages based on results (assuming True means success)
        messages = []
        success_count = 0
        fail_count = 0
        for i, review in enumerate(reviews): # Iterate original reviews to get card_id/rating
             card_id = review['card_id']
             rating = review['rating']
             # Check corresponding result if lengths match, otherwise assume failure?
             success = results[i] if i < len(results) else False # Default to False if mismatch
             if success:
                 messages.append(f"Card {card_id}: Marked as '{rating}' successfully.")
                 success_count += 1
             else:
                 messages.append(f"Card {card_id}: Failed to mark as '{rating}'.")
                 fail_count += 1

        summary = f"Review submission summary: {success_count} successful, {fail_count} failed."
        full_response = summary + "\n" + "\n".join(messages)
        logger.info(full_response)
        return full_response


@mcp.tool()
@handle_anki_connection_error # Apply decorator
async def add_note(
    deckName: str,
    modelName: str,
    fields: dict[str, str],
    tags: Optional[List[str]] = None) -> str: # Use standard optional list with None default
    """Add a flashcard to Anki. Ensure you have looked at examples before you do this, and that you have got approval from the user to add the flashcard.

    For code examples, use <code> tags to format your code.
    e.g. <code>def fibonacci(n):
    if n <= 1:
        return n
    return fibonacci(n-1) + fibonacci(n-2)</code>

    For MathJax, use the <math> tag to format your math equations. This will automatically render the math equations in Anki.
    # e.g. <math>\\frac{d}{dx}[3\\sin(5x)] = 15\\cos(5x)</math>

    Args:
        deckName: str - The target deck name.
        modelName: str - The note type (model) name.
        fields: dict - Dictionary of field names and their string content.
        tags: List[str] - Optional list of tags.
    """
    # Process fields using the helper function
    processed_fields = {
        name: _process_field_content(value) for name, value in fields.items()
    }

    note_payload = {
        "deckName": deckName,
        "modelName": modelName,
        "fields": processed_fields, # Use processed fields
        "tags": tags if tags is not None else [],
        "options": {
            "allowDuplicate": False,
            "duplicateScope": "deck",
            # "checkClobber": True # Optional: check if adding would overwrite based on first field
        }
    }

    async with get_anki_client() as anki:
        logger.info(f"Attempting to add note to deck '{deckName}' with model '{modelName}'.")
        logger.debug(f"Note Payload: {json.dumps(note_payload, indent=2)}") # Log the payload for debugging

        # Invoke addNote - errors (like duplicate, missing fields) will be caught
        # by the ValueError check in invoke or the decorator
        note_id = await anki.add_note(note=note_payload)

        # add_note returns the new note ID on success, or raises error/returns None/0 on failure
        if note_id:
            success_message = f"Successfully created note with ID: {note_id} in deck '{deckName}'."
            logger.info(success_message)
            return success_message
        else:
            # This case might occur if allowDuplicate=True and a duplicate was added,
            # or if the API behaves unexpectedly without raising an error.
            fail_message = f"Failed to add note to deck '{deckName}'. AnkiConnect did not return a note ID or indicated failure."
            logger.error(fail_message)
            # Return an error message for the LLM
            return f"SYSTEM_ERROR: {fail_message}"
