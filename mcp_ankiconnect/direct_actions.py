"""AnkiConnect actions emulated on an open `anki` Collection.

Only the actions this server uses are implemented, each returning exactly
what AnkiConnect v6 returns (so `AnkiConnectClient`'s typed methods and the
tools need no direct-mode branches). Writes go through Anki's own APIs
(scheduler, `update_card`, `set_deck`, tag and media managers), never raw
SQL, so undo entries, modification times and FSRS state stay consistent.
Raw SQL is used only for reads (review log, duplicate check), as AnkiConnect
does.

Behaviour that differs from AnkiConnect on purpose:
- `sync` does nothing: the direct backend never contacts AnkiWeb.
- `guiCurrentCard` / `guiSelectedNotes` report "nothing open".
- `forgetCards` uses Anki's "reset to new" instead of AnkiConnect's raw SQL.
- `setSpecificValueOfCard` only writes `flags`, `ivl` and `factor`.
"""

from __future__ import annotations

import base64
import hashlib
import os
import unicodedata
from collections.abc import Callable, Iterable
from typing import Any, Literal, cast

import httpx
from anki.card_rendering_pb2 import StripHtmlRequest
from anki.cards import Card, CardId
from anki.collection import Collection
from anki.consts import CARD_TYPE_RELEARNING, QUEUE_TYPE_LRN
from anki.dbproxy import DBProxy
from anki.decks import DeckId
from anki.errors import NotFoundError
from anki.notes import Note, NoteFieldsCheckResult, NoteId

from mcp_ankiconnect.ankiconnect_client import DirectBackendError

# Imported only on the direct path (see direct_client), so plain installs
# without the `direct` extra never load the `anki` package.

Handler = Callable[..., Any]
_HANDLERS: dict[str, Handler] = {}

# AnkiConnect refuses these setSpecificValueOfCard keys without warning_check.
_WARNING_KEYS = frozenset(
    [
        "did",
        "id",
        "ivl",
        "lapses",
        "left",
        "mod",
        "nid",
        "odid",
        "odue",
        "ord",
        "queue",
        "reps",
        "type",
        "usn",
    ]
)
_CARD_VALUE_KEYS = frozenset({"flags", "ivl", "factor"})
_REVIEW_COLUMNS = ("id", "usn", "ease", "ivl", "lastIvl", "factor", "time", "type")
_MEDIA_TAGS = {
    "picture": '<img src="{}">',
    "audio": "[sound:{}]",
    "video": "[sound:{}]",
}


def run_action(col: Collection, action: str, params: dict[str, Any]) -> Any:
    """Dispatch one AnkiConnect action (or a `multi` batch) to its handler."""
    if action == "multi":
        return [_run_one(col, a) for a in params.get("actions", [])]
    handler = _HANDLERS.get(action)
    if handler is None:
        raise ValueError(f"{action} is not available while Anki is closed")
    return handler(col, **params)


def _run_one(col: Collection, request: dict[str, Any]) -> dict[str, Any]:
    """One `multi` entry: AnkiConnect reports each call's error separately."""
    try:
        result = run_action(col, request["action"], request.get("params", {}))
    except DirectBackendError:
        raise
    except Exception as e:  # noqa: BLE001 - AnkiConnect reports any failure
        return {"result": None, "error": str(e)}
    return {"result": result, "error": None}


def _action(name: str) -> Callable[[Handler], Handler]:
    def register(func: Handler) -> Handler:
        _HANDLERS[name] = func
        return func

    return register


# --- Lookup helpers ---
# AnkiConnect passes plain ints; Anki's API types them as NewTypes.


def _cids(ids: Iterable[int]) -> list[CardId]:
    return [CardId(int(i)) for i in ids]


def _nids(ids: Iterable[int]) -> list[NoteId]:
    return [NoteId(int(i)) for i in ids]


def _db(col: Collection) -> DBProxy:
    if col.db is None:
        raise ValueError("the collection is not open")
    return col.db


def _deck_id(col: Collection, name: str) -> DeckId:
    """ID of the named deck, creating it as AnkiConnect does."""
    did = col.decks.id(name)
    if did is None:
        raise ValueError(f"could not create deck: {name}")
    return did


def _model_name(note: Note) -> str:
    model = note.note_type()
    return model["name"] if model is not None else ""


def _card_or_none(col: Collection, card_id: int) -> Card | None:
    try:
        return col.get_card(CardId(card_id))
    except NotFoundError:
        return None


def _note_or_none(col: Collection, note_id: int) -> Note | None:
    try:
        return col.get_note(NoteId(note_id))
    except NotFoundError:
        return None


