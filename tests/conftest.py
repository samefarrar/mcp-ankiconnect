"""Shared fixtures for direct-backend tests: real throwaway Anki collections.

These use the official `anki` package (the `direct` extra). Tests that need
it request `collection_path`, which skips cleanly when the extra is absent.
"""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def anki_collection():
    """The `anki.collection` module, or skip when the direct extra is absent."""
    return pytest.importorskip("anki.collection")


@pytest.fixture
def collection_path(tmp_path: Path, anki_collection) -> Path:
    """A fresh collection in a profile folder, with two Basic notes.

    The collection is closed again before the test runs, as it would be when
    Anki is not running.
    """
    path = tmp_path / "User 1" / "collection.anki2"
    path.parent.mkdir()
    col = anki_collection.Collection(str(path))
    try:
        basic = col.models.by_name("Basic")
        deck_id = col.decks.id("Spanish")
        for front, back in (("hola", "hello"), ("adiós", "goodbye")):
            note = col.new_note(basic)
            note["Front"], note["Back"] = front, back
            note.tags = ["spanish"]
            col.add_note(note, deck_id)
    finally:
        col.close()
    return path


@pytest.fixture
def open_col(anki_collection):
    """Open a collection for checking results; closes it after the test."""
    opened = []

    def _open(path: Path):
        col = anki_collection.Collection(str(path))
        opened.append(col)
        return col

    yield _open
    for col in opened:
        col.close()
