import json
import logging
import httpx
import asyncio
import mcp.server.stdio
from enum import Enum
from typing import Any, List, Optional
from contextlib import asynccontextmanager

from .server_prompts import claude_flashcards
from .config import (
    ANKI_CONNECT_URL, 
    ANKI_CONNECT_VERSION,
    RATING_TO_EASE,
    DEFAULT_REVIEW_LIMIT,
    MAX_FUTURE_DAYS,
    TIMEOUTS
)
from mcp.types import Tool, TextContent
from mcp.server import NotificationOptions, Server
from mcp.server.models import InitializationOptions
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

class Rating(str, Enum):
    WRONG = "wrong"  # Again - 1
    HARD = "hard"   # Hard - 2
    GOOD = "good"   # Good - 3
    EASY = "easy"   # Easy - 4

class AnkiAction(str, Enum):
    DECK_NAMES = "deckNames"
    FIND_CARDS = "findCards" 
    CARDS_INFO = "cardsInfo"
    ANSWER_CARDS = "answerCards"
    MODEL_NAMES = "modelNames"
    MODEL_FIELD_NAMES = "modelFieldNames"
    ADD_NOTE = "addNote"
    FIND_NOTES = "findNotes"
    NOTES_INFO = "notesInfo"

class AnkiConnectRequest(BaseModel):
    action: AnkiAction
    version: int = 6
    params: dict = Field(default_factory=dict)

class AnkiConnectResponse(BaseModel):
    result: Any
    error: Optional[str] = None

class AnkiConnectTools(str, Enum):
    NUM_CARDS_DUE_TODAY = "num_cards_due_today"
    GET_DUE_CARDS = "get_due_cards"
    SUBMIT_REVIEWS = "submit_reviews"
    LIST_NOTE_TYPES = "list_note_types"
    LIST_DECKS = "list_decks"
    ADD_NOTE = "add_note"
    GET_EXAMPLES = "get_examples"

class NumCardsDueToday(BaseModel):
    deck: Optional[str] = None

class GetDueCards(BaseModel):
    # Number of cards to review
    limit: int = 5
    # Optional deck filter
    deck: Optional[str] = None
    # Whether to only show cards due today
    today_only: bool = True

class CardReview(BaseModel):
    card_id: int
    rating: Rating

class SubmitReviews(BaseModel):
    reviews: List[CardReview]

class GetExamples(BaseModel):
    deck: Optional[str] = None
    limit: int = Field(default=3, ge=1, le=10)
    sample: str = Field(
        default="random",
        pattern="^(random|recent|most_reviewed|best_performance|mature|young)$"
    )

class AddNote(BaseModel):
    deck_name: str
    note_type: str  
    fields: dict[str, str]
    tags: List[str] = Field(default_factory=list)

