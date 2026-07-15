"""build_historical_officeholders.py

Merges all expert sources (seed pools, US health rosters, Wikipedia categories,
OpenAlex citation elites, and existing verified experts) into a single, clean,
deduplicated superset. Applies the 2025-2026 Officeholder Guardrail and
the complete contrarian blocklist to prevent false-positive contamination.
"""
import os
import re
import pandas as pd

OUT_PATH = "data/processed/mainstream_expert_augmented_superset_temp.csv"

# Contrarian/Maverick/Critic Blocklist (expanded 2025-2026 officeholders + name-collisions)
BLOCKLIST = [
    "bhattacharya", "jay bhattacharya", "rfk jr", "robert f. kennedy jr", 
    "robert kennedy", "scott atlas", "vladimir zelenko", "zelenko", "paul marik", 
    "pierre kory", "geert vanden bossche", "john ioannidis", "p.a. ioannidis",
    "roy spencer", "john christy", "chris exley", "christopher exley", "martin pall", 
    "diane harper", "angus dalgleish", "tom jefferson", "vinay prasad", 
    "kary mullis", "mullis", "kerry mullis", "suzanne humphries", 
    "wolfgang wodarg", "marcia angell", "frances haugen", "john lott", 
    "richard wolff", "charles krauthammer", "sidney gottlieb", "bruce ivins", 
    "colin a. ross", "john mack", "norman finkelstein", "peter dale scott", 
    "sam harris", "richard dawkins", "dawkins", "zbigniew brzezinski", 
    "condoleezza rice", "samantha power", "john brennan", "william colby", 
    "louis freeh", "steve kappes", "dov zakheim", "john poindexter", 
    "kash patel", "eric schmidt", "joseph ladapo", "ladapo", "martin kulldorff", 
    "kulldorff", "sunetra gupta",
    # Specific name-collisions & mavericks to exclude from consensus expert categories:
    "peter duesberg", "duesberg", "elon musk", "musk", "david chandler",
    "andrew jackson", "n. cohen", "n cohen", "david keith"
]

def pass_claude_judgment_guardrail(name):
    norm = str(name).lower().strip()
    
    # Skip short or empty names
    if len(norm) < 3:
        return False
        
    for c in BLOCKLIST:
        # Exact match
        if c == norm:
            print(f"BLOCKING '{name}' (Exact blocklist match '{c}')")
            return False
        # Whole-word boundary match
        pattern = r"\b" + re.escape(c) + r"\b"
        if re.search(pattern, norm):
            print(f"BLOCKING '{name}' (Matched blocklist term '{c}' as a whole word)")
            return False
    return True

def clean_expert_name(name):
    if not isinstance(name, str):
        return ""
    # Strip titles and post-nominals
    n = name.strip()
    n = re.sub(r"^(Dr\.|Sir|Dame|Prof\.)\s+", "", n, flags=re.IGNORECASE)
    n = re.sub(r"\s+([A-Z]{2,4}|PhD|MD|FRS|OBE|CBE)$", "", n)
    return n.strip()

def get_verified_expert_metadata(clean_name):
    # Default is Public Health / office
    domain = "Public Health"
    basis_type = "office"
    
    name_lower = clean_name.lower()
    
    # 1. Economics
    economics_names = [
        "yellen", "janet yellen", "greenspan", "alan greenspan",
        "bernanke", "ben bernanke", "summers", "lawrence summers", "larry summers",
        "krugman", "paul krugman", "gary becker", "becker", "galbraith", "john kenneth galbraith"
    ]
    if any(n == name_lower for n in economics_names):
        domain = "Economics"
        if name_lower in ["krugman", "paul krugman", "gary becker", "becker"]:
            basis_type = "nobel"
        else:
            basis_type = "office"
            
    # 2. Climate
    elif name_lower in ["james hansen", "kevin trenberth"]:
        domain = "Climate"
        basis_type = "academy"
        
    # 3. Science Communication
    elif name_lower in [
        "neil degrassi tyson", "neil degrassetyson", "neil de grassetyson",
        "neil degrasse tyson", "stephen hawking", "steven hawking", "hawking",
        "carl sagan", "carl sagan's", "sagan"
    ]:
        domain = "Science Communication"
        basis_type = "academy"
        
    # 4. Science/Academy - Satoshi Omura
    elif name_lower in ["satoshi ōmura", "satoshi omura"]:
        domain = "Science/Academy"
        basis_type = "nobel"
        
    # 5. Public Health Nobel Laureates
    elif name_lower in ["katalin karikó", "katalin kariko", "drew weissman", "weissman"]:
        domain = "Public Health"
        basis_type = "nobel"
        
    # 6. Public Health Academic/Researchers
    elif name_lower in [
        "stanley plotkin", "david baltimore", "robert gallo",
        "christian drosten", "drosten", "amesh adalja", "angela rasmussen",
        "michael osterholm", "tim spector", "kevin folta", "folta",
        "charlotte thålin", "charlotte thalin", "andrew read", "john oxford",
        "paul offit", "peter hotez"
    ]:
        domain = "Public Health"
        basis_type = "academy"
        
    return domain, basis_type

