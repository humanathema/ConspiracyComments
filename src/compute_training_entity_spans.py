"""compute_training_entity_spans.py

Fills in entity_spans for the stance classifier training data -- only
1,588/42,863 (3.7%) rows had this computed already. Simpler than the
general corpus-scanning span problem (pull_hitl_val_batch.py's
compute_spans_for_row): here every row already pairs `text` with the
exact `target_entity` it's a label for, so this just needs to locate
where that entity appears in that text, not decide whether it's there.

Tries progressively looser matches, in order, first hit wins:
1. Full target_entity phrase, case-insensitive.
2. Last word only (surname/single distinctive token), case-insensitive,
   word-boundary anchored -- covers rows where the training text uses a
   bare-surname form of a multi-word target_entity.
Rows where neither matches keep entity_spans=None (rare; likely rows
where the entity is referenced only via a pronoun or alias not literally
in the text, e.g. multi-comment thread context that didn't make it into
this row's `text`).

Output: overwrites data/processed/stance_classifier_training_data_round10_truncation_fixed.parquet
with entity_spans filled in (backs up the original first).
"""
import json
import re
import shutil

import pandas as pd

PATH = "data/processed/stance_classifier_training_data_round10_truncation_fixed.parquet"


def find_spans(text, target_entity):
    text = str(text)
    entity = str(target_entity).strip()
    if not entity or entity.lower() == "nan":
        return None

    # Try 1: full phrase, case-insensitive, word-boundary anchored.
    pat = re.compile(r"\b" + re.escape(entity) + r"\b", re.IGNORECASE)
    matches = [{"start": m.start(), "end": m.end(), "text": m.group(0)} for m in pat.finditer(text)]
    if matches:
        return json.dumps(matches)

    # Try 2: last word only (bare surname / single distinctive token).
    last_word = entity.split()[-1]
    if len(last_word) >= 4:
        pat2 = re.compile(r"\b" + re.escape(last_word) + r"\b", re.IGNORECASE)
        matches = [{"start": m.start(), "end": m.end(), "text": m.group(0)} for m in pat2.finditer(text)]
        if matches:
            return json.dumps(matches)

    return None


def main():
    shutil.copy(PATH, PATH.replace(".parquet", "_prespans.bak.parquet"))
    df = pd.read_parquet(PATH)
    print(f"{len(df):,} rows, {df['entity_spans'].notna().sum():,} already have spans", flush=True)

    missing = df["entity_spans"].isna()
    print(f"computing spans for {missing.sum():,} rows...", flush=True)
    df.loc[missing, "entity_spans"] = df.loc[missing].apply(
        lambda r: find_spans(r["text"], r["target_entity"]), axis=1
    )

    still_missing = df["entity_spans"].isna().sum()
    print(f"still missing after computation: {still_missing:,} ({still_missing/len(df):.1%})", flush=True)

    df.to_parquet(PATH, index=False)
    print(f"Saved to {PATH}", flush=True)


if __name__ == "__main__":
    main()
