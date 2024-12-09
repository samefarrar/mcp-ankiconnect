import os
from typing import Final, NamedTuple

class TimeoutConfig(NamedTuple):
    connect: float  # Connection establishment timeout
    read: float    # Read operation timeout
    write: float   # Write operation timeout

# AnkiConnect configuration
ANKI_CONNECT_URL: Final = os.getenv("ANKI_CONNECT_URL", "http://localhost:8765")
ANKI_CONNECT_VERSION: Final = 6

# Review configuration
DEFAULT_REVIEW_LIMIT: Final = 5
MAX_FUTURE_DAYS: Final = 5  # Maximum number of days to look ahead for due cards

# Timeout configuration
TIMEOUTS: Final = TimeoutConfig(
    connect=5.0,   # Shorter timeout for connection
    read=120.0,    # Longer timeout for read operations
    write=30.0     # Medium timeout for write operations
)

# Rating mappings
RATING_TO_EASE = {
    "wrong": 1,  # Again
    "hard": 2,   # Hard
    "good": 3,   # Good
    "easy": 4    # Easy
}

EXCLUDE_STRINGS = [
    "AnKing"
]
