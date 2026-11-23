---
name: card-judgement
description: "The quality bar for Anki cards: hard rules, a pre-flight checklist and triage calibration, distilled from a large corpus of real approve/reject verdicts on redesigned cards. Load it whenever you draft, redesign, rework, triage or critique Anki cards: making cards from notes or questions, fixing due or leech cards, deciding whether a card is good or bad, or turning a rejected card into a better one. card-writing covers the mechanics; where the two conflict, these rules win. A user's personal judgement skill, if loaded, wins over both."
---

# Card judgement

These rules come from thousands of verdicts in which a learner approved, rejected, edited or trimmed
redesigned cards. Roughly nine in ten redesigns were approved first time, and almost every rejection
had one cause: **the visible text handed over the answer.** Spend most of your checking effort there.
Bad → good pairs for each rule are in `examples.md`.

**Personal overlays.** Learners differ in what they already know and what they want carded. If a
personal judgement skill is loaded (one built from this user's own verdicts), its rules and
calibration override this file. If the user gives a verdict that contradicts a rule here, follow the
user, and record the verdict (see *Learning from verdicts*).

## Hard rules

1. **Nothing visible may give the answer away.** Brackets, explanatory clauses, qualifying phrases and
   "why not X" asides next to a cloze or in a Front all count. Do not name a step the learner should
   retrieve: if the stem gives a pathognomonic finding, asking "which subtype of *disease X*" has done
   the first retrieval for them.
2. **Hints give the answer TYPE only**, at the broadest level that is still unambiguous: "drug",
   "investigation", "timeframe", "number". A hint that paraphrases the answer ("bleeding ×3",
   "national programme") is a leak. Stem labels count as hints; naming a drug class often narrows the
   answer to a single drug.
3. **Retrieve the reasoning; don't hand it over.** A visible "(so X and Y are unsuitable)" supplies the
   reasoning the learner should produce. Cloze it, make it the Back of a Basic card, or cut it.
4. **No solving by elimination.** With c1…cN on one note, the visible items let the learner deduce the
   hidden one; with two options, the hidden answer is "the other one". Sibling cards leak in the same
   way. Fix: separate notes; one cloze number for a set that is truly one concept; or a Basic
   "name the N…" card that states the count.
5. **Extra is not storage.** Anything the learner must know gets its own tested card; Extra holds
   optional context and is often empty. Conversely, detail that makes a cloze easier belongs in Extra,
   not on the front.
6. **Test the knowledge directly; a scenario must earn its place.** Default to asking the fact
   ("First-line antibiotic for neutropenic sepsis?"). A vignette becomes the memorised cue: the learner
   learns the story, not the fact. Keep a short scenario only when its features *are* the cue (red
   flags, "what makes you suspect X"), and then strip age, vitals and story beyond those features.
   No MCQs, yes/no questions or option letters.
7. **Cloze the specifics.** Colours, days, numbers and thresholds are what learners get wrong; hide
   them.
8. **Merge co-dependent facts into one cloze number**, e.g. an investigation and its timeframe.
   Parallel rows that are always recalled together can share a number.
9. **Two-step retrieval beats a cued fact.** For a drug side effect, don't name the organ in the
   stem: `{{c1::Hydroxychloroquine::DMARD}} needs annual screening because of the risk of {{c2::…}}`.
10. **Card only what is needed.** Cut timings nobody asks for, legacy protocols, dose arithmetic,
    trivially obvious "why" cards and tangential discriminators. Default to the core fact plus the one
    confusion the learner actually showed. A one-off slip on a known topic needs no card. Guideline
    names go in Source, not in the question or answer.
11. **Verify, and card current practice.** Check every number, dose, threshold and first-line choice
    against a current authoritative source (for UK medicine: NICE, CKS, BNF, RCOG, Resuscitation
    Council, Green Book). When guidance has changed, card the new practice only.
12. **Visual diagnoses get images, as the learner will meet them.** Write (a) an image on the Front →
    diagnosis, with the text description in Extra, and (b) a text description → diagnosis, with the
    image in Extra. If the card has no image, look for a reusable one (DermNet, Wikimedia, Open-i) and
    put the URL and licence in Source.
13. **Read the image.** When the knowledge sits in an image (an MCQ screenshot, say), open it with
    `retrieve_media_file` so you card what it actually tests.
14. **Obey the user's comment literally.** "Suspend" or "delete" means take that action, not
    redesign. "Make into a front/back" means Basic; "redesign as a cloze" means Cloze; "split" means
    several notes.
15. **One question per card.** A Front asking "X, and Y?" should be two cards, or lose the half that
    isn't needed.
16. **Understand before memorising.** When a miss comes from not understanding a topic (a
    mechanism-heavy area, or repeated misses across related questions), don't card it; suggest studying
    it first.

## Triage calibration (is this card bad enough to redesign?)

Flag a card "bad" only when its design genuinely harms recall: it takes more than ten seconds, it is
ambiguous, it tests recognition, or it is wrong. Lapses support a verdict but are never the verdict on
their own. Learners override "bad" flags almost always towards **fine**, for:

- **Short one- or two-cloze cards with a mild leak or ambiguity** that the learner already knows.
  Flag these only if the flaw makes the card unanswerable.
- **Sets the learner treats as one well-known list.**
- **Cards in the learner's own specialist area** (research, work), which they know from experience.
- **Deliberately multi-part "higher-order" cards**; the ten-second rule does not apply to them.
- Image Occlusion notes, which are skipped in triage.

Agree "bad" without hesitation for MCQ, letter or yes/no answers; image-only cards with no question;
wrong or outdated facts; long paragraph answers; and unhinted clozes hiding whole clauses.

## Pre-flight checklist (run on EVERY card before showing it)

1. **Read each cloze from the hidden side.** Write out what is visible when cN is hidden, and ask:
   could I answer from this alone? Check the other clozes, brackets, clauses, the hint and stem labels.
2. **Hint:** does it state only the answer type? Would a broader hint still be unambiguous?
3. **Elimination:** are other items of the set visible, on this note or a sibling? Is the hidden answer
   "the other one"?
4. **Reasoning:** does a visible "because / so / since / instead of / not X" hand over what should be
   retrieved?
5. **Extra:** is anything there must-know (give it a card)? Does anything on the front make the answer
   easier (move it to Extra)?
6. **Scenario:** is there a vignette whose features are not the cue? Does the Front ask exactly one
   question?
7. **Need:** would the learner want this card? Cut legacy, arithmetic, obvious and tangential pieces.
8. **Verification:** is every specific checked against a current source, named in Source?
9. **Visual:** for a visual diagnosis, is there an image-front card and a description card?
10. **Mechanics** (per card-writing): the Front demands the Back, no orphaned cloze numbers on an
    in-place edit, acronyms spelled out.

## When a card is rejected

Rework from the comment, then re-run the whole checklist on the note: one named clue usually means
there are others, and most second-round rejections are a new clue introduced by the first fix.

## Learning from verdicts

The rules improve only if verdicts are kept. After a review session, append each verdict to the
user's judgements log (see due-card-redesign for the record format). When a pattern recurs (the same
kind of rejection three or more times, or a consistent override), propose a rule or calibration change
to the user's personal judgement skill as a diff for approval. Never change rules silently.
