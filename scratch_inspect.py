import sys
import os
import pandas as pd

# Add src/ to path so we can import the modules
sys.path.append(os.path.abspath('src'))

from maverick_authority_verified import VERIFIED_MAVERICK_AUTHORITY
from consensus_experts_verified import VERIFIED_CONSENSUS_EXPERTS
from refine_thesis_models import CANONICAL_EXPERTS

# Load maverick non-person candidates
non_person_df = pd.read_csv('data/processed/maverick_non_person_candidates.csv')
non_person_set = set(non_person_df['entity'].str.lower().dropna())

# Load attested entities from the corpus
attested_df = pd.read_csv('data/processed/maverick_authority_entities.csv')
attested_set = set(attested_df['entity'].str.lower().dropna())

# Surnames of maverick entities
maverick_surnames = {}
for m in VERIFIED_MAVERICK_AUTHORITY:
    parts = m.split()
    if len(parts) >= 2:
        surname = parts[-1]
        # Skip some common titles/suffixes
        if surname.lower() in ['jr.', 'jr', 'sr.', 'sr', 'ii', 'iii', 'iv']:
            if len(parts) >= 3:
                surname = parts[-2]
        maverick_surnames.setdefault(surname.lower(), []).append(m)

print(f"Total unique maverick surnames: {len(maverick_surnames)}")

# Let's find collisions with consensus experts
consensus_names = set(VERIFIED_CONSENSUS_EXPERTS)
consensus_surnames = {}
for c in VERIFIED_CONSENSUS_EXPERTS:
    parts = c.split()
    if len(parts) >= 2:
        surname = parts[-1]
        if surname.lower() in ['jr.', 'jr', 'sr.', 'sr']:
            if len(parts) >= 3:
                surname = parts[-2]
        consensus_surnames.setdefault(surname.lower(), []).append(c)

# Let's find collisions with canonical experts
canon_names = set(CANONICAL_EXPERTS)
canon_surnames = {}
for c in CANONICAL_EXPERTS:
    parts = c.split()
    if len(parts) >= 2:
        surname = parts[-1]
        canon_surnames.setdefault(surname.lower(), []).append(c)

# 1. Intra-maverick collisions (multiple mavericks share the same surname)
intra_collisions = {s: names for s, names in maverick_surnames.items() if len(names) > 1}
print("\n--- 1. INTRA-MAVERICK COLLISIONS ---")
for s, names in sorted(intra_collisions.items()):
    print(f"  {s}: {names}")

# 2. Maverick-Consensus/Canon collisions
cross_collisions = {}
for s, names in maverick_surnames.items():
    collides_with = []
    if s in consensus_surnames:
        collides_with.extend(consensus_surnames[s])
    if s in canon_surnames:
        collides_with.extend(canon_surnames[s])
    if collides_with:
        cross_collisions[s] = (names, collides_with)

print("\n--- 2. MAVERICK-CONSENSUS/CANON COLLISIONS ---")
for s, (m_names, c_names) in sorted(cross_collisions.items()):
    print(f"  {s}: {m_names} vs {c_names}")

# 3. Maverick-Non-Person collisions
non_person_collisions = {}
for s, names in maverick_surnames.items():
    if s in non_person_set:
        non_person_collisions[s] = names

print("\n--- 3. MAVERICK-NON-PERSON COLLISIONS ---")
for s, names in sorted(non_person_collisions.items()):
    print(f"  {s}: {names}")

# Let's check which of these surnames are actually attested in the corpus
print("\n--- SURNAMES THAT ARE ACTUALLY ATTESTED IN THE CORPUS (IN ATTESTED_SET) ---")
attested_surnames = {}
for s, names in maverick_surnames.items():
    if s in attested_set:
        attested_surnames[s] = names

for s, names in sorted(attested_surnames.items()):
    # Find any collisions
    col_str = []
    if len(names) > 1:
        col_str.append("intra-maverick")
    if s in cross_collisions:
        col_str.append(f"cross-expert ({cross_collisions[s][1]})")
    if s in non_person_set:
        col_str.append("non-person")
    col_desc = " | ".join(col_str) if col_str else "SAFE"
    print(f"  {s}: {names} ({col_desc})")
