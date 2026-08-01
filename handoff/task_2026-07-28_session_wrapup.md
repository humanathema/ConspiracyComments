# Session wrap-up, 2026-07-28 — read this first if picking up fresh

Long Claude Code session covering three broad threads: (1) getting the ATS
topic-assignment pipeline running on Kaggle GPU and extending it into a
broader AIITL (AI-in-the-loop) validation pass, (2) designing a cascade
architecture for cheap-to-expensive judgment at full-corpus scale, and
(3) building real, persistent shared infrastructure (context-repo +
wake-relay + a unified MCP gateway) so future sessions — any AI, not just
this one — aren't laptop-dependent or starting from zero context. All
three are real and tested, not speculative. Check `context-repo`'s
`conspiracycomments` and `context-repo` compartments via `context_checkpoint`
for the full granular trail this doc summarizes — this file is the
synthesized entry point, not a replacement for it.

## 1. Major finding, not yet acted on: entity-stance classifier reliability

An independent small-LLM (Qwen2.5-1.5B-Instruct, free/open-weight, no paid
API) audit job judged a stratified sample of 2,518 entity-mention windows
(both platforms, both `maverick`/`consensus` constructs) against the
existing stance classifier's own predicted labels. **Match rate: 33-36%
across every platform/construct combination** — close to random-chance
for a 3-way classifier (hostile/endorsement/other). This is a
*materially* bigger reliability concern than the previously-known
endorsement-detection weakness (kappa 0.243-0.274, macro AUC 0.649,
documented in `handoff/task_stance_endorsement_blindspot.md`) — this new
number suggests the classifier's labels may not be trustworthy at all,
not just weak specifically at endorsement.

**What this does and doesn't mean, and what's ruled out:**
- Not a sample-size artifact — 2,518 rows, stratified.
- Not (solely) an entity-list contamination issue — the sampled entities
  come from `per_entity_stance_breakdown.csv`, itself built from the
  already-corrected `consensus_experts_verified.py`/`maverick_authority_verified.py`
  allowlists, not the old contaminated bucket.
- The judge model's own self-reported `matches_label` field was found to
  be degenerate (always `true` regardless of category) and was discarded
  — the 33-36% figure is a *deterministic recomputation* from the judge's
  category output + the original predicted label, not trusted from the
  model's own claim.
- **Not yet investigated**: whether this is a real problem with the
  stance classifier itself, or a problem with how the 1.5B judge model
  interprets short, decontextualized text windows (i.e., is the judge
  wrong, or is the classifier wrong, or both). This needs resolving
  before treating 33-36% as a verdict on the classifier rather than a
  red flag worth chasing. See section 3 (cascade design) — Tier 1's own
  validation used this same data and found the *pattern* (confidence
  correlates with accuracy) held, which is at least consistent with the
  judge being a meaningful signal, not just noise.

Source data: `data/processed/entity_stance_aiitl_sample.parquet` (input),
judge output pulled from Kaggle kernel `tobiasnashktc/entity-stance-judge`
(not yet saved to a permanent local path — check Kaggle kernel output or
re-pull via `kaggle kernels output`).

## 2. Citation-window contamination — RETRACTED, see 2026-07-28b for the
## corrected number; do not cite 88.2%/83.0% as settled

**Correction added same day, later session (see
`handoff/task_2026-07-28b_kaggle_backlog_and_dedup.md` section 6 for the
full chain)**: the numbers below were measured with a judge prompt that
shows the model `predicted_label` and asks it to grade whether that
category is "defensible" -- confirmed via a follow-up blind re-judge
(same sample, same categories, but the model never sees `predicted_label`
at all) to have anchored/inflated its outputs. The blind re-judge found
real contamination at **43%**, not 88.2%/83.0% -- more than half of what
was reported below doesn't hold up. **Treat every number in this section
as superseded, not as background context that's still basically right.**
Original (unreliable) text preserved below for the record, not as a
citable finding:

