"""Refinement pass over Tier 1's low-confidence/unresolved entities.

Two-phase, batched to stay well within Wikipedia's rate limits:
  Phase 1 (cheap): batch-check (50 titles/request) whether each entity's
    current wp_title is a genuine Wikipedia disambiguation page. This is
    the "is this name ambiguous" signal Nash asked for.
  Phase 2 (targeted): only for confirmed disambiguation pages, fetch the
    page's linked candidates and rank them by real Wikipedia pageviews
    (last ~90 days) -- "backed by search term usage", per Nash's framing.
    Auto-resolve only when the top candidate's pageviews clearly beat the
    runner-up; otherwise leave it flagged ambiguous with the top candidates
    listed for a fast human pick.

Known residual gap (not fixable deterministically): a name can resolve
confidently to a real, non-disambiguation Wikipedia page that's simply the
WRONG entity (e.g. "Clintons" -> UK greeting-card chain, not the Clinton
family) with no disambiguation flag to catch it. Left for human review.

Output: data/processed/entity_disambiguation_refined.csv
"""
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
import requests

IN_PATH = "data/processed/entity_wikidata_tier1.csv"
OUT_PATH = "data/processed/entity_disambiguation_refined.csv"
WP_API = "https://en.wikipedia.org/w/api.php"
WP_PAGEVIEWS = "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia/all-access/all-agents/{}/monthly/20260401/20260701"
HEADERS = {"User-Agent": "ConspiracyThesisResearch/1.0 (academic research; contact: tobiasnash@gmail.com)"}


def get_with_backoff(url, params=None, max_retries=5):
    delay = 1.0
    for _ in range(max_retries):
        resp = requests.get(url, params=params, headers=HEADERS, timeout=15)
        if resp.status_code == 429:
            time.sleep(delay)
            delay = min(delay * 2, 30)
            continue
        return resp
    return None


def batch_check_disambiguation(titles):
    """titles: list of up to 50 Wikipedia page titles. Returns set of titles
    confirmed as disambiguation pages."""
    if not titles:
        return set()
    resp = get_with_backoff(WP_API, params={
        "action": "query", "titles": "|".join(titles),
        "prop": "pageprops", "format": "json",
    })
    if resp is None or resp.status_code != 200:
        return set()
    pages = resp.json().get("query", {}).get("pages", {})
    disambig = set()
    for p in pages.values():
        if "disambiguation" in p.get("pageprops", {}):
            disambig.add(p.get("title"))
    return disambig


def get_disambiguation_links(title, cap=10):
    resp = get_with_backoff(WP_API, params={
        "action": "query", "titles": title, "prop": "links",
        "plnamespace": 0, "pllimit": 30, "format": "json",
    })
    if resp is None or resp.status_code != 200:
        return []
    pages = resp.json().get("query", {}).get("pages", {})
    links = []
    for p in pages.values():
        for link in p.get("links", []):
            t = link.get("title", "")
            if not t.startswith("List of") and not t.startswith("Wikipedia:"):
                links.append(t)
    return links[:cap]


def get_pageviews_sum(title):
    resp = get_with_backoff(WP_PAGEVIEWS.format(title.replace(" ", "_")))
    if resp is None or resp.status_code != 200:
        return 0
    try:
        items = resp.json().get("items", [])
        return sum(i.get("views", 0) for i in items)
    except Exception:
        return 0


def resolve_disambiguated(entity, disambig_title):
    links = get_disambiguation_links(disambig_title)
    if not links:
        return "", 0, False, []
    scored = [(t, get_pageviews_sum(t)) for t in links]
    scored = [s for s in scored if s[1] > 0]
    scored.sort(key=lambda x: -x[1])
    if not scored:
        return "", 0, False, []
    top_title, top_views = scored[0]
    second_views = scored[1][1] if len(scored) > 1 else 0
    confident = top_views > 2 * max(second_views, 1)
    return top_title, top_views, confident, scored[:3]


def main():
    df = pd.read_csv(IN_PATH)
    # NOTE: disambiguation-page matches can score as "confident" under the
    # token-overlap heuristic when the query string equals the disambiguation
    # page's own title (e.g. "Bill" -> Wikipedia page literally titled
    # "Bill"). So this must check ALL resolved entities, not just the
    # low-confidence subset, or exactly those cases get silently missed.
    target = df.copy()
    print(f"{len(target)} entities to refine (all resolved + unresolved)")

    # Phase 1: batch disambiguation check, 50 titles/request
    titles_to_check = target[target["wp_title"].notna() & (target["wp_title"] != "")]["wp_title"].unique().tolist()
    print(f"Phase 1: checking {len(titles_to_check)} unique titles for disambiguation flag "
          f"({(len(titles_to_check)+49)//50} batched requests)...")
    disambig_titles = set()
    start = time.time()
    for i in range(0, len(titles_to_check), 50):
        batch = titles_to_check[i:i+50]
        disambig_titles |= batch_check_disambiguation(batch)
        if (i // 50 + 1) % 20 == 0:
            print(f"  {i+50}/{len(titles_to_check)} titles checked "
                  f"({(time.time()-start)/60:.1f} min elapsed)", flush=True)
    print(f"Phase 1 done: {len(disambig_titles)} confirmed disambiguation pages "
          f"({(time.time()-start)/60:.1f} min)")

    target["is_disambiguation"] = target["wp_title"].isin(disambig_titles)
    disambig_rows = target[target["is_disambiguation"]]
    print(f"\nPhase 2: resolving {len(disambig_rows)} disambiguation-flagged entities via pageviews...")

    results = {}
    start2 = time.time()
    with ThreadPoolExecutor(max_workers=5) as ex:
        futures = {ex.submit(resolve_disambiguated, row["entity"], row["wp_title"]): row["entity"]
                   for _, row in disambig_rows.iterrows()}
        for i, fut in enumerate(as_completed(futures)):
            entity = futures[fut]
            results[entity] = fut.result()
            if (i + 1) % 100 == 0:
                print(f"  {i+1}/{len(disambig_rows)} resolved "
                      f"({(time.time()-start2)/60:.1f} min elapsed)", flush=True)

    target["refined_title"] = target["entity"].map(lambda e: results.get(e, ("", 0, False, []))[0])
    target["refined_pageviews"] = target["entity"].map(lambda e: results.get(e, ("", 0, False, []))[1])
    target["refined_confident"] = target["entity"].map(lambda e: results.get(e, ("", 0, False, []))[2])
    target["refined_top3"] = target["entity"].map(
        lambda e: "; ".join(f"{t}({v})" for t, v in results.get(e, ("", 0, False, []))[3]))

    target.to_csv(OUT_PATH, index=False)
    print(f"\nSaved {len(target)} rows to {OUT_PATH}")
    print(f"\nDisambiguation-confirmed: {target['is_disambiguation'].sum()}")
    print(f"Successfully re-resolved with confidence: {target['refined_confident'].sum()}")


if __name__ == "__main__":
    main()
