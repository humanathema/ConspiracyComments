import os
import pandas as pd

def main():
    print("Generating reviewable candidate terms for Trump-era vs. Classical-conspiracy topic split...")
    
    # Format: (term, proposed_bucket, source_topic_id)
    candidates = [
        # --- Classical-conspiracy ---
        ("jfk", "classical", 34),
        ("kennedy", "classical", 34),
        ("oswald", "classical", 34),
        ("grassy knoll", "classical", 34),
        ("assassination", "classical", 34),
        ("dallas", "classical", 34),
        
        ("chemtrails", "classical", 33),
        ("contrails", "classical", 33),
        ("spraying", "classical", 33),
        
        ("illuminati", "classical", 36),
        ("satanic", "classical", 36),
        ("david icke", "classical", 36),
        ("icke", "classical", 36),
        ("occult", "classical", 36),
        ("satan", "classical", 36),
        
        ("nwo", "classical", 53),
        ("new world order", "classical", 53),
        
        ("ufo", "classical", 9),
        ("aliens", "classical", 9),
        ("ufos", "classical", 9),
        ("alien", "classical", 9),
        ("extraterrestrial", "classical", 9),
        
        ("nasa", "classical", 30),
        ("moon landing", "classical", 30),
        ("apollo", "classical", 30),
        
        ("mk-ultra", "classical", None),
        ("mkultra", "classical", None),
        ("rothschild", "classical", None),
        ("rockefeller", "classical", None),
        ("bohemian grove", "classical", None),
        ("reptilian", "classical", None),
        ("flat earth", "classical", None),
        ("area 51", "classical", None),
        
        # --- Trump-era ---
        ("maga", "trump_era", None),
        ("qanon", "trump_era", None),
        ("deep state", "trump_era", None),
        ("stolen election", "trump_era", None),
        ("jan 6", "trump_era", None),
        ("january 6", "trump_era", None),
        ("rigged election", "trump_era", None),
        ("adrenochrome", "trump_era", None),
        ("q drop", "trump_era", None),
        ("q drops", "trump_era", None),
        ("stolen ballots", "trump_era", None),
        ("election fraud", "trump_era", None),
        ("stop the steal", "trump_era", None),
        ("pizzagate", "trump_era", None),
        ("wayfair", "trump_era", None),
        ("save the children", "trump_era", None),
        ("great reset", "trump_era", None),
        ("dominion voting", "trump_era", None),
        ("fake news", "trump_era", None),
        ("trump", "trump_era", None),
        ("biden", "trump_era", None),
        ("hunter biden", "trump_era", None),
        ("burisma", "trump_era", None),
        ("storm the capitol", "trump_era", None),
        ("patriot party", "trump_era", None)
    ]
    
    df = pd.DataFrame(candidates, columns=["term", "proposed_bucket", "source_topic_id"])
    df["confirmed"] = "" # Keep blank for user review
    
    # Save to data/processed
    out_path = "data/processed/candidate_topic_split_terms.csv"
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    df.to_csv(out_path, index=False)
    
    print(f"Successfully generated {len(df)} candidate terms at {out_path}!")

if __name__ == "__main__":
    main()