A second AIITL job (same technique, different sample) found **88.2% of
ATS and 83.0% of Reddit citation-window samples were judged
`not_real_citation`** (boilerplate/copypasta/signature-block
contamination), much higher than the earlier naive duplicate-text
heuristic suggested (19-24%). Output:
`data/processed/source_stance_aiitl_judged_corrected.parquet` — the
`matches_label` field in this file *was* corrected (unlike the entity-stance
one above, which was pulled fresh from Kaggle and not yet locally
persisted) via `real_matches_label`, computed deterministically from
category + `predicted_label` rather than trusted from the model. Once
you exclude the `not_real_citation` rows, only 32-45% of the remaining
windows match their original label — consistent with, and possibly
explaining part of, the entity-stance finding above (if a meaningful
fraction of "citation windows" and "entity-mention windows" share the
same contamination mechanism).

**Corrected figures (blind judge, authoritative as of 2026-07-28)**:
contamination ~43% (not 88.2%/83.0%); non-contaminated agreement 59.2%
overall (ATS 64.9%, Reddit 41.2% — not 32-45%, and notably *higher* than
originally reported, the opposite direction from the contamination
correction). Source: `tobiasnashws/source-stance-blind-judge` Kaggle
kernel, written to context-repo as
`job_source_stance_blind_judge_AUTHORITATIVE_2026-07-28`.

## 3. Cascade design (embeddings -> cheap classifier -> distilled model -> full LLM)

Full-corpus sentence embeddings (`all-MiniLM-L6-v2`, free/open-weight) now
exist on Kaggle for all three corpora — ATS (9,237,764 rows), Reddit long
(21,349,908 rows), Reddit short (18,580,083 rows). **Deliberately not
downloaded locally** (disk was at 13GB free at one point mid-session) —
any embedding-dependent analysis should run on Kaggle itself, pulling
back only small aggregated results.

**Tier 1 (cheap classifier on frozen embeddings) — built and empirically
validated on two different tasks:**
- Entity-stance judgment: high-confidence predictions (top 15% by the
  classifier's own confidence) hit 74.2% accuracy; low-confidence
  predictions (bottom 37.5%) hit only 37.8% — barely above chance.
- Citation-category judgment: high-confidence (31.8%) hit 85.2%;
  low-confidence (14.7%) hit 46.6% — below the naive majority-class
  baseline for that imbalanced task.
- **The finding that matters**: confidence genuinely separates cases the
  cheap classifier can be trusted on from cases that need escalation,
  across two structurally different tasks. That's the empirical basis for
  building Tiers 2-3 rather than just trusting Tier 1 alone or giving up
  on the cheap-first approach entirely.

**Tier 2 (small distilled model trained on the uncertain band) — designed,
not built.** Would need: (a) a larger labeled sample specifically drawn
from Tier 1's low/mid-confidence band on the *full* corpus (not just the
original small stratified sample), via another Kaggle AIITL judge run,
then (b) an actual supervised fine-tuning job — genuinely a training task,
not inference with an off-the-shelf model. This is flagged as the best
candidate for TPU experimentation (Kaggle tracks TPU quota separately
from GPU, essentially unused so far across all accounts) if/when pursued,
since training benefits from TPU's large-batch strengths in a way
inference doesn't — but would need a JAX/Flax toolchain, not naive
PyTorch-on-TPU, to actually realize that advantage.

**Tier 3 (full reasoning LLM on the genuinely hard residual) — designed,
not built.** Only reached after Tier 2 also fails to confidently resolve
a case; should end up being a small fraction of the corpus.

## 4. Entity-coverage two-sided problem — investigated, designed, NOT built

Nash's framing: top-down curated expert/entity lists likely have real
recall gaps (miss real figures), bottom-up NER-mined candidate lists have
real precision problems (noise). Both confirmed concretely, not just
suspected:

