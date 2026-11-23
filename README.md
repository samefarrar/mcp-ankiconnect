# mcp-ankiconnect MCP server

Connect Claude conversations with AnkiConnect via MCP to make spaced repetition as easy as "Let's go through today's flashcards" or "Make flashcards for this"

## Components

### Tools

The server implements the following tools:

- `num_cards_due_today`: Get the number of cards due today
  - Optional `deck` argument to filter by specific deck
  - Returns count of due cards across all decks or specified deck

- `get_due_cards`: Get cards that are due for review
  - Optional `limit` argument (default: 5) to control number of cards
  - Optional `deck` argument to filter by specific deck
  - Optional `today_only` argument (default: true) to show only today's cards
  - Returns cards in XML format with questions and answers

- `submit_reviews`: Submit answers for reviewed cards
  - Takes list of `reviews` with `card_id` and `rating`
  - Ratings: "wrong", "hard", "good", "easy"
  - Returns confirmation of submitted reviews

- `search_notes`: Find notes by AnkiConnect query. Returns IDs + a short Front preview by default (cheap); pass `return_card_content=true` to receive cleaned field content inline.
- `inspect_cards`: View per-card state (including the flag colour) for given card IDs or note IDs. Sparse-fieldset selection via the `properties` list: any of `identity`, `state`, `scheduling`, `timestamps`, `history`, `fields`, or `all` (default: `["identity", "state", "scheduling"]`). The legacy `include_history=true` flag is still accepted as an alias.
- `update_note_fields`: Modify the text content of one note's fields. Uses the same MathJax/code conversions as `add_note`.
- `update_note_tags`: Add and/or remove tags on one or more notes.
- `set_suspended`: Suspend or unsuspend one or more cards.
- `change_deck`: Move cards (by card ID) into a different deck.
- `reschedule_cards`: Set due date, forget, or relearn one or more cards.
- `add_notes`: Add up to 100 notes in one request. Each note succeeds or fails
  on its own, and failures such as duplicates are reported per index, so one
  bad note never sinks the batch.
- `delete_notes`: Permanently delete notes. Requires `confirm=true`, which the
  assistant should set only after the user approves.
- `list_tags`: List existing tags, with an optional substring filter, so new
  cards reuse consistent tag names.
- `create_deck`: Create a deck or nested deck (`Parent::Child`).
- `sync`: Sync the collection with AnkiWeb.
- `get_review_stats`: Today's review count, daily series, average and current
  streak. Days follow Anki's rollover hour; set `ANKI_DAY_ROLLOVER_HOUR` if
  yours is not the default of 4am.
- `find_struggling_cards`: Cards with the most lapses and lowest ease, for
  targeted rewriting.
- `retrieve_media_file`: Return an image from Anki's media folder as image
  content, so the assistant can see card images.
- `get_gui_context`: The card shown in the reviewer and the notes selected in
  the browser, for requests like "fix this card".
- `set_card_flag`: Set or clear a card's coloured flag (red, orange, green and
  so on). Each card is re-read afterwards and reported as set or unchanged.
- `copy_scheduling`: Give redesigned cards the interval and ease of the
  original card or note. It refuses targets that already have reviews unless
  `overwrite_history=true`, and re-reads every target to confirm the copy.

Every tool declares MCP annotations (`readOnlyHint`, `destructiveHint` and so
on), so clients can auto-approve reads and gate destructive calls.

### Resources and instructions

