# Kaggle backlog push + entity dedup + explorer outage, 2026-07-28 (session 2)

Second Claude Code session on 2026-07-28, picking up directly from
`task_2026-07-28_session_wrapup.md`. Two Claude Code sessions were active
on this repo simultaneously today, both pushing to the same small pool of
Kaggle accounts — see "Cross-session coordination" below before touching
Kaggle again.

## 1. Unified-gateway TLS gap found and (pending) fixed

`context.kahatahi.co.nz:8423` (unified-gateway, `context_*` + `fs_*` tools)
was HTTP-only, no TLS at all — confirmed by testing both `:8423` and `:443`
over HTTPS, both failed. This almost certainly blocks claude.ai web's
custom-connector feature, which requires HTTPS for remote MCP servers —
this was the real blocker for "online agents" access, not just the
"claude mcp list reports Failed to connect" cosmetic issue noted earlier
today.

Also confirmed independently: even Claude Code's own registration of
`unified-gateway` isn't verified working — `ToolSearch` from inside a live
session that had the server registered mid-session returned **zero tools**
from it. Raw curl (init handshake, `tools/call`) works fine, so the server
itself is correct; whether a *fresh* Claude Code session actually loads
its tools is still unverified.

**Fixed and verified end-to-end, same day.** Three steps were needed, not
one — worth knowing the full chain if this ever needs reproducing
elsewhere:
1. DNS record for `context.kahatahi.co.nz` flipped to Cloudflare proxied
   (orange cloud) — gets free edge TLS, but Cloudflare's proxied mode only
   forwards to origin ports 80/443 by default, so this alone wasn't enough
   (requests still timed out).
2. Cloudflare **Origin Rule** (Rules -> Origin Rules) matching
   `Hostname equals context.kahatahi.co.nz`, action "Rewrite to origin
   port" -> 8423. Fixed the forwarding, but produced a new error:
   `HTTP 525` (Cloudflare-specific "SSL handshake failed with origin") --
   Cloudflare's zone-wide SSL/TLS mode is Full/Full-strict (needed for
   `api.kahatahi.co.nz`'s real Caddy/Let's Encrypt cert on the same zone),
   which means Cloudflare tries to speak HTTPS to the origin -- but
   unified-gateway only serves plain HTTP on 8423.
