"""Tier 1 of the entity-classification cascade (see corpus_entity_frequency_final.csv):
resolve each mined entity against Wikidata to get a structured, external
description, then apply a keyword heuristic to auto-bucket into the
maverick-authority taxonomy (mainstream_source / alternative_source /
mainstream_expert_authority / maverick_authority / villain / hero /
mainstream_figure_not_source / other / unresolved).

This does not require any corpus-context judgment calls -- it's a cheap,
objective pre-filter that should resolve a large fraction of entities before
Tier 2 (LLM classification on corpus examples) has to run on the residual.

Output: data/processed/entity_wikidata_tier1.csv
"""
import argparse
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
import requests

IN_PATH = "data/processed/corpus_entity_frequency_final.csv"
OUT_PATH = "data/processed/entity_wikidata_tier1.csv"
WD_API = "https://www.wikidata.org/w/api.php"
HEADERS = {"User-Agent": "ConspiracyThesisResearch/1.0 (academic research; contact: tobiasnash@gmail.com)"}

# Keyword -> bucket heuristic, checked in order against the Wikidata description
# (lowercased). First match wins. This is deliberately coarse -- it's meant to
# pre-sort the easy majority, not replace judgment on ambiguous cases.
BUCKET_RULES = [
    (r"\bwhistleblow", "maverick_authority"),
    (r"\bconspiracy theor", "maverick_authority"),
    (r"\bactivist\b.*\b(anti-vaccin|anti-vax|9/11 truth|chemtrail|flat earth)", "maverick_authority"),
    (r"\bufo\b|\bpseudo-?archaeolog|\bpseudo-?scien|\bparanormal", "maverick_authority"),
    (r"\bleaks?\b|\bleaked\b|\bleaking\b", "alternative_source"),
    (r"\bformer (cia|fbi|nsa|dia|dea|intelligence|mi5|mi6|kgb)\b", "maverick_authority"),
    (r"\bintelligence agency\b|\bsecret service\b|\bsecurity agency\b", "villain"),
    (r"\bgovernment agency\b|\bfederal agency\b|\bministry\b|\bdepartment of\b|\bexecutive department\b|\bfederal government\b|\blaw enforcement\b|\bdisaster response agency\b|\brevenue service\b", "mainstream_source"),
    (r"\badvocacy organi[sz]ation\b|\bpolitical party\b", "villain"),
    (r"\bnews agency\b|\bnewspaper\b|\btelevision network\b|\bbroadcaster\b|\bnews organi[sz]ation\b|\bmagazine\b", "mainstream_source"),
    (r"\bnon-?profit\b|\badvocacy group\b|\bthink tank\b", "alternative_source"),
    (r"\bpharmaceutical company\b|\bmultinational\b|\btechnology company\b|\bcorporation\b", "villain"),
    (r"\bpolitician\b|\bpresident\b|\bsenator\b|\bprime minister\b|\bmember of\b.*\bparliament\b|\bgovernor\b|\bcongress\b", "mainstream_figure_not_source"),
    (r"\bjournalist\b|\binvestigative\b", "alternative_source"),
    (r"\bscientist\b|\bphysicist\b|\bbiologist\b|\bvirologist\b|\bepidemiologist\b|\bprofessor\b|\bresearcher\b", "mainstream_expert_authority"),
    (r"\bactor\b|\bmusician\b|\bsinger\b|\bathlete\b|\bfootballer\b|\bcomedian\b|\brapper\b", "other"),
    (r"\breligious\b|\bdeity\b|\bgod\b|\bmythical\b|\bfictional\b", "other"),
]


def guess_bucket(description):
    if not description:
        return ""
    desc_l = description.lower()
    for pattern, bucket in BUCKET_RULES:
        if re.search(pattern, desc_l):
            return bucket
    return ""


WP_SEARCH_API = "https://en.wikipedia.org/w/api.php"
WP_SUMMARY_API = "https://en.wikipedia.org/api/rest_v1/page/summary/{}"


def looks_like_acronym_match(query, title):
    """WEF -> 'World Economic Forum' etc: query is all-caps and short, and its
    letters match the initials of the title's significant (capitalized) words."""
    q = re.sub(r"[^A-Za-z]", "", query)
    if not (2 <= len(q) <= 6 and q.isupper()):
        return False
    words = [w for w in re.findall(r"[A-Za-z]+", title) if w[0].isupper()]
    initials = "".join(w[0] for w in words).upper()
    return q in initials or initials.startswith(q)


