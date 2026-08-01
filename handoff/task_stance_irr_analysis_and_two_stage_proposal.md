# Stance IRR analysis + two-stage relabeling proposal — 2026-07-28

Follow-up to the recommended next step in `task_stance_classifier_finetune.md`
("establish actual human-human IRR ... before a 4th training variant").
`queue_irr_stance_shared.csv` had zero ratings; three raters (Tobias, Jono,
Lw) have now rated the same 99-row shared queue independently
(`data/hitl/irr_responses/irr_stance_shared__*.csv`). This doc is the
analysis of that data, done in a claude.ai chat session with the
project-fs-agent connector (not Claude Code), full recompute from raw
labels rather than trusting the leftover summary columns in the rating
CSVs (those don't cleanly map to any agreement metric I could identify —
likely stale spreadsheet-formula artifacts, ignore them).

## Headline numbers

99 rows, 3 raters, `queue_consensus_stance_CODEBOOK.md`'s 4-class scheme
(hostile/endorsement/neutral/ambiguous), collapsed to the production
3-class scheme (hostile/endorsement/other) to compare directly against
the classifier's kappa:

| | native 4-class | collapsed 3-class (matches model) |
|---|---|---|
| All-3-agree rate | 43/99 (43%) | 50/99 (51%) |
| Fleiss' kappa | 0.40 | **0.48** |
| Pairwise Cohen's kappa | 0.34–0.48 | 0.47–0.51 |

**Compare to the model:** production baseline kappa 0.345, best fine-tune
variant 0.324–0.344 (see `task_stance_classifier_finetune.md` results).
Human-human Fleiss' kappa (0.48, "moderate" on Landis-Koch) sits
meaningfully *above* the model (~0.32-0.35, "fair" one tier down) — a
gap of roughly 0.13-0.16 kappa points.

**Read on this:** the "three fixes landed on the same ceiling" conclusion
in the finetune doc is only half right. There IS real task ambiguity
(humans only reach "moderate," not "substantial"/"almost perfect," even
on the same fixed set) — but the model isn't AT the human ceiling, it's
notably below it. That gap says the three tried fixes (roberta swap,
256->512 tokens, class weighting) weren't the right lever, not that no
lever exists. Don't conclude "this is as good as it gets" from the
finetune result alone.

## What the disagreement actually is (read the text, not just the labels)

Pulled `queue_irr_stance_shared.csv`'s `full_text` column and read every
row where the 3 raters gave 3 different native-scheme labels (14 rows)
plus every true polarity flip (hostile vs endorsement present among the
3 raters, 6 rows). The disagreement is NOT uniform noise — it splits into
recognizable categories, each with a different fix:

1. **Sarcasm misses (true polarity flips, the serious disagreements).**
   `hjjxu3q` ("Of course Mullis is the only scientist you should trust...
   all these other scientists ... obviously incapable") — 1 rater caught
   the sarcasm (hostile), 2 took it literally (endorsement). `dg4e60t`
   similar pattern. This is a real, hard NLP problem, not fixable by more
   labeled data of the same kind.

2. **Coreference ambiguity in the source text itself.** `go34rsb`:
   "Trump did not pardon Assange! I think he is definitely a globalist."
   — "he" genuinely could resolve to either entity, target is Assange.
   Not a labeling failure, an unresolvable ambiguity in the comment.

3. **Citation/link-dump comments with minimal original evaluative
   language.** `gfaiuqc` — mostly a chain of links, entity tagged on one
   link. All 3 raters gave different labels. Matches the link-dump issue
   already partially handled by the Stage-1 filter mentioned in
   `task_stance_endorsement_blindspot.md` — this row shows it's not
   catching everything.

4. **Entity mentioned incidentally in a comment that isn't really about
   that entity.** `lyz3emx` (Gaetz named while the comment is actually
   about thread-topic relevance), `jy6369a` (joking aside inviting
   someone to "get ice cream with... Tony Fauci"). The codebook's
   neutral ("factual/descriptive") vs ambiguous ("genuinely unclear")
   distinction has no category for "entity is incidental, no real stance
   is being expressed at all" — raters are splitting these across both
   existing categories somewhat arbitrarily.

5. **Missing conversational context.** Several disagreement rows
   (`di5i86y`, `dwr2qpm`, `f22kl34`) are replies whose tone depends on a
   parent comment. **Open question, not verified**: does the labeling
   tool/spreadsheet actually surface parent-comment text to raters, or
   just the child `full_text`? The CSV carries `parent_id` but I could
   not confirm from the file alone whether raters could see it while
   rating. Worth checking before assuming this category is "genuine"
   ambiguity vs a labeling-setup artifact.

## Proposal: two-stage labeling instead of one 4-way pick

Rather than a single continuous/fuzzy slider (considered and explained
to Nash why not — unbounded sliders tend to make human raters *less*
consistent due to inconsistent anchoring; bounded 5-7 point ordinal
scales are the standard alternative in the measurement literature),
split the currently-conflated judgment into two:

1. **Stage 1, binary:** "Does this comment express any real evaluative
   stance toward the entity?" — directly targets category 3 and 4 above
   (citation-dumps, incidental mentions), which are the bulk of the
   disagreement.
2. **Stage 2, only if yes:** valence on a 5-point ordinal scale, hostile
   <-> endorsing.

This does NOT claim to fix category 1 (sarcasm) or category 2
(coreference) — those will and should still show up as real
disagreement under any scheme; a fuzzy/ordinal score reports them
honestly (large numeric gap) rather than hiding them.

## Recommended next step (cheap test before any full relabel)

Do NOT relabel everything blind. Rerun the SAME 99-row IRR set
(`queue_irr_stance_shared.csv`) with the two-stage scheme, same 3 raters
(Tobias/Jono/Lw), and compare ICC/Krippendorff's alpha against the
kappa numbers above on an apples-to-apples basis before committing to a
full relabel of the ~3,650-row training set. If it doesn't meaningfully
close the gap on this known set, that's a cheap negative result, not a
wasted relabel of everything.

Also worth resolving first: the parent-comment-visibility question in
category 5 above, since if raters were labeling blind to context that's
a labeling-protocol bug, not evidence about the task's true ambiguity
ceiling.

## Model-side note

The production classifier's confidence margin (already computed as a
free byproduct in `train_stance_classifier.py`, see "Confidence margin"
section of that script) is a post-hoc softmax-margin, not a real
calibrated score. If the labels move to ordinal, training a regression
or ordinal-loss head instead of 3-way softmax classification would give
a genuinely calibrated confidence output — a better match for
cascade-style routing (low-confidence rows -> bigger judge model,
already the pattern used elsewhere in this project, e.g.
`kaggle_source_stance_tier2_kernel`) than the current post-hoc margin.

## Not done yet

- Two-stage scheme not yet built as an actual rating queue/spreadsheet.
- Parent-comment-visibility question (category 5) not verified.
- No relabel of the full training set — deliberately, per "cheap test
  first" above.
- No code written for an ordinal/regression training head — this is a
  proposal, not an implementation.
