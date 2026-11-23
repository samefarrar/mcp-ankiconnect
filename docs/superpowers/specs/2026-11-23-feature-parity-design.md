# Anki workflow tools: parity, then fit to Sam's skills — design

Status: shaped without a grilling round, as Sam asked. Calls I made on his
behalf are marked **[my call]**.

## Intent and why

The literal ask was "feature parity with other Anki MCP servers". The outcome
behind that is that Sam's own Anki skills (`anki-cards`, `anki-due-redesign`
and `anki-card-judgement`, in `samefarrar/my-marketplace`) can do each Anki
operation in one well-shaped tool call. The AnkiConnect traps those skills
document should be absorbed by the server, not rediscovered by every caller.

Parity is a means. I checked the gaps against two sources:

- **Eight comparable servers:**
  [ankimcp](https://github.com/ankimcp/anki-mcp-server),
  [nailuoGG](https://github.com/nailuoGG/anki-mcp-server),
  [scorzeth](https://github.com/scorzeth/anki-mcp-server),
  [CamdenClark](https://github.com/CamdenClark/anki-mcp-server),
  [spacholski1225](https://github.com/spacholski1225/anki-connect-mcp),
  [arielbk](https://github.com/arielbk/anki-mcp),
  [johwiebe](https://github.com/johwiebe/anki-mcp) and
  [ujisati](https://github.com/ujisati/anki-mcp).
- **What Sam's skills actually do.** The skills surfaced two needs that none
  of the servers covers well:
  - **Card flags.** These are central to Sam's pipeline: red means a bad
    card, green a good one, and orange "maybe beyond FY1 level". The
    pipeline writes them with raw `setSpecificValueOfCard`.
  - **Scheduling transfer.** A redesigned card should inherit the original's
    interval and ease. The skill records that `setSpecificValueOfCard`
    "fails silently if newValues are strings", so every write has to be
    re-read to check it.

## Goals

1. Parity on the high-value gaps:
   - batch add;
   - delete;
   - tags and decks;
   - sync;
   - review statistics and struggling cards;
   - media read-back as images;
   - GUI context;
   - discoverability: tool annotations, server instructions and a
     search-syntax resource.
2. Flags as a first-class part of card state: set them, see them, and search
   for them.
3. Scheduling transfer from an original card onto its replacements, verified
   after writing.

## Non-goals

- Sam's pipeline conventions: the `redesigned::*` tags, the review UI and
  the apply scripts. These stay in his project scripts.
- Note-type authoring, deck options, `.apkg` import/export and the rarer
  `gui*` actions.
- Writing FSRS memory state. Sam's AnkiConnect fork blocks it.
- Any change to the marketplace skills (Sam said not for now).

## Anti-goals

- **A write that can be silently ignored and still reports success.** Where
  AnkiConnect is known to no-op silently, the tool re-reads the card and
  reports any mismatch per card.
- **Raw passthroughs that push traps onto the model,** for example
  exposing `setSpecificValueOfCard` directly.

## Constraints

- Upstream (legacy) AnkiConnect API, version 6. Sam's fork runs on port
  8999, which `ANKI_CONNECT_URL` already covers.
- Every tool returns strings; it never raises. That is the existing
  `handle_anki_connection_error` contract.
- Every tool carries an annotation preset, which a test enforces.
- Each bug gets a regression test first, and new features are built
  test-first (from CLAUDE.md).

## Facts that shaped the how

Source:
[API_LEGACY.md](https://raw.githubusercontent.com/FooSoft/anki-connect/master/API_LEGACY.md).

- **`setSpecificValueOfCard(card, keys, newValues, warning_check)`**
  - Valid keys include `flags`, `factor` and `ivl`. Among those three, only
    `ivl` needs `warning_check`.
  - `flags` cannot be combined with other keys in the same call.
  - The documentation does not say whether values should be ints or
    strings. Sam's pipeline found that strings fail silently on his fork.
- **`cardsInfo`** returns `flags`.
- **`addNotes`** rejects the whole batch if any note fails its pre-flight
  checks. Older versions saved some notes before raising. Either way, one
  bad note costs the whole batch. **`multi`** returns a
  `{result, error}` reply per action.
- **`guiCurrentCard`** returns `null` when not reviewing, and its reply has
  no note ID. **`guiSelectedNotes`** returns `[]` when the browser is
  closed.
- **`setDueDate`** takes `days` strings such as `"0"`, `"3-7"` and `"1!"`.
  It turns a new card into a review card.

## Approaches considered (for the flag and scheduling additions)

| Approach | Trade-off | Verdict |
|---|---|---|
| **A. Raw passthrough** (`set_specific_value_of_card`) | Most flexible. But the model must know about int coercion, `warning_check` and which keys can't be combined, and silent failures go unseen. | Rejected: it is the anti-goal. |
| **B. Intent tools that verify their writes** (`set_card_flag`, `copy_scheduling`) | Small and hard to misuse. Covers exactly what the skills do. Each call costs one extra read for verification. | **Picked.** |
| **C. Pipeline tool** (`replace_note`: add the new pieces, tag them, suspend the original, transfer scheduling) | One call for redesign steps 7–8, but it bakes Sam's tag conventions into a generic server. His `apply.py` already does this. | Deferred: this is the "bigger version". |

Climb (ambition), assessed:

- **Bigger version:** C, plus the skills calling the new tools. That needs
  marketplace changes, which Sam has excluded.
- **In between:** B, plus flags in `inspect_cards` and in the server
  instructions. **[my call]**

## Decided how

### Already built on this branch

- `add_notes`: one `multi` of `addNote` actions, with a result for each
  note.
- `delete_notes`: refuses unless `confirm=True`.
- `list_tags`, `create_deck` and `sync`.
- `get_review_stats`: "today" follows Anki's day, shifted by
  `ANKI_DAY_ROLLOVER_HOUR`, which defaults to 4.
- `find_struggling_cards`: above a scan cap it raises the lapse threshold
  rather than truncating by ID.
- `retrieve_media_file`: returns images as image content, except SVG.
- `get_gui_context`: fetches the note ID through `cardsInfo`.
- Annotation presets on every tool, server instructions, and the
  `anki://docs/search-syntax` resource.

### `set_card_flag(card_ids, flag)`

- **Flag names:** `flag` is one of `none`, `red`, `orange`, `green`,
  `blue`, `pink`, `turquoise` or `purple`, which map to 0–7. Names, not
  numbers, because Sam's skills think in colours. **[my call]**
- **Write:** one `multi` request holding one
  `setSpecificValueOfCard(card, ["flags"], [int])` per card. The value is
  sent as an int, since the documentation doesn't settle the type and
  Sam's evidence says ints.
- **Verify:** re-read the cards with `cardsInfo`. Each card is reported as
  `set`, or as `unchanged` with the flag Anki now holds. Cards that don't
  exist are reported as missing.
- **Scope:** takes card IDs only. Flags belong to cards, and `change_deck`
  makes the same choice.
- **Annotation:** `EDIT` (reversible and idempotent).

### Flags shown and searchable

- `inspect_cards`, `state` category: adds `flag` as a colour name, read from
  `cardsInfo.flags`. It is omitted when Anki doesn't report the field.
- Server instructions and the search cheat sheet name the colours and the
  matching `flag:N` searches.

### `copy_scheduling(target_card_ids, source_card_id | source_note_id, due="0-6")`

- **Source:** exactly one of `source_card_id` or `source_note_id`. Given a
  note, use its card with the longest interval, as Sam's
  `sched_transfer.py` does.
- **Refuse a fresh source:** if the source has never been reviewed
  (interval 0), return an error. Copying "new" scheduling is meaningless.
- **Writes, in order:**
  1. `setDueDate(targets, due)`. This makes them review cards. The `"0-6"`
     default spreads the reviews over a week, matching Sam's pipeline.
     **[my call]**
  2. In one `multi`, a `setSpecificValueOfCard(card, ["ivl", "factor"],
     [int, int], warning_check=True)` per target.
- **Verify:** re-read the targets with `cardsInfo`. Each card is reported
  `copied`, or `mismatch` with the expected and actual interval and factor.
- **Annotation:** `DESTRUCTIVE`. It overwrites the targets' scheduling.
- **What gets copied:** interval and factor only, nothing else. Sam's skill
  states the rule: "Each new card inherits the interval and factor of the
  original's longest-interval card". It also gives the write sequence,
  `setDueDate(cards, days="0-6")` and then
  `setSpecificValueOfCard(...keys=["ivl","factor"]...)`. The skill notes
  that "FSRS derives stability from ivl/ease at the first review", so
  copying interval and ease is enough under FSRS too. Answered from
  `anki-due-redesign/SKILL.md`.
- **History guard:** the tool refuses targets that already have reviews
  (`reps > 0`) unless `overwrite_history=True`. The intended targets are
  freshly added cards, and a wrong ID would otherwise silently wipe a
  mature card's progress. `delete_notes` already guards with
  `confirm=True`, and this follows the same idea. **[my call]**
- **Partial failure:** the tool reports and does not roll back. If
  `setDueDate` succeeds but the interval/factor write fails for a card,
  that card is reported as `mismatch` with its actual values. A rollback
  would be another write that can fail, and the report tells the caller
  exactly which cards to redo. **[my call]**

## Left to the builder

- Helper names, and how the shared multi-write-then-verify step is
  factored.
- Exact error wording, within the existing `SYSTEM_ERROR:` convention.
- Test structure, provided the regression tests cover silent no-ops: a
  write that "succeeds" but re-reads unchanged must show up as
  `unchanged` or `mismatch`.

## Outside judge, and what is not verified here

- No live Anki is reachable from the build container. The judges are the
  unit tests, a smoke test through the MCP layer (schemas and content
  types), and the AnkiConnect documentation quoted above.
- The first real-Anki run is Sam's: flag a card red, copy scheduling onto
  a redesigned card, and confirm both in the browser.
