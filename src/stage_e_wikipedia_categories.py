"""Ground-up categorical bucketing using Wikipedia's own category system,
rather than parsing a single one-line description. Motivating gap: of
15,493 entities resolved to a real Wikipedia page, only 2,154 (14%) got
auto-bucketed from description-text keyword matching -- description is a
thin signal (one sentence). Categories are much richer: a typical article
carries 10-30 categories, community-maintained, e.g. Michael Yeadon's page
includes "British anti-vaccination activists", "COVID-19 conspiracy
theorists", "Pfizer people", "British pharmacologists" -- directly usable
role signal that a one-line description mostly doesn't surface.

Batched (50 titles/request, same technique as the disambiguation-check
Phase 1) -- ~310 requests for 15,493 titles, a few minutes, not per-title.

Two-step filter on the raw category list:
1. Drop Wikipedia's internal maintenance/tracking categories (birth-year,
   "Living people", "CS1:...", "Articles needing...", etc.) -- these carry
   no topical signal.
2. Match substantive categories against an expanded keyword-rule set (richer
   than wikidata_entity_lookup.py's description-only BUCKET_RULES, since
   category names are more specific/compositional, e.g. "British
   anti-vaccination activists" vs. just "activist").

Output: data/processed/stage_e_category_buckets.csv
"""
import re
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
import requests

WP_API = "https://en.wikipedia.org/w/api.php"
HEADERS = {"User-Agent": "ConspiracyThesisResearch/1.0 (academic research; contact: tobiasnash@gmail.com)"}
OUT_PATH = "data/processed/stage_e_category_buckets.csv"

MAINTENANCE_PATTERNS = re.compile(
    r"articles|all pages|all wikipedia|pages using|cs1|wikipedia |short description|"
    r"use \w+ dates|commons category|living people|births|deaths|"
    r"year of birth|year of death|webarchive|dmy dates|mdy dates|"
    r"engvarb|engvara|redirect|orphaned|stub|"
    r"external links|dead external links|"
    r"pages with|template",
    re.IGNORECASE,
)

# category-name substring -> bucket, grouped into PRIORITY TIERS (not a flat
# list). Bug found and fixed 2026-07-14: a flat "most matching categories
# wins" scheme let generic occupation tags outvote far more specific,
# construct-defining ones -- Graham Hancock has 5 "journalist"-pattern
# categories (wrote for the Guardian/Times/Independent) vs. only 2
# "Pseudoarchaeologists"/"Pseudohistorians" categories, so alternative_source
# won on raw count despite pseudoarchaeology being the obviously correct,
# far more decisive signal. Fix: within a tier, count still breaks ties, but
# ANY match in a higher tier always beats ANY count in a lower tier --
# construct-specific signals (tier 1) are inherently more informative than
# generic occupational ones (tier 3), regardless of how many of the latter
# a page happens to carry.
CATEGORY_BUCKET_TIERS = [
    # tier 1: construct-specific, highly decisive -- wins regardless of count
    [
        (r"whistleblow", "maverick_authority"),
        (r"conspiracy theor", "maverick_authority"),
        (r"anti-vaccin|anti-vax", "maverick_authority"),
        (r"holocaust denial|hiv/aids denial|climate change denial|genocide denial", "maverick_authority"),
        (r"ufo |pseudoarchaeolog|pseudohistor|pseudoscien|paranormal", "maverick_authority"),
        (r"intelligence (officers|agents|operatives)|cia officers|fbi agents|"
         r"nsa (employees|officials)|former (cia|fbi|nsa|mi5|mi6|kgb)", "maverick_authority"),
    ],
    # tier 2: institutional/organizational signals
    [
        (r"intelligence agenc|secret service|security service", "villain"),
        (r"government agenc|federal agenc|executive department|law enforcement agenc", "mainstream_source"),
        (r"news agenc|newspapers?\b|television networks?|broadcast(ers|ing)|news organi[sz]ation|"
         r"magazines?\b|press associations?", "mainstream_source"),
        (r"non-?profit|advocacy group|think tank", "alternative_source"),
        (r"pharmaceutical compan|multinational compan|technology compan|corporations?\b", "villain"),
    ],
    # tier 3: generic occupational signals -- easily outnumbered on a page
    # that also carries tier-1/2 categories, so only used when nothing
    # more specific matched
    [
        (r"politicians?\b|presidents? of|senators?\b|prime ministers? of|"
         r"members? of .*parliament|governors? of|congress(men|women)?\b|"
         r"cabinet officials", "mainstream_figure_not_source"),
        (r"journalists?\b|investigative report", "alternative_source"),
        (r"physicists?\b|biologists?\b|virologists?\b|epidemiologists?\b|"
         r"professors?\b|academics?\b|scientists?\b|researchers?\b|pharmacologists?\b|"
         r"immunologists?\b", "mainstream_expert_authority"),
        (r"actors?\b|musicians?\b|singers?\b|athletes?\b|footballers?\b|"
         r"comedians?\b|rappers?\b|wrestlers?\b", "other"),
        (r"deities|mythical|fictional characters?|religious figures?", "other"),
    ],
]
# flattened for backward compat with anything importing the old flat name
CATEGORY_BUCKET_RULES = [rule for tier in CATEGORY_BUCKET_TIERS for rule in tier]

