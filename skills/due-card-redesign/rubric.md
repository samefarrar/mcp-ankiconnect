# Triage rubric

Before classifying, load the **card-judgement** skill and read its *Triage calibration* section,
which records the flags learners override. If a personal judgement skill is loaded, its calibration
wins.

For each note, decide `"bad"` (worth redesigning) or `"ok"` (leave alone). Mark "bad" only when the
design genuinely harms recall: it takes more than ten seconds, it is ambiguous, it tests recognition
rather than recall, or it is wrong. A terse but clear card is ok. Lapses support a verdict but are
never the verdict on their own. Learners agree with about 95% of well-calibrated "bad" flags; when in
doubt about a short card, mark it "ok".

## Issue codes (use any that apply)

- OVERLOAD: more than about three discrete facts, or a long paragraph answer.
- SET / ENUM: an unordered set or long list recalled as one block (fine if it is one known concept).
- AMBIGUOUS: the front doesn't specify what the back should contain, or several answers are valid.
- HIDDEN_EXPECT: the back contains content the front never asks for.
- CLOZE_LEAK: visible text gives away a hidden cloze: other clozes, brackets, clauses, semantic hints,
  a dichotomy split across c1/c2, or a list solvable by elimination.
- NO_HINT: a hidden cloze with no hint where the expected answer type is unclear.
- RECOGNITION: an MCQ, true/false or option-letter answer.
- NO_CONTEXT: an orphan fact without the context to cue it.
- ACRONYM: an unexplained acronym is the testable content.
- IMAGE_ONLY: only an image or link, with no question.
- FORMAT: formatting junk that hurts readability.
- INTERFERENCE: easily confused with a sibling card that has no disambiguating cue.
- EXTRA_STORAGE: must-know content parked in Extra, where it is never tested.
- COMPOUND: the Front asks two questions.
- FAKE_RECALL: answerable by recognising the wording rather than retrieving the fact (a vignette or
  long stem that becomes the memorised cue). Not a flaw when the scenario's features are the cue being
  learned, but flag padding beyond them.
- OUTDATED: likely wrong or superseded by current guidance. Flag only if confident; it is verified at
  redesign.
- TYPO: a spelling error in the testable content.

Severity: 1 minor, 2 a clear design flaw, 3 badly broken (leech-prone, unanswerable or wrong). Mark
"bad" only for severity ≥ 2, or severity 1 with OUTDATED or TYPO in the testable content.

## Leave alone ("ok") unless broken

- Cards in the learner's own specialist area, and deliberately multi-part higher-order cards.
- Short one- or two-cloze cards with only a mild leak or ambiguity.
- Anything the personal overlay lists as exempt (by tag or deck).

## Output

A JSON array, one object per note in input order, written to the file you are given:
`{"nid": <int>, "verdict": "bad"|"ok", "severity": 0-3, "issues": [codes], "reason": "<one sentence
naming the specific problem, citing the card's content>"}`. Re-read the file and check that the count
matches the input.
