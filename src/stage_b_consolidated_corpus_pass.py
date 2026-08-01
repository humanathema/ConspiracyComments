"""Stage B of the entity-disambiguation work program (ANTIGRAVITY_HANDOFF.md
§12). One consolidated pass over the full 21.4M-row corpus, capturing two
things that would otherwise need separate scans:

1. Word-bag collection for Yarowsky-style per-instance disambiguation.
   For each ambiguous bare name (e.g. "Bill"), we don't know who's meant.
   But every time the FULL, unambiguous name appears ("Bill Clinton", "Bill
   Gates", "Bill Kristol"), that's a free label -- pull the surrounding
   words from those instances to build each candidate's characteristic
   vocabulary ("labeled" bags). Separately, pull surrounding words from
   every BARE "Bill" instance ("unlabeled" bags, to be classified in Stage
   C against the labeled profiles). Capped per candidate to bound memory/
   runtime -- profiles stabilize well before thousands of samples.

2. Credential-pattern regex extraction: "(former|ex-) (CIA|FBI|...)
   (officer|agent|analyst)" plus the nearby capitalized name -- surfaces
   new maverick_authority-relevant candidates that might be too rare
   on their own to have cleared the doc_count>=20 floor, but show up
   specifically in this high-signal, construct-relevant pattern.

Runtime: Aho-Corasick + regex over 21.4M rows benchmarks at ~7-12 min
regardless of pattern-list size (see build_maverick_candidate_list.py,
extract_entity_context_windows.py) -- this is NOT the expensive part of the
pipeline. The expensive part is any subsequent external API calls, which
this stage avoids entirely.

Output:
    data/processed/stage_b_word_bags.json -- {cluster: {candidate: [bags]}}
    data/processed/stage_b_credential_pattern_hits.csv
"""
import json
import os
import pickle
import re
import time
from collections import defaultdict
import argparse

import ahocorasick
import pandas as pd
import pyarrow.parquet as pq

CORPUS_PATH = "data/processed/empath_scores_full_mapped.parquet"
WORDBAGS_OUT = "data/processed/stage_b_word_bags.json"
CREDENTIAL_OUT = "data/processed/stage_b_credential_pattern_hits.csv"

WINDOW_WORDS = 15  # words each side of a match, for word-bag collection
MAX_SAMPLES_PER_CANDIDATE = 2000  # cap -- profiles stabilize well before this
STOPWORDS = set("""the a an and or but if of to in on at for with by from as is
are was were be been being this that these those it its he she they them his
her their i you we me my your our not no so do does did have has had will
would can could should just very really like about""".split())