- **Top-down gap is self-documented in the codebase already**:
  `consensus_experts_verified.py`'s own preserved docstring says the list
  was expanded (2026-07-15) via cross-referencing `query_openalex_experts.py`
  (OpenAlex academic database) and `query_petscan_experts.py`
  (Wikipedia/Wikidata category tool via PetScan) to 82 name-variants /
  ~57 people — but explicitly flags that only the health domain got this
  treatment; physics/economics/other domains are named as a likely
  similarly-uncovered blind spot. **Correction to an earlier session
  misread**: this is NOT still a 19-person Wikipedia-only list (that's
  historical lineage preserved in the docstring, not current state) —
  don't repeat that mistake.
- **Bottom-up noise is severe in the rawest candidate pool**:
  `data/processed/entity_frequency_full_corpus.csv` (16,534 rows) is
  mostly non-entity garbage at the top by frequency ("the [", "~~It",
  "THat", "NOT" — capitalized-token extraction artifacts, not real
  entities).
- **A better-structured bottom-up pool exists**:
  `data/processed/corpus_entity_frequency.csv` (683,635 distinct entity
  strings, real spaCy PERSON/ORG/NORP labels, doc counts, 2 example
  contexts each, an `in_candidate_list` flag) — this is a legitimate
  candidate pool to build a noise-filtering AIITL job from.
- **Found in passing, separate bug**: `corpus_entity_frequency_cleaned.csv`
  and `corpus_entity_frequency_final.csv` are both **corrupted** —
  unreadable via standard CSV parsing (buffer overflow from malformed
  embedded quotes/newlines in the example-text fields). Not fixed.

**Designed but not built**: an AIITL job using `corpus_entity_frequency.csv`
to judge each candidate into {genuine distinct entity / NER-mislabeled
non-entity / duplicate-variant-needs-merging / too-generic-institutional}.
This is squarely the kind of task the small open-weight Kaggle models are
good at (judging existing candidates), unlike the top-down gap-finding
half, which genuinely needs broader world-knowledge recall that small
local models are comparatively weak at (flagged, not resolved — Nash's
own "shared context repo + rotating chat-instance" workflow is a better
fit for that specific half, not something to force onto Kaggle).

**This was paused, not abandoned** — the session pivoted into the
shared-infra build (section 5) before this got built. Next session should
pick this up as a concrete, scoped Kaggle job if it's still a priority.

## 5. Shared infrastructure — now live, persistent, not laptop-dependent

Three services, all on one Oracle Cloud instance (`context-repo-host`,
`VM.Standard.E2.1.Micro`, ap-sydney-1, systemd-managed with
`Restart=always`, survive reboot):

- **context-repo** (ports 8420 HTTP API / 8421 MCP) — the shared semantic
  memory store, migrated off a laptop+ngrok setup. DNS:
  `context.kahatahi.co.nz` (A record, DNS-only/unproxied in Cloudflare —
  proxied mode only forwards 80/443 by default, breaks these ports).
  **This repo (`~/Projects/context-repo`) is now public on GitHub**
  (secret-scanned clean first — 4 commits, zero credential patterns in
  history, `data/` gitignored from the first commit).
- **wake-relay** (port 8422) — the always-on half of "wake my laptop's
  fs-agent on demand without permanently exposing it." A remote agent
  POSTs `/wake`; the laptop's `wake_poller.py` (launchd job
  `com.nash.wake-poller`, polls every 30s via outbound-only requests,
  works behind NAT) picks it up, starts `project-fs-agent` + a
  `cloudflared` quick tunnel, and POSTs `/announce` with the resulting
  URL. 20-minute idle shutdown (flat timer, not activity-based yet).
- **unified-gateway** (port 8423) — one MCP connector exposing both
  `context_*` tools (served directly in-process, same host as the store)
  and `fs_*` tools (proxied through wake-relay to the laptop on demand).
  Built specifically because free-tier custom-connector slots (e.g.
  claude.ai web) are typically limited to one — this collapses "shared
  context" and "project filesystem access" into a single attachable
  connector. First `fs_*` call after inactivity takes up to ~90s (wake +
  tunnel startup) — expected, not a bug.

