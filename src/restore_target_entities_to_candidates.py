"""restore_target_entities_to_candidates.py

Recover the target_entity column for batch_escalation_candidates_round8.csv
by regex-matching the comment text against known entity patterns.

Same entity/alias list as build_stance_classifier_training_data.py and
the existing queue-building scripts.
"""
import re
import pandas as pd

INPUT_PATH = 'data/processed/batch_escalation_candidates_round8.csv'
OUTPUT_PATH = 'data/processed/batch_escalation_candidates_round8_with_entity.csv'

# Entity aliases → canonical form (order matters: longer/more specific first)
ENTITY_PATTERNS = [
    # Whistleblowers
    (r'\bwikileaks?\b', 'WikiLeaks'),
    (r'\bjulian\s+assange\b|\bassange\b', 'Julian Assange'),
    (r'\bedward\s+snowden\b|\bsnowden\b', 'Edward Snowden'),
    (r'\baaron\s+swartz\b|\bswartz\b', 'Aaron Swartz'),
    (r'\bglenn\s+greenwald\b|\bgreenwald\b', 'Glenn Greenwald'),
    # Consensus experts
    (r'\bdr\.?\s*fauci\b|\banthony\s+fauci\b|\bfauci\b', 'Anthony Fauci'),
    (r'\bbill\s+gates\b|\bgates\b', 'Bill Gates'),
    (r'\b(?:the\s+)?cdc\b', 'CDC'),
    (r'\b(?:the\s+)?who\b', 'WHO'),
    # Mavericks
    (r'\balex\s+jones\b|\binfowars\b', 'Alex Jones'),
    (r'\btucker\s+carlson\b|\bcarlson\b', 'Tucker Carlson'),
    (r'\broger\s+stone\b', 'Roger Stone'),
    (r'\bmatt\s+gaetz\b|\bgaetz\b', 'Matt Gaetz'),
]

compiled = [(re.compile(pat, re.IGNORECASE), canonical) for pat, canonical in ENTITY_PATTERNS]


def detect_entity(text):
    if pd.isna(text):
        return None
    for pattern, canonical in compiled:
        if pattern.search(str(text)):
            return canonical
    return None


print("Loading escalation candidates...")
df = pd.read_csv(INPUT_PATH)
print(f"  {len(df)} rows, columns: {list(df.columns)}")

if 'target_entity' in df.columns:
    print("  target_entity already exists, checking coverage...")
    missing = df['target_entity'].isna().sum()
    print(f"  Missing: {missing}/{len(df)}")
else:
    df['target_entity'] = None
    print("  No target_entity column, creating from text...")

# Fill missing entities from text
mask = df['target_entity'].isna()
df.loc[mask, 'target_entity'] = df.loc[mask, 'text'].apply(detect_entity)

print(f"\nEntity coverage:")
print(f"  Resolved: {df['target_entity'].notna().sum()}/{len(df)}")
print(f"  Still missing: {df['target_entity'].isna().sum()}")
print()
print("Entity distribution:")
print(df['target_entity'].value_counts().head(20))

df.to_csv(OUTPUT_PATH, index=False)
print(f"\n✓ Saved to {OUTPUT_PATH}")
