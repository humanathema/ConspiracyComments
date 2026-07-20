"""score_hedged_suspicion_full.py

Scores the full 21.4M-row length-filtered corpus with the previously-trained
but never-scaled `hedged_suspicion` classifier (data/processed/hedged_suspicion_pipeline.pkl,
a fitted TfidfVectorizer+LogisticRegression sklearn Pipeline, kappa=0.872 / F1=0.933
against HITL labels -- see pipeline_validity_audit.md).

STAGE-1 FILTER (added after an initial no-filter run showed hs_prob compressed
to mean=0.46/std=0.05 across all 21M rows -- clearly out-of-population). The
classifier was trained on hedged_suspicion_hitl_queue_deduped.csv, itself built
in the legacy notebook (ConspiracyMaster_Final_Architecture copy.ipynb) via a
two-pass regex intersection: SYNTACTIC_ANCHORS_HIGH_CONF (hedging FORM) AND
CONCEALMENT_MARKERS (institutional-distrust/concealment CONTENT) both had to
match the same comment body. Reproduced verbatim below so Stage-2 only ever
scores text resembling what the model was actually trained on -- same
Stage-1-then-Stage-2 shape as personal_experience/procedural_skepticism in
score_main_corpus_staged.py. Rows that don't pass both regex passes are
auto-assigned hs_prob=0.0 rather than run through the model.
"""
import re
import time
import joblib
import pandas as pd
import pyarrow.parquet as pq

MODEL_PATH = "data/processed/hedged_suspicion_pipeline.pkl"
INPUT_PARQUET = "data/processed/empath_scores_full.parquet"
OUTPUT_PARQUET = "data/processed/hedged_suspicion_scores_full21m.parquet"

# --- STAGE 1 REGEX PATTERNS (verbatim from the original candidate-queue build) ---
SYNTACTIC_ANCHORS_HIGH_CONF = [
    r"funny how", r"funny that", r"\bconveniently\b", r"makes (you|one|me|us) wonder",
    r"doesn't add up", r"don't add up", r"what they aren't telling",
    r"what they('re| are) not telling", r"read between the lines", r"suspicious timing",
    r"too convenient", r"\bcui bono\b", r"behind closed doors", r"willing to bet",
    r"curiously enough", r"\bcuriously\b", r"of course they",
    r"they would (say|claim|tell us) that", r"we('re| are) not supposed to",
    r"for some reason", r"makes (you|one|me) think", r"just asking questions",
    r"i'?m just saying", r"not saying (that|it|he|she|they)",
]
CONCEALMENT_MARKERS = [
    r"cover.?up", r"cover(ing|ed) up", r"hidden agenda", r"they('re| are) hiding",
    r"being hidden", r"being suppressed", r"don't want you to know",
    r"doesn't want (us|you|people) to know", r"keep(ing)? (us|you|people|the public) in the dark",
    r"what (they|the government|the media) (don't|doesn't|won't) tell",
    r"official (story|narrative|account|version)", r"mainstream (media|narrative|story)",
    r"\bmsm\b", r"the government (lied|lies|is lying|knew|knows)", r"they knew",
    r"they (lied|lie|are lying)", r"false flag",
    r"controlled (narrative|demolition|opposition|media)", r"narrative",
    r"follow the money", r"who benefits", r"who (really|actually) (did|did it|controls|runs)",
    r"deep state", r"shadow (government|elite|group|cabal)", r"powers? that be",
    r"\belite\b", r"they (planned|orchestrated|staged|allowed)", r"let it happen",
    r"inside job", r"false (flag|story|narrative)", r"commission (report|findings)",
    r"whitewash", r"(rigged|fake|staged) (investigation|report|inquiry|trial)",
    r"never investigated", r"swept under",
]

ANCHOR_PATTERN = re.compile("|".join(SYNTACTIC_ANCHORS_HIGH_CONF), re.IGNORECASE)
CONCEALMENT_PATTERN = re.compile("|".join(CONCEALMENT_MARKERS), re.IGNORECASE)


def pass_hedged_suspicion_filter(text):
    text_str = str(text)
    return bool(ANCHOR_PATTERN.search(text_str)) and bool(CONCEALMENT_PATTERN.search(text_str))


def score_hedged_suspicion_full():
    start_time = time.time()

    print(f"Loading fitted hedged_suspicion pipeline from {MODEL_PATH}...")
    pipe = joblib.load(MODEL_PATH)

    print(f"Processing {INPUT_PARQUET} in chunks...")
    parquet_file = pq.ParquetFile(INPUT_PARQUET)

    processed_chunks = []
    total_rows = 0
    total_passed_s1 = 0

    for i, batch in enumerate(parquet_file.iter_batches(batch_size=500_000, columns=["id", "text"])):
        chunk_start = time.time()
        df_chunk = batch.to_pandas()
        n_rows = len(df_chunk)
        total_rows += n_rows

        df_scored = pd.DataFrame({"id": df_chunk["id"], "hs_prob": 0.0})

        pass_s1 = df_chunk["text"].apply(pass_hedged_suspicion_filter)
        total_passed_s1 += pass_s1.sum()
        passed_idx = df_chunk[pass_s1].index

        if len(passed_idx) > 0:
            texts = df_chunk.loc[passed_idx, "text"].fillna("")
            probs = pipe.predict_proba(texts)[:, 1]
            df_scored.loc[passed_idx, "hs_prob"] = probs

        processed_chunks.append(df_scored)

        print(f"  Chunk #{i + 1} ({n_rows:,} rows, cumulative {total_rows:,}, "
              f"{pass_s1.sum():,} passed Stage 1) done in {time.time() - chunk_start:.1f}s")

    print("\nConcatenating and saving...")
    final_df = pd.concat(processed_chunks, ignore_index=True)
    final_df.to_parquet(OUTPUT_PARQUET, index=False)

    elapsed = time.time() - start_time
    print(f"\nFinished scoring {total_rows:,} rows in {elapsed / 60:.2f} minutes.")
    print(f"Passed Stage 1 filter: {total_passed_s1:,} ({total_passed_s1 / total_rows * 100:.2f}%)")
    print(f"Saved to {OUTPUT_PARQUET}")
    print(f"hs_prob distribution (all rows, including Stage-1 auto-zeros):\n{final_df['hs_prob'].describe()}")
    nonzero = final_df[final_df["hs_prob"] > 0]["hs_prob"]
    print(f"\nhs_prob distribution (Stage-1-passed rows only, n={len(nonzero):,}):\n{nonzero.describe()}")


if __name__ == "__main__":
    score_hedged_suspicion_full()