def main():
    print("=== Merging and Filtering Mainstream Experts ===")
    
    # 1. Existing verified experts
    from consensus_experts_verified import VERIFIED_CONSENSUS_EXPERTS
    verified_records = []
    for name in VERIFIED_CONSENSUS_EXPERTS:
        clean_name = clean_expert_name(name)
        domain, basis_type = get_verified_expert_metadata(clean_name)
        verified_records.append({
            "name": clean_name,
            "domain": domain,
            "basis_type": basis_type,
            "basis_detail": "Existing Verified Expert",
            "source_url": "",
            "tenure_start": "",
            "tenure_end": "",
            "in_corpus_window": "Y",
            "h_index": "",
            "citation_count": "",
            "institution": "",
            "country": "",
            "notes": "Verified from consensus_experts_verified.py"
        })
    df_ver = pd.DataFrame(verified_records)
    print(f"Loaded {len(df_ver)} existing verified experts.")

    # 2. US Health Office Rosters
    df_roster = pd.read_csv("data/processed/us_health_office_rosters.csv")
    df_roster["name"] = df_roster["name"].apply(clean_expert_name)
    df_roster["notes"] = "US Health Office Roster"
    print(f"Loaded {len(df_roster)} US Health Office roster rows.")

    # 3. Mainstream Expert Seed Pool
    df_seed = pd.read_csv("data/processed/mainstream_expert_seed_pool.csv")
    df_seed["name"] = df_seed["name"].apply(clean_expert_name)
    print(f"Loaded {len(df_seed)} mainstream expert seed pool rows.")

    # 4. Institutional Authority Seed Pool
    df_inst = pd.read_csv("data/processed/institutional_authority_seed_pool.csv")
    df_inst["name"] = df_inst["name"].apply(clean_expert_name)
    print(f"Loaded {len(df_inst)} institutional authority seed pool rows.")

    # 5. PetScan (Wikipedia Academy) Experts
    df_pet = pd.read_csv("data/processed/petscan_experts.csv")
    df_pet["name"] = df_pet["name"].apply(clean_expert_name)
    print(f"Loaded {len(df_pet)} Wikipedia category expert rows.")

    # 6. OpenAlex Experts
    df_oa = pd.read_csv("data/processed/openalex_experts.csv")
    df_oa["name"] = df_oa["name"].apply(clean_expert_name)
    print(f"Loaded {len(df_oa)} OpenAlex expert rows.")

    # Merge all dataframes
    dfs = [df_ver, df_roster, df_seed, df_inst, df_pet, df_oa]
    merged = pd.concat(dfs, ignore_index=True)
    print(f"Total merged raw entries: {len(merged):,}")

    # Apply Claude Judgment Guardrail / Blocklist
    initial_len = len(merged)
    merged = merged[merged["name"].apply(pass_claude_judgment_guardrail)]
    print(f"Filtered out {initial_len - len(merged)} contrarian/blocked entries.")

    # Deduplicate by name, keeping the first occurrence (which preserves higher-precision details)
    # Ensure empty string is treated as NaN for deduplication or ignore it
    merged = merged[merged["name"] != ""]
    deduped = merged.drop_duplicates(subset=["name"], keep="first").copy()
    print(f"Deduplicated to {len(deduped):,} unique expert names.")

    # Fill optional missing columns
    cols = [
        "name", "domain", "basis_type", "basis_detail", "source_url",
        "tenure_start", "tenure_end", "in_corpus_window", "h_index",
        "citation_count", "institution", "country", "notes"
    ]
    for c in cols:
        if c not in deduped.columns:
            deduped[c] = ""
    
    # Enforce standard column ordering
    deduped = deduped[cols]
    
    # Save intermediate superset
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    deduped.to_csv(OUT_PATH, index=False)
    print(f"Saved merged deduplicated superset to {OUT_PATH}")

if __name__ == "__main__":
    main()