def token_overlap_ok(query, title):
    """Cheap guard against Wikipedia search returning an unrelated same-first-name
    match (e.g. 'Whitney Webb' -> 'Whitney Blake'). Requires meaningful token
    overlap, containment, or acronym-initials match before trusting the match."""
    q_norm, t_norm = query.lower(), title.lower()
    if q_norm in t_norm or t_norm in q_norm:
        return True
    if looks_like_acronym_match(query, title):
        return True
    q_tokens = set(re.findall(r"\w+", q_norm))
    t_tokens = set(re.findall(r"\w+", t_norm))
    if not q_tokens or not t_tokens:
        return False
    overlap = len(q_tokens & t_tokens) / len(q_tokens | t_tokens)
    return overlap >= 0.5


def get_with_backoff(url, params=None, max_retries=5):
    """GET with exponential backoff on 429s. Returns the Response, or None
    after exhausting retries."""
    delay = 1.0
    for attempt in range(max_retries):
        resp = requests.get(url, params=params, headers=HEADERS, timeout=15)
        if resp.status_code == 429:
            time.sleep(delay)
            delay = min(delay * 2, 30)
            continue
        return resp
    return None


def lookup_entity(entity):
    try:
        resp = get_with_backoff(
            WP_SEARCH_API,
            params={"action": "query", "list": "search", "srsearch": entity,
                    "format": "json", "srlimit": 1},
        )
        if resp is None or resp.status_code != 200:
            return entity, "", f"__ERROR__: search status {resp.status_code if resp else 'no-response'}", False
        hits = resp.json().get("query", {}).get("search", [])
        if not hits:
            return entity, "", "", False
        title = hits[0]["title"]
        confident = token_overlap_ok(entity, title)

        summ = get_with_backoff(WP_SUMMARY_API.format(title.replace(" ", "_")))
        if summ is None or summ.status_code != 200:
            return entity, title, "", confident
        sdata = summ.json()
        desc = sdata.get("description", "") or ""
        return entity, title, desc, confident
    except Exception as e:
        return entity, "", f"__ERROR__: {e}", False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-doc-count", type=int, default=20)
    ap.add_argument("--limit", type=int, default=None, help="cap number of entities (for smoke tests)")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--input", default=IN_PATH)
    ap.add_argument("--output", default=OUT_PATH)
    args = ap.parse_args()

    df = pd.read_csv(args.input, usecols=["entity", "doc_count", "in_candidate_list", "already_triaged"])
    fresh = df[(~df["already_triaged"]) & (df["doc_count"] >= args.min_doc_count)].copy()
    fresh = fresh.sort_values("doc_count", ascending=False).reset_index(drop=True)
    if args.limit:
        fresh = fresh.head(args.limit)

    entities = fresh["entity"].tolist()
    print(f"Looking up {len(entities)} entities against Wikidata (min_doc_count={args.min_doc_count}, workers={args.workers})...")

    results = {}
    start = time.time()
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futures = {ex.submit(lookup_entity, e): e for e in entities}
        for i, fut in enumerate(as_completed(futures)):
            entity, title, desc, confident = fut.result()
            results[entity] = (title, desc, confident)
            if (i + 1) % 1000 == 0:
                elapsed = time.time() - start
                print(f"  {i+1}/{len(entities)} done ({elapsed/60:.1f} min elapsed, "
                      f"{(i+1)/elapsed:.1f} req/sec)", flush=True)

    elapsed = time.time() - start
    print(f"\nDone: {len(entities)} lookups in {elapsed/60:.1f} min")

    fresh["wp_title"] = fresh["entity"].map(lambda e: results.get(e, ("", "", False))[0])
    fresh["wp_description"] = fresh["entity"].map(lambda e: results.get(e, ("", "", False))[1])
    fresh["match_confident"] = fresh["entity"].map(lambda e: results.get(e, ("", "", False))[2])
    fresh["tier1_bucket_guess"] = fresh.apply(
        lambda r: guess_bucket(r["wp_description"]) if r["match_confident"] else "", axis=1)
    fresh["bucket"] = ""  # final human-confirmed bucket, blank for review

    fresh = fresh.sort_values("doc_count", ascending=False)
    fresh.to_csv(args.output, index=False)
    print(f"Saved {len(fresh)} rows to {args.output}")

    resolved = (fresh["wp_title"] != "") & (~fresh["wp_description"].str.startswith("__ERROR__", na=False))
    print(f"\nResolved (found a Wikipedia page): {resolved.sum()} / {len(fresh)}")
    print(f"Confident match (token overlap check passed): {fresh['match_confident'].sum()} / {len(fresh)}")
    print(f"Auto-bucketed by keyword rule: {(fresh['tier1_bucket_guess'] != '').sum()} / {len(fresh)}")
    print(f"\nBucket guess distribution:")
    print(fresh["tier1_bucket_guess"].value_counts(dropna=False).to_string())


if __name__ == "__main__":
    main()