# expert-credential signal, checked independently of bucket assignment --
# answers "does this person have (or claim) formal expert credentials",
# cross-cuts the bucket taxonomy rather than being one more bucket. This is
# what actually separates Michael Yeadon (pharmacologist) or Kary Mullis
# (Nobel chemist) from Alex Jones (radio host) or David Icke (former
# footballer/broadcaster) within maverick_authority.
EXPERT_CREDENTIAL_PATTERN = re.compile(
    r"physicists?\b|biologists?\b|chemists?\b|virologists?\b|epidemiologists?\b|"
    r"immunologists?\b|pharmacologists?\b|neurologists?\b|cardiologists?\b|"
    r"geneticists?\b|microbiologists?\b|toxicologists?\b|physicians?\b|"
    r"surgeons?\b|professors?\b|academics?\b|scientists?\b|researchers?\b|"
    r"engineers?\b|nobel laureates?\b|phd|doctorate",
    re.IGNORECASE,
)

# Broader than formal academic credentials: institutional-INSIDER status is
# its own distinct source of epistemic authority-appeal in this corpus --
# "I used to work at/for X, so I know what really happens there" is a
# recognizable, recurring rhetorical move independent of whether the person
# also holds a degree. Ex-intelligence (already partly captured as a
# maverick_authority bucket trigger, tier 1) is one instance of this
# pattern; ex-pharma/corporate insiders (the "Pfizer guy" pattern -- Wikipedia
# tags this as e.g. "Pfizer people") and military/government-official
# insider status are others. Checked independently of bucket assignment,
# same spirit as EXPERT_CREDENTIAL_PATTERN -- this is about SOURCE OF
# AUTHORITY, not formal credentials specifically.
INSTITUTIONAL_INSIDER_PATTERN = re.compile(
    r"cia (officers|agents|operatives|personnel)|fbi agents|nsa (employees|officials)|"
    r"(central intelligence agency|federal bureau of investigation|"
    r"national security agency|mi5|mi6|kgb|mossad) (people|officers|officials|personnel)|"
    r"intelligence officers|intelligence analysts|"
    r"pfizer people|moderna people|johnson & johnson people|"
    r"astrazeneca people|monsanto people|"
    r"(pharmaceutical|biotech) (company )?(employees|executives|people)|"
    r"military officers|generals|admirals|"
    r"government officials|diplomats|ambassadors|"
    r"cabinet members|white house (officials|staff)",
    re.IGNORECASE,
)