# entity -> {bare: [...], candidates: {full_name: [...aliases...]}}
# Candidate sets are informed by what Stage-earlier corpus-context checks
# actually found (e.g. "Hunter" -> Thompson, not just the assumed Biden;
# "Bill" -> Gates/Kristol/Clinton all attested). Extend this dict as more
# ambiguous clusters are found -- it's the main thing a future session
# would want to add to.
AMBIGUOUS_CLUSTERS = {
    "bill": {
        "bare": ["bill"],
        "candidates": {
            "Bill Clinton": ["bill clinton"],
            "Bill Gates": ["bill gates"],
            "Bill Kristol": ["bill kristol"],
        },
    },
    "hunter": {
        "bare": ["hunter"],
        "candidates": {
            "Hunter S. Thompson": ["hunter s. thompson", "hunter thompson", "hunter s thompson"],
            "Hunter Biden": ["hunter biden"],
        },
    },
    "kennedy": {
        "bare": ["kennedy"],
        "candidates": {
            "John F. Kennedy": ["john f. kennedy", "john f kennedy", "jfk"],
            "John F. Kennedy Jr.": ["john f. kennedy jr", "jfk jr"],
            "Robert F. Kennedy Jr.": ["robert f. kennedy jr", "rfk jr", "bobby kennedy"],
        },
    },
    "clinton": {
        "bare": ["clinton"],
        "candidates": {
            "Bill Clinton": ["bill clinton"],
            "Hillary Clinton": ["hillary clinton"],
        },
    },
    "sanders": {
        "bare": ["sanders"],
        "candidates": {
            "Bernie Sanders": ["bernie sanders"],
            "Sarah Sanders": ["sarah sanders", "sarah huckabee sanders"],
        },
    },
    "rich": {
        "bare": ["rich"],
        "candidates": {
            "Seth Rich": ["seth rich"],
        },
    },
    "tucker": {
        "bare": ["tucker"],
        "candidates": {
            "Tucker Carlson": ["tucker carlson"],
        },
    },
    "hawking": {
        # Added 2026-07-20: "Hawking" was a blind bare-form alias for
        # Stephen Hawking (VERIFIED_CONSENSUS_EXPERTS) with no
        # disambiguation -- caught matching the common verb "hawking"
        # (selling), confirmed by hand-reviewing HITL stance queue rows.
        # Negative-class labels seeded from literal verb-usage phrases
        # (same free-labeling trick as the other clusters, just with a
        # generic-usage class instead of a second named person).
        "bare": ["hawking"],
        "candidates": {
            "Stephen Hawking": ["stephen hawking", "steven hawking"],
            "hawking (verb, not a person)": [
                "hawking his", "hawking her", "hawking their", "hawking your",
                "hawking wares", "hawking goods", "hawking merch",
                "hawking products", "hawking cigarettes", "hawking snake oil",
                "hawking books", "hawking bibles", "hawking shoes",
                "war hawking", "keep hawking", "still hawking",
                "was hawking", "is hawking", "hawking training",
            ],
        },
    },
}

MAVERICK_AMBIGUOUS_CLUSTERS = {
    "manning": {
        "bare": ["manning"],
        "candidates": {
            "Chelsea Manning": ["chelsea manning"],
            "Bradley Manning": ["bradley manning"],
        },
    },
    "jones": {
        "bare": ["jones"],
        "candidates": {
            "Alex Jones": ["alex jones"],
            "Steven E. Jones": ["steven e. jones", "steven jones", "steve jones"],
        },
    },
    "adams": {
        "bare": ["adams"],
        "candidates": {
            "Mike Adams": ["mike adams"],
            "Jerome Adams": ["jerome adams", "dr. adams", "dr adams"],
            "Stanley Adams": ["stanley adams"],
            "Jad Adams": ["jad adams"],
        },
    },
    "watkins": {
        "bare": ["watkins"],
        "candidates": {
            "Jim Watkins": ["jim watkins"],
            "Ron Watkins": ["ron watkins"],
            "Sherron Watkins": ["sherron watkins"],
        },
    },
    "garrison": {
        "bare": ["garrison"],
        "candidates": {
            "Ben Garrison": ["ben garrison"],
            "Jim Garrison": ["jim garrison"],
        },
    },
    "cooper": {
        "bare": ["cooper"],
        "candidates": {
            "Milton William Cooper": ["milton william cooper", "william cooper", "bill cooper"],
            "Cynthia Cooper": ["cynthia cooper"],
        },
    },
    "mccarthy": {
        "bare": ["mccarthy"],
        "candidates": {
            "Jenny McCarthy": ["jenny mccarthy"],
            "Joseph McCarthy": ["joseph mccarthy", "joe mccarthy"],
        },
    },
    "webb": {
        "bare": ["webb"],
        "candidates": {
            "Whitney Webb": ["whitney webb"],
            "Gary Webb": ["gary webb"],
        },
    },
    "malone": {
        "bare": ["malone"],
        "candidates": {
            "Robert W. Malone": ["robert w. malone", "robert malone", "dr malone", "dr. malone"],
            "Post Malone": ["post malone"],
        },
    },
    "ventura": {
        # Added 2026-07-20: "Ventura" was a blind bare-form alias for Jesse
        # Ventura with no disambiguation -- picks up "Ventura County"/
        # "Ventura, California" (place name), confirmed by hand-reviewing
        # corpus samples during the audit that also found the "Brand" and
        # "Hawking" contamination.
        "bare": ["ventura"],
        "candidates": {
            "Jesse Ventura": ["jesse ventura"],
            "Ventura (place name, not a person)": [
                "ventura county", "ventura, california", "ventura, ca",
                "ventura freeway", "port of ventura", "ventura boulevard",
            ],
        },
    },
    "hancock": {
        # Added 2026-07-20: same audit -- bare "Hancock" mostly resolves to
        # Graham Hancock (the actual maverick) but occasionally picks up
        # Matt Hancock (UK politician, different real person entirely).
        "bare": ["hancock"],
        "candidates": {
            "Graham Hancock": ["graham hancock"],
            "Matt Hancock": ["matt hancock"],
        },
    },
    "kory": {
        # Added 2026-07-20: same audit -- bare "Kory" mostly resolves to
        # Pierre Kory but at least one instance was "Kory Langhofer"
        # (Trump campaign lawyer, different real person). Low volume (52
        # corpus matches) but cheap to add now the framework is here.
        "bare": ["kory"],
        "candidates": {
            "Pierre Kory": ["pierre kory", "dr. kory", "dr kory"],
            "Kory (other person, surname collision)": ["kory langhofer"],
        },
    },
}

