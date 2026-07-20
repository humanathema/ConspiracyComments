"""Stage C of the entity-disambiguation work program (ANTIGRAVITY_HANDOFF.md
§12 step 9). Pure local computation on Stage B's word bags -- no corpus
access, no API calls, just counting.

Design (agreed with Nash 2026-07-14, do not deviate without checking):
classify each AMBIGUOUS BARE-NAME INSTANCE individually against candidate
profiles built from unambiguous full-name instances. Do NOT use a global
majority vote across all instances of a bare name -- that was an earlier,
explicitly rejected design (it would mislabel every real minority-referent
mention as the majority candidate).

Method: for each candidate, find its "signature words" -- words that are
disproportionately common in ITS labeled bags vs. every OTHER candidate in
the same cluster (ratio test, not raw frequency, so a common word shared by
both candidates isn't treated as distinctive of either). For each bare
instance, count signature-word hits against each candidate; classify by
whichever candidate wins, but only if it wins by a real margin -- ties/
close calls are left unresolved rather than forced. Interpretable by
design: signature words can be printed and eyeballed for a sanity check,
unlike a black-box similarity score.

Known cross-cluster data-collision fix: "Bill Clinton" is a candidate under
both the `bill` and `clinton` clusters in Stage B's config, but Stage B's
single shared alias->candidate dict meant only ONE cluster's assignment
survived (bill.Bill Clinton ended up with 0 samples, clinton.Bill Clinton
got all 2000). This script borrows clinton's Bill Clinton bags into bill's
candidate set before building profiles, since it's the same person.

Input:  data/processed/stage_b_word_bags.json
Output: data/processed/entity_disambiguation_classified.csv
        (per-instance classifications)
        data/processed/stage_c_signature_words.json
        (for human sanity-check of what the classifier learned)
"""
import json
from collections import Counter
import argparse

import pandas as pd

WORDBAGS_PATH = "data/processed/stage_b_word_bags.json"
CLASSIFIED_OUT = "data/processed/entity_disambiguation_classified.csv"
SIGNATURE_OUT = "data/processed/stage_c_signature_words.json"

MIN_SIGNATURE_RATIO = 0.7  # word must be this concentrated in one candidate vs rest
MIN_SIGNATURE_COUNT = 3    # word must appear at least this many times for that candidate
TOP_N_SIGNATURE_WORDS = 40  # cap per candidate, keep the most distinctive
MARGIN_REQUIRED = 1.5      # winning candidate's hit count must beat runner-up by this ratio


def clean_bag(bag):
    """Drop URL/markdown-link fragments and pure-numeric tokens -- these are
    unique per-occurrence (a specific article URL, a timestamp) so they
    trivially score as 100%-concentrated "signature" words for whichever
    candidate happened to co-occur with that one copypasted link, without
    carrying any real thematic signal. Found corrupting the Kennedy
    cluster's profiles on the first run (signature words were almost all
    raw http:// fragments instead of vocabulary)."""
    return [w for w in bag
            if "http" not in w and "www" not in w and "](" not in w
            and not w.replace(":", "").replace("-", "").isdigit()
            and len(w) < 25]


def build_candidate_word_counts(bags):
    """bags: list of word-lists. Returns Counter of all words across bags."""
    c = Counter()
    for bag in bags:
        c.update(clean_bag(bag))
    return c


def build_signature_words(candidate_counts):
    """candidate_counts: {candidate_name: Counter}. Returns {candidate_name:
    set(signature_words)} -- words disproportionately concentrated in one
    candidate's bags relative to the others in the same cluster."""
    all_words = set()
    for c in candidate_counts.values():
        all_words |= set(c.keys())

    signatures = {name: [] for name in candidate_counts}
    for word in all_words:
        total = sum(c.get(word, 0) for c in candidate_counts.values())
        if total < MIN_SIGNATURE_COUNT:
            continue
        for name, counts in candidate_counts.items():
            this_count = counts.get(word, 0)
            if this_count < MIN_SIGNATURE_COUNT:
                continue
            ratio = this_count / total
            if ratio >= MIN_SIGNATURE_RATIO:
                signatures[name].append((word, ratio, this_count))

    # keep top-N most distinctive (highest ratio, tie-broken by count) per candidate
    result = {}
    for name, words in signatures.items():
        words.sort(key=lambda x: (-x[1], -x[2]))
        result[name] = [w[0] for w in words[:TOP_N_SIGNATURE_WORDS]]
    return result


