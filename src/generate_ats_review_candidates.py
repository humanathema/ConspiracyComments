# src/generate_ats_review_candidates.py
"""
Generates a spreadsheet of new and ambiguous entity candidates unique to AboveTopSecret (ATS),
providing a blank decision column for Nash's human review before any changes are integrated.

Inputs:
  - data/processed/stage_b_ats_credential_hits.csv
  - data/processed/stage_b_ats_maverick_credential_hits.csv
  - data/processed/ats_entity_disambiguation_classified.csv
  - data/processed/ats_maverick_entity_disambiguation_classified.csv
  - data/processed/ats_comments_final.parquet

Output:
  - data/processed/ats_new_candidates_review.csv
"""
import os
import re
import csv
import json
import pandas as pd
import duckdb
from collections import defaultdict

from rerun_refined_regressions_v2 import load_entities_split_corrected

OUT_PATH = "data/processed/ats_new_candidates_review.csv"

# Stoplist of common false positives / noise words that shouldn't be treated as name candidates
STOPLIST = {
    "cia", "fbi", "nsa", "dia", "dea", "kgb", "mi5", "mi6", "fisa", "un", "unwise",
    "american", "americans", "russian", "russians", "chinese", "german", "germans",
    "british", "european", "europeans", "jewish", "jews", "jew", "christian", "christians",
    "nazi", "nazis", "republicans", "republican", "democrats", "democrat", "israeli",
    "israelis", "muslim", "muslims", "gop", "msm", "covid", "covid-19", "agent", "officer",
    "analyst", "operative", "former", "retired", "informant", "contractor", "director",
    "deputy", "chief", "chairman", "president", "secretary", "attorney", "general",
    "whistleblower", "whistleblowers", "source", "insider", "leak", "leaker", "leaks",
    "embassy", "department", "agency", "council", "committee", "office", "court", "judge"
}


