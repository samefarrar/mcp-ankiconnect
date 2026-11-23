---
name: due-card-redesign
description: "Triage and redesign a batch of badly designed Anki cards using only the ankiconnect MCP tools: gather due, red-flagged, leech or chosen notes, triage them with parallel subagents, get the user's verdicts in chat, redesign the bad ones in parallel, get approval, apply the changes, carry scheduling over to the new cards, rework rejections, and log every verdict so the judgement rules improve. Use it when the user says 'fix my due cards', 'triage today's Anki', 'redesign my bad cards', 'clean up my leeches', 'go through my red flags', or asks to rework rejected redesigns."
---

# Due-card triage and redesign

The pipeline runs as triage, verdicts, redesign, approval, apply, scheduling, rework and distil.
It needs nothing but this plugin's MCP tools, subagents and a scratch working directory. Load
**card-judgement** before any triage or redesign, and make every subagent load it too. A personal
overlay skill may set the deck, tags, flag meanings, paths and exclusions; its settings replace the
defaults below.

**Never write to Anki before the user approves in chat.** Steps 1–6 only read Anki and write local
files; only step 7 onwards writes, and only what was approved.

## Working directory and records

Use `WORK = <root>/<YYYY-MM-DD>/`, where `<root>` is the overlay's path or else `./anki-redesign/`.
Files, all JSON, written with the Write tool and validated by re-reading:

| File | Holds |
|---|---|
| `notes.json` | the gathered notes: `nid`, `model`, `tags`, `fields`, `card_ids`, `lapses`, `flag` |
| `chunk{i}.json` → `class{i}.json` | triage input and output (format in `rubric.md`) |
| `verdicts.json` | the user's triage verdicts: `{nid: {"verdict", "comment"}}` |
| `rd{i}.json` → `prop{i}.json` | redesign input and output (format in `redesign_brief.md`) |
| `decisions.json` | approval per note and per piece: approve, reject (with comment), edit, exclude |
| `applied.json` | what was written, with the **original fields** of every in-place edit, for undo |
| `<root>/ledger.jsonl` | one line per note ever triaged (`nid`, date, verdict), so later sessions skip it |
| judgements log | one line per user verdict (below); the overlay names its path, else `<root>/judgements.jsonl` |

Judgements log record (append-only; never rewrite earlier lines):
`{"date", "stage": "triage"|"redesign"|"rework", "nid", "cycle", "claude": {verdict or proposal},
"user": {"verdict": "bad"|"ok"|"approve"|"reject"|"edit"|"exclude", "comment"}, "issues": [codes]}`

## Steps

1. **Gather.** Build the set with `search_notes(query, limit=100, return_card_content=true)`, paging
   with narrower queries if needed:
   - due today: `is:due -is:suspended`
   - red flags (always included, due or not): `flag:1`
   - leeches or struggling cards: `tag:leech`, or `find_struggling_cards`
   - specific notes: `nid:123,456`

   Exclude notes tagged `redesigned::*`, notes already in `ledger.jsonl`, and Image Occlusion notes
   (their fields collapse to a placeholder). Add `lapses`, `card_ids` and the flag with
   `inspect_cards(note_ids=[…], properties=["identity", "scheduling", "state"])`. Images appear as
   `[image: filename]`; `retrieve_media_file` shows one. Write `notes.json` and tell the user the
   count before going on.
2. **Chunk** into files of about 35 notes.
3. **Triage in parallel.** Launch one subagent per chunk in a single message (a fast model is
   enough). Prompt: "Load the card-judgement skill and follow `${CLAUDE_SKILL_DIR}/rubric.md`.
   Classify `WORK/chunk{i}.json` and write `WORK/class{i}.json`." Merge and check that every nid
   has exactly one row. Red-flagged notes count as the user's own "bad" verdict.
4. **Verdicts, on the review page or in chat.** Show only the notes judged bad, in batches of
   about ten. **Review page** (preferred where the app displays it): call
   `open_card_review(note_ids, context)` with, per note, `"<issue codes>: <reason>. Approve =
   redesign it; Reject = leave it as it is."` The user's submit posts a message listing each
   decision and comment; read approve as "bad", reject as "ok", skip as undecided, and a comment of
   "suspend" or "delete" as that action. If the tool returns plain JSON instead of a page, the app
   cannot display it: say so once and use chat. **Chat:** number, the cleaned card text, the issue
   codes and the one-line reason, with replies such as
   `1 ok · 2 bad · 3 suspend · 4 bad: also cut the dose`. A bare "go" accepts the batch as judged.
   Write `verdicts.json`, append every note to `ledger.jsonl`, and append each verdict to the
   judgements log. If the user says "you decide", record `"user": {"verdict": "delegated"}` so the
   log never passes off Claude's verdicts as the user's.
