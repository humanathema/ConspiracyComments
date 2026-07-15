"""validate_attribution_scorer.py

Read-only validation pass for attribution_confidence_scorer.py against a
real, diverse sample pulled from the corpus -- not just the 6 hand-picked
sentences in that file's __main__ block. Does NOT modify any existing
pipeline file, does NOT touch consensus_experts_verified.py or
rerun_refined_regressions_v2.py. Writes one new output file only.

Purpose: build real evidence on the scorer's precision/recall before
wiring it into the actual has_maverick/has_consensus_expert pipeline
(staged as follow-up, not done here -- see attribution_confidence_scorer.py
docstring).

Output: data/processed/attribution_scorer_validation_sample.csv --
entity, sentence, confidence tier, pattern type -- for manual spot-check
review, same "produce a reviewable sample, don't auto-trust it" pattern
used throughout this session (consensus_experts_verified.py,
mainstream_expert_augmented_superset.csv).
"""
import re
import sys
import os
import duckdb
import pandas as pd
import spacy

sys.path.insert(0, os.path.dirname(__file__))
from attribution_confidence_scorer import score_entity_attribution
from verified_maverick_additions import VERIFIED_MAVERICK_ADDITIONS

STAGED_PATH = "data/processed/research_corpus_staged_scores_full21m.parquet"
EMPATH_PATH = "data/processed/empath_scores_full.parquet"
ENTITY_PATH = "data/processed/entity_final_review.csv"
OUT_PATH = "data/processed/attribution_scorer_validation_sample.csv"
SAMPLE_SIZE = 400


def build_maverick_regex():
    df_entity = pd.read_csv(ENTITY_PATH)
    ents = df_entity[df_entity["final_bucket_guess"] == "maverick_authority"]["entity"].dropna().astype(str).unique().tolist()
    ents = [e for e in ents if len(e) >= 3]
    ents = list(dict.fromkeys(ents + VERIFIED_MAVERICK_ADDITIONS))
    ents_sorted = sorted(ents, key=len, reverse=True)
    pattern = r"\b(" + "|".join(re.escape(e) for e in ents_sorted) + r")\b"
    return ents, re.compile(pattern, re.IGNORECASE)


def main():
    print("Building maverick entity regex...")
    entities, rx = build_maverick_regex()
    print(f"{len(entities)} entities loaded")

    print("Pulling a random sample of comments containing a maverick entity mention...")
    con = duckdb.connect()
    pattern_str = rx.pattern
    # NOTE 2026-07-15: `USING SAMPLE n ROWS` samples BEFORE the WHERE filter
    # applies in DuckDB, not after -- the first run of this script pulled
    # only 7 matching comments from a random 400 raw rows instead of 400
    # actual matches. Fixed with ORDER BY random() LIMIT, which correctly
    # samples from the filtered set.
    query = f"""
        SELECT e.text
        FROM read_parquet('{EMPATH_PATH}') e
        WHERE regexp_matches(e.text, $1)
        ORDER BY random()
        LIMIT {SAMPLE_SIZE}
    """
    rows = con.execute(query, [pattern_str]).fetchall()
    print(f"Pulled {len(rows)} candidate comments")

    print("Loading spaCy for sentence splitting...")
    nlp = spacy.load("en_core_web_sm", disable=["ner", "parser", "lemmatizer"])
    if "sentencizer" not in nlp.pipe_names:
        nlp.add_pipe("sentencizer")

    results = []
    for (text,) in rows:
        if not text:
            continue
        doc = nlp(str(text)[:2000])  # cap length, avoid pathological long comments
        for sent in doc.sents:
            sent_text = sent.text.strip()
            if len(sent_text) < 5:
                continue
            for m in rx.finditer(sent_text):
                entity_matched = m.group(0)
                other_entities = [e for e in entities if e.lower() != entity_matched.lower()]
                # limit competing-entity check list for speed -- only ones
                # that actually appear elsewhere in this sentence
                nearby_others = [e for e in other_entities if e.lower() in sent_text.lower()][:10]
                result = score_entity_attribution(sent_text, entity_matched, m.start(), m.end(),
                                                   other_known_entities=nearby_others)
                results.append({
                    "entity": entity_matched,
                    "sentence": sent_text[:300],
                    "confidence": result.confidence,
                    "pattern_type": result.pattern_type,
                    "pattern_text": result.pattern_text,
                    "competing_entity": result.competing_entity,
                    "accusation_conflict": result.accusation_conflict,
                })

    df = pd.DataFrame(results)
    df.to_csv(OUT_PATH, index=False)
    print(f"\nSaved {len(df)} scored (entity, sentence) pairs to {OUT_PATH}")
    print("\nConfidence tier distribution:")
    print(df["confidence"].value_counts())
    print(f"\nOf {len(df)} entity mentions, {(df['confidence']=='none').sum()} ({(df['confidence']=='none').mean():.1%}) "
          f"show NO attribution pattern at all -- i.e. bare co-occurrence would have flagged these as "
          f"has_maverick=1 with no evidentiary function, exactly the gap this scorer targets.")


if __name__ == "__main__":
    main()
