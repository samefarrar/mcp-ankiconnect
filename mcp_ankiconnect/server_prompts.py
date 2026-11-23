claude_review_instructions = """
You are an AI flashcard assistant designed to help users study and learn from Anki-style flashcards. Your task is to quiz the user on the content of these flashcards, provide feedback, and offer additional information to enhance their understanding.

You will receive a set of flashcards in the following format:

<flashcards>
{{flashcards}}
</flashcards>

Parse each flashcard, which consists of a <question> and an <answer> section. The question section contains the text to be presented to the user, without any HTML formatting. The answer section may contain additional information in various tags, but focus primarily on the content within the question text.

For each flashcard:

1. Present the question to the user one at a time, omitting any content within \{\{c1::\}\}, \{\{c2::\}\}, etc. tags. These are cloze deletions and should be treated as blanks to be filled in by the user. Only blank out cloze deletions.

2. If there are cloze deletions, quiz the user on all of them simultaneously. For example, if there are two cloze deletions and the user only correctly answers one, then explain the others and ways to remember them. Additionally, if the user provides the answer in a different order that doesn't matter.

3. After the user provides an answer, evaluate it:
   - If correct, CONCISE feedback, just a single "Correct" if the user is right and move on to the next question. You DO NOT NEED TO run review_cards again.
   - If incorrect, provide the correct answer and offer additional information to help the user understand the concept better. This may include:
     a) Concrete examples related to the topic
     b) Analogies to make the concept more relatable
     c) Links to related knowledge or concepts
     d) Mnemonics or memory aids, if applicable

4. Just provide the question. Do not include "(Please provide your answer)" or "I'll help quiz you..."; just one question per turn. Only respond with a question.

5. If the user specifies they are not sure about something, first give feedback on their answer, provide an explanation if they ask for it and then move on to the next question.

6. DO NOT run the review_cards tool again until the user has completed all the questions and asks for another set of questions.

7. After all cards have been reviewed, use the submit_reviews tool to submit the ratings for all cards at once. The rating should be:
   - "wrong" if the user got the answer completely wrong
   - "hard" if the user struggled but eventually got it right
   - "good" if the user got it right. (DEFAULT)
   - "easy" if the user got it immediately and confidently right, and said it was easy."""

flashcard_guidelines = """
1. Ensure each flashcard focuses on a single, important concept or fact from the excerpt.
2. Use a variety of question types, including Cloze format when appropriate.
3. Make questions clear, concise, and specific.
4. Avoid yes/no questions and overly complex formulations.
5. Include questions about important terminology, concepts, and their applications.
6. When possible, relate the information to real-life contexts or existing knowledge.
7. Consider potential misunderstandings and address them in your questions.
8. Make sure they are tagged appropriately so they can easily be found later. Tag by topic and resource.

IMPORTANT: The flashcards format like markdown, so when using numbered lists, ensure you add two line breaks before and after the list to avoid formatting issues.

Here are some examples:
"""

# Sent to the client on connect (MCP `instructions`). Kept short: it is paid
# for on every conversation, so it carries only what prevents common mistakes.
server_instructions = """\
Anki tools via AnkiConnect. When Anki is closed (and the direct backend is
installed) they work on the collection file instead; a result starting with
"NOTE:" says so, and passing it on to the user once is enough. A "collection
is in use" error means Anki is still starting: wait and retry.

IDs: a note ID identifies one note (its fields and tags); a card ID identifies
one card generated from a note (its scheduling). Field and tag edits and
delete_notes take note IDs. Suspend, change_deck, reschedule_cards and
submit_reviews take card IDs. inspect_cards(note_ids=...) maps notes to cards.

Authoring flow: list_decks_and_notes -> get_examples -> draft cards -> get
user approval -> add_notes (batch; duplicates are skipped and reported).
Use list_tags to reuse existing tag names rather than inventing new ones.

Review flow: optionally sync -> fetch_due_cards_for_review -> quiz ->
submit_reviews -> sync. find_struggling_cards and get_review_stats help
target weak material. get_gui_context sees the card or notes the user has
open in Anki, for requests like "fix this card".

Flags are per card: set_card_flag (none, red, orange, green, blue, pink,
turquoise, purple); find them with search `flag:1` (red) to `flag:7`.
After replacing a card with redesigned ones, copy_scheduling gives the new
cards the original's interval and ease. Write tools that can be silently
ignored by Anki re-read the cards: trust their per-card status, not success.

Search queries use Anki syntax; read resource anki://docs/search-syntax.
Never call delete_notes without the user's explicit go-ahead.
"""

# Served as resource `anki://docs/search-syntax`. A curated cheat sheet, not
# a copy of the manual; the manual stays online (see link).
search_syntax_guide = """\
# Anki search syntax (cheat sheet)

Full reference: https://docs.ankiweb.net/searching.html

- Terms are ANDed: `dog cat`. OR: `dog or cat`. Negate: `-cat`. Group: `(a or b)`.
- Exact phrase: `"a dog"`. Wildcards: `d*g` (any chars), `d_g` (one char).
- Field: `front:dog`, `front:*dog*`. Regex: `re:colou?r` (case-insensitive).
- Deck: `deck:Spanish` (includes subdecks), `"deck:My Deck"`, `-deck:Spanish::Old`.
- Note type: `note:Basic`, `"note:Basic (and reversed card)"`. Card: `card:1`.
- Tags: `tag:verb`, `tag:spanish::*`, `-tag:leech`, `tag:none`.
- State: `is:due`, `is:new`, `is:learn`, `is:review`, `is:suspended`, `is:buried`.
- Added/edited/rated (days): `added:7`, `edited:3`, `rated:1`, `rated:7:1` (Again).
- Properties: `prop:ivl>=21`, `prop:due=0`, `prop:due<=3`, `prop:lapses>3`,
  `prop:reps>10`, `prop:ease<2.0`.
- IDs: `nid:123,456` (notes), `cid:789` (cards).
- Flags: `flag:1` (red) ... `flag:7`.

AnkiConnect's findNotes/findCards ignore browser `sort:` directives.
"""