def classify_instance(bag, signature_sets):
    """bag: list of words from one bare-name instance. signature_sets:
    {candidate_name: set(words)}. Returns (winner_or_None, scores_dict)."""
    bag_set = set(bag)
    scores = {name: len(bag_set & sig) for name, sig in signature_sets.items()}
    if not any(scores.values()):
        return None, scores
    ranked = sorted(scores.items(), key=lambda x: -x[1])
    top_name, top_score = ranked[0]
    second_score = ranked[1][1] if len(ranked) > 1 else 0
    if top_score == 0:
        return None, scores
    if second_score > 0 and top_score < MARGIN_REQUIRED * second_score:
        return None, scores  # too close, leave unresolved
    return top_name, scores


def main():
    parser = argparse.ArgumentParser(description="Stage C ambiguous classifier")
    parser.add_argument("--maverick", action="store_true", help="Run maverick disambiguation mode")
    parser.add_argument("--mainstream", action="store_true", help="Run mainstream expert mode")
    args = parser.parse_args()

    if args.maverick:
        wordbags_path = "data/processed/stage_b_maverick_word_bags.json"
        classified_out = "data/processed/maverick_entity_disambiguation_classified.csv"
        signature_out = "data/processed/stage_c_maverick_signature_words.json"
        mode_name = "Maverick Expert"
    else:
        wordbags_path = WORDBAGS_PATH
        classified_out = CLASSIFIED_OUT
        signature_out = SIGNATURE_OUT
        mode_name = "Mainstream Expert"

    print(f"Running classification in {mode_name} mode...")

    with open(wordbags_path) as f:
        word_bags = json.load(f)

    # fix the bill/clinton cross-cluster collision: borrow Bill Clinton's
    # bags from the clinton cluster into bill's candidate set
    if "bill" in word_bags and "clinton" in word_bags:
        if not word_bags["bill"].get("Bill Clinton"):
            word_bags["bill"]["Bill Clinton"] = word_bags["clinton"].get("Bill Clinton", [])
            print("Applied bill/clinton cross-cluster fix: borrowed "
                  f"{len(word_bags['bill']['Bill Clinton'])} Bill Clinton bags into 'bill' cluster")

    all_signature_words = {}
    all_classifications = []

    for cluster_key, spec in word_bags.items():
        candidate_names = [k for k in spec if k != "__bare__"]
        candidate_counts = {name: build_candidate_word_counts(spec[name]) for name in candidate_names}
        candidate_counts = {name: c for name, c in candidate_counts.items() if sum(c.values()) > 0}
        if len(candidate_counts) < 2:
            print(f"'{cluster_key}': fewer than 2 candidates with data, skipping classification")
            continue

        signatures = build_signature_words(candidate_counts)
        signature_sets = {name: set(words) for name, words in signatures.items()}
        all_signature_words[cluster_key] = signatures

        print(f"\n=== {cluster_key} ===")
        for name, words in signatures.items():
            print(f"  {name} ({sum(candidate_counts[name].values())} total words): "
                  f"{', '.join(words[:12])}{'...' if len(words) > 12 else ''}")

        bare_instances = spec.get("__bare__", [])
        n_resolved = 0
        for inst in bare_instances:
            winner, scores = classify_instance(clean_bag(inst["bag"]), signature_sets)
            all_classifications.append({
                "cluster": cluster_key,
                "id": inst["id"],
                "classified_as": winner or "",
                "scores": json.dumps(scores),
            })
            if winner:
                n_resolved += 1
        print(f"  bare instances: {len(bare_instances)}, resolved: {n_resolved} "
              f"({n_resolved/max(len(bare_instances),1)*100:.1f}%)")

    with open(signature_out, "w") as f:
        json.dump(all_signature_words, f, indent=2)
    print(f"\nSaved signature words to {signature_out}")

    out_df = pd.DataFrame(all_classifications)
    out_df.to_csv(classified_out, index=False)
    print(f"Saved {len(out_df)} per-instance classifications to {classified_out}")


if __name__ == "__main__":
    main()