**Real bugs found and fixed during this build, worth knowing about if
touching this again:**
- FastMCP's built-in DNS-rebinding protection defaults `allowed_hosts` to
  localhost only, rejecting `cloudflared`'s dynamic `*.trycloudflare.com`
  hostname (a new random subdomain every run). Fixed properly (extended
  the allowlist via a `PROJECTFSAGENT_ALLOWED_HOST` env var set by
  `wake_poller.py` once the tunnel URL is known, requiring one `api.py`
  restart per wake cycle since the host isn't known until after the port
  is already live) — not by disabling the protection.
- launchd jobs don't inherit the interactive shell's PATH — the bare
  `"cloudflared"` subprocess call that worked fine tested by hand failed
  silently once actually deployed as a launchd job. Fixed with an
  absolute path (`CLOUDFLARED_BIN` env var).
- The security-relevant design choice in `unified_gateway/fs_bridge.py`:
  wake-relay deliberately never stores the full bearer token (only a
  4-char hint), so the gateway holds its own copy via `FS_AGENT_TOKEN`,
  checked against the hint for a mismatch (e.g. if the laptop's token
  file is ever regenerated without updating the gateway) rather than
  trusted blindly.
- OCI instances need firewall rules opened at **two independent layers**
  for every new port — the cloud-level security list AND the OS-level
  `iptables` (Ubuntu's default image ships a REJECT-all-except-22 policy
  independent of the cloud firewall). Both need updating together;
  `iptables-persistent` installed so the OS-level rules survive reboot.

**Local mirror**: a second, separate context-repo instance still runs on
the laptop (`mcp_server.py` process, tunneled via a pre-existing ngrok
setup on port 8421) — deliberately kept alive, not decommissioned, since
something (likely a running Antigravity session) may still be pointed at
that old URL. Both stores were manually kept in sync throughout this
session (every write mirrored to both) but this is a **manual, fragile
arrangement** — decide when it's safe to fully migrate off the local one
and say so explicitly rather than let it silently drift.

## 6. Compute patchwork status

