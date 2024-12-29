from typing import List, Optional, Literal, Dict, Union
import json
import random
import logging
from contextlib import asynccontextmanager
from mcp.server.fastmcp import FastMCP
from mcp_ankiconnect.ankiconnect_client import AnkiConnectClient
from mcp_ankiconnect.config import EXCLUDE_STRINGS, RATING_TO_EASE
from mcp_ankiconnect.server_prompts import flashcard_guidelines, claude_review_instructions
from pydantic import Field

logger = logging.getLogger(__name__)

logger.info("Initializing MCP-AnkiConnect server")
mcp = FastMCP("mcp-ankiconnect")
logger.debug("Created FastMCP instance")

@asynccontextmanager
async def get_anki_client():
    client = AnkiConnectClient()
    try:
        yield client
    finally:
        await client.close()

mcp = FastMCP("mcp-ankiconnect")

async def get_cards_by_due_and_deck(deck: Optional[str] = None, day: Optional[int] = 0) -> List[int]:
    async with get_anki_client() as anki:
        decks = await anki.deck_names()
        if deck and deck not in decks:
            raise ValueError(f"Deck '{deck}' does not exist")

        if day > 0:
            prop = f"prop:due<{day+1}"
        else:
            prop = "prop:due<=0"
        # Construct the search query
        query = f"is:due -is:suspended {prop}"
        if deck:
            query += f' deck:{deck}'
        # Get and return the due cards
        return await anki.find_cards(query=query)

@mcp.tool()
async def num_cards_due_today(deck: Optional[str] = None) -> str:
    """Get the number of cards due today with an optional deck filter"""
    anki = AnkiConnectClient()

    card_ids = await get_cards_by_due_and_deck(deck, 0)
    if deck:
        return f"There are {len(card_ids)} cards due in deck '{deck}'"
    else:
        return f"There are {len(card_ids)} cards due across all decks"

@mcp.tool()
async def list_decks_and_notes() -> str:
    """Get all decks and note types with their fields"""
    anki = AnkiConnectClient()

    decks = await anki.deck_names()
    decks = [deck for deck in decks if not any(exclude.lower() in deck.lower() for exclude in EXCLUDE_STRINGS)]

    model_names = await anki.model_names()
    note_types = []
    for model in model_names:
        if any(exclude.lower() in model.lower() for exclude in EXCLUDE_STRINGS):
            continue
        fields = await anki.model_field_names(model)
        note_types.append({"name": model, "fields": fields})

    result = f"""You have {len(decks)} decks: {', '.join(decks)}
Your note types are: {[note['name'] for note in note_types]}:
{chr(10).join([f"{note['name']}" + ': { ' + ', '.join([f'"{field}": "string"' for field in note['fields']]) + ' }' for note in note_types])}
"""
    return result

@mcp.tool()
async def get_examples(
    deck: Optional[str] = None,
    limit: int = Field(default = 5, ge = 1),
    sample: str = Field(
        default = "random",
        pattern="^(random|recent|most_reviewed|best_performance|mature|young)$"
    ))-> str:
        """Get example notes from Anki to guide your flashcard making. Limit the number of examples returned and provide a sampling technique:

            - random: Randomly sample notes
            - recent: Notes added in the last week
            - most_reviewed: Notes with more than 10 reviews
            - best_performance: Notes with less than 3 lapses
            - mature: Notes with interval greater than 21 days
            - young: Notes with interval less than 7 days
            """
        anki = AnkiConnectClient()

        query = "-is:suspended " + " ".join([f"-note:*{exclude_string}*" for exclude_string in EXCLUDE_STRINGS]) + " "

        if deck:
            query += f"deck:{deck} "

        match sample:
            case "recent":
                query += "added:7"  # Added in last week
            case "most_reviewed":
                query += "prop:reps>10 -is:learn"  # Reviewed cards excluding learning
            case "best_performance":
                query += "prop:lapses<3 is:review"  # Review cards with few lapses
            case "mature":
                query += "prop:ivl>=21 -is:learn"  # Mature cards not in learning
            case "young":
                query += "is:review prop:ivl<=7 -is:learn"  # Young review cards
            case "random":
                query += "prop:due<180"

        note_ids = await anki.find_notes(query=query)
        if len(note_ids) > limit and sample == "random":
            note_ids = random.sample(note_ids, limit)
        note_ids = note_ids[:limit]

        if not note_ids:
            return "No example notes found matching criteria"

        notes = await anki.notes_info(note_ids)
        examples = []
        for note in notes:
            example = {
                "tags": note["tags"],
                "modelName": note["modelName"],
                "fields": {name: {k: v for k, v in value.items() if k != "order"} for name, value in note["fields"].items()}
            }
            examples.append(example)

        result = flashcard_guidelines + "\n" + json.dumps(examples, indent=2)

        return result