CREDENTIAL_PATTERN = re.compile(
    r"\b(former|ex-|retired)\s+(CIA|FBI|NSA|DIA|DEA|MI5|MI6|KGB)\s+"
    r"(officer|agent|analyst|operative|employee|contractor|trainee)\b",
    re.IGNORECASE,
)
NEARBY_NAME_PATTERN = re.compile(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2})\b")



def extract_word_bag(text, match_start, match_end, exclude_words):
    before = text[:match_start].split()[-WINDOW_WORDS:]
    after = text[match_end:].split()[:WINDOW_WORDS]
    words = [w.strip(".,!?;:\"'()[]").lower() for w in before + after]
    return [w for w in words if w and w not in STOPWORDS and w not in exclude_words and len(w) > 2]


_WORD_CHAR_RE = re.compile(r"[a-z0-9]")


def build_automaton(alias_to_candidate, bare_to_cluster):
    """Single Aho-Corasick automaton over every alias and bare form, so each
    comment's text is scanned ONCE (O(text length) total) regardless of how
    many patterns exist, instead of the previous per-row nested loop over
    every alias/bare string (O(rows x patterns)) -- this is what the
    module's own docstring always claimed the design was, but the actual
    code underneath had drifted to naive `.find()` loops instead. Bare-form
    entries get a boundary check at match time (cheap -- one char lookup on
    each side of an actual hit) rather than baking boundary markers into the
    automaton itself."""
    A = ahocorasick.Automaton()
    for alias, payload in alias_to_candidate.items():
        A.add_word(alias, ("alias", alias, payload))
    for bare, cluster_key in bare_to_cluster.items():
        A.add_word(bare, ("bare", bare, cluster_key))
    A.make_automaton()
    return A


def scan_row(text_l, automaton, cluster_dict, sample_counts, word_bags, row_id, priority_ids):
    """Runs the automaton once over this row's text, then applies the same
    labeled/bare-form bookkeeping the old nested-loop version did (sample
    caps, skip-bare-if-full-form-present), just without re-scanning the text
    once per pattern to get there."""
    alias_hits = []   # (end_idx, alias, cluster_key, cand_name)
    bare_hits = []    # (end_idx, bare, cluster_key)
    clusters_with_full_form = set()

    for end_idx, (kind, pattern, payload) in automaton.iter(text_l):
        start_idx = end_idx - len(pattern) + 1
        if kind == "alias":
            cluster_key, cand_name = payload
            alias_hits.append((start_idx, end_idx, pattern, cluster_key, cand_name))
            clusters_with_full_form.add(cluster_key)
        else:
            # boundary check: bare form must not be part of a longer word
            before_ok = start_idx == 0 or not _WORD_CHAR_RE.match(text_l[start_idx - 1])
            after_ok = end_idx + 1 >= len(text_l) or not _WORD_CHAR_RE.match(text_l[end_idx + 1])
            if before_ok and after_ok:
                bare_hits.append((start_idx, end_idx, pattern, payload))

    for start_idx, end_idx, alias, cluster_key, cand_name in alias_hits:
        sample_key = (cluster_key, cand_name)
        if sample_counts[sample_key] >= MAX_SAMPLES_PER_CANDIDATE:
            continue
        bag = extract_word_bag(text_l, start_idx, end_idx + 1, {alias})
        if bag:
            word_bags[cluster_key][cand_name].append(bag)
            sample_counts[sample_key] += 1

    for start_idx, end_idx, bare, cluster_key in bare_hits:
        if cluster_key in clusters_with_full_form:
            continue
        sample_key = (cluster_key, "__bare__")
        if sample_counts[sample_key] >= MAX_SAMPLES_PER_CANDIDATE and str(row_id) not in priority_ids:
            continue
        bag = extract_word_bag(text_l, start_idx, end_idx + 1, {bare})
        if bag:
            word_bags[cluster_key]["__bare__"].append({"id": row_id, "bag": bag})
            sample_counts[sample_key] += 1