| Resource | Status |
|---|---|
| Kaggle (4-5 accounts) | Working. `Registry.submit_with_fallback()` built in `surge-compute` — ranks providers by real headroom, falls through on error, full attempt log. `KaggleKernelsProvider.capacity()` now reports real GPU-quota headroom (was a placeholder claiming this wasn't queryable — it is, via `kagglesdk`'s internal client). TPU quota tracked separately, ~unused. |
| Oracle Micro | Running, hosts the 3 services above. |
| Oracle A1 (bigger, 2 OCPU/12GB — the tenancy's real quota, confirmed via `oci.limits.LimitsClient` after an earlier over-request hit a quota wall) | Still retrying against Sydney's contested free-tier capacity as of session end — unresolved, not failed; genuinely unpredictable timing. Tenancy is capped to its home region only (a second-region subscription attempt hit `TenantCapacityExceeded`, a hard account-tier limit) and home region can't be changed without an Oracle support ticket (not pursued). |
| GCP Cloud Run (3 accounts) | Was broken all session — `google-cloud-run` pip package simply wasn't installed (not a version mismatch as the old error implied). Fixed with one `pip install`. Real quota/headroom still not wired into `capacity()` (placeholder note), same gap as GitHub Actions. |
| GitHub Actions | Registered, healthy, unlimited free minutes now available for the now-public `context-repo` (2,000 min/month if used against the still-private `ConspiracyComments` instead). Not yet actively used — see section 7. |
| Fly.io / Hugging Face Spaces / Colab / Cloudflare R2 / Workers | Assessed, deliberately deferred, not built. Workers can't run stateful services like this (isolate model, no persistent disk); Spaces/Colab don't fit always-on or synchronously-callable needs; R2 is a real option for storage specifically if GCS's 5GB free tier becomes binding, not urgent. Fly.io is a legitimate second-host candidate if Oracle proves unreliable over time — revisit then, not pre-emptively. |
| Kaggle Datasets (storage) | The three canonical corpus files (`ats_comments_final.parquet`, `empath_scores_full_mapped.parquet`, `conspiracy_comments_short_lte100chars_mapped.parquet`) backed up to `tobiasnashws/conspiracycomments-canonical-corpus` — verified symlinks are NOT reliably followed by Kaggle's zip-mode CLI before trusting a 9GB upload, used real copies instead, deleted the local staging copies afterward. |

**GH Actions / Kaggle porting assessment** (not executed, just scoped):
went through the 85-file `src/` inventory against GH Actions' real
constraints (2,000 min/month for a private repo, 2-core/~7GB RAM/~14GB
disk, no GPU). Roughly a third of the scripts (pure external-API calls —
`query_openalex_experts.py`, `query_petscan_experts.py`,
`wikidata_entity_lookup.py`, etc. — plus small-data validation/stats
scripts) are a genuinely good fit. The full-corpus scoring/disambiguation
pipeline (`score_*_full.py`, `stage_a` through `stage_g`) is a poor GH
Actions fit but now maps cleanly onto Kaggle, since the canonical corpus
dataset above means every one of those scripts could mount the same
staged data without separate per-script upload work.

## 7. GCP billing hard-stop — explicitly handed to a different session

Nash has real trial credit on two of the three linked GCP accounts:
`contact@tobiasnash.co.nz` (project `graphic-height-502723-t6`) has
**$224.45** remaining; `contact@kaha-tahi.com` (project
`sapient-zodiac-502400-k2`) has **$84.67** remaining. Third account
(`contact@kahatahi.co.nz`, project `surge-compute-kahatahi`) — credit
status not stated, don't assume.

**Real prior incident**: a ~$100 overrun happened on one of these
accounts despite Nash believing safeguards were in place — almost
certainly because a plain GCP budget *alert* is notification-only and
does not actually stop spend, which is the trap to avoid repeating.

**Agreed approach** (confirmed explicitly by Nash): a GCP budget that
publishes to Pub/Sub on threshold breach, triggering a Cloud Function
that calls the Cloud Billing API to actually disable billing on the
project — this is Google's own documented pattern for a genuine hard
stop, not the default alert-only budget UI.

All three accounts were re-authenticated successfully this session (via
`surge-compute/scripts/reauth_gcp_accounts.sh` — loops `gcloud auth login`
across all three, one password prompt per account each time it's run,
not collapsible to a single prompt since that's gcloud's own per-account
flow). **This was explicitly assigned to a separate session/agent to
actually build** — not done here. Specific dollar thresholds for the
Cloud Function trigger were not decided with Nash before handoff —
confirm before building, don't assume a number.

## What's explicitly NOT done — quick scan list

- Entity-coverage AIITL noise-filtering job (section 4) — designed, not built.
- Cascade Tiers 2-3 (section 3) — designed, not built.
- GCP billing hard-stop (section 7) — handed to another session.
- GitHub Actions actually used for anything — registered, idle.
- `corpus_entity_frequency_cleaned.csv`/`_final.csv` corruption (section 4) — found, not fixed.
- Local context-repo mirror decommissioning (section 5) — deliberately kept alive, not resolved.
- Oracle A1 provisioning (section 6) — still retrying, unresolved.
- Media-personality category / byline-extraction re-validation / citation-coverage
  expansion — see the two background-agent audit reports referenced in
  `context-repo`'s `conspiracycomments` compartment (search for "media
  personality" and "citation events" if `context_query` is available;
  otherwise these were reported verbatim in this session's own
  transcript, not yet copied into a dedicated task file).
