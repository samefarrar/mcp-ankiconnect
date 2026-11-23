"""Pin the card-quality guidance that reaches plain (non-plugin) MCP users.

Plugin installs get the full `card-judgement` skill; a user who adds the
server to a client config gets only `flashcard_guidelines` (returned by
`get_examples`) and `server_instructions` (sent on connect). These tests keep
the core rules in both and stop them drifting back to generic advice.
"""

from mcp_ankiconnect.server_prompts import flashcard_guidelines, server_instructions


def test_guidelines_carry_the_core_card_judgement_rules():
    text = flashcard_guidelines.lower()
    for rule in (
        "hidden side",  # read each cloze from the hidden side
        "answer type",  # hints name the type only
        "elimination",
        "extra",  # Extra is not storage
        "one question",
        "verify",
    ):
        assert rule in text, rule


def test_guidelines_no_longer_invite_vignettes():
    # The old line pushed scenario framing, which real verdicts reject.
    assert "real-life contexts" not in flashcard_guidelines


def test_guidelines_do_not_duplicate_the_examples_heading():
    # get_examples appends its own "Here are some examples…" line.
    assert "here are some examples" not in flashcard_guidelines.lower()


def test_guidelines_stay_short():
    # Returned on every get_examples call; the skills hold the detail.
    assert len(flashcard_guidelines.split()) < 320


def test_connect_instructions_ask_for_the_hidden_side_check():
    assert "hidden side" in server_instructions.lower()
