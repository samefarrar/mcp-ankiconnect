from .server_prompts import claude_flashcards
from enum import Enum
from typing import Any, List, Optional

import httpx
import mcp.server.stdio
from mcp.types import Tool, TextContent
from mcp.server import NotificationOptions, Server
from mcp.server.models import InitializationOptions
from pydantic import BaseModel, Field

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

class AnkiConnectClient:
    def __init__(self, base_url: str = "http://localhost:8765"):
        self.base_url = base_url
        self.client = httpx.AsyncClient(timeout=120.0)

    async def invoke(self, action: str, **params) -> Any:
        request = AnkiConnectRequest(action=action, params=params)

        try:
            response = await self.client.post(self.base_url, json=request.model_dump())
            response.raise_for_status()

            anki_response = AnkiConnectResponse.model_validate(response.json())
            if anki_response.error:
                raise ValueError(f"AnkiConnect error: {anki_response.error}")

            return anki_response.result

        except Exception as e:
            # Re-raise the exception to ensure it propagates
            raise

    async def cards_info(self, card_ids: List[int]) -> List[dict]:
        try:
            return await self.invoke(AnkiAction.CARDS_INFO, cards=card_ids)
        except Exception as e:
            raise RuntimeError(f"Error getting cards info: {str(e)}") from e

    async def deck_names(self) -> List[str]:
        try:
            return await self.invoke(AnkiAction.DECK_NAMES)
        except Exception as e:
            raise RuntimeError(f"Error getting deck names: {str(e)}") from e

    async def find_cards(self, query: str) -> List[int]:
        try:
            return await self.invoke(AnkiAction.FIND_CARDS, query=query)
        except Exception as e:
            raise RuntimeError(f"Error finding cards: {str(e)}") from e

    async def answer_cards(self, answers: List[dict]) -> List[bool]:
        """Answer multiple cards with their ease ratings.

        Args:
            answers: List of dicts with cardId and ease (1-4) for each card
        Returns:
            List of booleans indicating success for each card
        """
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
                case _:
                    raise ValueError(f"Unknown tool: {name}")

    async def submit_reviews(self, reviews: List[CardReview]) -> List[TextContent]:
        if not reviews:
            raise ValueError("Reviews required for submitting reviews")
        input_model = SubmitReviews(reviews=reviews)

        # Map ratings to Anki ease values
        rating_map = {
            Rating.WRONG: 1,  # Again
            Rating.HARD: 2,   # Hard
            Rating.GOOD: 3,   # Good
            Rating.EASY: 4    # Easy
        }

        # Convert reviews to AnkiConnect format
        answers = [
            {"cardId": review.card_id, "ease": rating_map[review.rating]}
            for review in input_model.reviews
        ]

        # Submit all reviews at once
        results = await self.anki.answer_cards(answers)

        # Generate response messages
        messages = []
        for review, success in zip(input_model.reviews, results):
            status = "successfully" if success else "failed to be"
            messages.append(f"Card {review.card_id} {status} marked as {review.rating.value}")

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
