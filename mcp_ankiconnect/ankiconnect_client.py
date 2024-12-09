from typing import Any, List, Optional
import logging
import httpx
import asyncio
from enum import Enum

try:
    from mcp_ankiconnect.config import (
        ANKI_CONNECT_URL,
        ANKI_CONNECT_VERSION,
        TIMEOUTS,
    )
except ImportError:
    from config import (
        ANKI_CONNECT_URL,
        ANKI_CONNECT_VERSION,
        TIMEOUTS,
    )

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

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

class AnkiConnectResponse(BaseModel):
    result: Any
    error: Optional[str] = None

class AnkiConnectRequest(BaseModel):
    action: AnkiAction
    version: int = 6
    params: dict = Field(default_factory=dict)

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

    async def model_field_names(self, model_name: str) -> List[str]:
        try:
            return await self.invoke(AnkiAction.MODEL_FIELD_NAMES, modelName=model_name)
        except Exception as e:
            raise RuntimeError(f"Error getting model field names: {str(e)}") from e

    async def model_names(self) -> List[str]:
        try:
            return await self.invoke(AnkiAction.MODEL_NAMES)
        except Exception as e:
            raise RuntimeError(f"Error getting model names: {str(e)}") from e

    async def find_notes(self, query: str) -> List[int]:
        try:
            return await self.invoke(AnkiAction.FIND_NOTES, query=query)
        except Exception as e:
            raise RuntimeError(f"Error finding notes: {str(e)}") from e

    async def add_note(self, note: dict) -> int:
        try:
            return await self.invoke(AnkiAction.ADD_NOTE, note=note)
        except Exception as e:
            raise RuntimeError(f"Error adding note: {str(e)}") from e


    async def notes_info(self, note_ids: List[int]) -> List[dict]:
        try:
            return await self.invoke(AnkiAction.NOTES_INFO, notes=note_ids)
        except Exception as e:
            raise RuntimeError(f"Error getting notes info: {str(e)}") from e


    async def close(self):
        await self.client.aclose()