@mcp.tool()
async def fetch_due_cards_for_review(
    deck: Optional[str] = None,
    limit: int = 5,
    today_only: bool = True,
) -> str:
    """Fetch cards that are due for learning and format them for review. Takes optional arguments:
      - deck: str - Filter by specific deck.
      - limit: int - Maximum number of cards to fetch (default 5). More than 5 is overwhelming for users.
      - today_only: bool - If true, only fetch cards due today, else fetch cards up to 5 days ahead."""
    anki = AnkiConnectClient()
    days_to_review = 0 if today_only else 5

    card_ids = await get_cards_by_due_and_deck(deck, days_to_review)
    card_ids = card_ids[:limit]

    cards = await anki.cards_info(card_ids=card_ids)

    # Format the card information into a readable message
    cards_info = []
    for card in cards:
        # Get question fields (where order != fieldOrder)
        question_fields = [
            f"<{name.lower()}>{field['value']}</{name.lower()}>"
            for name, field in card['fields'].items()
            if field['order'] == card['fieldOrder']
        ]

        # Get answer fields (where order == fieldOrder)
        answer_fields = [
            f"<{name.lower()}>{field['value']}</{name.lower()}>"
            for name, field in list(card['fields'].items())[:5]
            if field['order'] != card['fieldOrder']
        ]

        cards_info.append(
            f"<card id=\"{card['cardId']}\">\n"
            f"  <question>{'; '.join(question_fields)}</question>\n"
            f"  <answer>{'; '.join(answer_fields)}</answer>\n"
            f"</card>")

    cards_text = "\n\n".join(cards_info)
    if not cards_text:
        cards_text = "No cards found to review"

    examples_prompt = claude_review_instructions.replace("{{flashcards}}", cards_text)

    return examples_prompt

@mcp.tool()
async def submit_reviews(reviews: List[Dict[Literal["card_id", "rating"], Union[int, Literal["wrong", "hard", "good", "easy"]]]]) -> str:
    """Submit multiple card reviews to Anki.

    Args:
        reviews: List of dictionaries containing:
            - card_id (int): The ID of the card being reviewed
            - rating (str): The rating to give the card, one of:
                "wrong" - Card was incorrect (Again)
                "hard" - Card was difficult (Hard)
                "good" - Card was good (Good)
                "easy" - Card was very easy (Easy)
    """
    anki = AnkiConnectClient()
    if not reviews:
        raise ValueError("Arguments required for submitting reviews")

    # Convert reviews to AnkiConnect format
    answers = [
        {"cardId": review["card_id"], "ease": RATING_TO_EASE[review["rating"]]}
        for review in reviews
    ]

    # Submit all reviews at once
    results = await anki.answer_cards(answers)

    # Generate response messages
    messages = [
        f"Card {review['card_id']} {'successfully' if success else 'failed to be'} marked as {review['rating']}"
        for review, success in zip(reviews, results)
    ]

    return "\n".join(messages)

@mcp.tool()
async def add_note(
    deckName: str,
    modelName: str,
    fields: dict[str, str],
    tags: List[str] = Field(default_factory = list)) -> str:
    """Add a flashcard to Anki. Ensure you have looked at examples before you do this, and that you have got approval from the user to add the flashcard.
    Args:
        deckName: str - The name of the deck to add the flashcard to.
        modelName: str - The name of the note type to use.
        fields: dict - The fields of the flashcard to add.
        tags: List[str] - The tags to add to the flashcard."""
    anki = AnkiConnectClient()
    note = {
        "deckName": deckName,
        "modelName": modelName,
        "fields": fields,
        "tags": tags,
        "options": {
            "allowDuplicate": False,
            "duplicateScope": "deck",
        }
    }

    note_id = await anki.add_note(note)

    return f"Successfully created note with ID: {note_id}"
