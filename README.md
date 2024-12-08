# mcp-ankiconnect MCP server

Connect Claude conversations with AnkiConnect via MCP to make spaced repetition as easy as "Help me remember this"

## Components

### Tools

The server implements three tools:

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

## Configuration

### Prerequisites

- Anki must be running with AnkiConnect plugin installed
- AnkiConnect must be configured to accept connections (default port: 8765)

### Installation

## Quickstart

1. Install the AnkiConnect plugin in Anki:
   - Tools > Add-ons > Get Add-ons...
   - Enter code: `2055492159`
   - Restart Anki

2. Install mcp-ankiconnect:
   ```bash
   pip install mcp-ankiconnect
   ```

3. Configure Claude Desktop:

   On MacOS: `~/Library/Application\ Support/Claude/claude_desktop_config.json`  
   On Windows: `%APPDATA%/Claude/claude_desktop_config.json`

   Add this configuration:
   ```json
   {
     "mcpServers": {
       "mcp-ankiconnect": {
         "command": "uvx",
         "args": ["mcp-ankiconnect"]
       }
     }
   }
   ```

4. Start Anki and ensure AnkiConnect is running
5. Restart Claude Desktop

## Development

### Building and Publishing

To prepare the package for distribution:

1. Sync dependencies and update lockfile:
```bash
uv sync
```

2. Build package distributions:
```bash
uv build
```

This will create source and wheel distributions in the `dist/` directory.

3. Publish to PyPI:
```bash
uv publish
```

Note: You'll need to set PyPI credentials via environment variables or command flags:
- Token: `--token` or `UV_PUBLISH_TOKEN`
- Or username/password: `--username`/`UV_PUBLISH_USERNAME` and `--password`/`UV_PUBLISH_PASSWORD`

### Debugging

Since MCP servers run over stdio, debugging can be challenging. For the best debugging
experience, we strongly recommend using the [MCP Inspector](https://github.com/modelcontextprotocol/inspector).


You can launch the MCP Inspector via [`npm`](https://docs.npmjs.com/downloading-and-installing-node-js-and-npm) with this command:

```bash
npx @modelcontextprotocol/inspector uv --directory /Users/samfarrar/Documents/Programming/claude/mcp-ankiconnect run mcp-ankiconnect
```


Upon launching, the Inspector will display a URL that you can access in your browser to begin debugging.