def _fields(note: Note) -> dict[str, dict[str, Any]]:
    return {
        name: {"value": value, "order": i}
        for i, (name, value) in enumerate(note.items())
    }


# --- Decks, models, tags ---


@_action("deckNames")
def deck_names(col: Collection) -> list[str]:
    return [d.name for d in col.decks.all_names_and_ids()]


@_action("createDeck")
def create_deck(col: Collection, deck: str) -> int:
    return int(_deck_id(col, deck))


@_action("modelNames")
def model_names(col: Collection) -> list[str]:
    return [m.name for m in col.models.all_names_and_ids()]


@_action("modelFieldNames")
def model_field_names(col: Collection, modelName: str) -> list[str]:
    model = col.models.by_name(modelName)
    if model is None:
        raise ValueError(f"model was not found: {modelName}")
    return col.models.field_names(model)


@_action("getTags")
def get_tags(col: Collection) -> list[str]:
    return col.tags.all()


@_action("addTags")
def add_tags(col: Collection, notes: list[int], tags: str) -> None:
    col.tags.bulk_add(_nids(notes), tags)


@_action("removeTags")
def remove_tags(col: Collection, notes: list[int], tags: str) -> None:
    col.tags.bulk_remove(_nids(notes), tags)


# --- Searching and reading ---


@_action("findNotes")
def find_notes(col: Collection, query: str = "") -> list[int]:
    return [int(n) for n in col.find_notes(query)]


@_action("findCards")
def find_cards(col: Collection, query: str = "") -> list[int]:
    return [int(c) for c in col.find_cards(query)]


@_action("notesInfo")
def notes_info(col: Collection, notes: list[int]) -> list[dict[str, Any]]:
    return [_note_info(_note_or_none(col, nid)) for nid in notes]


def _note_info(note: Note | None) -> dict[str, Any]:
    if note is None:
        return {}
    return {
        "noteId": int(note.id),
        "modelName": _model_name(note),
        "tags": list(note.tags),
        "fields": _fields(note),
        "mod": note.mod,
        "cards": [int(c) for c in note.card_ids()],
    }


@_action("cardsInfo")
def cards_info(col: Collection, cards: list[int]) -> list[dict[str, Any]]:
    return [_card_info(col, _card_or_none(col, cid)) for cid in cards]


def _card_info(col: Collection, card: Card | None) -> dict[str, Any]:
    if card is None:
        return {}
    note = card.note()
    model = note.note_type() or {"name": "", "css": ""}
    return {
        "cardId": int(card.id),
        "fields": _fields(note),
        "fieldOrder": card.ord,
        "question": card.question(),
        "answer": card.answer(),
        "modelName": model["name"],
        "ord": card.ord,
        "deckName": col.decks.name(card.did),
        "css": model["css"],
        "factor": card.factor,
        "interval": card.ivl,
        "note": int(card.nid),
        "type": card.type,
        "queue": card.queue,
        "due": card.due,
        "reps": card.reps,
        "lapses": card.lapses,
        "left": card.left,
        "mod": card.mod,
        "flags": card.flags,
    }


@_action("areSuspended")
def are_suspended(col: Collection, cards: list[int]) -> list[bool | None]:
    found = [_card_or_none(col, cid) for cid in cards]
    return [None if c is None else c.queue == -1 for c in found]


@_action("getReviewsOfCards")
def get_reviews_of_cards(col: Collection, cards: list[int]) -> dict[str, list[dict]]:
    """Review log per card. Keys are strings, as AnkiConnect's JSON has them."""
    query = f"select {', '.join(_REVIEW_COLUMNS)} from revlog where cid = ?"
    return {
        str(cid): [
            dict(zip(_REVIEW_COLUMNS, row, strict=True))
            for row in _db(col).all(query, cid)
        ]
        for cid in cards
    }


@_action("getNumCardsReviewedByDay")
def get_num_cards_reviewed_by_day(col: Collection) -> list[list]:
    """[[day, count]] newest first, days split at Anki's rollover hour.

    Same query as AnkiConnect, so both backends bucket days identically.
    """
    import time

    cutoff_hour = int(time.strftime("%H", time.localtime(col.sched.day_cutoff)))
    rows = _db(col).all(
        "select date(id/1000 - ?, 'unixepoch', 'localtime') as day, count() "
        "from revlog group by day order by day desc",
        cutoff_hour * 3600,
    )
    return [list(r) for r in rows]


# --- Adding and editing notes ---


