import os
from typing import Final

# AnkiConnect configuration
ANKI_CONNECT_URL: Final = os.getenv("ANKI_CONNECT_URL", "http://localhost:8765")
ANKI_CONNECT_VERSION: Final = 6

# Review configuration
DEFAULT_REVIEW_LIMIT: Final = 5
MAX_FUTURE_DAYS: Final = 5  # Maximum number of days to look ahead for due cards
HTTPX_TIMEOUT: Final = 120.0  # Timeout for AnkiConnect requests in seconds

# Rating mappings
RATING_TO_EASE = {
    "wrong": 1,  # Again
    "hard": 2,   # Hard
    "good": 3,   # Good
    "easy": 4    # Easy
}
