# mcp-ankiconnect

Python MCP server that bridges Claude with Anki via the AnkiConnect add-on (HTTP on `localhost:8765`). Exposes tools for reviewing due cards, adding notes (with images), and searching the collection.

## Architecture

- `mcp_ankiconnect/server.py` — FastMCP instance, annotation presets (`READ_ONLY`/`ADDITIVE`/`EDIT`/`DESTRUCTIVE`/`NETWORK`), core tools and formatting helpers.
- `mcp_ankiconnect/edit_tools.py` — inspect/edit tools on existing notes and cards, including flags and scheduling transfer. Writes via `setSpecificValueOfCard` can no-op silently, so those tools re-read cards and report per-card status.
- `mcp_ankiconnect/collection_tools.py` — batch add, delete, tags, decks, sync, review stats, media read-back, GUI context.
- `mcp_ankiconnect/ankiconnect_client.py` — `httpx` client with retry + `AnkiConnectionError`. Wraps each AnkiConnect action as a typed method.
- `mcp_ankiconnect/backend_mode.py`, `direct_client.py`, `direct_actions.py`, `collection_locator.py` — dual backend. Each tool call probes AnkiConnect (0.5 s connect timeout); if nothing listens and the optional `direct` extra (`anki` PyPI package, Anki's own Rust engine) is installed, `get_anki_client()` yields a `DirectAnkiClient` instead. It subclasses `AnkiConnectClient` and overrides only `invoke`, emulating exactly the AnkiConnect actions in `AnkiAction` with AnkiConnect's return shapes, so typed methods and tools are unchanged (only `sync` and `get_gui_context` branch on `backend_mode`). `collection_locator` finds the file (`ANKI_COLLECTION_PATH`, else `ANKI_PROFILE`, last-used profile in `prefs21.db`, or the only profile). The decorator prepends a one-line `NOTE:` to the first text result after the backend flips (none for the usual open-from-the-start case). `ANKI_DIRECT_FALLBACK=0` turns it off.
- `mcp_ankiconnect/config.py` — constants (`TIMEOUTS`, `RATING_TO_EASE`, `EXCLUDE_STRINGS`, `MAX_FUTURE_DAYS`).
- `mcp_ankiconnect/server_prompts.py` — long-form LLM prompts (review instructions, flashcard guidelines).
- `mcp_ankiconnect/main.py` — `mcp.run()` entry point.
- `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`, `.mcp.json` — the repo is also the Claude Code plugin `ankiconnect` and its own marketplace. `.mcp.json` runs this checkout via `uv run --directory ${CLAUDE_PLUGIN_ROOT} --extra direct`; the AnkiConnect URL, Anki profile and collection path come from `userConfig`.
- `skills/` — generic plugin skills: `card-writing`, `card-judgement`, `due-card-redesign`. Keep them free of personal data (names, note IDs, local paths); personal rules live in a user's own overlay plugin. `tests/test_plugin_packaging.py` fails if a skill names a tool that does not exist, so rename tools and skills together. Keep `plugin.json` `version` equal to `pyproject.toml`'s.

Every `@mcp.tool` is wrapped in `@handle_anki_connection_error` which converts exceptions into `SYSTEM_ERROR: ...` strings the LLM can act on — do NOT raise from tools; return strings.

## Tools exposed

`num_cards_due_today`, `list_decks_and_notes`, `get_examples`, `fetch_due_cards_for_review`, `submit_reviews`, `add_note`, `add_notes`, `store_media_file`, `retrieve_media_file`, `search_notes`, `inspect_cards`, `update_note_fields`, `update_note_tags`, `set_suspended`, `change_deck`, `reschedule_cards`, `set_card_flag`, `copy_scheduling`, `delete_notes`, `list_tags`, `create_deck`, `sync`, `get_review_stats`, `find_struggling_cards`, `get_gui_context`.

Every new tool MUST pass an annotation preset to `@mcp.tool(annotations=...)`; `tests/test_collection_tools.py::test_every_tool_declares_annotations` enforces it. Resource: `anki://docs/search-syntax`.

## Run / debug

- Run server: `uv run mcp-ankiconnect`
- MCP Inspector (preferred for dev): `uv run mcp dev mcp_ankiconnect/server.py`
- Tests: `uv run pytest` (asyncio_mode=auto, see `pyproject.toml`)

Anki must be running with the AnkiConnect add-on (id `2055492159`) listening on `localhost:8765` for any AnkiConnect smoke test; unit tests mock the client. Direct-mode smoke test: point `ANKI_COLLECTION_PATH` at a scratch collection and `ANKI_CONNECT_URL` at an unused port.

## Gotchas

- **AnkiConnect `findNotes` does NOT support `sort:` directives** — they are a browser-UI feature only. Do ordering/sampling in Python after the result returns. See `_build_example_query` in `server.py`.
- **Image attachments**: prefer the `path` parameter (absolute file path) over `data` (base64) when the user shares a local file — AnkiConnect reads from disk faster and avoids large payloads. Source priority in AnkiConnect: `data > path > url`.
- **macOS AppSleep** can slow AnkiConnect dramatically; the workaround is in `README.md`.
- **Direct mode opens the collection per action and closes it straight after** (inside `asyncio.to_thread`, under a process-wide lock so concurrent tool calls do not look like a running Anki). Never cache a `Collection` across calls: holding it locks Anki out. If Anki holds the file, `Collection()` raises `DBError("Anki already open…")`; we turn that into a `DirectBackendError` and never retry or wait for the lock.
- **Schema guard.** `Collection()` silently upgrades an older schema (verified: ver 15/17 → 18, not downgraded on close) and refuses a newer one (`FileTooNew`). `direct_client.check_schema` reads `col.ver` with an `immutable=1` sqlite open (a plain read-only open leaves `-wal`/`-shm` files) and opens only when it equals the version the installed `anki` package creates (`supported_schema_version()`, learned from a scratch collection). Do not relax this to "older is fine".
- **Direct mode never contacts AnkiWeb.** `sync` reports that changes reach AnkiWeb the next time Anki syncs; GUI actions report "nothing open". Writes go through Anki APIs (`sched.answerCard` on the v3 scheduler, `set_due_date`, `set_user_flag_for_cards`, `update_card`), never raw SQL. `setSpecificValueOfCard` supports only `flags`/`ivl`/`factor` there.
- **Direct-mode tests use real collections** built with the `anki` package in tmp dirs (`tests/conftest.py`); `anki` is also in the dev group so `uv run pytest` runs them; they skip only where it is absent.
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