class AnkiConnectClient:
    def __init__(self, base_url: str = ANKI_CONNECT_URL):
        self.base_url = base_url
        self.client = httpx.AsyncClient(timeout=TIMEOUTS)
        logger.info(f"Initialized AnkiConnect client with base URL: {base_url}")

    async def invoke(self, action: str, **params) -> Any:
        request = AnkiConnectRequest(
            action=action,
            version=ANKI_CONNECT_VERSION,
            params=params
        )
        
        logger.debug(f"Invoking AnkiConnect action: {action} with params: {params}")
        
        retries = 3
        for attempt in range(retries):
            try:
                response = await self.client.post(
                    self.base_url,
                    json=request.model_dump()
                )
                break
            except httpx.TimeoutException as e:
                if attempt == retries - 1:
                    raise RuntimeError(f"Unable to connect to Anki after {retries} attempts. Please ensure Anki is running and the AnkiConnect plugin is installed.")
                await asyncio.sleep(2 ** attempt)  # Exponential backoff: 1, 2, 4 seconds
                continue
        try:
            response.raise_for_status()

            anki_response = AnkiConnectResponse.model_validate(response.json())
            if anki_response.error:
                logger.error(f"AnkiConnect error for action {action}: {anki_response.error}")
                raise ValueError(f"AnkiConnect error: {anki_response.error}")

            return anki_response.result

        except httpx.HTTPError as e:
            logger.error(f"HTTP error while invoking {action}: {str(e)}")
            raise RuntimeError(f"Failed to communicate with AnkiConnect: {str(e)}") from e
        except ValueError as e:
            # Re-raise ValueError (from AnkiConnect errors) directly
            raise
        except Exception as e:
            logger.error(f"Unexpected error while invoking {action}: {str(e)}")
            raise RuntimeError(f"Unexpected error during AnkiConnect operation: {str(e)}") from e

    async def cards_info(self, card_ids: List[int]) -> List[dict]:
        try:
            return await self.invoke(AnkiAction.CARDS_INFO, cards=card_ids)
        except Exception as e:
            raise RuntimeError(f"Error getting cards info: {str(e)}") from e

    async def deck_names(self) -> List[str]:
        try:
            return await self.invoke(AnkiAction.DECK_NAMES)
        except Exception as e:
            if isinstance(e, RuntimeError) and "Unable to connect to Anki" in str(e):
                raise
            raise RuntimeError(f"Error getting deck names: {str(e)}") from e

    async def find_cards(self, query: str) -> List[int]:
        try:
            return await self.invoke(AnkiAction.FIND_CARDS, query=query)
        except Exception as e:
            raise RuntimeError(f"Error finding cards: {str(e)}") from e

    async def answer_cards(self, answers: List[dict]) -> List[bool]:
        try:
            return await self.invoke(AnkiAction.ANSWER_CARDS, answers=answers)
        except Exception as e:
            raise RuntimeError(f"Error answering cards: {str(e)}") from e

    async def close(self):
        await self.client.aclose()


