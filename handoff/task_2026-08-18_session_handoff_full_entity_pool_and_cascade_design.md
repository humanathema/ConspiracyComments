# Session handoff: full entity-mention pool, confidence cascade design, author-stance infrastructure

**Status: active, mid-session.** This is a working state dump, not a closed-out task record — written on request so nothing gets lost, not because the thread is finished. If picking this up cold, read the whole thing; several pieces (domain taxonomy expansion, confidently-wrong detection) are designed but not yet built.

## 1. What's actually done and verified this session

### Binary + confidence classifier (Stage 1 of the cascade reframe)
- `src/train_binary_confidence.py`: hostile/endorsement binary classifier + DeVries-Taylor self-assessed confidence head. Trained including "other" rows at low weight (`OTHER_CONF_LAMBDA=0.15`) rather than polar-only.
- Result: polarity kappa **0.7386** (up from 0.7111 polar-only baseline), other-vs-polar confidence separation P=0.794 (up from 0.700).
- Confidence-as-stage1-proxy check (using confidence threshold as a stand-in for the old has-stance-vs-other gate): best kappa 0.348 at threshold=0.5 — sits at the *top* of the old broken stage1's historical 0.22-0.37 range, a real if modest improvement, achieved at the natural threshold rather than needing an aggressive cutoff.
- Ensembling this confidence signal with the old 8-model stance ensemble gives a further small gain: AUC 0.796→0.810, best kappa 0.382→0.428 at a 70/30 old/new blend. Confirms the new signal adds real independent information, doesn't just duplicate the old ensemble.
- Checkpoint saved locally: `outputs/checkpoints/binconf_other015_binary_confidence/` (gitignored, 1.5GB).

### Full entity-mention pool (`data/processed/round9/full_entity_mention_pool.parquet`)
Final: **476,112 rows across 214 entities** (385,471 maverick / 66,371 alt_media / 15,596 consensus / 8,674 leak_whistleblower). This is NOT the same thing as `round9_unlabeled_pool.parquet` (22,459 rows) — that file is a 150-per-entity capped sample; this is the true uncapped full-corpus scan, built via new script `src/build_full_entity_mention_pool.py`.