3. Cloudflare **Configuration Rule** (a different rule type from Origin
   Rules) matching the same hostname, overriding SSL/TLS mode to
   **Flexible** *scoped to this one hostname* (not zone-wide, which would
   have broken `api.kahatahi.co.nz`'s proper TLS) -- Cloudflare<->browser
   stays HTTPS, Cloudflare<->origin drops to plain HTTP, matching what
   unified-gateway actually speaks.

Verified working end-to-end after all three: unauthenticated request
correctly gets `401 {"error":"unauthorized"}` over HTTPS, authenticated
request gets a real `200` MCP `initialize` response. **Still not verified**:
whether a fresh Claude Code session or claude.ai web actually loads tools
from it (the "ToolSearch returns zero tools from a registered server"
issue noted below is about the MCP *client* side, separate from this
transport fix, and remains unconfirmed).

One side effect worth remembering: while `context.kahatahi.co.nz` was
proxied but the Origin Rule/Configuration Rule weren't in place yet, plain
`http://context.kahatahi.co.nz:8423/...` calls (used as a raw-curl
fallback throughout this session) stopped reaching the origin at all,
since DNS now resolves to Cloudflare's anycast IPs instead of the real
server. Worked around with `curl --resolve context.kahatahi.co.nz:8423:
137.23.17.157 ...` to bypass Cloudflare and hit the origin directly during
the gap -- useful trick if this ever needs debugging again, but the real
fix is having the Cloudflare rules in place, not relying on the bypass.

## 1b. A second connector was built for claude.ai specifically -- runs on
## the laptop, not Oracle, real tradeoff accepted deliberately

The Oracle-hosted `https://context.kahatahi.co.nz/mcp` above is fully
fixed and works with any client that can attach a custom `Authorization`
header. **claude.ai's own "Add custom connector" UI, as of 2026-07-28,
does not offer that** -- it only has a server URL field plus two
*optional* OAuth client id/secret fields, no custom-header option, and
unified-gateway doesn't implement OAuth. So claude.ai specifically cannot
reach the Oracle-hosted gateway no matter how correct the TLS setup is --
this was a separate, unrelated blocker discovered after the TLS fix
already worked for raw HTTP clients.

Also could not fix this on the Oracle side by deploying an OAuth-aware
version: **no SSH access exists in this working environment for
`context-repo-host` (137.23.17.157)** -- checked thoroughly (`~/.ssh/`,
OCI API keys, GCP-style auto-configured SSH blocks), no matching key
found. Whoever picks this up should either locate/restore that key, or
treat the laptop-hosted path below as the real answer for claude.ai
specifically and the Oracle one as the answer for everything else.

**What was built instead**: `surge-compute/unified_gateway/gateway_local.py`
-- same tool surface (`context_*` + `fs_*`) as the Oracle gateway.py, two
differences:
1. **Query-param token fallback**: `BearerAuthMiddleware` now also accepts
   `?token=<token>` in the URL when there's no `Authorization` header --
   the one field claude.ai's connector form actually lets you fill in.
   Same `secrets.compare_digest` check, same token file
   (`~/.oracle-services/unified-gateway-token`), just two ways in. Trade-
   off: the token ends up in server logs / browser history this way --
   accepted as proportionate given this only gates a personal project's
   context store and filesystem access, not a real production system.
2. **`fs_*` tools call `projectfsagent.tools` directly, in-process** --
   no wake-relay hop needed since the gateway and the filesystem it's
   exposing are now the same machine. Simpler and faster than the Oracle
   version's proxy-through-wake-relay design, but only possible because
   this *is* running on the laptop.

**Real architectural tradeoff, chosen deliberately by Nash, not a
default worth repeating**: this makes `context_*` access laptop-dependent
again -- exactly what migrating context-repo to Oracle earlier today was
meant to avoid. Chosen because (a) claude.ai can't reach the Oracle
gateway anyway per above, and (b) Cloudflare Tunnels' free path requires
a Zero Trust dashboard signup that's blocked by a credit-card requirement
tied to an unrelated Oracle signup dispute -- not something Nash wanted
to unblock today. **If claude.ai's connector UI later adds custom-header
support, or the Cloudflare card block gets resolved, or SSH access to the
Oracle box gets restored, revisit whether this laptop-hosted path is
still needed** -- it's a workaround for today's specific constraints, not
a permanent architecture decision.

**One-time data sync performed before standing this up**: the laptop
already had a *separate*, previously-diverging local context-repo store
(`context-repo/data/chroma.sqlite3`, the one the OTHER live Claude Code
session's local stdio MCP connection was writing to all day) -- it had
zero overlap with today's Oracle-side writes before this sync. Pulled all
8 compartments (224 facts total) from the Oracle store via
`context_checkpoint` and wrote them into the local store using its own
similarity-based dedup (`store.write`'s merge-vs-insert logic) -- 15
facts were genuinely new to the local store, 209 were already present.
**Going forward, the local store is what `gateway_local.py` reads/writes
-- it will drift from the Oracle one again unless re-synced.** No
automatic sync exists; if this matters later, build one rather than
assuming the two stay aligned.

**Stable URL**: claude.ai custom connectors need a URL that doesn't
change on restart. Two attempts before landing on the working one:
- Cloudflare quick tunnel (`cloudflared tunnel --url ...`, no login
  needed) -- works but the `*.trycloudflare.com` hostname is randomly
  regenerated every time the process restarts, unusable for a saved
  connector config.
- Cloudflare *named* tunnel (stable hostname, needs `cloudflared tunnel
  login` or the Zero Trust dashboard) -- blocked, dashboard path requires
  a credit card Nash has deliberately left blocked (unrelated dispute
  with Oracle over a separate signup attempt).
- **ngrok's free-tier static domain** (already had an authenticated
  ngrok install and account from before) -- this is what's actually
  running: `alesia-unforgetful-victor.ngrok-free.dev`, permanent as long
  as the ngrok account exists, doesn't change on restart. Runs alongside
  the *other*, pre-existing `ngrok http 8421` tunnel (the local
  context-repo mirror mentioned above) -- ngrok supports multiple
  concurrent agent sessions under one account without conflict, confirmed
  by running both simultaneously.

**Made persistent via launchd** (same pattern as the existing
`com.nash.wake-poller` job): two new LaunchAgents,
`~/Library/LaunchAgents/com.nash.unified-gateway-local.plist` (runs
`gateway_local.py` via context-repo's venv, `KeepAlive` + `RunAtLoad`,
logs to `/tmp/unified_gateway_local.log`) and
`com.nash.ngrok-gateway-tunnel.plist` (runs `ngrok http --domain=...
8423`, same persistence pattern, logs to `/tmp/ngrok_gateway_tunnel.log`).
Both survive a laptop restart and auto-restart if either process dies.
Hit the same FastMCP DNS-rebinding-protection issue as project-fs-agent's
tunnel setup earlier today (`421 Invalid Host header` until the tunnel's
actual hostname is added to `allowed_hosts` -- fixed the same way, via an
env var, `UNIFIED_GATEWAY_ALLOWED_HOST`).

Verified end-to-end after making it persistent (not just when manually
foregrounded): `https://alesia-unforgetful-victor.ngrok-free.dev/mcp?token=<token>`
correctly returns `401` with no token, `200` with the query-param token,
and both `context_list_compartments` and `fs_list` tool calls succeed
through the tunnel.

## 1c. Real SSH access to the Oracle box existed all along -- correction
## to section 1b above

**Correction, same day**: section 1b above says "no SSH access exists in
this working environment for `context-repo-host`" -- that was wrong, just
not yet discovered. `~/.ssh/gcp_key` (already present locally, named for
GCP but apparently also authorized on the Oracle box during initial
setup) works fine: `ssh -i ~/.ssh/gcp_key ubuntu@137.23.17.157`. Found
this because several old background SSH deployment tasks from earlier in
the session (before a context-window compaction boundary, part of the
original OCI-watcher deployment work) finally reported back and revealed
the key had been used successfully hours earlier -- it just hadn't been
tried again when the TLS/connector work in section 1b ran into the
"no SSH access" wall. **Whoever needs to deploy to this box next: use
`gcp_key`, don't re-search for a missing key.**

With real deploy access confirmed, pushed the query-param-token fix (from
section 1b) to the *Oracle*-hosted `gateway.py` too (previously only the
laptop's `gateway_local.py` had it) -- deployed via
`scp -i ~/.ssh/gcp_key ... && ssh ... sudo systemctl restart unified-gateway`,
verified working. **This means the Oracle URL now supports the same
`?token=` fallback as the laptop one** --
`https://context.kahatahi.co.nz/mcp?token=<token>` -- which is the better
option going forward since it doesn't depend on the laptop staying on.
The laptop-hosted path from section 1b is now a redundant fallback, not
the only option -- keep both running for now (low cost) but treat Oracle
as primary.

## 1d. The actual connector fix: OAuth-discovery paths were 401ing,
## not 404ing, and that's what broke claude.ai specifically

Even after both URLs worked via raw curl, claude.ai's connector still
failed with **"Couldn't register with context-repo's sign-in service"**.
Root cause, found by tailing both servers' logs live while Nash retried
the connection: claude.ai's MCP client always probes
`/.well-known/oauth-protected-resource`, `/.well-known/oauth-authorization-server`,
and `POST /register` to discover OAuth support, *regardless of whether a
plain request to `/mcp` already succeeded* (confirmed in the logs: the
`?token=` request got a clean `200`, then these probe requests followed
immediately after). None of those paths are real routes on this app --
but `BearerAuthMiddleware` applied to every path uniformly, so they got
the same blanket `401` as any other unauthenticated request. claude.ai
reads `401` on those specific paths as "this server requires OAuth I
can't complete" and gives up entirely, even though the actual endpoint
it needs already works.

**Fix**: added an explicit exemption list (`_OAUTH_DISCOVERY_PATHS`) in
both `gateway.py` and `gateway_local.py` so those specific paths skip the
auth check and fall through to FastMCP's own routing -- which 404s them
naturally, since they don't exist. `404` is read by the client as "no
OAuth here, proceed with what you've got" rather than `401`'s "auth
required, and I don't know how." Verified: discovery paths now return
clean `404`s on both servers, the real `/mcp?token=...` endpoint still
works, and **Nash confirmed the claude.ai connector actually connects
now** -- this is the piece that made the whole day's TLS/tunnel/token work
actually usable end-to-end, not just reachable via curl.

**Lesson worth generalizing**: a bearer-auth middleware that blanket-
protects every path on an app is safe for security but can actively
break auto-discovery client behavior that expects a clean `404` to mean
"this feature isn't offered." Any future MCP server fronting claude.ai
(or similar) should explicitly allow well-known discovery/registration
paths through to natural 404s rather than gating them like real
endpoints.

## 2. GCP explorer outage — billing disabled, not investigated further

`https://api.kahatahi.co.nz/explorer/` (the corpus explorer, documented in
`task_corpus_explorer_live_backend.md`) is down. Root cause confirmed:
**billing is disabled on GCP project `sapient-zodiac-502400-k2`**
(`contact@kaha-tahi.com`) — `gcloud compute instances describe` on the VM
that hosts it (`instance-20260722-010225`) fails with "This API method
requires billing to be enabled." GCP stops billable resources when billing
is disabled, consistent with the VM being fully unreachable at the TCP
level (not just the app being down).

This project is one of the two GCP accounts a *separate* session was
building a billing hard-stop safety mechanism for today (a Cloud Function
triggered by a Pub/Sub budget alert that actually calls the Billing API to
disable billing — see section 7 of the prior wrap-up doc).

**Resolved, with a real design flaw confirmed**: Nash confirmed the
mechanism fired as designed, not a bug in the sense of malfunctioning —
but the threshold itself is too blunt. The account had used **$414 in the
past month** against credit that's now down to ~$84, and the hard-stop cut
billing the instant usage crossed *whatever threshold it was configured
with*, with no gradation — killing the always-free-tier explorer VM along
with anything actually expensive. Nash's direction: **re-enable billing
now** (done — `gcloud billing projects link sapient-zodiac-502400-k2
--billing-account=01F51D-F852DB-0E42E4`, VM restarted, explorer confirmed
back at HTTP 200), but **don't use this account (`contact@kaha-tahi.com`)
for any AI/Cloud Run calls beyond the always-free tier it currently uses**
until the hard-stop gets a more subtle design (e.g. graduated
alert-then-throttle rather than one binary cutoff, or a cutoff threshold
that accounts for the always-free baseline separately from paid usage).
**Whoever built the original hard-stop mechanism should revisit the
threshold logic** — this isn't a one-off glitch, the binary
cutoff-at-threshold design itself is the problem.

## 3. Bigger open-weight model re-judge of entity-stance disagreements

The entity-stance classifier reliability finding (33-36% match rate,
section 1 of the prior wrap-up doc) was re-run against a *bigger* model to
help settle whether the classifier or the small 1.5B judge is wrong.

- Pulled the original judge output (`tobiasnashktc/entity-stance-judge`,
  2,518 rows) and recomputed disagreements directly from
  `predicted_label` vs `judged_label` (this file's own `matches` field
  *is* trustworthy here — cross-tab against the recomputed value is a
  perfect match, unlike the degenerate `matches_label` field found
  elsewhere in the citation-window job. Don't assume every AIITL job has
  the same degenerate-field bug; check each one).
- 1,606 genuine disagreement rows (excluding judge parse errors) pulled
  into `entity_stance_disagreements.parquet`.
- New kernel: `surge-compute/kaggle_entity_stance_bigmodel_kernel/
  entity_stance_bigmodel_judge.py` — Qwen2.5-7B-Instruct (still free,
  open-weight; 4-bit quantized via bitsandbytes to fit a T4's 16GB
  comfortably), re-judges each disagreement case with a self-reported
  confidence rubric (high/medium/low, explicit criteria for each) so a
  human reviewer can triage down to the high-confidence-disagreement
  subset instead of reading all 1,606 by hand.
- Pushed to `manawatusamaritans/entity-stance-bigmodel-judge` (the one
  account not in use by the other session at push time) — **check
  `kaggle kernels status manawatusamaritans/entity-stance-bigmodel-judge`
  for current state**, was RUNNING as of this doc being written.
- **What this will and won't settle**: if the 7B model still disagrees
  with the classifier at a similar rate on these same cases, that's real
  evidence the classifier itself is wrong (a much better model, with
  explicit confidence self-assessment, still doesn't back it up) rather
  than the small judge being under-provisioned. If it mostly sides with
  the classifier instead, the earlier finding flips around. Either way,
  a human still needs to read the high-confidence-disagreement subset to
  make the final call — this doesn't eliminate that need, just shrinks it
  from ~1,600 rows to whatever's flagged high-confidence.

**Result, completed same day**: the 7B model corroborates the small
judge, doesn't undermine it. Across all 1,606 disagreement cases it
agrees with the classifier only 24.4% of the time and with the 1.5B judge
51.6% of the time. On its own high-confidence subset (467 rows) it sides
with the small judge **69.2%** of the time vs. the classifier's 26.6%.
Manually spot-checked the 323 rows where both judges agree against the
classifier (`data/processed/entity_stance_priority_review.parquet`) —
these are not borderline calls: "died of Aids" about an AIDS denier
scored **endorsement** by the classifier (obviously hostile mockery);
"lol at paul joseph watson" scored **other** (obviously hostile); Andrew
Huberman praised alongside other "good health-related episodes" scored
**hostile** (obviously endorsement); "Great job you've been doing" about
Brett Giroir scored **hostile** (obviously endorsement).

**This is now a real, corroborated finding, not just a red flag**: the
production entity-stance classifier has a genuine reliability problem
independent of the small judge's own limitations. Full output saved to
`data/processed/entity_stance_bigmodel_judged.parquet` (all 1,606 rows)
and `data/processed/entity_stance_priority_review.parquet` (the 323-row
highest-confidence-agreement subset, small enough for a final manual
check if still wanted before treating this as settled). This should now
be treated as blocking further work that depends on entity-stance labels
being correct (`build_extended_entity_stance.py`,
`build_maverick_stance_queue.py`, and any consensus/maverick breakdown
built on top of them) until the classifier itself is investigated or
replaced — not filed away as an open question anymore.

## 4. Entity dedup — deterministic pass, real bug found and fixed mid-build

Built `src/build_entity_canonical_map.py`: groups
`corpus_entity_frequency.csv`'s 683,635 entity strings by case-folded,
punctuation-stripped normalization (e.g. "Covid"/"COVID"/"covid" -> one
canonical form, the highest-`doc_count` variant). Deliberately does NOT
use the entity-coverage AIITL judge's free-text `reason` field as a merge
target — spot-checking that output found it calling "MSM" a misspelling
of "media services", "Wikipedia" a misspelling of "encyclopedia", "NYT" a
misspelling of "New York Times" (backwards — NYT is an abbreviation, not
a misspelling). A 1.5B model's free-text reasoning about *what something
is a variant of* is not reliable enough to drive automated merges;
string-identical-modulo-case is a much safer, more limited claim to
automate.

**Real bug hit and fixed while building this**: the naive normalization
regex (`[^a-z0-9 ]` stripped) collapses anything with no ASCII letters —
emoji, Cyrillic/Arabic script, box-drawing characters, and Unicode
"mathematical alphanumeric" stylized text (used to fake bold/italic Latin
letters in some comments) — down to an empty or whitespace-only string.
First pass merged 782 completely unrelated entities into a fake cluster
keyed on emptiness (canonical form ended up literally being "🤔🤔🤔").
Second attempt still failed the same way for multi-word Unicode-symbol
strings, because the original `.strip()` ran *before* punctuation removal,
so leftover internal whitespace from stripped characters didn't collapse.
Fixed by collapsing whitespace and re-stripping *after* the punctuation
regex, then falling back to the original string (not the empty
normalized form) as the grouping key for anything that normalizes to
nothing. Verified via spot-check before and after — this is worth reading
the script's own comments if extending it, the failure mode is not obvious
until you look at what actually ends up in the biggest "duplicate"
clusters.

**Result**: 683,635 -> 600,558 distinct entity strings (12.2% reduction),
zero LLM calls, zero risk of wrong semantic merges since every merge is a
literal case/punctuation match. Output:
`data/processed/entity_canonical_map.csv` (one row per original entity,
its normalized form, assigned canonical form, cluster size) and
`data/processed/entity_canonical_aggregated.csv` (one row per canonical
form, summed doc_count).

**Not done**: abbreviation/acronym expansion (MSM -> mainstream media,
NYT -> New York Times, WaPo -> Washington Post) is a genuinely different,
harder problem needing real-world knowledge rather than string
similarity — explicitly out of scope for this mechanical pass, and not
something the entity-coverage judge's reasoning can be trusted for either
(see above). If this matters, it needs a dedicated small task with a
verified-correct reference list, not a mechanical or free-text-LLM
solution.

## 5. Corrupted entity-frequency CSVs — one was never actually broken

Correction to a claim in the prior wrap-up doc: **`corpus_entity_frequency_
final.csv` was never corrupted.** Re-tested with plain
`pandas.read_csv()` — reads fine, 526,202 rows, matches its own docstring
count exactly. It's also the one 3 real scripts (`wikidata_entity_
lookup.py`, `stage_g_auto_disambiguate.py`, `run_mainstream_expert_
alignment.py`) actually read, so this matters — nothing was ever blocked.

`corpus_entity_frequency_cleaned.csv` genuinely was broken (C-engine
parser buffer overflow from unescaped embedded newlines/quotes in
`example_1`), but `DATA_MANIFEST.md` already lists this file as an
**orphan — no script reads it**, so it wasn't blocking anything either.
Repaired anyway for completeness: read with pandas' Python engine
(handles the malformed rows), re-saved with proper quoting. 610,558 of
610,573 rows fully recovered; ~130 rows (0.02%) lost fields from
genuinely unrecoverable corruption (some `example_1`/`label`/`doc_count`
values are NaN in the repaired file). `bucket` is NaN for all 610,558
rows — pre-existing, not something this repair touched, worth knowing if
anyone ever does want to read this orphan file.

## 6. Source-stance Tier2 sampling bug — root-caused and fixed, not re-run

See the other session's message (relayed in this conversation) for the
original finding: an implausible 100% judge/classifier agreement on the
non-contaminated subset of a "low-confidence" resample.

Root cause: `build_source_stance_tier2_sample.py` computed a single
global bottom-50%-by-margin cutoff across all three predicted labels
(hostile/endorsement/other) to define the "uncertain band." The
classifier is systematically far more confident whenever it predicts
`other` than hostile/endorsement, so the global cutoff pulled `other`
almost entirely out of the sample (4/5998 rows in the earlier run vs a
~9% true base rate) — the "uncertain band" was actually "hostile vs
endorsement, filtered to the hard cases," not a genuine reflection of
uncertainty across all three classes. That structural narrowing to an
easier binary call is consistent with the implausible near-100% agreement
result.

**Fixed**: cutoff is now computed as the median margin *within* each
predicted_label group separately, so each class contributes its own
bottom-50% to the combined uncertain pool. Verified locally: `other` now
sits at 9.0% of the reddit uncertain band and 31.4% of the ats band,
tracking real base rates. `data/processed/source_stance_tier2_sample.parquet`
(6,000 rows, corrected) is already regenerated. `source_stance_tier2_
judge.py` needs zero changes — same input schema.

**Not pushed to Kaggle** — this is the other session's kernel
(`tobiasnashws/source-stance-tier2-judge`) and account, deliberately left
for them to re-run rather than pushing a competing version under their
kernel slug, per Nash's explicit instruction not to collide with that
session's Kaggle usage. Messaged them directly with the fix.

**Re-run result: the sampling fix was correct but didn't fix the real
problem.** The other session re-ran with the corrected sample (`other`
verified at 9.2%/30.1% by platform, matching base rate) and the
near-100% non-contaminated agreement persisted anyway (99.6%). Real root
cause, found by reading actual judge output text: **89.6% (474/529) of
the judge's `reason` fields literally say some variant of "the classifier
correctly identifies..."** — anchoring/sycophancy, not independent
judgment. The prompt shows the judge the classifier's `predicted_label`
and asks it to assess whether that category is "defensible" — which
primes confirmation rather than an independent read.

**This has a bigger implication than just this one Tier2 run**: the same
prompt pattern was used in the *original*
`source_stance_aiitl_judged_corrected.parquet` (the "32-45% match rate
once contamination is excluded" figure reported in section 2 of the
2026-07-28 wrap-up doc). **That figure should now be treated as
unreliable too, and probably optimistic** — if anchoring inflates
agreement, true citation-window classifier reliability could be *worse*
than 32-45%, not better. Only the contamination/`not_real_citation` calls
(~88.2% ATS / ~83.0% Reddit) still hold up — that's a more surface-level
judgment (spotting boilerplate/copypasta) less susceptible to this
specific bias.

**Contrast worth keeping**: `entity_stance_judge.py` has a structurally
similar predicted-label-in-prompt design but did NOT show this anchoring
pattern — its 33-36% disagreement finding was independently corroborated
by a bigger model (section 3) and manual spot-check. So showing a model
the predicted label isn't inherently unsafe — this specific citation
prompt's exact phrasing ("is this defensible under the given label")
is what invites the sycophancy. **Any future judge prompt that grades a
given label rather than asking for a blind independent choice should be
treated as suspect until checked for this pattern** — read a sample of
the actual `reason` text, not just the label distribution, before
trusting an agreement number.

**Final, authoritative result (blind re-judge, `tobiasnashws/source-
stance-blind-judge`, same day)**: the other session built the blind
version (predicted_label never shown to the model at all; match/mismatch
computed after the fact in the script, not model-reported) and got real
numbers with no anchoring:
- **Non-contaminated agreement: 59.2% overall** (ATS 64.9%, Reddit
  41.2%) — a genuine, moderate, real disagreement rate. Notably *higher*
  than the originally-reported 32-45%, the opposite direction from the
  contamination correction below — the anchoring bias didn't uniformly
  inflate everything, it distorted different numbers in different
  directions depending on what was being asked.
- **Contamination itself dropped from 91% (anchored Tier2 rerun) to
  43% (blind)** — more than half. This has a bigger implication than the
  Tier2 run alone: the *original* "88.2% ATS / 83.0% Reddit"
  contamination finding from this morning's
  `source_stance_aiitl_judged_corrected.parquet` run (section 2 of
  `task_2026-07-28_session_wrapup.md`, presented there as "quantified at
  real scale") used the identical predicted-label-shown prompt and is
  **now retracted, not just caveated** — see that file, now corrected in
  place. Contamination classification was assumed to be surface-level
  and anchor-resistant when this bug was first found; that assumption
  was wrong, it moved just as much as the directional judgment did.

**Take the corrected figures (43% contamination, 59.2% agreement) as the
current best estimate**, written to context-repo as
`job_source_stance_blind_judge_AUTHORITATIVE_2026-07-28`. Any thesis
writing that already cites 88.2%/83.0% contamination or 32-45% agreement
needs updating before this goes further — those numbers are not "close
enough," they were built on a since-confirmed-broken measurement method.

## Cross-session coordination — two live Claude Code sessions today

A second Claude Code session (id `local_73e80c9f-c5b8-42f6-b4d5-df27d6e1150d`,
title "Kaggle and Reddit embedding status") was independently active on
this exact repo for most of today, running its own Tier2 cascade resample
jobs and an entity-coverage AIITL judge. Real duplicate work happened
before either session noticed (see `context-repo`'s `conspiracycomments`
compartment for the full blow-by-blow) — both built near-identical
entity-coverage/entity-noise judges independently, wasting Kaggle quota on
two accounts running the same thing.

**Before pushing anything to Kaggle**: run `context_checkpoint` on the
`conspiracycomments` compartment AND check `kaggle kernels list -m` on
all 4 accounts (tobiasnashktc, tobiasnashws, tobiasnash,
manawatusamaritans) for currently-RUNNING kernels. There is no way to
cancel a running Kaggle kernel via the CLI once pushed — the only real
prevention is checking before pushing, not after.

## What's explicitly NOT done — quick scan list (this session)

- TLS fix for `context.kahatahi.co.nz` — DNS change handed to Nash
  (Cloudflare dashboard, no API token available), not yet verified.
- Whether Claude Code (any fresh session, not this long-running one)
  actually loads `unified-gateway`'s tools — still unverified.
- claude.ai web custom-connector setup itself — manual step in Nash's
  account, not started as far as this session knows.
- GCP billing re-enable decision for `sapient-zodiac-502400-k2` — explicit
  Nash call needed, not made here.
- Bigmodel entity-stance re-judge — pushed, running as of this doc, output
  not yet pulled/analyzed.
- Source-stance Tier2 re-run with the corrected sample — fix built and
  verified locally, not pushed to Kaggle (see section 6).
- Abbreviation/acronym entity expansion (MSM, NYT, WaPo, etc.) — explicitly
  out of scope for the dedup pass built here, needs its own approach.
- `too_generic_institutional` category never once assigned by the
  entity-coverage judge — flagged by the other session, not investigated
  in this session either.