def clean_name(name):
    # Strip non-alphabetic chars from ends and normalize spaces
    name = re.sub(r"[^A-Za-z\s\.-]", "", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name


def main():
    print("=== Generating ATS Human-Review Entity Candidates ===")

    # 1. Load already verified entities
    print("Loading existing verified entity lists...")
    mavericks, canon, consensus = load_entities_split_corrected()
    known_entities = set()
    for name in mavericks + canon + consensus:
        known_entities.add(name.strip().lower())

    if os.path.exists("data/processed/missing_entity_candidates.csv"):
        try:
            df_missing = pd.read_csv("data/processed/missing_entity_candidates.csv")
            for name in df_missing["entity"].dropna().unique():
                known_entities.add(name.strip().lower())
            print(f"Loaded {len(df_missing)} entities from missing_entity_candidates.csv")
        except Exception as e:
            print(f"Warning reading missing_entity_candidates: {e}")

    # 2. Extract and aggregate new credential hits (whistleblower/insider candidates)
    print("\nProcessing credential hits...")
    candidate_scores = defaultdict(int)
    candidate_triggers = defaultdict(set)
    candidate_contexts = {}  # name_lower -> example_context
    candidate_ids = {}  # name_lower -> sample_post_id
    candidate_display_names = {}  # name_lower -> best casing

    credential_files = [
        "data/processed/stage_b_ats_credential_hits.csv",
        "data/processed/stage_b_ats_maverick_credential_hits.csv"
    ]

    for fpath in credential_files:
        if not os.path.exists(fpath):
            print(f"  Note: {fpath} not found, skipping.")
            continue
        try:
            df_cred = pd.read_csv(fpath)
            print(f"  Loaded {len(df_cred)} hits from {fpath}")
            for _, row in df_cred.iterrows():
                raw_name = str(row["name"])
                cleaned = clean_name(raw_name)
                if not cleaned or len(cleaned) < 4:
                    continue
                key = cleaned.lower()
                if key in STOPLIST or key in known_entities:
                    continue
                # Skip simple dictionary words or things with no capital letters
                if not any(c.isupper() for c in raw_name):
                    continue

                candidate_scores[key] += 1
                candidate_triggers[key].add(str(row["trigger"]))
                # Keep first context as example
                if key not in candidate_contexts:
                    candidate_contexts[key] = str(row["context"])
                    candidate_ids[key] = str(row["id"])
                    candidate_display_names[key] = cleaned
        except Exception as e:
            print(f"  Error reading {fpath}: {e}")

    # 3. Extract and aggregate unresolved bare forms
    print("\nProcessing unresolved bare forms...")
    unresolved_counts = defaultdict(int)
    unresolved_ids = defaultdict(list)

    classification_files = [
        "data/processed/ats_entity_disambiguation_classified.csv",
        "data/processed/ats_maverick_entity_disambiguation_classified.csv"
    ]

    for fpath in classification_files:
        if not os.path.exists(fpath):
            print(f"  Note: {fpath} not found, skipping.")
            continue
        try:
            df_class = pd.read_csv(fpath)
            # Find rows where classified_as is null or empty
            df_unresolved = df_class[df_class["classified_as"].isna() | (df_class["classified_as"] == "")]
            print(f"  Loaded {len(df_class)} rows from {fpath} ({len(df_unresolved)} unresolved bare forms)")
            for _, row in df_unresolved.iterrows():
                cluster = str(row["cluster"])
                post_id = str(row["id"])
                unresolved_counts[cluster] += 1
                unresolved_ids[cluster].append(post_id)
        except Exception as e:
            print(f"  Error reading {fpath}: {e}")

    # Fetch contexts for unresolved bare forms from parquet
    all_unresolved_ids = []
    for cluster, ids in unresolved_ids.items():
        # Keep up to 5 sample IDs to fetch
        all_unresolved_ids.extend(ids[:5])

    unresolved_text_map = {}
    if all_unresolved_ids:
        print(f"  Fetching contexts for {len(all_unresolved_ids)} unresolved bare posts from ATS parquet...")
        try:
            con = duckdb.connect()
            # Fetch bodies for the unresolved IDs
            ids_str = ", ".join(f"'{id_}'" for id_ in all_unresolved_ids)
            query = f"""
                SELECT post_id, body 
                FROM read_parquet('data/processed/ats_comments_final.parquet')
                WHERE post_id IN ({ids_str})
            """
            rows = con.execute(query).fetchall()
            for post_id, body in rows:
                unresolved_text_map[post_id] = body
            con.close()
        except Exception as e:
            print(f"  Error fetching unresolved contexts from parquet: {e}")

    # 4. Write compiled spreadsheet
    review_rows = []

    # Add credential whistleblower candidates sorted by score
    sorted_candidates = sorted(candidate_scores.items(), key=lambda x: -x[1])
    print(f"\nAdding {len(sorted_candidates)} whistleblower/insider candidates next to credentials...")
    for key, count in sorted_candidates:
        display_name = candidate_display_names[key]
        triggers = ", ".join(sorted(candidate_triggers[key]))
        ctx = candidate_contexts[key].replace("\r", " ").replace("\n", " ").strip()
        review_rows.append({
            "entity": display_name,
            "source_type": f"credential_hit (trigger: {triggers})",
            "occurrences": count,
            "context_example": ctx,
            "decision": ""
        })

    # Add unresolved ambiguous bare-form summaries
    print(f"Adding unresolved bare-form summaries...")
    for cluster, count in sorted(unresolved_counts.items(), key=lambda x: -x[1]):
        # Get a sample text context
        ctx = "No context available"
        for pid in unresolved_ids[cluster]:
            if pid in unresolved_text_map:
                full_text = unresolved_text_map[pid]
                # Find bare form in text to extract a nice window
                idx = full_text.lower().find(cluster.lower())
                if idx != -1:
                    start_idx = max(0, idx - 80)
                    end_idx = min(len(full_text), idx + 80)
                    ctx = f"... {full_text[start_idx:end_idx].strip()} ..."
                    break

        review_rows.append({
            "entity": f"bare_form: {cluster}",
            "source_type": "unresolved_ambiguous_bare",
            "occurrences": count,
            "context_example": ctx.replace("\r", " ").replace("\n", " ").strip(),
            "decision": ""
        })

    if review_rows:
        df_out = pd.DataFrame(review_rows)
        df_out.to_csv(OUT_PATH, index=False)
        print(f"\nSUCCESS: Generated {len(df_out)} reviewable candidates to {OUT_PATH}")
    else:
        # Create empty file with columns
        with open(OUT_PATH, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["entity", "source_type", "occurrences", "context_example", "decision"])
        print(f"\nNo new candidates detected, created empty spreadsheet at {OUT_PATH}")


if __name__ == "__main__":
    main()