class AnkiServer:
    def __init__(self):
        self.server = Server("mcp-ankiconnect")
        self.anki = AnkiConnectClient()
        self.setup_handlers()

    def setup_handlers(self):
        @self.server.list_tools()
        async def handle_list_tools() -> list[Tool]:
            return [
                Tool(
                    name="num_cards_due_today",
                    description="Get the number of cards due today with an optional deck filter",
                    inputSchema=NumCardsDueToday.schema(),
                ),
                Tool(
                    name="get_due_cards",
                    description="Get cards due for review with an optional limit and deck filter",
                    inputSchema=GetDueCards.schema(),
                ),
                Tool(
                    name="submit_reviews",
                    description="Submit answers for multiple flashcard reviews",
                    inputSchema=SubmitReviews.schema(),
                ),
                Tool(
                    name="list_note_types",
                    description="Get available note types and their field names",
                    inputSchema={"type": "object", "properties": {}},
                ),
                Tool(
                    name="list_decks",
                    description="Get available deck names",
                    inputSchema={"type": "object", "properties": {}},
                ),
                Tool(
                    name="add_note",
                    description="Create a new flashcard note",
                    inputSchema=AddNote.schema(),
                ),
                Tool(
                    name="get_examples",
                    description="Get example notes to understand card structure and content style",
                    inputSchema=GetExamples.schema(),
                ),
            ]

        @self.server.call_tool()
        async def handle_call_tool(
            name: str, arguments: Optional[dict] = None
        ) -> List[TextContent]:
            match name:
                case AnkiConnectTools.NUM_CARDS_DUE_TODAY:
                    return await self.num_cards_due_today(arguments)
                case AnkiConnectTools.GET_DUE_CARDS:
                    return await self.get_due_cards(arguments)
                case AnkiConnectTools.SUBMIT_REVIEWS:
                    return await self.submit_reviews(arguments)
                case AnkiConnectTools.LIST_NOTE_TYPES:
                    return await self.list_note_types()
                case AnkiConnectTools.LIST_DECKS:
                    return await self.list_decks()
                case AnkiConnectTools.ADD_NOTE:
                    return await self.add_note(arguments)
                case AnkiConnectTools.GET_EXAMPLES:
                    return await self.get_examples(arguments)
                case _:
                    raise ValueError(f"Unknown tool: {name}")

    async def list_note_types(self) -> List[TextContent]:
        """Get all note types and their fields"""
        try:
            # Get all model names
            model_names = await self.anki.invoke(AnkiAction.MODEL_NAMES)
            
            # Get fields for each model
            note_types = []
            for model in model_names:
                fields = await self.anki.invoke(AnkiAction.MODEL_FIELD_NAMES, modelName=model)
                note_types.append({"name": model, "fields": fields})
            
            return [TextContent(
                type="text",
                text=json.dumps(note_types, indent=2)
            )]
        except Exception as e:
            raise RuntimeError(f"Failed to get note types: {str(e)}")

    async def list_decks(self) -> List[TextContent]:
        """Get all deck names"""
        try:
            decks = await self.anki.deck_names()
            return [TextContent(
                type="text",
                text=json.dumps(decks, indent=2)
            )]
        except Exception as e:
            raise RuntimeError(f"Failed to get decks: {str(e)}")

    async def add_note(self, arguments: Optional[dict]) -> List[TextContent]:
        """Create a new note"""
        if not arguments:
            raise ValueError("Arguments required for adding note")
        
        input_model = AddNote(**arguments)
        
        try:
            note = {
                "deckName": input_model.deck_name,
                "modelName": input_model.note_type,
                "fields": input_model.fields,
                "tags": input_model.tags,
                "options": {
                    "allowDuplicate": False,
                    "duplicateScope": "deck",
                }
            }
            
            note_id = await self.anki.invoke(AnkiAction.ADD_NOTE, note=note)
            return [TextContent(
                type="text",
                text=f"Successfully created note with ID: {note_id}"
            )]
        except Exception as e:
            raise RuntimeError(f"Failed to add note: {str(e)}")

    async def get_examples(self, arguments: Optional[dict]) -> List[TextContent]:
        """Get example notes based on criteria"""
        if not arguments:
            arguments = {}
        
        input_model = GetExamples(**arguments)
        
        try:
            # Construct search query based on sampling method
            query = ""
            if input_model.deck:
                query += f"deck:{input_model.deck} "
            
            match input_model.sample:
                case "recent":
                    query += "added:7"  # Added in last week
                case "most_reviewed":
                    query += "prop:reps>10"  # Cards reviewed more than 10 times
                case "best_performance":
                    query += "prop:lapses<3"  # Cards with few lapses
                case "mature":
                    query += "prop:ivl>=21"  # Cards with intervals >= 21 days
                case "young":
                    query += "prop:ivl<=7"   # Cards with intervals <= 7 days
            
            # Find notes matching criteria
            note_ids = await self.anki.invoke(AnkiAction.FIND_NOTES, query=query)
            
            # Limit results
            note_ids = note_ids[:input_model.limit]
            
            if not note_ids:
                return [TextContent(
                    type="text",
                    text="No example notes found matching criteria"
                )]
            
            # Get detailed note info
            notes = await self.anki.invoke(AnkiAction.NOTES_INFO, notes=note_ids)
            
            # Format response
            examples = []
            for note in notes:
                example = {
                    "note_type": note["modelName"],
                    "deck": note["deckName"],
                    "fields": note["fields"],
                    "tags": note["tags"],
                    "stats": {
                        "reviews": note.get("reps", 0),
                        "lapses": note.get("lapses", 0),
                        "interval": note.get("interval", 0)
                    }
                }
                examples.append(example)
            
            return [TextContent(
                type="text",
                text=json.dumps(examples, indent=2)
            )]
        except Exception as e:
            raise RuntimeError(f"Failed to get example notes: {str(e)}")

    async def submit_reviews(self, arguments: Optional[dict]) -> List[TextContent]:
        if not arguments:
            raise ValueError("Arguments required for submitting reviews")
        if 'reviews' not in arguments:
            raise ValueError("'reviews' field must be present for submitting reviews")
            
        reviews = arguments.get("reviews")
        try:
            if isinstance(reviews, list) and all(isinstance(r, CardReview) for r in reviews):
                arguments["reviews"] = reviews
            else:
                reviews = json.loads(reviews) if isinstance(reviews, str) else reviews
                arguments["reviews"] = [CardReview.model_validate(r) for r in reviews]

            input_model = SubmitReviews(**arguments)

            # Convert reviews to AnkiConnect format
            answers = [
                {"cardId": review.card_id, "ease": RATING_TO_EASE[review.rating]}
                for review in input_model.reviews
            ]

            # Submit all reviews at once
            results = await self.anki.answer_cards(answers)

            # Generate response messages
            messages = [
                f"Card {review.card_id} {'successfully' if success else 'failed to be'} marked as {review.rating.value}"
                for review, success in zip(input_model.reviews, results)
            ]

            return [TextContent(
                type="text",
                text="\n".join(messages)
            )]
        except Exception as e:
            logger.error(f"Error submitting reviews: {str(e)}")
            raise RuntimeError(f"Failed to submit reviews: {str(e)}") from e

        # Submit all reviews at once
        results = await self.anki.answer_cards(answers)

        # Generate response messages
        messages = [
            f"Card {review.card_id} {'successfully' if success else 'failed to be'} marked as {review.rating.value}"
            for review, success in zip(input_model.reviews, results)
        ]

        return [TextContent(
            type="text",
            text="\n".join(messages)
        )]

    async def get_cards_due(
        self, deck: Optional[str] = None, day: Optional[int] = 0
    ) -> List[int]:
        # First get the deck names to validate deck if provided
        decks = await self.anki.deck_names()
        if deck and deck not in decks:
            raise ValueError(f"Deck '{deck}' does not exist")

        if day > 0:
            prop = f"prop:due<{day+1}"
        else:
            prop = "prop:due=0"
        # Construct the search query
        query = f"is:due {prop}"
        if deck:
            query += f' deck:{deck}'

        # Get and return the due cards
        return await self.anki.find_cards(query=query)

    async def get_due_cards(
        self,
        arguments: Optional[dict],
    ) -> List[TextContent]:
        if arguments is None:
            arguments = {}

        input_model = GetDueCards(**arguments)
        deck = input_model.deck
        limit = input_model.limit
        days_to_review = 0 if input_model.today_only else 5

        card_ids = await self.get_cards_due(deck, days_to_review)
        card_ids = card_ids[:limit]

        cards = await self.anki.cards_info(card_ids=card_ids)

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

        flashcard_prompt = claude_flashcards.replace("{{flashcards}}", cards_text)

        return [TextContent(type="text", text=flashcard_prompt)]

    async def num_cards_due_today(
        self, arguments: Optional[dict] = None
    ) -> List[TextContent]:
        deck = arguments.get("deck") if arguments else None

        card_ids = await self.get_cards_due(deck, 0)
        if deck:
            msg = f"There are {len(card_ids)} cards due in deck '{deck}'"
        else:
            msg = f"There are {len(card_ids)} cards due across all decks"
        return [TextContent(type="text", text=msg)]

    async def run(self):
        async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
            await self.server.run(
                read_stream,
                write_stream,
                InitializationOptions(
                    server_name="mcp-ankiconnect",
                    server_version="0.1.0",
                    capabilities=self.server.get_capabilities(
                        notification_options=NotificationOptions(),
                        experimental_capabilities={},
                    ),
                ),
            )

    async def cleanup(self):
        await self.anki.close()


async def main():
    server = AnkiServer()
    try:
        await server.run()
    finally:
        await server.cleanup()
