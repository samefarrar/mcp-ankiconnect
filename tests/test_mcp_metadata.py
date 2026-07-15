from mcp.types import ToolAnnotations

from mcp_ankiconnect import mcp
from mcp_ankiconnect.tool_metadata import ADDITIVE_WRITE, SERVER_INSTRUCTIONS


EXPECTED_ANNOTATIONS = {
    "num_cards_due_today": ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
    "list_decks_and_notes": ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
    "get_examples": ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
    "fetch_due_cards_for_review": ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
    "submit_reviews": ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=True,
        idempotentHint=False,
        openWorldHint=False,
    ),
    "add_note": ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=True,
        idempotentHint=False,
        openWorldHint=True,
    ),
    "store_media_file": ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=True,
        idempotentHint=False,
        openWorldHint=True,
    ),
    "search_notes": ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
    "inspect_cards": ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
    "update_note_fields": ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=True,
        idempotentHint=False,
        openWorldHint=False,
    ),
    "update_note_tags": ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=True,
        idempotentHint=True,
        openWorldHint=False,
    ),
    "set_suspended": ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=True,
        idempotentHint=True,
        openWorldHint=False,
    ),
    "change_deck": ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=True,
        idempotentHint=False,
        openWorldHint=False,
    ),
    "reschedule_cards": ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=True,
        idempotentHint=False,
        openWorldHint=False,
    ),
}


async def test_every_exposed_tool_has_explicit_annotations():
    tools = {tool.name: tool for tool in await mcp.list_tools()}

    assert tools.keys() == EXPECTED_ANNOTATIONS.keys()
    for name, expected in EXPECTED_ANNOTATIONS.items():
        assert tools[name].annotations == expected
        assert all(
            getattr(tools[name].annotations, hint) is not None
            for hint in (
                "readOnlyHint",
                "destructiveHint",
                "idempotentHint",
                "openWorldHint",
            )
        )


def test_unused_additive_profile_remains_explicit():
    assert ADDITIVE_WRITE == ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=False,
        openWorldHint=False,
    )


def test_server_instructions_are_exposed_during_initialization():
    options = mcp._mcp_server.create_initialization_options()

    assert options.instructions == SERVER_INSTRUCTIONS
    first_512_characters = SERVER_INSTRUCTIONS[:512]
    for phrase in (
        "target deck",
        "note type",
        "required fields",
        "search_notes",
        "add_note",
    ):
        assert phrase in first_512_characters
    assert "fetch_due_cards_for_review" in SERVER_INSTRUCTIONS
    assert "submit_reviews" in SERVER_INSTRUCTIONS
    assert "inspect_cards(note_ids=...)" in SERVER_INSTRUCTIONS
    assert "successes and failures" in SERVER_INSTRUCTIONS
