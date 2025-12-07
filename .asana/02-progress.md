# Progress Log

## 2025-12-07

- Added `search_notes` tool to expose Anki's powerful built-in search functionality.
- Added `_format_search_results` helper function for formatting note search results.
- Comprehensive docstring includes common search patterns (text, field, deck, tag, state, properties, etc.).
- Added tests for `search_notes` tool and `_format_search_results` helper.

## 2025-04-28

- Started refactoring `mcp-ankiconnect` based on APSD review.
- Completed `ankiconnect_client.py` refactor (timeout handling, invoke method, imports).
- Completed `server.py` refactor (extracting helpers for `add_note`, `fetch_due_cards_for_review`, `get_examples`).
- **Completed:** `tests/` updates (added tests for new server helper functions).
