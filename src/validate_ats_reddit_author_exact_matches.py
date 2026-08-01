"""validate_ats_reddit_author_exact_matches.py

Validates the exact (case-insensitive) username-match tier of
`data/processed/authmatch.csv` (1,658 candidate ATS<->reddit author
pairs) by asking whether same-username pairs actually write more
alike than random pairs from the same pool. Username collision alone
is weak evidence of shared identity (see handoff conversation,
2026-07-26) -- this is the sanity check before trusting it for anything.

Method: per author, per platform, build four independent feature
representations from that author's own comments:
  1. Function-word frequency vector (classic authorship-attribution
     style fingerprint, topic-independent).
  2. Char n-gram TF-IDF vector (style + vocabulary + topic combined).
  3. Word-level (1-2 gram) TF-IDF vector with function words stripped
     (topic/subject-matter overlap specifically).
  4. Rare/idiosyncratic vocabulary Jaccard overlap -- words used by only
     a handful of authors in the whole qualifying pool (misspellings,
     invented terms, niche slang, unusual phrasing), the classic
     "distinctive vocabulary" authorship-verification signal, which
     common-word style vectors dilute.

For every true username-matched pair, each ATS author is scored against
the ENTIRE qualifying reddit-author pool (leave-one-out retrieval, not
a small sampled decoy set) -- a much stronger test than a handful of
random decoys, since it reports where the true match actually ranks
out of everyone, not just against 9 strangers. An ensemble score
(row-wise z-scored average across all four features) is also reported.

Only authors with >= MIN_COMMENTS on both platforms are scored --
median activity in the exact-match tier is far too sparse (10 ATS / 5
reddit comments) for stylometry below that, so most of the 1,658 pairs
are excluded from this pass, not silently trusted.

Outputs:
- data/processed/ats_reddit_author_match_validation_pairs.csv
  (per-pair scores -- internal/methods use, not for direct thesis
  citation by username, same convention as authmatch.csv already in
  the repo)
- data/processed/ats_reddit_author_match_validation_report.md
  (aggregate-only summary -- this is the one safe to reference)
"""
import os
import re
import numpy as np
import pandas as pd
import duckdb
from datetime import datetime
from scipy.stats import mannwhitneyu
from sklearn.feature_extraction.text import TfidfVectorizer, CountVectorizer
from sklearn.feature_extraction import text as sk_text
from sklearn.metrics.pairwise import cosine_similarity

BASE = os.path.dirname(os.path.abspath(__file__)) + "/../data/processed/"
MIN_COMMENTS = 15              # per author, per platform, to qualify for scoring
MAX_COMMENTS_PER_AUTHOR = 2000  # cap pulled text volume (8GB-RAM guardrail)
RARE_MIN_DF = 2                 # a "rare" word must be shared by >=2 authors (else no overlap possible)
RARE_MAX_DF = 8                  # ...but used by very few authors overall, out of ~n*2 author-docs
RNG_SEED = 42

FUNCTION_WORDS = """
i me my myself we our ours ourselves you your yours he him his she her hers
it its they them their and but or nor for so yet because although if unless
while since the a an this that these those of to in on at by with about
against between into through during before after above below from up down
out off over under again further then once here there when where why how
all any both each few more most other some such no not only own same than
too very can will just should now
""".split()


def count_syllables(word):
    word = word.lower()
    vowels = "aeiouy"
    count, prev_vowel = 0, False
    for ch in word:
        is_vowel = ch in vowels
        if is_vowel and not prev_vowel:
            count += 1
        prev_vowel = is_vowel
    if word.endswith("e") and count > 1:
        count -= 1
    return max(count, 1)


def readability_features(texts):
    """Flesch reading ease + basic complexity stats over an author's comments."""
    joined = " ".join(texts)
    words = re.findall(r"[a-zA-Z']+", joined)
    sentences = [s for s in re.split(r"[.!?]+", joined) if s.strip()]
    n_words = max(len(words), 1)
    n_sentences = max(len(sentences), 1)
    syllables = sum(count_syllables(w) for w in words)
    avg_word_len = np.mean([len(w) for w in words]) if words else 0.0
    words_per_sentence = n_words / n_sentences
    syllables_per_word = syllables / n_words
    flesch = 206.835 - 1.015 * words_per_sentence - 84.6 * syllables_per_word
    lower_words = [w.lower() for w in words]
    ttr = len(set(lower_words)) / n_words
    return {
        "n_words": n_words,
        "avg_word_len": avg_word_len,
        "words_per_sentence": words_per_sentence,
        "flesch_reading_ease": flesch,
        "type_token_ratio": ttr,
    }


