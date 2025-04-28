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
- [ ] **`tests/` Updates:**
    - [ ] Add specific tests for new helper functions in `server.py`.
    - [ ] Consider using fixtures or `async with` for client cleanup in tests.