def epistemic_authority_kind(cats):
    """Returns a list of which authority-source signals apply (can be
    multiple) -- 'formal_credential' (physicist/professor/etc),
    'institutional_insider' (ex-CIA/ex-Pfizer/ex-military/etc), or both.
    Independent of bucket assignment; meant to be cross-tabbed against
    final_bucket_guess afterwards, not to replace it."""
    kinds = []
    if EXPERT_CREDENTIAL_PATTERN.search(" | ".join(cats)):
        kinds.append("formal_credential")
    if INSTITUTIONAL_INSIDER_PATTERN.search(" | ".join(cats)):
        kinds.append("institutional_insider")
    return kinds


def get_with_backoff(url, params, max_retries=5, timeout=20):
    delay = 1.0
    for _ in range(max_retries):
        resp = requests.get(url, params=params, headers=HEADERS, timeout=timeout)
        if resp.status_code == 429:
            time.sleep(delay)
            delay = min(delay * 2, 30)
            continue
        return resp
    return None


def batch_get_categories(titles, max_pages=25):
    """MediaWiki's cllimit caps the TOTAL categories returned across the
    WHOLE batched query, not per-title -- one title with ~50 categories can
    exhaust the response and silently starve every other title in the
    batch (confirmed: even batch size 3 only reliably populated 1 title).
    Fix: follow the `clcontinue` pagination token until the API stops
    returning one, accumulating categories across all pages."""
    result = defaultdict(list)
    params = {
        "action": "query", "titles": "|".join(titles),
        "prop": "categories", "cllimit": 50, "redirects": 1, "format": "json",
    }
    for _ in range(max_pages):
        resp = get_with_backoff(WP_API, params)
        if resp is None or resp.status_code != 200:
            break
        data = resp.json()
        pages = data.get("query", {}).get("pages", {})
        for p in pages.values():
            title = p.get("title", "")
            cats = [c["title"].replace("Category:", "") for c in p.get("categories", [])]
            result[title].extend(cats)
        cont = data.get("continue", {})
        if not cont:
            break
        params.update(cont)
    return dict(result)


def fetch_all_categories(titles, batch_size=20, workers=6):
    batches = [titles[i:i+batch_size] for i in range(0, len(titles), batch_size)]
    all_categories = {}
    start = time.time()
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = {ex.submit(batch_get_categories, b): b for b in batches}
        for i, fut in enumerate(as_completed(futures)):
            all_categories.update(fut.result())
            if (i + 1) % 20 == 0:
                print(f"  {(i+1)*batch_size}/{len(titles)} titles done "
                      f"({(time.time()-start)/60:.1f} min elapsed)", flush=True)
    return all_categories


def filter_substantive(cats):
    return [c for c in cats if not MAINTENANCE_PATTERNS.search(c)]


def guess_bucket_from_categories(cats):
    """Returns (bucket, n_matching_categories, tier_used). Two independent
    reliability problems, two independent fixes:
    (1) A single matching category out of a page's full category list
    (30-50+) is weak evidence on its own -- confirmed: 64% of
    maverick_authority matches were single-category-triggered, many false
    positives (Nixon, Giuliani, Michael Flynn). Multiple independent
    category matches for the same bucket is real corroboration a single
    incidental tag isn't -- see the n_matching_categories return value,
    used elsewhere to gate a "reliable" vs "weak_hint" confidence tier.
    (2) Even among matches, generic occupational categories (journalist,
    scientist) can outnumber far more specific, decisive ones
    (pseudoarchaeologist, whistleblower) on the same page just by raw count
    -- Graham Hancock has 5 journalist-pattern categories vs. 2
    pseudoarchaeology ones. Fixed by checking tiers in order: any match in
    tier 1 wins outright over any tier-3-only result, regardless of count.
    Bin Laden is a case (case (1) applies, not (2) -- "conspiracy theorist"
    genuinely is his single matching tier-1 category, correctly surfaced as
    weak/low-confidence by the caller, not something tiering fixes)."""
    for tier_idx, tier in enumerate(CATEGORY_BUCKET_TIERS):
        bucket_counts = defaultdict(int)
        for c in cats:
            c_l = c.lower()
            for pattern, bucket in tier:
                if re.search(pattern, c_l):
                    bucket_counts[bucket] += 1
                    break
        if bucket_counts:
            top_bucket, top_n = max(bucket_counts.items(), key=lambda x: x[1])
            return top_bucket, top_n, tier_idx
    return "", 0, None