- `anki://docs/search-syntax`: a cheat sheet for Anki search queries. It
  links to the [official manual](https://docs.ankiweb.net/searching.html).
- On connect, the server sends instructions that explain note IDs versus card
  IDs and the recommended authoring and review flows.

## Configuration

### Prerequisites

- Anki must be running with [AnkiConnect plugin](https://ankiweb.net/shared/info/2055492159) installed (plugin id 2055492159)
  AnkiConnect can be slow on Macs due to the AppSleep feature, so disable it for Anki. To do so run the following in your terminal.
  ```bash
  defaults write net.ankiweb.dtop NSAppSleepDisabled -bool true
  defaults write net.ichi2.anki NSAppSleepDisabled -bool true
  defaults write org.qt-project.Qt.QtWebEngineCore NSAppSleepDisabled -bool true
  ```

### Environment variables

| Variable | Default | What it does |
| --- | --- | --- |
| `ANKI_CONNECT_URL` | detected | Where AnkiConnect listens. Leave unset to read the port from the AnkiConnect add-on's own settings (`addons21/2055492159`, falling back to `http://localhost:8765`). |
| `ANKI_AUTO_LAUNCH` | `true` | Open Anki in the background when a tool needs it and nothing is listening. `0`, `false`, `no` or `off` turn it off. |
| `ANKI_APP_PATH` | `Anki` (macOS), `anki` (Linux) | App name, `.app` path or executable used to open Anki. |
| `ANKI_LAUNCH_TIMEOUT` | `30` | Seconds to wait for AnkiConnect to answer after opening Anki. |
| `ANKI_DAY_ROLLOVER_HOUR` | `4` | Hour at which Anki starts a new day. |

**Opening Anki automatically.** When Anki is closed, the first tool call opens
it without taking focus (`open -g -a Anki` on macOS, a detached `anki` on
Linux; Windows tries `%LOCALAPPDATA%\Programs\Anki\anki.exe`), waits for
AnkiConnect, and carries on. The result then starts with a line such as
`NOTE: Anki was closed, so I opened it in the background (took 7 s).` Only a
refused connection to a local AnkiConnect triggers this; a busy Anki that times
out is never launched again. If AnkiConnect does not answer in time, Anki is
usually waiting at the profile picker or the add-on is missing, and the server
will not try again for 60 s.

### Installation

## Claude Code plugin

This repository is also a Claude Code plugin, `ankiconnect`, and its own
marketplace. Installing it gives you the MCP server (run from the plugin's own
copy with `uv`, so tools and skills always match) plus three skills:

- `card-writing`: note types, cloze engineering, the approve-then-add workflow
  and the review cycle.
- `card-judgement`: the quality bar every card must clear, with a pre-flight
  checklist and triage calibration distilled from thousands of real
  approve/reject verdicts.
- `due-card-redesign`: triage a batch of due, red-flagged or leech cards with
  parallel subagents, agree verdicts and redesigns in chat, apply them, carry
  scheduling over with `copy_scheduling`, and log verdicts so the rules improve.

```
/plugin marketplace add samefarrar/mcp-ankiconnect
/plugin install ankiconnect@mcp-ankiconnect
```

You need [uv](https://docs.astral.sh/uv/) on your `PATH`, and Anki running with
AnkiConnect. The plugin asks for no settings: the server reads AnkiConnect's
port from the add-on's own settings, and opens Anki in the background when a
tool needs it. To override either, set `ANKI_CONNECT_URL` or
`ANKI_AUTO_LAUNCH=false` in the environment Claude runs in.

**Personal overlays.** The skills are generic on purpose. To teach them your own
conventions (default deck, note types, tags, flag meanings) and your own
verdicts, write a small plugin of your own that depends on `ankiconnect` and
adds skills such as `my-card-judgement`. The generic skills defer to a loaded
personal skill wherever the two conflict.

## Quickstart

1. Install the AnkiConnect plugin in Anki:
   - Tools > Add-ons > Get Add-ons...
   - Enter code: `2055492159`
   - Restart Anki

2. Configure Claude Desktop:

   On MacOS: `~/Library/Application\ Support/Claude/claude_desktop_config.json`
   On Windows: `%APPDATA%/Claude/claude_desktop_config.json`

   Add this configuration:
   ```json
   {
     "mcpServers": {
       "mcp-ankiconnect": {
         "command": "uv",
         "args": ["run", "--with", "mcp-ankiconnect", "mcp-ankiconnect"]
       }
     }
   }
   ```

3. Restart Anki and Claude desktop

### Debugging

Since MCP servers run over stdio, debugging can be challenging. For the best debugging
experience, we strongly recommend using the [MCP Inspector](https://github.com/modelcontextprotocol/inspector).
First, clone the repository and install the dependencies:

```bash
git clone https://github.com/samefarrar/mcp-ankiconnect.git
cd mcp-ankiconnect
uv sync
```
You can launch the MCP Inspector via the mcp CLI:

```bash
uv run mcp dev mcp_ankiconnect/server.py
```

Upon launching, the Inspector will display a URL you can access in your browser to begin debugging.
