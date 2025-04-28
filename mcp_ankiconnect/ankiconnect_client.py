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
        TimeoutConfig, # Import TimeoutConfig
    )
except ImportError:
    # Attempt to import TimeoutConfig from config if the primary import fails
    try:
        from config import (
            ANKI_CONNECT_URL,
            ANKI_CONNECT_VERSION,
            TIMEOUTS,
            TimeoutConfig, # Import TimeoutConfig
        )
    except ImportError:
        # Handle cases where config.py might not define TimeoutConfig directly
        # or provide a fallback if necessary. This might indicate a setup issue.
        # For now, we assume TimeoutConfig is available via one of the paths.
        # If TimeoutConfig is defined *within* config.py, this structure is fine.
        # If it's imported *into* config.py, ensure the original source is in sys.path.
        # Re-raising might be appropriate if TimeoutConfig is essential and missing.
        raise ImportError("Could not import AnkiConnect configuration including TimeoutConfig.")


from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# --- Custom Exception ---
class AnkiConnectionError(Exception):
    """Raised when the client cannot connect to the AnkiConnect server after retries."""
    pass
# --- End Custom Exception ---

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

    # Use model_dump for Pydantic v2+
    def to_dict(self):
        return self.model_dump(exclude_unset=True)


class AnkiConnectClient:
    def __init__(self, base_url: str = ANKI_CONNECT_URL):
        self.base_url = base_url
        # Ensure TIMEOUTS is correctly passed or use httpx.Timeout object
        # Assuming TIMEOUTS is a NamedTuple like TimeoutConfig(connect=5.0, read=120.0, write=30.0)
        # Check if TIMEOUTS is an instance of the specific TimeoutConfig NamedTuple
        if isinstance(TIMEOUTS, TimeoutConfig): # Check against the specific class
             # Convert NamedTuple to httpx.Timeout object
             timeout_config = httpx.Timeout(TIMEOUTS.connect, read=TIMEOUTS.read, write=TIMEOUTS.write)
        else:
            # If TIMEOUTS is not the expected NamedTuple, log a warning and use it directly.
            # This assumes it might be a float, dict, or httpx.Timeout object already.
            # Consider adding more specific type checks if needed.
            logger.warning(f"TIMEOUTS config is not a TimeoutConfig NamedTuple (type: {type(TIMEOUTS)}). Using value directly.")
            # Assume it's already in a format httpx understands (like float or httpx.Timeout)
            timeout_config = TIMEOUTS # Or provide a default httpx.Timeout if TIMEOUTS might be invalid

        self.client = httpx.AsyncClient(base_url=base_url, timeout=timeout_config) # Set base_url here
        logger.info(f"Initialized AnkiConnect client with base URL: {self.base_url}")

    async def invoke(self, action: AnkiAction, **params) -> Any: # Use AnkiAction enum
        request = AnkiConnectRequest(
            action=action,
            # version=ANKI_CONNECT_VERSION, # version is now in AnkiConnectRequest default
            params=params
        )

        logger.debug(f"Invoking AnkiConnect action: {action.value} with params: {params}")

        retries = 3
        last_exception = None # Keep track of the last exception for the final error message

        for attempt in range(retries):
            try:
                response = await self.client.post(
                    "/", # POST to base_url root
                    json=request.to_dict() # Use the method to get dict
                )
                response.raise_for_status() # Check for HTTP 4xx/5xx errors first

                # Successful request, break retry loop
                break
            # --- Catch specific connection errors ---
            except (httpx.ConnectError, httpx.TimeoutException, httpx.NetworkError) as e: # Added NetworkError
                last_exception = e
                logger.warning(f"Attempt {attempt + 1}/{retries} failed for action {action.value}: {e}")
                if attempt == retries - 1:
                    # Raise custom error after all retries failed
                    error_message = (
                        f"Unable to connect to AnkiConnect at {self.base_url} after {retries} attempts. "
                        f"Please ensure Anki is running and the AnkiConnect add-on is installed and enabled. "
                        f"Last error: {last_exception}"
                    )
                    logger.error(error_message)
                    raise AnkiConnectionError(error_message) from last_exception
                # Exponential backoff: 1, 2, 4 seconds
                backoff_time = 2 ** attempt
                logger.info(f"Retrying in {backoff_time} seconds...")
                await asyncio.sleep(backoff_time)
                continue # Go to next retry attempt
            # --- End connection error handling ---
            except httpx.HTTPStatusError as e:
                # Handle non-connection HTTP errors (like 403 Forbidden, 500 Internal Server Error from AnkiConnect)
                logger.error(f"HTTP error invoking {action.value}: Status {e.response.status_code}, Response: {e.response.text}")
                # Reraise as a runtime error, potentially including response body
                raise RuntimeError(f"AnkiConnect request failed with status {e.response.status_code}: {e.response.text}") from e
            except Exception as e:
                 # Catch any other unexpected errors during the request/response cycle
                 logger.exception(f"Unexpected error during AnkiConnect invoke action '{action.value}': {e}")
                 # Reraise as a generic runtime error or a more specific custom error if identifiable
                 raise RuntimeError(f"An unexpected error occurred during the AnkiConnect request: {e}") from e
        else:
             # This else block executes if the loop completed without break (i.e., all retries failed)
             # This should theoretically be covered by the retry == retries - 1 check inside the loop,
             # but adding it for robustness in case of unexpected loop exit.
             if last_exception:
                 error_message = f"AnkiConnect action {action.value} failed after {retries} retries. Last error: {last_exception}"
                 logger.error(error_message)
                 raise AnkiConnectionError(error_message) from last_exception
             else:
                 # Should not happen if loop finishes, but handle defensively
                 error_message = f"AnkiConnect action {action.value} failed after {retries} retries for an unknown reason."
                 logger.error(error_message)
                 raise RuntimeError(error_message)


        # --- Process successful response ---
        try:
            # Decode the JSON response (synchronous in httpx)
            response_data = response.json()

            # Check if the response is the expected dictionary format or just the result
            if isinstance(response_data, dict) and 'result' in response_data and 'error' in response_data:
                # Standard format, validate directly
                anki_response = AnkiConnectResponse.model_validate(response_data)
            else:
                # Assume response_data is the result itself (e.g., a list for deckNames)
                logger.debug(f"Received direct result payload for action {action.value}. Wrapping in AnkiConnectResponse.")
                anki_response = AnkiConnectResponse(result=response_data, error=None)

            if anki_response.error:
                logger.error(f"AnkiConnect API returned error for action {action.value}: {anki_response.error}")
                # This is an error reported by the AnkiConnect API itself
                raise ValueError(f"AnkiConnect error: {anki_response.error}")

            logger.debug(f"AnkiConnect action {action.value} successful.")
            return anki_response.result

        except ValueError as e:
            # Re-raise ValueError (from AnkiConnect errors or JSON parsing issues) directly
            logger.error(f"Error processing AnkiConnect response for action {action.value}: {e}")
            raise
        except Exception as e:
            logger.exception(f"Unexpected error processing AnkiConnect response for {action.value}: {str(e)}")
            raise RuntimeError(f"Unexpected error processing AnkiConnect response: {str(e)}") from e
        # --- End response processing ---


    # --- Wrapper methods ---
    # Remove redundant try/except blocks, rely on invoke's error handling
    async def cards_info(self, card_ids: List[int]) -> List[dict]:
        return await self.invoke(AnkiAction.CARDS_INFO, cards=card_ids)

    async def deck_names(self) -> List[str]:
        return await self.invoke(AnkiAction.DECK_NAMES)

    async def find_cards(self, query: str) -> List[int]:
        return await self.invoke(AnkiAction.FIND_CARDS, query=query)

    async def answer_cards(self, answers: List[dict]) -> List[bool]:
        # AnkiConnect expects list of {"cardId": int, "ease": int}
        # Ensure the input format matches or convert here if needed
        return await self.invoke(AnkiAction.ANSWER_CARDS, answers=answers)

    async def model_field_names(self, model_name: str) -> List[str]:
        return await self.invoke(AnkiAction.MODEL_FIELD_NAMES, modelName=model_name)

    async def model_names(self) -> List[str]:
        return await self.invoke(AnkiAction.MODEL_NAMES)

    async def find_notes(self, query: str) -> List[int]:
        return await self.invoke(AnkiAction.FIND_NOTES, query=query)

    async def add_note(self, note: dict) -> int:
        # Note structure should match AnkiConnect requirements:
        # {"deckName": ..., "modelName": ..., "fields": {...}, "tags": [...], "options": {...}}
        return await self.invoke(AnkiAction.ADD_NOTE, note=note)

    async def notes_info(self, note_ids: List[int]) -> List[dict]:
        return await self.invoke(AnkiAction.NOTES_INFO, notes=note_ids)

    async def close(self):
        await self.client.aclose()
