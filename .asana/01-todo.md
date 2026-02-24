# To Do List

## Refactor mcp-ankiconnect based on APSD Review

- [x] **`ankiconnect_client.py` Refactor:**
    - [x] Simplify `__init__` timeout handling (expect `TimeoutConfig`).
    - [x] Refactor `invoke` into `_send_request_with_retries` and `_parse_response`.
    - [x] Remove redundant `else` block in retry loop.
    - [x] Remove fallback import logic for `config`.
- [x] **`server.py` Refactor:**
    - [x] Extract field processing from `add_note` into `_process_field_content`.
    - [x] Extract formatting from `fetch_due_cards_for_review` into `_format_cards_for_llm`.
    - [x] Extract query building/formatting from `get_examples` into helpers (`_build_example_query`, `_format_example_notes`).
- [x] **`tests/` Updates:**
    - [x] Add specific tests for new helper functions in `server.py`.
    - [ ] Consider using fixtures or `async with` for client cleanup in tests.

## Add search_notes Tool

- [x] **`server.py`:**
    - [x] Add `_format_search_results` helper function.
    - [x] Add `search_notes` tool with comprehensive docstring documenting Anki search syntax.
- [x] **`tests/test_server.py`:**
    - [x] Add tests for `search_notes` tool (success, no results, limit, connection error, complex query).
    - [x] Add tests for `_format_search_results` helper.

## Update MCP SDK and Add Image Support

- [x] **Update MCP SDK:** Bumped `mcp[cli]` from `>=1.2.0` to `>=1.26.0` (resolved 1.6.0 → 1.26.0).
- [x] **`ankiconnect_client.py`:**
    - [x] Add `STORE_MEDIA_FILE` action to `AnkiAction` enum.
    - [x] Add `store_media_file` wrapper method with support for data, url, and path sources.
- [x] **`server.py`:**
    - [x] Add `picture` parameter to `add_note` tool for inline image attachments via AnkiConnect's native addNote picture support.
    - [x] Add standalone `store_media_file` tool for storing images independently.
- [x] **`tests/test_server.py`:**
    - [x] Add tests for `add_note` with picture URL, base64, multiple pictures, and no picture.
    - [x] Add tests for `store_media_file` with URL, base64, no source, and connection error.
- [x] **`tests/test_ankiconnect_client.py`:**
    - [x] Add tests for `store_media_file` client wrapper (URL and data sources).