def function_word_vector(texts):
    joined = " ".join(texts).lower()
    words = re.findall(r"[a-z']+", joined)
    n = max(len(words), 1)
    counts = {fw: 0 for fw in FUNCTION_WORDS}
    for w in words:
        if w in counts:
            counts[w] += 1
    return np.array([counts[fw] / n for fw in FUNCTION_WORDS])


def hour_of_day_hist(hours):
    hist, _ = np.histogram(hours, bins=24, range=(0, 24))
    total = hist.sum()
    return hist / total if total > 0 else hist


def parse_ats_hour(raw_timestamp):
    try:
        return datetime.strptime(raw_timestamp, "%b, %d %Y @ %I:%M %p").hour
    except (ValueError, TypeError):
        return None


def rank_and_topk(sim_matrix):
    """For a square (n_ats x n_reddit, aligned so diagonal = true pair)
    similarity matrix, return per-row rank of the true match (1 = best)
    and the mean similarity to all other (non-true) candidates."""
    n = sim_matrix.shape[0]
    diag = np.diag(sim_matrix)
    ranks = np.zeros(n, dtype=int)
    others_mean = np.zeros(n)
    for i in range(n):
        row = sim_matrix[i]
        others = np.delete(row, i)
        ranks[i] = 1 + int((others > diag[i]).sum())
        others_mean[i] = others.mean()
    return diag, others_mean, ranks


def zscore_rows(mat):
    mu = mat.mean(axis=1, keepdims=True)
    sd = mat.std(axis=1, keepdims=True)
    sd[sd == 0] = 1.0
    return (mat - mu) / sd


