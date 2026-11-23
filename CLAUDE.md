# mcp-ankiconnect

Python MCP server that bridges Claude with Anki via the AnkiConnect add-on (HTTP on `localhost:8765`). Exposes tools for reviewing due cards, adding notes (with images), and searching the collection.

## Architecture

- `mcp_ankiconnect/server.py` — FastMCP instance, annotation presets (`READ_ONLY`/`ADDITIVE`/`EDIT`/`DESTRUCTIVE`/`NETWORK`), core tools and formatting helpers.
- `mcp_ankiconnect/edit_tools.py` — inspect/edit tools on existing notes and cards, including flags and scheduling transfer. Writes via `setSpecificValueOfCard` can no-op silently, so those tools re-read cards and report per-card status.
- `mcp_ankiconnect/collection_tools.py` — batch add, delete, tags, decks, sync, review stats, media read-back, GUI context.
- `mcp_ankiconnect/ankiconnect_client.py` — `httpx` client with retry + `AnkiConnectionError`. Wraps each AnkiConnect action as a typed method.
- `mcp_ankiconnect/launcher.py` — opens Anki in the background when AnkiConnect refuses the connection. Its one entry point, `AnkiLauncher.recover`, is called by `AnkiConnectClient.invoke` on `httpx.ConnectError` only (never on timeouts); it holds the per-platform command, polling of `version`, an `asyncio.Lock` and a 60 s backoff after a failed launch. A launch records a NOTE line that `handle_anki_connection_error` prepends to the tool result (a `note` key for dicts; images unchanged). Env: `ANKI_AUTO_LAUNCH`, `ANKI_APP_PATH`, `ANKI_LAUNCH_TIMEOUT`.
- `mcp_ankiconnect/config.py` — constants (`TIMEOUTS`, `RATING_TO_EASE`, `EXCLUDE_STRINGS`, `MAX_FUTURE_DAYS`).
- `mcp_ankiconnect/ankiconnect_url.py` — resolves `ANKI_CONNECT_URL` at import: an explicit value wins; blank or an unexpanded `${user_config…}` means read `webBindAddress`/`webBindPort` from the AnkiConnect add-on's `config.json` merged with `meta.json` ["config"] under Anki's base folder (`ANKI_BASE` override); else `http://localhost:8765`. Exists because the plugin cannot ask for settings (see below).
- `mcp_ankiconnect/server_prompts.py` — long-form LLM prompts (review instructions, flashcard guidelines).
- `mcp_ankiconnect/app_tools.py` + `ui/card_review.html` — MCP Apps spike: `open_card_review` links a `ui://` page that hosts supporting MCP Apps (Claude Desktop, claude.ai; not the Claude Code CLI) render; its buttons call the app-only `record_card_decisions`, which appends to a JSONL log (`ANKI_DECISIONS_FILE`) and never writes to Anki. Card text is rendered with `textContent` only.
- `mcp_ankiconnect/main.py` — `mcp.run()` entry point.
- `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`, `.mcp.json` — the repo is also the Claude Code plugin `ankiconnect` and its own marketplace. `.mcp.json` runs this checkout via `uv run --directory ${CLAUDE_PLUGIN_ROOT}`; it declares no `userConfig`, because the Claude desktop app refuses to start a plugin server that needs user settings (`user_config_unsupported`); the server detects the port and defaults auto-launch on instead, and `test_plugin_declares_no_user_settings` keeps it that way. Bump `version` in both `plugin.json` and `pyproject.toml` with every release, or `/plugin update` will not fetch it.
- `skills/` — generic plugin skills: `card-writing`, `card-judgement`, `due-card-redesign`. Keep them free of personal data (names, note IDs, local paths); personal rules live in a user's own overlay plugin. `tests/test_plugin_packaging.py` fails if a skill names a tool that does not exist, so rename tools and skills together. Keep `plugin.json` `version` equal to `pyproject.toml`'s.

Every `@mcp.tool` is wrapped in `@handle_anki_connection_error` which converts exceptions into `SYSTEM_ERROR: ...` strings the LLM can act on — do NOT raise from tools; return strings.

## Tools exposed

`num_cards_due_today`, `list_decks_and_notes`, `get_examples`, `fetch_due_cards_for_review`, `submit_reviews`, `add_note`, `add_notes`, `store_media_file`, `retrieve_media_file`, `search_notes`, `inspect_cards`, `update_note_fields`, `update_note_tags`, `set_suspended`, `change_deck`, `reschedule_cards`, `set_card_flag`, `copy_scheduling`, `delete_notes`, `list_tags`, `create_deck`, `sync`, `get_review_stats`, `find_struggling_cards`, `get_gui_context`, `open_card_review`, `record_card_decisions` (app-only).

Every new tool MUST pass an annotation preset to `@mcp.tool(annotations=...)`; `tests/test_collection_tools.py::test_every_tool_declares_annotations` enforces it. Resource: `anki://docs/search-syntax`.

## Run / debug

- Run server: `uv run mcp-ankiconnect`
- MCP Inspector (preferred for dev): `uv run mcp dev mcp_ankiconnect/server.py`
- Tests: `uv run pytest` (asyncio_mode=auto, see `pyproject.toml`)

Anki must be running with the AnkiConnect add-on (id `2055492159`) listening on `localhost:8765` for any integration smoke test; unit tests mock the client.

## Gotchas

- **AnkiConnect `findNotes` does NOT support `sort:` directives** — they are a browser-UI feature only. Do ordering/sampling in Python after the result returns. See `_build_example_query` in `server.py`.
- **Image attachments**: prefer the `path` parameter (absolute file path) over `data` (base64) when the user shares a local file — AnkiConnect reads from disk faster and avoids large payloads. Source priority in AnkiConnect: `data > path > url`.
- **Auto-launch is on by default.** A refused connection to a local AnkiConnect makes the server open Anki (`open -g -a Anki` on macOS, a detached `anki` on Linux). Tests that let a real client hit a closed port must swap `mcp_ankiconnect.launcher.LAUNCHER` for a fake (see `tests/test_launcher.py`), or they will try to start Anki. A launch that times out is usually Anki's profile picker or a missing add-on.
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
