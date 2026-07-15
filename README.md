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
- `inspect_cards`: View per-card state for given card IDs or note IDs. Sparse-fieldset selection via the `properties` list: any of `identity`, `state`, `scheduling`, `timestamps`, `history`, `fields`, or `all` (default: `["identity", "state", "scheduling"]`). The legacy `include_history=true` flag is still accepted as an alias.
- `update_note_fields`: Modify the text content of one note's fields. Uses the same MathJax/code conversions as `add_note`.
- `update_note_tags`: Add and/or remove tags on one or more notes.
- `set_suspended`: Suspend or unsuspend one or more cards.
- `change_deck`: Move cards (by card ID) into a different deck.
- `reschedule_cards`: Set due date, forget, or relearn one or more cards.

## Configuration

### Prerequisites

- Anki must be running with [AnkiConnect plugin](https://ankiweb.net/shared/info/2055492159) installed (plugin id 2055492159)
  AnkiConnect can be slow on Macs due to the AppSleep feature, so disable it for Anki. To do so run the following in your terminal.
  ```bash
  defaults write net.ankiweb.dtop NSAppSleepDisabled -bool true
  defaults write net.ichi2.anki NSAppSleepDisabled -bool true
  defaults write org.qt-project.Qt.QtWebEngineCore NSAppSleepDisabled -bool true
  ```

### Installation

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
uv run mcp dev mcp_ankiconnect/main.py
```

Upon launching, the Inspector will display a URL you can access in your browser to begin debugging.