def main():
    np.random.seed(RNG_SEED)

    print("=== Loading authmatch.csv, filtering to exact (score==100) tier ===")
    authmatch = pd.read_csv(BASE + "authmatch.csv")
    authmatch.columns = ["idx", "ats_author", "reddit_author", "score"]
    exact = authmatch[authmatch.score == 100].drop_duplicates("ats_author").copy()
    print(f"Exact-match pairs: {len(exact)}")

    con = duckdb.connect()
    con.register("exact", exact)

    print("\n=== Counting per-author comment volume on both platforms ===")
    ats_counts = con.execute("""
        SELECT author AS ats_author, count(*) AS n_ats
        FROM read_parquet(?)
        WHERE author IN (SELECT ats_author FROM exact)
        GROUP BY author
    """, [BASE + "ats_comments_final.parquet"]).fetchdf()

    reddit_counts = con.execute("""
        SELECT author AS reddit_author, count(*) AS n_reddit
        FROM read_parquet(?)
        WHERE author IN (SELECT reddit_author FROM exact)
        GROUP BY author
    """, [BASE + "empath_scores_full_mapped.parquet"]).fetchdf()

    merged = exact.merge(ats_counts, on="ats_author", how="left").merge(
        reddit_counts, on="reddit_author", how="left"
    )
    merged[["n_ats", "n_reddit"]] = merged[["n_ats", "n_reddit"]].fillna(0)

    qualifying = merged[
        (merged.n_ats >= MIN_COMMENTS) & (merged.n_reddit >= MIN_COMMENTS)
    ].copy()
    print(f"Pairs with >={MIN_COMMENTS} comments on both platforms: "
          f"{len(qualifying)} / {len(exact)}")

    if len(qualifying) < 20:
        print("Too few qualifying pairs to run a meaningful validation. Stopping.")
        return

    ats_authors = qualifying.ats_author.tolist()
    reddit_authors = qualifying.reddit_author.tolist()

    print("\n=== Pulling comment text + timestamps for qualifying authors ===")
    con.register("qualifying", qualifying)
    ats_text = con.execute("""
        SELECT a.author, a.body, a.raw_timestamp
        FROM read_parquet(?) a
        JOIN qualifying q ON a.author = q.ats_author
        WHERE a.body IS NOT NULL
    """, [BASE + "ats_comments_final.parquet"]).fetchdf()

    reddit_text = con.execute("""
        SELECT a.author, a.text, a.created_utc
        FROM read_parquet(?) a
        JOIN qualifying q ON a.author = q.reddit_author
        WHERE a.text IS NOT NULL
    """, [BASE + "empath_scores_full_mapped.parquet"]).fetchdf()

    print(f"ATS comments pulled: {len(ats_text):,}")
    print(f"Reddit comments pulled: {len(reddit_text):,}")

    # Cap per-author volume to bound memory/compute
    ats_text = (
        ats_text.groupby("author", group_keys=False)[["author", "body", "raw_timestamp"]]
        .apply(lambda g: g.sample(min(len(g), MAX_COMMENTS_PER_AUTHOR), random_state=RNG_SEED))
    )
    reddit_text = (
        reddit_text.groupby("author", group_keys=False)[["author", "text", "created_utc"]]
        .apply(lambda g: g.sample(min(len(g), MAX_COMMENTS_PER_AUTHOR), random_state=RNG_SEED))
    )

    print("\n=== Building per-author corpora ===")
    ats_by_author = ats_text.groupby("author")["body"].apply(list).to_dict()
    reddit_by_author = reddit_text.groupby("author")["text"].apply(list).to_dict()
    ats_hours_by_author = (
        ats_text.assign(hour=ats_text.raw_timestamp.map(parse_ats_hour))
        .dropna(subset=["hour"])
        .groupby("author")["hour"].apply(list).to_dict()
    )
    reddit_hours_by_author = (
        reddit_text.assign(hour=(reddit_text.created_utc // 3600) % 24)
        .groupby("author")["hour"].apply(list).to_dict()
    )

    # Only keep pairs where both sides actually produced text after the join/cap
    valid_pairs = [
        (a, r) for a, r in zip(ats_authors, reddit_authors)
        if a in ats_by_author and r in reddit_by_author
    ]
    print(f"Pairs with usable text on both sides: {len(valid_pairs)}")
    ats_list = [a for a, _ in valid_pairs]
    reddit_list = [r for _, r in valid_pairs]
    n = len(valid_pairs)

    print("\n=== Computing stylometric features (function words, readability) ===")
    ats_fw = np.vstack([function_word_vector(ats_by_author[a]) for a in ats_list])
    reddit_fw = np.vstack([function_word_vector(reddit_by_author[r]) for r in reddit_list])

    ats_read = [readability_features(ats_by_author[a]) for a in ats_list]
    reddit_read = [readability_features(reddit_by_author[r]) for r in reddit_list]

    ats_hour_hist = np.vstack([
        hour_of_day_hist(ats_hours_by_author.get(a, [])) for a in ats_list
    ])
    reddit_hour_hist = np.vstack([
        hour_of_day_hist(reddit_hours_by_author.get(r, [])) for r in reddit_list
    ])

    print("=== Fitting shared char n-gram TF-IDF space (style + vocab + topic) ===")
    ats_docs = [" ".join(ats_by_author[a]) for a in ats_list]
    reddit_docs = [" ".join(reddit_by_author[r]) for r in reddit_list]
    all_docs = ats_docs + reddit_docs

    char_vectorizer = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 4), min_df=2, max_features=20000)
    char_tfidf = char_vectorizer.fit_transform(all_docs)
    ats_char, reddit_char = char_tfidf[:n], char_tfidf[n:]

    print("=== Fitting word-level (1-2 gram) TF-IDF space, function words stripped (topic overlap) ===")
    topic_stopwords = list(set(FUNCTION_WORDS) | set(sk_text.ENGLISH_STOP_WORDS))
    word_vectorizer = TfidfVectorizer(
        analyzer="word", ngram_range=(1, 2), min_df=3, max_features=20000,
        stop_words=topic_stopwords, token_pattern=r"[a-zA-Z']{3,}",
    )
    word_tfidf = word_vectorizer.fit_transform(all_docs)
    ats_topic, reddit_topic = word_tfidf[:n], word_tfidf[n:]

    print("=== Building rare/idiosyncratic vocabulary index (distinctive-word overlap) ===")
    rare_vectorizer = CountVectorizer(
        analyzer="word", token_pattern=r"[a-zA-Z']{4,}", binary=True,
        min_df=RARE_MIN_DF, max_df=RARE_MAX_DF,
    )
    rare_binary = rare_vectorizer.fit_transform(all_docs)
    print(f"Rare-vocabulary terms found (used by {RARE_MIN_DF}-{RARE_MAX_DF} of {2*n} author-docs): "
          f"{rare_binary.shape[1]}")
    ats_rare, reddit_rare = rare_binary[:n], rare_binary[n:]
    ats_rare_counts = np.asarray(ats_rare.sum(axis=1)).flatten()
    reddit_rare_counts = np.asarray(reddit_rare.sum(axis=1)).flatten()

    print("\n=== Scoring every ATS author against the FULL qualifying reddit pool (leave-one-out) ===")
    fw_sim = cosine_similarity(ats_fw, reddit_fw)
    char_sim = cosine_similarity(ats_char, reddit_char)
    topic_sim = cosine_similarity(ats_topic, reddit_topic)

    rare_intersection = (ats_rare @ reddit_rare.T).toarray()
    rare_union = ats_rare_counts[:, None] + reddit_rare_counts[None, :] - rare_intersection
    with np.errstate(divide="ignore", invalid="ignore"):
        rare_jaccard = np.where(rare_union > 0, rare_intersection / rare_union, 0.0)

    ensemble_sim = zscore_rows(fw_sim) + zscore_rows(char_sim) + zscore_rows(topic_sim) + zscore_rows(rare_jaccard)
    ensemble_sim /= 4.0

    feature_matrices = {
        "fw": fw_sim,
        "char_tfidf": char_sim,
        "word_topic": topic_sim,
        "rare_vocab": rare_jaccard,
        "ensemble": ensemble_sim,
    }

    rows = []
    for i in range(n):
        row = {"ats_author": ats_list[i], "reddit_author": reddit_list[i], "n_candidates": n}
        for fname, mat in feature_matrices.items():
            diag_i = mat[i, i]
            others = np.delete(mat[i], i)
            rank_i = 1 + int((others > diag_i).sum())
            row[f"{fname}_sim_true"] = diag_i
            row[f"{fname}_sim_others_mean"] = others.mean()
            row[f"{fname}_rank_of_true"] = rank_i
        row["flesch_diff"] = abs(ats_read[i]["flesch_reading_ease"] - reddit_read[i]["flesch_reading_ease"])
        row["ttr_diff"] = abs(ats_read[i]["type_token_ratio"] - reddit_read[i]["type_token_ratio"])
        row["avg_word_len_diff"] = abs(ats_read[i]["avg_word_len"] - reddit_read[i]["avg_word_len"])
        row["hour_hist_cos_sim"] = cosine_similarity([ats_hour_hist[i]], [reddit_hour_hist[i]])[0][0]
        row["ats_rare_words"] = int(ats_rare_counts[i])
        row["reddit_rare_words"] = int(reddit_rare_counts[i])
        rows.append(row)

    results = pd.DataFrame(rows)
    results.to_csv(BASE + "ats_reddit_author_match_validation_pairs.csv", index=False)
    print(f"Wrote per-pair scores: {BASE}ats_reddit_author_match_validation_pairs.csv "
          f"({len(results)} rows)")

    print("\n=== Aggregate validation stats (full leave-one-out pool, n={} candidates) ===".format(n))
    chance_top1 = 1 / n
    feature_labels = {
        "fw": "Function-word style (topic-independent)",
        "char_tfidf": "Char n-gram TF-IDF (style+vocab+topic)",
        "word_topic": "Word-level topic overlap (function words stripped)",
        "rare_vocab": "Rare/idiosyncratic vocabulary Jaccard overlap",
        "ensemble": "Ensemble (z-scored average of all four)",
    }
    stats = {}
    for fname, label in feature_labels.items():
        true_sim = results[f"{fname}_sim_true"]
        others_sim = results[f"{fname}_sim_others_mean"]
        _, p = mannwhitneyu(true_sim, others_sim, alternative="greater")
        top1 = (results[f"{fname}_rank_of_true"] == 1).mean()
        top5 = (results[f"{fname}_rank_of_true"] <= 5).mean()
        median_pct = (results[f"{fname}_rank_of_true"] / n).median()
        stats[fname] = dict(true_mean=true_sim.mean(), others_mean=others_sim.mean(),
                             p=p, top1=top1, top5=top5, median_pct=median_pct)
        print(f"{label}: true-match sim mean={true_sim.mean():.4f}, others mean={others_sim.mean():.4f}, "
              f"p={p:.2e}, top-1={top1:.1%}, top-5={top5:.1%}, "
              f"median percentile rank={median_pct:.1%} (chance top-1={chance_top1:.1%})")

    report_lines = [
        "# ATS <-> reddit exact-username-match validation (aggregate only)",
        "",
        f"Validates the {len(exact)} exact (case-insensitive) username matches from "
        "`authmatch.csv` by testing whether same-username authors actually write more "
        "alike than random pairs from the same pool -- username collision alone is weak "
        "evidence of shared identity. Each ATS author is scored against the **entire** "
        f"qualifying reddit-author pool (n={n}, leave-one-out), not a small sampled "
        "decoy set, so rank/percentile figures below reflect where the true match "
        "actually falls among everyone, not just against a handful of strangers.",
        "",
        f"- Pairs with >={MIN_COMMENTS} comments on both platforms: {len(qualifying)} / {len(exact)}",
        f"- Pairs with usable text/features on both sides: {n}",
        f"- Chance-level top-1 retrieval with n={n} candidates: {chance_top1:.1%}",
        f"- Rare-vocabulary terms indexed (shared by {RARE_MIN_DF}-{RARE_MAX_DF} of {2*n} author-docs): "
        f"{rare_binary.shape[1]}",
        "",
    ]
    for fname, label in feature_labels.items():
        s = stats[fname]
        report_lines += [
            f"## {label}",
            f"- True-match similarity: mean={s['true_mean']:.4f}",
            f"- Similarity to all other (non-true) candidates: mean={s['others_mean']:.4f}",
            f"- Mann-Whitney U (true > others): p={s['p']:.2e}",
            f"- Top-1 retrieval (true match is THE single best fit out of {n}): {s['top1']:.1%}",
            f"- Top-5 retrieval (true match is in the top 5 of {n}): {s['top5']:.1%}",
            f"- Median percentile rank of true match: {s['median_pct']:.1%} "
            "(50% = no better than random, lower is better)",
            "",
        ]
    report_lines += [
        "## Posting-hour-of-day histogram similarity (behavioral, not stylometric)",
        f"- Mean cosine similarity between platforms' hour-of-day histograms: "
        f"{results.hour_hist_cos_sim.mean():.4f}",
        "- Caveat: ATS `raw_timestamp` timezone is not confirmed against reddit's "
        "UTC `created_utc` -- treat this as suggestive, not confirmatory, until "
        "that's checked. Not included in the ensemble score above for that reason.",
        "",
        "## Readability/complexity descriptive stats",
        f"- Mean |Flesch reading-ease difference| across matched pairs: "
        f"{results.flesch_diff.mean():.2f}",
        f"- Mean |type-token-ratio difference|: {results.ttr_diff.mean():.4f}",
        f"- Mean |avg word length difference|: {results.avg_word_len_diff.mean():.4f}",
        "- No decoy baseline computed for these scalar features in this pass -- "
        "descriptive only, not folded into the ensemble score.",
        "",
        "## Reading this result",
        "If true-match similarity is not meaningfully higher than the others-mean and "
        "top-1/top-5 retrieval sit near chance, the exact-username tier is NOT "
        "validated as reliable identity evidence and should not be used for downstream "
        "analysis without a stronger signal. If it is meaningfully higher -- especially "
        "on the ensemble and rare-vocabulary features, which are the least likely to be "
        "explained by shared subreddit/forum culture rather than shared identity -- "
        "that supports (but does not prove for any single pair) that exact-username "
        "matches in this corpus pair tend to be the same person.",
        "",
        "Per-pair scores are in `ats_reddit_author_match_validation_pairs.csv` for "
        "methods review -- per the project's privacy guardrail, any number that goes "
        "into the actual thesis analysis should be reported at the aggregate level "
        "above, not by matched username.",
    ]
    with open(BASE + "ats_reddit_author_match_validation_report.md", "w") as f:
        f.write("\n".join(report_lines))
    print(f"\nWrote aggregate report: {BASE}ats_reddit_author_match_validation_report.md")


if __name__ == "__main__":
    main()
