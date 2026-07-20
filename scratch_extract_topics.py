import pandas as pd
import json

df = pd.read_csv('data/processed/monthTopics1.csv')
extracted = []
for idx, row in df.iterrows():
    extracted.append({
        'Topic': int(row['Topic']),
        'Count': int(row['Count']),
        'Name': str(row['Name']),
        'Representation': eval(row['Representation']) if isinstance(row['Representation'], str) else row['Representation']
    })

with open('data/processed/topics_summary.json', 'w') as f:
    json.dump(extracted, f, indent=2)

print(f"Extracted {len(extracted)} topics to data/processed/topics_summary.json")