5. **Redesign in parallel.** "suspend" and "delete" comments are actions, not redesigns: queue them
   for step 7. Chunk the remaining bad notes with their triage reason and the user's comment, then
   launch one subagent per chunk: "Load card-judgement and follow `${CLAUDE_SKILL_DIR}/
   redesign_brief.md`. Redesign `WORK/rd{i}.json` and write `WORK/prop{i}.json`." Merge, then check
   every proposal yourself: field names match the model (from `list_decks_and_notes`), the in-place
   piece's model equals the original's, no image was lost without a reason, and no cloze number is
   dropped on an in-place edit. Re-run the pre-flight checklist on anything that looks borderline.
6. **Approval, on the review page or in chat.** For each note show the original, then every
   proposed piece labelled `2a`, `2b`… with its cloze hidden-side view when it is a cloze.
   **Review page:** `open_card_review(note_ids, context)` shows the original card; put the
   proposed pieces in its `context` as plain text (`2a [Cloze] …`, `2b [Basic] Front … / Back …`).
   Approve = apply the whole proposal, reject = rework it (the comment says why), skip = leave for
   later. A comment such as "exclude 2b" or "edit 2a: <text>" applies to that piece. **Chat:**
   replies such as `2 ok · 3 reject: hint gives it away · 4b exclude · 5a edit: <text>`. Write
   `decisions.json` and append each decision to the judgements log.
7. **Apply, approved items only.** Record each original's fields in `applied.json` first.
   - In-place piece: `update_note_fields(note_id, fields)`, keeping the note's history.
   - New pieces: `add_notes([…])`, tagged with the original's tags plus `redesigned::<date>`; store
     any approved, newly found images first with `store_media_file`.
   - Replaced originals (no in-place piece): `set_suspended(card_ids, true)` and
     `update_note_tags(add=["redesigned::replaced"])`.
   - In-place originals: `update_note_tags(add=["redesigned::<date>"])`.
   - Queued actions: `set_suspended`, or `delete_notes(confirm=true)` only for notes the user said
     to delete in this session.
   - Clear handled red flags with `set_card_flag(card_ids, "none")`.
8. **Scheduling transfer.** New cards would otherwise start from scratch. Get their card IDs
   with `inspect_cards(note_ids=[new nids])`, show a dry-run table (original → new cards, interval,
   ease), and after the user agrees, call `copy_scheduling(target_card_ids, source_note_id=original)`.
   Skip notes whose issues include OUTDATED or TYPO: corrected facts are relearned from new. Redo
   any "mismatch" rows; log results in `applied.json`.
9. **Rework rejections.** Archive each rejected proposal in `decisions.json` under
   `rejected_v<cycle>`, then send the rejected notes to one subagent with `redesign_brief.md` in
   rework mode (the rejected proposal, the user's comment and earlier rejections). Repeat steps 6–9
   until nothing is rejected.
10. **Distil.** Always the final step. Read this session's lines in the judgements log, and look for
    repeated rejection reasons, overrides of "bad" flags, edits and excluded pieces. Propose changes
    to the user's personal judgement skill (or, if there is none, offer to start one), as a diff for
    approval. Never change rules silently.

## Gotchas

- **Writes can fail silently.** `set_card_flag` and `copy_scheduling` re-read cards and report each
  as set, copied, unchanged or mismatch; read those reports rather than assuming success.
- **Filtered decks.** A card sitting in a filtered deck reports that deck; new notes go to the home
  deck (ask, or use the overlay's default).
- **Orphan clozes.** An in-place cloze edit that drops a number leaves an empty card. Keep the
  numbering, or make the piece a new note instead.
- **Undo** an in-place edit with `update_note_fields` and the original in `applied.json`.
- **Guideline sites.** Some (nice.org.uk, for one) block automated fetches; fall back to mirrors or
  formularies and name the source used.
