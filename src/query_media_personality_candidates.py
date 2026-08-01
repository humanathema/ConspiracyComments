"""query_media_personality_candidates.py

Pulls media/commentary-figure membership lists from the Wikipedia
Category API, same reproducible pattern as query_petscan_experts.py.
Stage 1 of handoff/task_2026-07-28c_media_personality_candidate_list_in_progress.md
-- see that file for the full plan and why this exists (the whistleblower
vs. media-personality stance contrast currently rests on 4 hardcoded
names, this builds a properly sourced candidate list for review instead).

"American_political_pundits" was checked against the live API and does
not exist as a category -- dropped, not included below.
"""
import os
import requests
import pandas as pd

OUT_PATH = "data/processed/media_personality_wikipedia_candidates.csv"

CATEGORIES = {
    "TV talk show host": "Category:American_television_talk_show_hosts",
    "Political commentator": "Category:American_political_commentators",
    "Podcaster": "Category:American_podcasters",
    "Talk radio host": "Category:American_talk_radio_hosts",
}


def fetch_category_members(category_name, limit=2000):
    print(f"Fetching members for {category_name}...")
    url = "https://en.wikipedia.org/w/api.php"
    headers = {"User-Agent": "HonoursThesisAcademicPipeline/1.0 (research)"}
    params = {
        "action": "query",
        "list": "categorymembers",
        "cmtitle": category_name,
        "cmlimit": 500,
        "format": "json",
    }

    members = []
    while len(members) < limit:
        r = requests.get(url, params=params, headers=headers)
        if r.status_code != 200:
            print(f"Error: Wikipedia API returned status {r.status_code}")
            break

        data = r.json()
        results = data.get("query", {}).get("categorymembers", [])
        for m in results:
            if m.get("ns") == 0:
                members.append(m.get("title"))

        if len(results) < 500 or "continue" not in data:
            break

        params["cmcontinue"] = data["continue"]["cmcontinue"]

    print(f"Retrieved {len(members)} pages for {category_name}")
    return members[:limit]


def is_valid_person_name(name):
    name_lower = name.lower().strip()
    if name_lower.startswith("list of"):
        return False
    if name_lower in [
        "american television talk show hosts",
        "american political commentators",
        "american podcasters",
        "american talk radio hosts",
    ]:
        return False
    return True


def main():
    print("=== Querying Wikipedia Media-Personality Categories ===")

    all_records = []
    for detail, cat_title in CATEGORIES.items():
        names = fetch_category_members(cat_title)
        for name in names:
            clean_name = name.split("(")[0].strip()
            if not is_valid_person_name(clean_name):
                print(f"Filtering out non-person category page: {clean_name}")
                continue
            all_records.append({
                "name": clean_name,
                "domain": "Media/Commentary",
                "basis_type": "media_platform",
                "basis_detail": detail,
                "source_url": f"https://en.wikipedia.org/wiki/{cat_title}",
                "notes": "Pulled from Wikipedia media-personality category",
            })

    df = pd.DataFrame(all_records)
    df = df.drop_duplicates(subset=["name"], keep="first")
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    df.to_csv(OUT_PATH, index=False)
    print(f"Saved {len(df)} unique media-personality candidates to {OUT_PATH}")
    print(df["basis_detail"].value_counts())


if __name__ == "__main__":
    main()
