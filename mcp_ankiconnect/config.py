import os
from typing import Final, NamedTuple

from mcp_ankiconnect.ankiconnect_url import resolve_ankiconnect_url

class TimeoutConfig(NamedTuple):
    connect: float  # Connection establishment timeout
    read: float    # Read operation timeout
    write: float   # Write operation timeout

# AnkiConnect configuration
# Explicit ANKI_CONNECT_URL, else read from the AnkiConnect add-on's settings
# on disk, else http://localhost:8765. See ankiconnect_url.py.
ANKI_CONNECT_URL: Final = resolve_ankiconnect_url()
ANKI_CONNECT_VERSION: Final = 6

# Review configuration
DEFAULT_REVIEW_LIMIT: Final = 5
MAX_FUTURE_DAYS: Final = 5  # Maximum number of days to look ahead for due cards
MAX_BATCH_NOTES: Final = 100  # add_notes batch ceiling (one AnkiConnect call)
# find_struggling_cards: most cardsInfo rows fetched to rank in Python.
MAX_STRUGGLING_SCAN: Final = 500
# Hour at which Anki starts a new day (Preferences > Review > "Next day
# starts at"). Reviews are bucketed by this day, not the calendar date.
ANKI_DAY_ROLLOVER_HOUR: Final = int(os.getenv("ANKI_DAY_ROLLOVER_HOUR", "4"))

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
    "AnKing",
    "#AK_",
    "!AK_"
]
