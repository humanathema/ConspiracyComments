# src/build_ats_entity_examples.py
"""
Performs a consolidated scan over AboveTopSecret (ATS) corpus to extract entity mentions,
resolves bare forms using Stage B/C disambiguation lookups, filters list dumps,
orders examples by stars descending, and outputs the final ats_entity_examples.parquet
and ats_entity_examples.csv.

Stance and predicted labels are populated with placeholder values (to be classified in Task 2).

Entity matching uses an Aho-Corasick automaton (one linear pass per row over
all ~570 entity name variants combined) rather than a single giant regex
alternation run via Python's backtracking `re` engine -- the original
version took over an hour on the 9.24M-row corpus (profiled directly:
almost all of it inside `_sre_SRE_Scanner_search`) because Python's `re`
module scales poorly with large alternations at this row count, same root
cause as stage_b_consolidated_corpus_pass.py's fix earlier the same day.
Writes one Parquet file per chunk (globbed together at the end) instead of
a single incrementally-written file, so a killed/interrupted run can be
resumed by skipping chunks that already have an output file, rather than
restarting from scratch.
"""
import glob
import os
import re
import sys
import time
import pandas as pd
import numpy as np
import pyarrow.parquet as pq
import pyarrow as pa
import duckdb
import ahocorasick

sys.path.insert(0, os.path.dirname(__file__))
from refine_thesis_models import build_regex
from rerun_refined_regressions_v2 import load_entities_split_corrected
from combined_maverick_detector import CANDIDATE_TO_BARES as MAVERICK_CANDIDATE_TO_BARES
from consensus_disambiguation_lookup import CANDIDATE_TO_BARES as CONSENSUS_CANDIDATE_TO_BARES
from stance_window_utils import extract_entity_window, filter_quoted_spans, is_list_or_link_dump_window

ATS_CORPUS = "data/processed/ats_comments_final.parquet"
CHUNK_DIR = "data/processed/.ats_entity_mentions_chunks"
OUT_PARQUET = "data/processed/ats_entity_examples.parquet"
OUT_CSV = "data/processed/ats_entity_examples.csv"

_WORD_CHAR_RE = re.compile(r"[a-z0-9]")


def build_automaton(entities):
    """entities: list of original-case strings (e.g. "Julian Assange").
    Keys the automaton on lowercase text, payload is the original string,
    matching build_regex()'s IGNORECASE behavior."""
    A = ahocorasick.Automaton()
    for e in entities:
        A.add_word(e.lower(), e)
    A.make_automaton()
    return A


def find_spans_automaton(text_l, automaton):
    """Same shape of output as the old regex.finditer()-based version:
    a list of {"start", "end", "text"} dicts, boundary-checked so e.g.
    "cia" doesn't match inside "encyclopedia"."""
    spans = []
    for end_idx, original in automaton.iter(text_l):
        start_idx = end_idx - len(original) + 1
        before_ok = start_idx == 0 or not _WORD_CHAR_RE.match(text_l[start_idx - 1])
        after_ok = end_idx + 1 >= len(text_l) or not _WORD_CHAR_RE.match(text_l[end_idx + 1])
        if before_ok and after_ok:
            spans.append({"start": start_idx, "end": end_idx + 1, "text": text_l[start_idx:end_idx + 1]})
    return spans


def entity_groups_for_row(text, text_l, cid, automaton, lookup, candidate_to_bares):
    """Returns {entity_key: [span, ...]}. Filters out quoted spans. Same
    logic/behavior as the original regex-based version, just fed by the
    automaton match list instead of rx.finditer()."""
    direct_spans = find_spans_automaton(text_l, automaton)
    direct_spans = filter_quoted_spans(text, direct_spans)
    groups = {}
    for s in direct_spans:
        groups.setdefault(s["text"].lower(), []).append(s)
    if not groups:
        resolved = lookup.get(str(cid))
        if resolved:
            bares = candidate_to_bares.get(resolved, [])
            fallback_spans = []
            for bare in bares:
                bare_rx = re.compile(r'\b' + re.escape(bare) + r'\b', re.IGNORECASE)
                fallback_spans.extend({"start": m.start(), "end": m.end(), "text": m.group(0)} for m in bare_rx.finditer(text))
            fallback_spans = filter_quoted_spans(text, fallback_spans)
            if fallback_spans:
                groups[resolved.lower()] = fallback_spans
    return groups


def load_maverick_disambiguation_lookup():
    path = "data/processed/ats_maverick_entity_disambiguation_classified.csv"
    if not os.path.exists(path):
        print(f"WARNING: {path} not found. Maverick bare-form fallback will be empty.")
        return {}
    df = pd.read_csv(path)
    df = df[df["classified_as"].notna() & (df["classified_as"] != "")]
    return dict(zip(df["id"].astype(str), df["classified_as"]))


def load_consensus_disambiguation_lookup():
    path = "data/processed/ats_entity_disambiguation_classified.csv"
    if not os.path.exists(path):
        print(f"WARNING: {path} not found. Consensus bare-form fallback will be empty.")
        return {}
    df = pd.read_csv(path)
    df = df[df["classified_as"].notna() & (df["classified_as"] != "")]
    return dict(zip(df["id"].astype(str), df["classified_as"]))


