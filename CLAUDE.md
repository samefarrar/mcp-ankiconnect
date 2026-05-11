# mcp-ankiconnect

Python MCP server that bridges Claude with Anki via the AnkiConnect add-on (HTTP on `localhost:8765`). Exposes tools for reviewing due cards, adding notes (with images), and searching the collection.

## Architecture

- `mcp_ankiconnect/server.py` — FastMCP tool definitions and formatting helpers (the surface area).
- `mcp_ankiconnect/ankiconnect_client.py` — `httpx` client with retry + `AnkiConnectionError`. Wraps each AnkiConnect action as a typed method.
- `mcp_ankiconnect/config.py` — constants (`TIMEOUTS`, `RATING_TO_EASE`, `EXCLUDE_STRINGS`, `MAX_FUTURE_DAYS`).
- `mcp_ankiconnect/server_prompts.py` — long-form LLM prompts (review instructions, flashcard guidelines).
- `mcp_ankiconnect/main.py` — `mcp.run()` entry point.

Every `@mcp.tool` is wrapped in `@handle_anki_connection_error` which converts exceptions into `SYSTEM_ERROR: ...` strings the LLM can act on — do NOT raise from tools; return strings.

## Tools exposed

`num_cards_due_today`, `list_decks_and_notes`, `get_examples`, `fetch_due_cards_for_review`, `submit_reviews`, `add_note`, `store_media_file`, `search_notes`.

## Run / debug

- Run server: `uv run mcp-ankiconnect`
- MCP Inspector (preferred for dev): `uv run mcp dev mcp_ankiconnect/server.py`
- Tests: `uv run pytest` (asyncio_mode=auto, see `pyproject.toml`)

Anki must be running with the AnkiConnect add-on (id `2055492159`) listening on `localhost:8765` for any integration smoke test; unit tests mock the client.

## Gotchas

- **AnkiConnect `findNotes` does NOT support `sort:` directives** — they are a browser-UI feature only. Do ordering/sampling in Python after the result returns. See `_build_example_query` in `server.py`.
- **Image attachments**: prefer the `path` parameter (absolute file path) over `data` (base64) when the user shares a local file — AnkiConnect reads from disk faster and avoids large payloads. Source priority in AnkiConnect: `data > path > url`.
- **macOS AppSleep** can slow AnkiConnect dramatically; the workaround is in `README.md`.
- **Reference docs stay online.** Do not commit standalone Anki-Connect API or MCP spec dumps to the repo — link out instead.
- **If `.venv` looks broken** (e.g. `uv run` complains about a missing Python executable), delete it and let `uv` recreate it on the next command rather than reinstalling piecemeal.

## Project Management
- Use `uv` for Python package management and running tools (NEVER pip)
- Add packages: `uv add package_name`
- Remove packages: `uv remove package_name`
- Running Python tools: `uv run <tool>`
- Run all tests: `uv run pytest`
- Run single test: `uv run pytest tests/path_to_test.py::TestClass::test_method -v`
- Type checking: `uv run pyright .`
- Linting: `uv run ruff check .`
- Run formatter: `uv run ruff format .`
- Async testing: use anyio, not asyncio

## Code Style
- Use type hints for function signatures
- Functions must be small and focused
- Error handling: Use try/except with specific exceptions
- Document functions with docstrings (include "why" not just "what")
- Use f-strings for string formatting
- Max line length: 88 characters
- Program in the spirit of A Philosophy of Software Design by John Ousterhout.
- Explicit None checks for Optional types
- YOU MUST add regression tests when your encounter a bug. This should be the first thing you do when you are told about a bug.

## Testing notes

- TDD: start with failing tests, then implement.
- Unit tests live next to the functionality (in `mcp_ankiconnect/`); integration tests in `tests/`.
- Avoid mocks unless requested — but the existing test suite mocks `AnkiConnectClient.invoke` heavily to avoid requiring a running Anki instance.
- Tests use `pytest-asyncio` with `asyncio_mode = "auto"` (already configured in `pyproject.toml`).
