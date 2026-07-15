"""Classification half of Stage G -- same signature-word method as Stage C
(stage_c_classify_ambiguous.py), generalized to loop over however many
auto-discovered clusters Stage G's corpus pass found (up to ~181), instead
of a hardcoded 7-cluster dict.

Input:  data/processed/stage_g_word_bags.json
Output: data/processed/stage_g_classified.csv (per-instance)
        data/processed/stage_g_signature_words.json
        data/processed/stage_g_cluster_summary.csv (per-cluster resolution
        rate, for merging into entity_final_review.csv)
"""
import json
from collections import Counter

import pandas as pd

WORDBAGS_PATH = "data/processed/stage_g_word_bags.json"
CLASSIFIED_OUT = "data/processed/stage_g_classified.csv"
SIGNATURE_OUT = "data/processed/stage_g_signature_words.json"
SUMMARY_OUT = "data/processed/stage_g_cluster_summary.csv"

MIN_SIGNATURE_RATIO = 0.7
MIN_SIGNATURE_COUNT = 3
TOP_N_SIGNATURE_WORDS = 40
MARGIN_REQUIRED = 1.5


def build_candidate_word_counts(bags):
    c = Counter()
    for bag in bags:
        c.update(bag)
    return c


def build_signature_words(candidate_counts):
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
    result = {}
    for name, words in signatures.items():
        words.sort(key=lambda x: (-x[1], -x[2]))
        result[name] = [w[0] for w in words[:TOP_N_SIGNATURE_WORDS]]
    return result


def classify_instance(bag, signature_sets):
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
        return None, scores
    return top_name, scores


def main():
    with open(WORDBAGS_PATH) as f:
        word_bags = json.load(f)

    all_classifications = []
    cluster_summary = []

    for cluster_key, spec in word_bags.items():
        candidate_names = [k for k in spec if k != "__bare__"]
        candidate_counts = {name: build_candidate_word_counts(spec[name]) for name in candidate_names}
        candidate_counts = {name: c for name, c in candidate_counts.items() if sum(c.values()) > 0}
        if len(candidate_counts) < 2:
            continue

        signatures = build_signature_words(candidate_counts)
        signature_sets = {name: set(words) for name, words in signatures.items()}

        bare_instances = spec.get("__bare__", [])
        n_resolved = 0
        vote_counts = Counter()
        for bag in bare_instances:
            winner, scores = classify_instance(bag, signature_sets)
            all_classifications.append({
                "cluster": cluster_key,
                "classified_as": winner or "",
            })
            if winner:
                n_resolved += 1
                vote_counts[winner] += 1

        total = len(bare_instances)
        summary_parts = [f"{n/total*100:.0f}% {name} (n={n})" for name, n in vote_counts.most_common()]
        n_unresolved = total - n_resolved
        summary_parts.append(f"{n_unresolved/total*100:.0f}% unresolved (n={n_unresolved})" if total else "no instances")
        cluster_summary.append({
            "cluster": cluster_key,
            "n_candidates": len(candidate_counts),
            "candidates": ", ".join(candidate_counts.keys()),
            "n_bare_instances": total,
            "n_resolved": n_resolved,
            "resolution_rate": n_resolved / total if total else 0,
            "disambiguation_note": "AMBIGUOUS NAME, mixed referents: " + ", ".join(summary_parts) if total else "",
        })

    with open(SIGNATURE_OUT, "w") as f:
        json.dump({row["cluster"]: row for row in cluster_summary}, f, indent=2)

    class_df = pd.DataFrame(all_classifications)
    class_df.to_csv(CLASSIFIED_OUT, index=False)

    summary_df = pd.DataFrame(cluster_summary).sort_values("n_bare_instances", ascending=False)
    summary_df.to_csv(SUMMARY_OUT, index=False)

    print(f"{len(summary_df)} clusters classified")
    print(f"Total bare instances processed: {summary_df.n_bare_instances.sum()}")
    print(f"Total resolved: {summary_df.n_resolved.sum()} "
          f"({summary_df.n_resolved.sum()/max(summary_df.n_bare_instances.sum(),1)*100:.1f}%)")
    print(f"\nOverall resolution rate distribution:")
    print(summary_df.resolution_rate.describe().to_string())
    print(f"\nTop 20 clusters by instance volume:")
    print(summary_df[["cluster", "n_candidates", "n_bare_instances", "resolution_rate"]].head(20).to_string(index=False))


if __name__ == "__main__":
    main()