def find_credential_pattern_names(text):
    hits = []
    for m in CREDENTIAL_PATTERN.finditer(text):
        window = text[max(0, m.start() - 60):m.end() + 60]
        names = NEARBY_NAME_PATTERN.findall(window)
        for n in names:
            if n.lower() not in {"cia", "fbi", "nsa", "dia", "dea"} and len(n) > 3:
                hits.append((n, m.group(0), window.replace("\n", " ").strip()))
    return hits


def main():
    parser = argparse.ArgumentParser(description="Stage B consolidated corpus pass")
    parser.add_argument("--maverick", action="store_true", help="Run maverick disambiguation mode")
    parser.add_argument("--mainstream", action="store_true", help="Run mainstream expert mode")
    parser.add_argument("--ats", action="store_true", help="Run on AboveTopSecret (ATS) corpus")
    parser.add_argument("--fresh", action="store_true", help="Ignore any existing checkpoint and start over")
    args = parser.parse_args()

    if args.ats:
        corpus_path = "data/processed/ats_comments_final.parquet"
        id_col = "post_id"
        text_col = "body"
        if args.maverick:
            cluster_dict = MAVERICK_AMBIGUOUS_CLUSTERS
            wordbags_out = "data/processed/stage_b_ats_maverick_word_bags.json"
            credential_out = "data/processed/stage_b_ats_maverick_credential_hits.csv"
            mode_name = "ATS Maverick Expert"
        else:
            cluster_dict = AMBIGUOUS_CLUSTERS
            wordbags_out = "data/processed/stage_b_ats_word_bags.json"
            credential_out = "data/processed/stage_b_ats_credential_hits.csv"
            mode_name = "ATS Mainstream Expert"
    else:
        corpus_path = CORPUS_PATH
        id_col = "id"
        text_col = "text"
        if args.maverick:
            cluster_dict = MAVERICK_AMBIGUOUS_CLUSTERS
            wordbags_out = "data/processed/stage_b_maverick_word_bags.json"
            credential_out = "data/processed/stage_b_maverick_credential_hits.csv"
            mode_name = "Maverick Expert"
        else:
            cluster_dict = AMBIGUOUS_CLUSTERS
            wordbags_out = WORDBAGS_OUT
            credential_out = CREDENTIAL_OUT
            mode_name = "Mainstream Expert"

    print(f"Running in {mode_name} mode...")

    # Load validation queue comment IDs to bypass max-sample capping for bare instances
    priority_ids = set()
    if not args.ats:
        try:
            val_df = pd.read_csv("data/hitl/queue_maverick_authority.csv")
            if "id" in val_df.columns:
                priority_ids = set(val_df["id"].dropna().astype(str))
                print(f"Loaded {len(priority_ids)} priority comment IDs from validation queue")
        except Exception as e:
            print(f"Warning: could not load validation queue: {e}")

    # Build a simple lowercase substring search structure: for each cluster,
    # bare form(s) and every candidate alias, so a single lowercase scan of
    # each comment's text can tag which (if any) it matched.
    bare_to_cluster = {}
    alias_to_candidate = {}  # alias (lowercase) -> (cluster_key, candidate_name)
    for cluster_key, spec in cluster_dict.items():
        for b in spec["bare"]:
            bare_to_cluster[b] = cluster_key
        for cand_name, aliases in spec["candidates"].items():
            for a in aliases:
                alias_to_candidate[a] = (cluster_key, cand_name)

    automaton = build_automaton(alias_to_candidate, bare_to_cluster)

    # Checkpoint: resume from the last fully-completed chunk rather than
    # restart from scratch if this run gets killed/interrupted (real risk on
    # a run this long, and the exact scenario that motivated adding this --
    # a mid-run kill earlier today lost everything since the old version
    # only wrote output at the very end).
    checkpoint_path = wordbags_out + ".checkpoint.pkl"
    start_chunk = 0
    word_bags = {c: {"__bare__": []} for c in cluster_dict}
    for c, spec in cluster_dict.items():
        for cand in spec["candidates"]:
            word_bags[c][cand] = []
    sample_counts = defaultdict(int)
    credential_hits = []

    if not args.fresh and os.path.exists(checkpoint_path):
        with open(checkpoint_path, "rb") as f:
            ckpt = pickle.load(f)
        word_bags = ckpt["word_bags"]
        sample_counts = defaultdict(int, ckpt["sample_counts"])
        credential_hits = ckpt["credential_hits"]
        start_chunk = ckpt["next_chunk"]
        print(f"Resuming from checkpoint: {start_chunk} chunk(s) already done "
              f"({ckpt['total_rows']:,} rows), {len(credential_hits):,} credential hits so far.")

    pf = pq.ParquetFile(corpus_path)
    total = start_chunk * 1_000_000
    start = time.time()
    for i, batch in enumerate(pf.iter_batches(batch_size=1_000_000, columns=[id_col, text_col])):
        if i < start_chunk:
            continue
        chunk = batch.to_pandas()
        total += len(chunk)

        ids = chunk[id_col].tolist()
        texts = chunk[text_col].tolist()
        for row_id, text in zip(ids, texts):
            if not isinstance(text, str) or len(text) < 5:
                continue
            text_l = text.lower()

            # credential-pattern scan (cheap regex, only runs if trigger words present)
            if "former" in text_l or "ex-" in text_l or "retired" in text_l:
                for name, trigger, window in find_credential_pattern_names(text):
                    credential_hits.append({"name": name, "trigger": trigger,
                                             "context": window, "id": row_id})

            scan_row(text_l, automaton, cluster_dict, sample_counts, word_bags, row_id, priority_ids)

        elapsed_min = (time.time() - start) / 60
        rate = (total - start_chunk * 1_000_000) / max(elapsed_min, 1e-6)
        print(f"  chunk {i+1}: {total:,} rows scanned, "
              f"{len(credential_hits):,} credential-pattern hits so far "
              f"({elapsed_min:.1f} min elapsed, ~{rate:,.0f} rows/min)", flush=True)

        with open(checkpoint_path, "wb") as f:
            pickle.dump({
                "word_bags": word_bags,
                "sample_counts": dict(sample_counts),
                "credential_hits": credential_hits,
                "next_chunk": i + 1,
                "total_rows": total,
            }, f)

    with open(wordbags_out, "w") as f:
        json.dump(word_bags, f)
    print(f"\nSaved word bags to {wordbags_out}")
    for c in cluster_dict:
        counts = {k: len(v) for k, v in word_bags[c].items()}
        print(f"  {c}: {counts}")

    cred_df = pd.DataFrame(credential_hits)
    cred_df.to_csv(credential_out, index=False)
    print(f"\nSaved {len(cred_df)} credential-pattern hits to {credential_out}")
    if len(cred_df):
        print(cred_df["name"].value_counts().head(20).to_string())

    if os.path.exists(checkpoint_path):
        os.remove(checkpoint_path)
        print(f"Removed checkpoint file (run completed successfully).")


if __name__ == "__main__":
    main()

