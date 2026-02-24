# Progress Log

## 2026-02-24

- Updated MCP Python SDK from `>=1.2.0` to `>=1.26.0` (resolved version: 1.6.0 → 1.26.0).
- Added image attachment support for Anki cards:
  - Extended `add_note` tool with optional `picture` parameter for inline image attachments.
  - Added standalone `store_media_file` tool for independent media storage.
  - Added `STORE_MEDIA_FILE` action and `store_media_file` wrapper to `AnkiConnectClient`.
- Added 10 new tests (63 total, all passing):
  - 4 tests for `add_note` with pictures (URL, base64, multiple, none).
  - 4 tests for `store_media_file` tool (URL, base64, no source, connection error).
  - 2 tests for `store_media_file` client wrapper (URL, data).

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
