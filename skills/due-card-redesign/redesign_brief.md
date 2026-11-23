# Redesign brief

**First load the `card-judgement` skill** (and any personal judgement skill), and read `examples.md`
for any rule you are unsure of. Its hard rules and pre-flight checklist override this brief. Follow
`card-writing` for note types and cloze mechanics. This brief covers only the task format and style
defaults.

Each input note has `nid`, `model`, `fields` (cleaned; images appear as `[image: filename]`), `tags`,
`classification` (issues and reason from triage), `user_comment` (the user's own instruction: obey it,
it overrides everything) and `lapses`. In rework mode it also has `rejected_proposal`,
`user_rejection_comment` and `earlier_rejections`: fix what was named, then re-run the whole
checklist, because one named clue usually means there are others.

## Style defaults

- Minimum information: one fact per card, answerable in under ten seconds. Splitting a bloated card
  into several lean notes is encouraged.
- Cloze for facts, with key terms in bold, and every hint stating the answer type only. Basic for
  reasoning ("why/how") and for "name the N…" sets; the Front demands exactly what the Back holds.
- A short topic prefix where it disambiguates (`<b>Bronchiolitis</b>: …`), as long as it doesn't
  summarise the answer.
- MCQ, true/false or letter cards become a recall card on the fact the question tested. If the
  question is an image, view it with `retrieve_media_file` first.
- **Keep every image the original had**, as `<img src="filename">`, in the Extra of the piece it
  illustrates or on the Front if it is the question. If one truly has to go (an MCQ screenshot now
  transcribed, an exact duplicate), list it in `"dropped_images"` with the reason in `rationale`.
- Visual diagnoses: an image-front card plus a description card, each holding the other in Extra.
  For an image found online, give its URL in `"new_images": [{"filename", "url", "licence"}]` and cite
  it in Source; the main session stores it only after approval.
- Extra: optional context only, often empty, two sentences at most.
- Spell out acronyms on first use. Follow current guidance for the user's locale (the overlay may name
  sources).
- **Verify specifics.** For OUTDATED or TYPO flags and any number, dose, threshold, timing or
  first-line choice you assert, check with a web search and name the source in Source. If you cannot
  verify it, say so in `rationale` and keep the claim conservative.
- Simple HTML only: `<b> <i> <br> <ul><li> <sup> <sub>`.

## Note types

Use the models and exact field names the main session gives you (from `list_decks_and_notes`), with
every field present (`""` to blank one). Deck: the overlay's default, else the deck you are given.
Tags: the original note's tags.

In-place: if one piece uses the same model as the original, set `in_place_index` to it; this keeps
the review history. For a cloze, keep its numbering from c1 with no gaps or dropped numbers, otherwise
make it a new note. If no piece fits, use `null`: every piece becomes a new note and the original is
suspended.

## Output

A JSON object keyed by nid (as a string), written to the file you are given:

```json
{"<nid>": {"action": "redesign", "in_place_index": 0,
           "new_notes": [{"model": "...", "deck": "...", "fields": {}, "tags": []}],
           "dropped_images": [], "new_images": [],
           "rationale": "1–2 sentences: what was wrong, what you did, what you verified where."}}
```

Every input nid must appear. Before writing, run the pre-flight checklist on every piece, and for each
cloze write down what is visible while it is hidden. Then re-read the file and check the count and the
field names.
