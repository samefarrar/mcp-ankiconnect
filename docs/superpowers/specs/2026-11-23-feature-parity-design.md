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
| `add_notes` (batch, ≤100) | `multi` of `addNote` | additive | An LLM usually makes 5–30 cards at a time. Each note succeeds or fails on its own, so one duplicate cannot fail the whole batch. |
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
- `add_notes` sends a single `multi` request made of `addNote` actions, and
  reports per-index results: `added` with its id, or `failed` with a reason.
  We rejected two alternatives:
  - `addNotes` saves what it can, then raises one error for the whole batch,
    which loses the IDs of the notes it did save.
  - A `canAddNotesWithErrorDetail` pre-check ignores pictures. It wrongly
    rejects notes filled only by a picture, and misses picture URLs that
    fail to download.
- The streak calculation takes `today` as a parameter so it can be tested
  deterministically. "Today" means Anki's day: the local time minus
  `ANKI_DAY_ROLLOVER_HOUR` (default 4).
- `get_gui_context` looks up the note ID with `cardsInfo`, because
  `guiCurrentCard` does not include it.
- `retrieve_media_file` does not return SVG as image content, because model
  APIs accept only png, jpeg, gif and webp.
- Annotation presets (`READ_ONLY`, `ADDITIVE`, `EDIT`, `DESTRUCTIVE`,
  `NETWORK`) are
  defined once in `server.py`.