def is_reliable_match(n_matches, tier_idx, total_substantive_categories):
    """2+ matches is reliable regardless of context (established earlier:
    multiple independent category assignments agreeing is real
    corroboration). Below that: a SINGLE tier-1 (most decisive) match can
    still be reliable if the page just doesn't have many categories to
    begin with -- AE911Truth has only 6 substantive categories total, one
    of which is "9/11 conspiracy theorists" (unambiguous, ~17% of all
    available signal on a thin page), very different from ADL's 1-in-50
    dilution (one incidental "genocide denial" tag among 50 categories
    about being an anti-hate-speech org). Threshold: page has <=10 total
    substantive categories AND the match came from tier 1."""
    if n_matches >= 2:
        return True
    if n_matches == 1 and tier_idx == 0 and total_substantive_categories <= 10:
        return True
    return False


def has_expert_credential(cats):
    """Independent of bucket assignment -- does this entity's category list
    show any formal expert-credential signal (physicist, pharmacologist,
    professor, etc)? Meant to cross-cut maverick_authority specifically:
    Michael Yeadon/Kary Mullis/John Clauser have this True, Alex
    Jones/David Icke/Roger Stone have it False."""
    return any(EXPERT_CREDENTIAL_PATTERN.search(c) for c in cats)


def main():
    t1 = pd.read_csv("data/processed/entity_wikidata_tier1.csv")
    d = pd.read_csv("data/processed/stage_d_resolved.csv")
    combined = pd.concat([t1, d], ignore_index=True)
    resolved = combined[combined["wp_title"].notna() & (combined["wp_title"] != "")].copy()
    titles = resolved["wp_title"].unique().tolist()
    print(f"{len(titles)} unique resolved titles, fetching categories "
          f"(batched w/ pagination, 6 parallel workers)...")

    title_categories = fetch_all_categories(titles, batch_size=20, workers=6)
    print(f"Done fetching categories for {len(title_categories)}/{len(titles)} titles")

    resolved["raw_categories"] = resolved["wp_title"].map(lambda t: title_categories.get(t, []))
    resolved["substantive_categories"] = resolved["raw_categories"].map(filter_substantive)
    resolved["category_bucket_guess"] = resolved["substantive_categories"].map(guess_bucket_from_categories)
    resolved["substantive_categories_str"] = resolved["substantive_categories"].map(lambda c: "; ".join(c))

    out_cols = ["entity", "doc_count", "wp_title", "wp_description",
                "tier1_bucket_guess", "category_bucket_guess", "substantive_categories_str"]
    out = resolved[[c for c in out_cols if c in resolved.columns]]
    out.to_csv(OUT_PATH, index=False)
    print(f"\nSaved {len(out)} rows to {OUT_PATH}")

    had_desc_bucket = (resolved["tier1_bucket_guess"].fillna("") != "")
    has_cat_bucket = (resolved["category_bucket_guess"] != "")
    print(f"\nHad a description-based bucket already: {had_desc_bucket.sum()}")
    print(f"Has a category-based bucket: {has_cat_bucket.sum()}")
    print(f"NEW bucket assignments from categories (had none before): "
          f"{(has_cat_bucket & ~had_desc_bucket).sum()}")
    print(f"\nCategory bucket distribution:")
    print(resolved["category_bucket_guess"].value_counts(dropna=False).to_string())


if __name__ == "__main__":
    main()