@_action("addNote")
def add_note(col: Collection, note: dict[str, Any]) -> int:
    """AnkiConnect's addNote: validate, attach media, check duplicates, add."""
    model = col.models.by_name(note.get("modelName", ""))
    if model is None:
        raise ValueError(f"model was not found: {note.get('modelName')}")
    deck = col.decks.by_name(note.get("deckName", ""))
    if deck is None:
        raise ValueError(f"deck was not found: {note.get('deckName')}")
    anki_note = col.new_note(model)
    anki_note.tags = list(note.get("tags") or [])
    _assign_fields(anki_note, note.get("fields", {}))
    _attach_media(col, anki_note, note)
    _check_addable(col, anki_note, deck["id"], note.get("options") or {})
    col.add_note(anki_note, deck["id"])
    return int(anki_note.id)


def _assign_fields(note: Note, fields: dict[str, str]) -> None:
    """Set fields matching names case-insensitively, as AnkiConnect does."""
    names = note.keys()  # a Note is not a dict: iterating it yields no names
    by_lower = {k.lower(): k for k in names}
    for name, value in fields.items():
        key = by_lower.get(name.lower())
        if key is not None:
            note[key] = value


def _attach_media(col: Collection, note: Note, spec: dict[str, Any]) -> None:
    """Store `picture`/`audio`/`video` entries and append their tags to fields."""
    for kind, template in _MEDIA_TAGS.items():
        for media in spec.get(kind) or []:
            stored = store_media_file(
                col,
                filename=media["filename"],
                data=media.get("data"),
                path=media.get("path"),
                url=media.get("url"),
                skipHash=media.get("skipHash"),
            )
            if not stored:
                continue
            for field in media.get("fields") or []:
                if field in note:
                    note[field] += template.format(stored)


def _check_addable(
    col: Collection, note: Note, deck_id: int, options: dict[str, Any]
) -> None:
    state = note.fields_check()
    if state == NoteFieldsCheckResult.EMPTY:
        raise ValueError("cannot create note because it is empty")
    if options.get("duplicateScope") == "deck":
        duplicate = _duplicate_in_deck(col, note, deck_id)
    else:
        duplicate = state == NoteFieldsCheckResult.DUPLICATE
    if duplicate and not options.get("allowDuplicate", False):
        raise ValueError("cannot create note because it is a duplicate")


def _duplicate_in_deck(col: Collection, note: Note, deck_id: int) -> bool:
    """AnkiConnect's deck-scoped check: same note type and first field, same deck."""
    csum = _field_checksum(col, note.fields[0])
    for nid in _db(col).list(
        "select id from notes where csum = ? and mid = ?", csum, note.mid
    ):
        if deck_id in _db(col).list("select did from cards where nid = ?", nid):
            return True
    return False


def _field_checksum(col: Collection, text: str) -> int:
    """Anki's `notes.csum`: first 8 hex digits of the SHA-1 of the stripped field.

    Why not `anki.utils.field_checksum`: it needs a process-global backend
    that only the desktop app sets up, so the collection's own backend
    strips the HTML here.
    """
    stripped = col._backend.strip_html(
        text=text, mode=StripHtmlRequest.PRESERVE_MEDIA_FILENAMES
    )
    return int(hashlib.sha1(stripped.encode("utf-8")).hexdigest()[:8], 16)


@_action("updateNoteFields")
def update_note_fields(col: Collection, note: dict[str, Any]) -> None:
    anki_note = _note_or_none(col, note["id"])
    if anki_note is None:
        raise ValueError(f"note was not found: {note['id']}")
    for name, value in note.get("fields", {}).items():
        if name in anki_note:
            anki_note[name] = value
    col.update_note(anki_note)


@_action("deleteNotes")
def delete_notes(col: Collection, notes: list[int]) -> None:
    col.remove_notes(_nids(notes))


# --- Card state and scheduling ---


def _set_suspended(col: Collection, cards: list[int], suspend: bool) -> bool:
    """AnkiConnect's rule: False when no card needed changing."""
    to_change = []
    for cid in cards:
        card = _card_or_none(col, cid)
        if card is None:
            raise ValueError(f"card was not found: {cid}")
        if (card.queue == -1) != suspend:
            to_change.append(cid)
    if not to_change:
        return False
    if suspend:
        col.sched.suspend_cards(_cids(to_change))
    else:
        col.sched.unsuspend_cards(_cids(to_change))
    return True


@_action("suspend")
def suspend(col: Collection, cards: list[int]) -> bool:
    return _set_suspended(col, cards, True)


@_action("unsuspend")
def unsuspend(col: Collection, cards: list[int]) -> bool:
    return _set_suspended(col, cards, False)


@_action("changeDeck")
def change_deck(col: Collection, cards: list[int], deck: str) -> None:
    col.set_deck(_cids(cards), _deck_id(col, deck))


@_action("setDueDate")
def set_due_date(col: Collection, cards: list[int], days: str) -> bool:
    col.sched.set_due_date(_cids(cards), days)
    return True