def process_chunk(chunk, rx_mav_auto, rx_con_auto, lookup_mav, lookup_con):
    schema = pa.schema([
        ("comment_id", pa.string()),
        ("entity_key", pa.string()),
        ("construct", pa.string()),
        ("predicted_label", pa.string()),
        ("p_hostile", pa.float64()),
        ("p_endorsement", pa.float64()),
        ("upvotes", pa.float64()),
        ("text", pa.string()),
    ])
    chunk_rows = []
    for row in chunk.itertuples(index=False):
        cid = str(row.post_id)
        body = row.body
        starred = float(row.starred) if row.starred is not None else 0.0

        if not isinstance(body, str) or len(body) < 20:
            continue
        body_l = body.lower()

        mav_matches = entity_groups_for_row(body, body_l, cid, rx_mav_auto, lookup_mav, MAVERICK_CANDIDATE_TO_BARES)
        con_matches = entity_groups_for_row(body, body_l, cid, rx_con_auto, lookup_con, CONSENSUS_CANDIDATE_TO_BARES)

        clean_text = None
        for construct_name, matches in (("maverick", mav_matches), ("consensus", con_matches)):
            for entity_key, spans in matches.items():
                window = extract_entity_window(body, spans)
                if is_list_or_link_dump_window(window):
                    continue
                if clean_text is None:
                    clean_text = re.sub(r"[\r\n\t]+", " ", body).strip()
                chunk_rows.append({
                    "comment_id": cid,
                    "entity_key": entity_key,
                    "construct": construct_name,
                    "predicted_label": "unclassified",
                    "p_hostile": 0.0,
                    "p_endorsement": 0.0,
                    "upvotes": starred,
                    "text": clean_text,
                })
    if not chunk_rows:
        return None
    df_chunk = pd.DataFrame(chunk_rows)
    return pa.Table.from_pandas(df_chunk, schema=schema, preserve_index=False)


def main():
    print("=== Building ATS Entity Examples ===")

    print("Loading verified entity lists...")
    mavericks, canon, consensus = load_entities_split_corrected()
    rx_mav_auto = build_automaton(mavericks)
    rx_con_auto = build_automaton(consensus)
    print(f"  Built automatons: {len(mavericks)} maverick entities, {len(consensus)} consensus entities.")

    print("Loading ATS disambiguation lookups...")
    lookup_mav = load_maverick_disambiguation_lookup()
    lookup_con = load_consensus_disambiguation_lookup()
    print(f"  Loaded {len(lookup_mav)} Maverick lookup entries, {len(lookup_con)} Consensus lookup entries.")

    os.makedirs(CHUNK_DIR, exist_ok=True)
    cols = ["post_id", "body", "starred"]

    pf = pq.ParquetFile(ATS_CORPUS)
    total_comments = 0
    start = time.time()

    print("\nScanning ATS comments in chunks...")
    for i, batch in enumerate(pf.iter_batches(batch_size=500_000, columns=cols)):
        chunk_out_path = os.path.join(CHUNK_DIR, f"chunk_{i:04d}.parquet")
        total_comments += batch.num_rows
        if os.path.exists(chunk_out_path):
            print(f"  Chunk {i+1}: already done (checkpoint), skipping.", flush=True)
            continue

        chunk = batch.to_pandas()
        table = process_chunk(chunk, rx_mav_auto, rx_con_auto, lookup_mav, lookup_con)
        n_mentions = table.num_rows if table is not None else 0
        if table is not None:
            pq.write_table(table, chunk_out_path, compression="zstd")
        else:
            # Write an empty marker file so this chunk isn't re-scanned on resume
            open(chunk_out_path + ".empty", "w").close()

        elapsed_min = (time.time() - start) / 60
        print(f"  Chunk {i+1}: scanned {total_comments:,} comments, found {n_mentions:,} valid mentions "
              f"({elapsed_min:.1f} min elapsed)", flush=True)

    print(f"\nScanning complete. Total scanned: {total_comments:,} comments.")

    print("\nRanking mentions and keeping top 300 per entity key via DuckDB...")
    con = duckdb.connect()
    chunk_glob = os.path.join(CHUNK_DIR, "chunk_*.parquet")
    con.execute(f"""
        CREATE TABLE ranked_mentions AS
        WITH ranked AS (
            SELECT *,
                ROW_NUMBER() OVER (PARTITION BY entity_key ORDER BY upvotes DESC) AS rn
            FROM read_parquet('{chunk_glob}')
        )
        SELECT comment_id, entity_key, construct, predicted_label, p_hostile, p_endorsement, upvotes, text
        FROM ranked
        WHERE rn <= 300
    """)

    print(f"Writing final ranked examples to {OUT_PARQUET}...")
    con.execute(f"COPY (SELECT * FROM ranked_mentions) TO '{OUT_PARQUET}' (FORMAT PARQUET, COMPRESSION ZSTD)")

    print(f"Writing final ranked examples to {OUT_CSV}...")
    con.execute(f"COPY (SELECT * FROM ranked_mentions) TO '{OUT_CSV}' (FORMAT CSV, HEADER)")

    total_rows = con.execute("SELECT COUNT(*) FROM ranked_mentions").fetchone()[0]
    distinct_entities = con.execute("SELECT COUNT(DISTINCT entity_key) FROM ranked_mentions").fetchone()[0]
    print(f"\nSUCCESS: Materialized {total_rows:,} rows across {distinct_entities:,} unique entity keys.")

    con.close()

    for f in glob.glob(chunk_glob) + glob.glob(os.path.join(CHUNK_DIR, "*.empty")):
        os.remove(f)
    if os.path.isdir(CHUNK_DIR) and not os.listdir(CHUNK_DIR):
        os.rmdir(CHUNK_DIR)
    print("Removed chunk checkpoint files (run completed successfully).")


if __name__ == "__main__":
    main()