Built by fixing a chain of real bugs found during QA, all fixed in `src/pull_hitl_val_batch.py` unless noted:
1. **Disambiguation checker false positives** (nicknames, sentence/quote-initial capitalization, single-token bare-surname aliases previously fully ungated, misspelling tolerance via edit-distance-1). Gated-subset fail rate 15.5% → 7.1%, verified via spot-check that remaining fails are genuine collisions (Scott Gottlieb ≠ Sidney Gottlieb, Rico Rodriguez ≠ William Rodriguez, etc).
2. **Catastrophic over-match**: "America's Frontline Doctors" was bare-matching the common word "doctors" anywhere in text — 123,311/473,447 (26%) of the first full-pool build was this false match. Root cause: `_bare_surname_key()` takes an entity's last word regardless of whether it's a person or an org. Fixed via `AMBIGUOUS_SURNAMES` addition; corrected count is ~150-192 genuine mentions.
3. **Original-11 exclusion bug**: `SKIP_ENTITIES` (built to stop `pull_hitl_val_batch.py` requesting redundant new HITL labels) was silently dropping Tucker Carlson, Alex Jones, Roger Stone, Matt Gaetz, Aaron Swartz, WikiLeaks entirely from a pool meant for full inference coverage. Fixed via new `skip_original_11` param on `build_person_entities()` (default True, preserves every other caller's behavior).
4. **Multi-entity dedup bug**: final pool assembly deduped on `id` alone, silently discarding one entity-label whenever a comment mentioned 2+ tracked entities. Fixed to dedup on `(id, target_entity)`. Confirmed real: 10,111 rows now correctly share an id with another row (was 0 before the fix).
5. **Duplicate-condition safety net**: some recovered/existing entities share byte-identical SQL match conditions under different display names (Julian Assange/Assange, Edward Snowden/Snowden, and 7 more found mechanically: Ruppert, Steve Kirsch, Wakefield, Yeadon, Halbig, Webster Tarpley, Scott Gottlieb). Would have double-labeled the same matched comments. General dedup-by-condition-string filter added in `build_full_entity_mention_pool.py`, not just hardcoded for the 2 manually found cases.
6. **Verified entity list expansion**: added Sean Hannity, Rush Limbaugh, Laura Loomer to `VERIFIED_MAVERICK_AUTHORITY` (frequency-checked: 2256/2087/1087 doc_count, well above the 100 floor). Landed with real volume (6,544/2,433/1,592 rows respectively).
7. **Documented, not fixed**: no bare-first-name/coreference matching exists at all (e.g. a reply saying just "Julian" after someone else named "Assange" is invisible to current matching). Real recall gap, high false-positive risk to fix naively (first names collide far more than surnames), needs actual coreference resolution not a regex. Flagged for the thesis limitations section.
8. **Known gap, not yet fixed**: `rt.com` (Russia Today, alt_media-classified) is missing from the domain list — its stripped key "rt" is only 2 chars, correctly filtered by the length≥5 safety floor (would be a severe false-match risk otherwise, same class of bug as #2). Would need the same full-phrase-fallback mechanism the person list has for short surnames (`AMBIGUOUS_SURNAMES`), which the domain list doesn't currently have.

### Author-entity-stance ledger (`data/processed/author_entity_stance_ledger.parquet`)
`src/build_author_entity_stance_ledger.py`. 27,869 observations, 13,059 distinct authors, 318 distinct entities, three trust-tiered sources kept separate (never blended into one column):
- `human` (2,882 rows): HITL-labeled training data, recovered to author via exact text-match join (training parquet has no comment id).
- `frontier_judge` (3,108 rows): round9's frontier-AI escalation pass, independent second-opinion score.
- `ensemble` (21,879 rows): the 8-model ensemble's own predictions, explicitly lowest trust.
- `stance_label` (string, human/ensemble) and `stance_score` (float -1..1, frontier_judge) kept as separate columns — a single mixed-type column broke the parquet write once already.
- Only 415 authors currently have ≥5 distinct entities mentioned — thin, because this only draws on already-labeled/scored data, not the new 476K-row pool. Will grow substantially once the cascade scores the full pool and unions in as a 4th tier.
- **Deliberately stops at assembling raw observations** — no correlation-mining, no assumed relationship form. That's future work once there's real volume, per Nash's explicit caution against greedily grabbing whatever pattern shows up first.

### Entity description lookup (`data/processed/entity_description_lookup.csv`)
`src/build_entity_description_lookup.py`. 214 rows (183 person + 31 domain at time of build — will need rerun once domain list expands), source-tagged:
- `wikipedia` (167 persons): from existing `entity_wikidata_tier1.csv`, matched directly + parenthetical-suffix stripping.
- `claude_general_knowledge` (16 persons): hand-written for the entities Wikidata coverage missed, mostly original-11 (predates the project's Wikidata tooling). Explicitly flagged as NOT independently verified, distinct from the Wikipedia tier.
- `domain_metadata` (31 domains): derived from `domain_classification_lookup.csv`'s category + MBFC reliability label, not free text (no natural-language source exists for these).
- **Not yet wired into the classifier's input format** — this is the next concrete step once entity list stabilizes (see open threads).

### Entity relationship lookup (`data/processed/entity_relationships.csv`)
`src/build_entity_relationships.py`. NOT a merge — each entity keeps its own separate label everywhere else. 8 pairs, two tiers:
- `name_embedded` (2, mechanically detected — domain core name literally contains the person's surname): Mercola/mercola.com, Greenwald/greenwald.substack.com.
- `associated_org` (6, hand-curated founder/host/chair facts, common-knowledge confidence, only where both sides already verified-present): Assange/WikiLeaks, Alex Jones/infowars.com + prisonplanet.com, Mike Adams/naturalnews.com, RFK Jr./childrenshealthdefense.org, Greenwald/theintercept.com.
- Purpose: check later (once ledger has volume) whether stance toward the person correlates with stance toward the org — not assumed, just now recorded so it's checkable.

## 2. Cascade architecture — decisions made this session, not all built yet

### Epistemic vs aleatoric escalation (Stage 4)
Reuses an already-validated mechanism rather than inventing one: `round9_epistemic_aleatoric_classification.csv` already empirically classified rows by whether adding parent/post context moves the ensemble's confidence margin (`margin_ctx` vs `margin_orig`). Proposed routing for the new cascade:
1. Confidence ≥ ~0.95 → accept as-is.
2. Below threshold → add parent context, re-check. Improves → epistemic, accept context-augmented prediction. Doesn't improve → aleatoric.
3. Aleatoric + still low → do NOT blanket-escalate to the frontier judge (that's the pattern that caused the earlier $100 budget blowout). Either (a) a small, deliberately capped/prioritized subset gets frontier-judged, or (b) default: accept the low-confidence prediction and let the continuous confidence score down-weight it in the regression — the whole point of the binary+confidence redesign. Leaning toward (b) as default, (a) only if the confidence-weighted regression later shows real sensitivity to the unresolved tail.

### Author-augmented resolution module (separate from base classifier)
Explicit design to capture author-typing signal for low-confidence rows WITHOUT contaminating either the base classifier or the author-entity correlation analysis:
- Base classifier stays text + entity-description only, no author signal, ever — confirmed directly in code (`[ENTITY: name] <text>`, nothing else) that category/author currently guide nothing.
- For rows still low-confidence after epistemic escalation: separate pass, fed comment text + a **specific per-entity** author-typing summary (not a collapsed aggregate score — "does this author like X, dislike Y" is the right grain, not "68% hostile toward mavericks" — the ledger is already shaped this way).
- Output lands in its own column (`stance_author_augmented`), never overwrites base `stance`.
- **Circularity rule, load-bearing**: this column is safe to toggle into the regression (legitimate alternate measurement, fine as a robustness check) but must NEVER be used in the author-behavior-correlation analysis — using it there is circular by construction (the label would be partly derived from the same author-profile being correlated against).
- **Self-reinforcement guard**: author profile must be built ONLY from high-confidence base-classifier rows, frozen, then used to resolve low-confidence rows once. Never feed resolved rows back into the profile — that's a strict DAG, not an iteration, specifically to avoid the PageRank-without-damping failure mode of errors compounding. A genuine iterative/EM joint-inference version (letting author-judgment and comment-judgment mutually inform each other properly) is real future-work, flagged explicitly, not attempted now — meaningfully harder to get right under time pressure.

### Confidently-wrong detection (distinct problem from low-confidence)
Real, correctly-identified harder problem: low-confidence rows are self-flagging (the confidence score IS the queue), confidently-wrong rows aren't — no natural detection mechanism exists yet. Already ruled out earlier this session: length, has_link, has_citation as predictive heuristics (not the answer). Agreed first move, not yet built:
- Deterministic paraphrase/perturbation stability check on the human-labeled set (few thousand rows, cheap). No LLM needed for generation — comparing WordNet synonym substitution vs. local masked-LM fill-in substitution (mask a word, take the existing model's top prediction) on a small sample first, since this corpus's informal register (slang, profanity, political shorthand) may not suit WordNet's curated synsets well.
- Reuse the existing trained checkpoint, no retraining. Row flagged if perturbation flips the prediction away from the known true label, confidently.
- Scope explicitly: target polar-vs-other confident errors, NOT hostile/endorsement polarity flips — polarity is already solid (~0.71-0.74 kappa), matches established findings, don't re-litigate a solved axis.
- Sequencing: run the stability check, look at what it surfaces, THEN decide whether a dedicated meta-classifier is warranted (only if the candidate list is large and has real structure) or whether direct hand-review/frontier-judge of a small list is sufficient.
- Nash is also expanding the human val set (410 done, another 410 possible, minus wrong_match rows) — merge as usual when ready, feeds this thread too.

## 3. Domain taxonomy — in progress, not finished

Current stance-classifier domain list (31) is `alt_media` + `leak_whistleblower` ONLY — deliberately narrower than the full `domain_classification_lookup.csv` taxonomy, which also has `mainstream_news` (71), `government_official` (37), `academic_scientific` (22), and smaller categories. This was originally fine because a SEPARATE, already-comprehensive mechanism (`link_source_tier` in `run_link_source_tier_regressions.py`) already covers mainstream-vs-alt at the link-citation level for the regression.

**But Nash's call, reversing the earlier "fine as-is" framing**: since the actual research question is explicitly about how people respond to maverick vs consensus figures, the domain list SHOULD include consensus-side domains too, mirroring how consensus persons (Fauci et al.) are already tracked. Not frequency-selected currently (the whole taxonomy, including the 31 already-used domains, comes from a hand-curated source, `cell_61_taxonomy` — NOT corpus-frequency-driven). Plan:
1. Get real corpus frequency for the 130 mainstream_news/government_official/academic_scientific candidates (in progress at session-pause time, script `src/scratch_count_consensus_domains.py`, output `/tmp/consensus_domain_counts.csv` — SCRATCH FILE, not committed, rerun if needed).
2. Apply a frequency floor (same standard as the person list, `MIN_COMBINED_DOC_COUNT`-style) rather than including all 130 indiscriminately — avoid diluting with barely-mentioned domains.
3. PubMed IS in the taxonomy already (`ncbi.nlm.nih.gov`, `pubmed.ncbi.nlm.nih.gov` under academic_scientific; `nih.gov` under government_official) — just not currently tracked, same as the rest of this category.
4. `rt.com` gap (see §1.8) still needs the full-phrase-fallback mechanism if it's to be safely included.
5. **FBI vault / FOIA reclassification**: `vault.fbi.gov`, `foia.state.gov`, `governmentattic.org` are currently miscategorized as `leak_whistleblower` alongside genuine leak sites (`dcleaks.com`, `cryptome.org`) — these are official government primary-source portals (or, for governmentattic.org, a citizen archive of legally-obtained FOIA documents), substantively different, and this matters for the thesis: conspiracy theorists citing FBI's own declassified files is a "appeal to consensus/official primary sources" finding, currently invisible because it's mislabeled as the opposite. Nash's call: don't build a fractional-weighting system, just tag them into BOTH categories for now (`government_official` + `leak_whistleblower`), revisit precision later if needed. Not yet implemented.
6. Once frequency counts are in: hand-label a batch of the highest-count consensus domains (Nash's offer, capacity permitting) so they have real training signal before the next training round, same pattern as every other entity expansion this project has done.
7. Once expanded, entity description lookup (§1) needs a rerun to cover the new domains.
8. **Third-person-source clarification** (Nash's correction): a cited article's author isn't a new category — they're just another instance of the same maverick/consensus PERSON entity system. If prominent enough they're likely already tracked; if not, byline extraction's job is to surface candidate additions to the SAME list, not build a separate system.

## 4. Infra guidance

- Entity-list/domain-scan work (DuckDB regex scans, no GPU): **local is fine**, proven — the 476K-row full-corpus scan ran locally in ~75 min with no memory issues on this 8GB machine.
- GPU work (model training/inference): VM has been the right call all session (proven pattern, ~1h50min for a full binary+confidence training run) — but **VM credits are a genuinely scarce, already-strained resource** (2-3 free-trial orgs burned through across this project), not just a speed/convenience tradeoff. Default to **Kaggle's free tier for anything not time-critical**, even though it's slower/more cumbersome (weaker GPU, session limits) — reserve VM credit for genuinely urgent GPU work.
- Git: pushed clean throughout this session via `git -c credential.helper='!gh auth git-credential' push` (plain `git push` fails here, no stored HTTPS credential — gh's credential helper works). Repo was 5 days stale at session start (last commit 2026-08-13); caught up across several commits this session, all pushed to `origin/master`.

## 5. Task list state at time of writing (in-app task tracker, not this file)
1. Stage 1 (binary classifier + confidence head) — completed.
2. Stage 2 (entity description column) — built, not yet wired into classifier input.
3. Stage 3 (author features) — reframed as ledger-derived, not classifier input; infrastructure built, thin until full inference runs.
4. Stage 4 (epistemic/aleatoric routing) — designed (§2), not built.
5. Stage 5 (cascade routing logic) — not started.
6. Stage 6 (validation harness) — not started.
7. Entity disambiguation checker fixes — completed.
8. Full entity-mention pool — completed (476,112 rows).
9. Consensus domain frequency counts — in progress at session-pause.

## 6. Open threads / not yet resolved, don't treat as closed
- Confidently-wrong detection: paraphrase-stability check agreed, not yet built.
- Domain taxonomy expansion: counts in progress, not yet acted on.
- FBI vault/FOIA dual-category tagging: agreed approach, not yet implemented.
- `rt.com` and any other domain with a too-short stripped key: needs the AMBIGUOUS_SURNAMES-equivalent fallback for domains.
- Bare-first-name/coreference matching: documented limitation, not attempted (deliberately — high false-positive risk without real coreference resolution).
- Wider "halo markers of epistemic credibility" idea (whistleblower framing, censorship narratives, courage-of-departing-from-establishment as perceived credibility signals independent of formal expertise) — spitballed, not scoped into anything concrete yet.
- Source-trust vs. author-framing as two separate feature families (hedged_suspicion etc. validated for comment-level framing, not source-credibility evaluation) — scoping note only, no action needed now.
- Platform-vs-content/author tension (PubMed hosting a Wakefield-style claim, same structure as the FBI-vault case) — explicitly a regression-level interaction (`link_source_tier` × entity-stance), not a classifier concern. No new infra needed, just needs both pieces to exist as covariates.