@_action("forgetCards")
def forget_cards(col: Collection, cards: list[int]) -> None:
    col.sched.schedule_cards_as_new(
        _cids(cards), restore_position=True, reset_counts=False
    )


@_action("relearnCards")
def relearn_cards(col: Collection, cards: list[int]) -> None:
    """Put cards in relearning (type 3, learn queue), as AnkiConnect does."""
    found = [c for c in (_card_or_none(col, cid) for cid in cards) if c is not None]
    for card in found:
        card.type, card.queue = CARD_TYPE_RELEARNING, QUEUE_TYPE_LRN
    if found:
        col.update_cards(found)


@_action("answerCards")
def answer_cards(col: Collection, answers: list[dict[str, int]]) -> list[bool]:
    """Answer through Anki's v3 scheduler, exactly as AnkiConnect does.

    `answerCard` asks the backend for the card's scheduling states and
    applies the chosen one, so FSRS and learning steps behave as in Anki.
    The timer starts just before answering, so time taken is ~0 ms, the same
    as AnkiConnect records. Missing cards give False.
    """
    results = []
    for answer in answers:
        card = _card_or_none(col, answer["cardId"])
        if card is None:
            results.append(False)
            continue
        card.start_timer()
        ease = cast(Literal[1, 2, 3, 4], int(answer["ease"]))
        col.sched.answerCard(card, ease)
        results.append(True)
    return results


@_action("setSpecificValueOfCard")
def set_specific_value_of_card(
    col: Collection,
    card: int,
    keys: list[str],
    newValues: list[Any],
    warning_check: bool = False,
) -> bool | list:
    """AnkiConnect's reply shape: False, [True] or [[False, reason]]."""
    if not isinstance(keys, list) or len(keys) != len(newValues):
        return False
    if not warning_check and any(k in _WARNING_KEYS for k in keys):
        return False
    unsupported = [k for k in keys if k not in _CARD_VALUE_KEYS]
    if unsupported:
        return [[False, f"{unsupported} not supported while Anki is closed"]]
    anki_card = _card_or_none(col, card)
    if anki_card is None:
        return [[False, f"card was not found: {card}"]]
    _write_card_values(col, anki_card, dict(zip(keys, newValues, strict=True)))
    return [True]


def _write_card_values(col: Collection, card: Card, values: dict[str, Any]) -> None:
    """Flags via Anki's flag API; interval and ease via `update_card`."""
    if "flags" in values:
        col.set_user_flag_for_cards(int(values.pop("flags")), [card.id])
        card.load()
    if values:
        for key, value in values.items():
            setattr(card, key, int(value))
        col.update_card(card)


# --- Media ---


@_action("storeMediaFile")
def store_media_file(
    col: Collection,
    filename: str,
    data: str | None = None,
    path: str | None = None,
    url: str | None = None,
    skipHash: str | None = None,
    deleteExisting: bool = True,
) -> str | None:
    """Write into the collection's media folder; source priority data > path > url.

    Like AnkiConnect, a same-named file is replaced (moved to Anki's media
    trash first) rather than stored under a new name.
    """
    content = _media_bytes(data, path, url)
    if skipHash is not None and hashlib.md5(content).hexdigest() == skipHash:
        return None
    if deleteExisting and col.media.have(filename):
        col.media.trash_files([filename])
    return col.media.write_data(filename, content)


def _media_bytes(data: str | None, path: str | None, url: str | None) -> bytes:
    if data:
        return base64.b64decode(data)
    if path:
        with open(path, "rb") as f:
            return f.read()
    if url:
        response = httpx.get(url, follow_redirects=True, timeout=30)
        response.raise_for_status()
        return response.content
    raise ValueError('You must provide a "data", "path", or "url" field.')


@_action("retrieveMediaFile")
def retrieve_media_file(col: Collection, filename: str) -> str | bool:
    """Base64 content, or False when missing. Names are reduced to a basename."""
    name = unicodedata.normalize("NFC", os.path.basename(filename))
    full = os.path.join(col.media.dir(), name)
    if not name or not os.path.isfile(full):
        return False
    with open(full, "rb") as f:
        return base64.b64encode(f.read()).decode("ascii")


# --- Network and GUI: nothing to do while Anki is closed ---


@_action("sync")
def sync(col: Collection) -> None:
    """Never contact AnkiWeb from here; Anki syncs the changes when next opened."""


@_action("guiCurrentCard")
def gui_current_card(col: Collection) -> None:
    """No reviewer is open: AnkiConnect's "not reviewing" reply."""


@_action("guiSelectedNotes")
def gui_selected_notes(col: Collection) -> list[int]:
    return []
