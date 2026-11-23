# Feature parity with other Anki MCP servers — design

## Context

We surveyed the other Anki MCP servers with the most adoption:
[ankimcp](https://github.com/ankimcp/anki-mcp-server),
[nailuoGG](https://github.com/nailuoGG/anki-mcp-server),
[scorzeth](https://github.com/scorzeth/anki-mcp-server),
[CamdenClark](https://github.com/CamdenClark/anki-mcp-server),
[spacholski1225](https://github.com/spacholski1225/anki-connect-mcp),
[arielbk](https://github.com/arielbk/anki-mcp),
[johwiebe](https://github.com/johwiebe/anki-mcp) and
[ujisati](https://github.com/ujisati/anki-mcp).
Our server is strong on review, inspection and editing. It falls behind on
batch creation, analytics, sync, media read-back, GUI context, deletion and
discoverability (tool annotations, server instructions, a search-syntax
resource).

## In scope

| Tool / feature | AnkiConnect | Annotation | Rationale |
|---|---|---|---|
| `add_notes` (batch, ≤100) | `canAddNotesWithErrorDetail`, `addNotes` | additive | An LLM usually makes 5–30 cards at a time. The pre-check means one duplicate no longer fails the whole batch. |
| `delete_notes` | `deleteNotes` | destructive | Clean-up and merging duplicates. Requires `confirm=True`. |
| `list_tags` | `getTags` | read-only | Keeps tag names consistent with the user's existing tags. |
| `create_deck` | `createDeck` | additive, idempotent | Creates a deck explicitly before batch adds. |
| `sync` | `sync` | open-world | Sync before reviewing and after making edits. |
| `get_review_stats` | `getNumCardsReviewedByDay` | read-only | Progress talk: today's count, daily series, streak. |
| `find_struggling_cards` | `findCards`, `cardsInfo` | read-only | Finds leeches and weak cards to target for rewriting. |
| `retrieve_media_file` | `retrieveMediaFile` | read-only | Returns MCP `Image` content, so the model can see card images. |
| `get_gui_context` | `guiCurrentCard`, `guiSelectedNotes` | read-only | Lets the user say "fix this card" or "fix the selected notes". |
| Tool annotations on every tool | — | — | Clients can auto-approve reads and gate destructive tools. |
| Server `instructions` | — | — | Explains card IDs vs note IDs and the recommended authoring flow. |
| `anki://docs/search-syntax` resource | — | — | Short cheat sheet that links to the official manual. |

## Out of scope (low value for an LLM flashcard workflow)

These are deliberately left out:

- note-type authoring (`createModel`, template and CSS edits);
- deck options;
- `.apkg` import and export;
- the remaining `gui*` actions;
- interval and due checks.

## Design notes

- The new tools live in `mcp_ankiconnect/collection_tools.py` and register
  on the shared `mcp` instance. This follows the pattern `edit_tools.py`
  already uses.
- `add_note` and `add_notes` share one `_build_note_payload` helper. That
  way MathJax and code conversion, and the duplicate options, cannot drift
  apart.
- `add_notes` sends only the notes that pass the pre-check. It then reports
  per-index results: `added` with its id, or `skipped` with a reason. The
  pre-check is needed because recent AnkiConnect versions make `addNotes`
  fail outright when any one note is invalid.
- The streak calculation takes `today` as a parameter so it can be tested
  deterministically.
- Annotation presets (`READ_ONLY`, `ADDITIVE`, `EDIT`, `DESTRUCTIVE`) are
  defined once in `server.py`.
