---
name: card-writing
description: "Write, add, search and review Anki flashcards with the ankiconnect MCP tools. Use it whenever the user asks to make flashcards or Anki cards, add cards to Anki, turn notes or a session into cards ('make cards from this', 'add these to Anki'), search existing cards, check what is due, or do an Anki review. It covers note-type choice, cloze engineering, the approval workflow and the review cycle. Load card-judgement alongside it before showing any drafted card."
---

# Writing and reviewing Anki cards

This skill covers the mechanics: which tool to call, which note type to use, how to build a cloze,
and how to get approval before anything is written. The **card-judgement** skill covers the quality
bar every card must clear; load it too. Where a personal conventions skill is loaded (default deck,
note types, tagging scheme), its choices replace the defaults here.

The design philosophy follows SuperMemo's "20 rules of formulating knowledge": minimum information,
recall over recognition, and no card the learner does not need.

## 1. Tools

| Job | Tools |
|---|---|
| Discover decks, note types, field names | `list_decks_and_notes`, `list_tags` |
| Calibrate to the user's existing style | `get_examples` (`sample`: `recent`, `mature`, `best_performance`, …) |
| Check for duplicates | `search_notes` (Anki query syntax; resource `anki://docs/search-syntax`) |
| Add | `add_note` (one), `add_notes` (up to 100, per-note success or failure) |
| Media | `store_media_file` (prefer `path` for a local file, then `url`, then `data`), `retrieve_media_file` to view an image |
| Edit existing | `inspect_cards`, `update_note_fields`, `update_note_tags`, `set_suspended`, `change_deck` |
| Review | `num_cards_due_today`, `fetch_due_cards_for_review`, `submit_reviews` |
| "Fix this card" | `get_gui_context` (the card on screen, or the browser selection) |

Note IDs and card IDs differ: a note owns one or more cards. Field edits and tags act on notes;
suspension, flags, decks and scheduling act on cards. `inspect_cards(note_ids=[…])` maps one to the
other.

## 2. Note types

Call `list_decks_and_notes` before the first add of a session and use the exact model and field
names it returns. Without other instructions, use two shapes:

- **Basic** (Front, Back, and any source or explanation fields the model has). The Front must demand
  everything the Back contains.
- **Cloze** (Text, Extra, and any source field). `{{c1::answer::hint}}` deletions.

If the user has no preferred deck, ask once, then reuse it for the session.

## 3. Design principles

- **The 10-second rule.** Each card should be answerable in under ten seconds. More than about three
  discrete facts means split it.
- **One card, one concept.** A short list is fine only when the list *is* the concept.
- **The Front demands the Back.** If the Back has three parts, the Front says so ("Name the three…").
- **Spell out acronyms** unless the user is fluent with them; never make an acronym the sole answer.
- **Tags** use the `::` hierarchy for topic and source (`Neurology::Epilepsy`, `Source::Textbook`).
  Check `list_tags` first so new cards reuse existing names.

## 4. Cloze engineering

When `cN` is tested, every other cloze is visible. Most bad clozes fail because of that.

1. **Visible clozes must not give away the hidden one.** `MS affects {{c1::young women}}, sex ratio
   {{c2::3:1 female to male}}`: testing c1, the visible ratio gives the answer away. Merge them or
   restructure.
2. **Merge co-dependent facts under one number.** Items sharing a number are hidden and revealed
   together.
3. **Separate independent facts**, each with a hint so it can be answered in isolation.
4. **Every hint names the answer type** ("drug", "number", "timeframe"), never a semantic clue.
5. **Contrasting dichotomies stay together.** `Praevia = {{c1::painless}}; abruption = {{c2::painful}}`
   is broken: the visible side reveals the hidden one. Either put both sides under one number, or ask
   a Basic question about one side.
6. **Extra is overflow, not storage.** Second-line options and exceptions may go there; anything that
   must be known needs its own card.

### Basic or Cloze?

| Basic | Cloze |
|---|---|
| A short explanation or reasoning chain ("why", "how") | A specific fact, term or number in a sentence |
| A "name the N…" set | Two to four independent facts in one natural sentence |

When in doubt, prefer Basic: a well-written Front is more forgiving than a cloze.

## 5. Workflow

1. **Prepare.** Optionally `get_examples` to match the user's style; `search_notes` for duplicates.
2. **Draft** every card, grouped by topic and numbered (C1, C2, …).
3. **Pre-flight.** Run the card-judgement checklist on every card.
4. **Get approval.** Never add a card without the user's explicit approval. Expect cuts, merges and
   rewording; apply them and show the revised set when the changes are extensive.
5. **Add** with `add_notes` (or `add_note` for one), then report the count and any per-note failures
   (duplicates, a missing model, Anki not running).

## 6. Review workflow

1. `num_cards_due_today` for the count.
2. `fetch_due_cards_for_review` with a sensible `limit` (`today_only=false` to pull cards due soon).
3. Show the question, let the user answer, then reveal the answer.
4. Collect `{card_id, rating}` with ratings `wrong`, `hard`, `good` or `easy`, and send them in
   batches with `submit_reviews`. Ratings reschedule cards and cannot be undone here.

If a card is badly designed, say so; the **due-card-redesign** skill fixes cards in bulk.

## 7. Formatting

- Simple HTML only: `<b>`, `<i>`, `<br>`, `<ul><li>`, `<ol><li>`, `<sup>`, `<sub>`, `<code>`.
  `<math>…</math>` becomes MathJax.
- Images: `add_note`'s `picture` parameter (`filename`, one of `path`/`url`/`data`, and the
  `fields` that get the `<img>` tag), or `store_media_file` and then `<img src="filename">`.
- Keep Extra to two or three sentences.

## 8. Quality checklist

- [ ] Under ten seconds to answer?
- [ ] Does the Front make clear exactly what is expected, with nothing hidden in the Back?
- [ ] When cN is hidden, do the visible clozes or clauses give it away?
- [ ] Is the core content in Text or Back, not in Extra?
- [ ] Right note type, tags present, and no duplicates (`search_notes`)?
- [ ] **Specifics verified.** Every number, dose, threshold or first-line choice is checked
  against a current primary source with a web search. Recall from training is not enough; a wrong
  number carded is weeks of reinforcing the wrong answer.
- [ ] **Current terminology.** When a classification has been superseded, card the current one only.
