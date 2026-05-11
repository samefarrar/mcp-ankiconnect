from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mcp_ankiconnect.ankiconnect_client import (
    AnkiConnectClient,
)


@pytest.fixture
def mock_anki_client():
    mock = MagicMock(spec=AnkiConnectClient)
    mock.find_cards = AsyncMock()
    mock.cards_info = AsyncMock()
    mock.are_suspended = AsyncMock()
    mock.get_reviews_of_cards = AsyncMock()
    mock.update_note_fields = AsyncMock()
    mock.add_tags = AsyncMock()
    mock.remove_tags = AsyncMock()
    mock.suspend = AsyncMock()
    mock.unsuspend = AsyncMock()
    mock.change_deck = AsyncMock()
    mock.set_due_date = AsyncMock()
    mock.forget_cards = AsyncMock()
    mock.relearn_cards = AsyncMock()
    mock.close = AsyncMock()
    return mock


@pytest.fixture(autouse=True)
def patch_get_anki_client(mock_anki_client):
    with patch("mcp_ankiconnect.edit_tools.get_anki_client") as cm:
        cm.return_value.__aenter__.return_value = mock_anki_client
        cm.return_value.__aexit__ = AsyncMock(return_value=None)
        yield cm


def test_module_imports_and_registers_tools():
    """edit_tools must import cleanly and contribute its tools to the shared FastMCP instance."""
    import mcp_ankiconnect.edit_tools  # noqa: F401
    from mcp_ankiconnect.edit_tools import (
        change_deck,
        inspect_cards,
        reschedule_cards,
        set_suspended,
        update_note_fields,
        update_note_tags,
    )

    assert all(
        callable(t)
        for t in (
            inspect_cards,
            update_note_fields,
            update_note_tags,
            set_suspended,
            change_deck,
            reschedule_cards,
        )
    )
