import os
import sys
import asyncio
import pandas as pd
import time

# Ensure we can import from src/
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from src.classification import (
    init_vertex_ai,
    get_model,
    classify_comment_async,
    TARGET_CATEGORIES
)

async def main():
    print("🚀 Starting Conspiracy Commons LLM Run...")
    
    # 1. Initialize Vertex AI
    print("🔑 Initializing Vertex AI...")
    try:
        init_vertex_ai()
        model = get_model()
        print("✅ Vertex AI and model initialized successfully.")
    except Exception as e:
        print(f"❌ Initialization failed: {e}")
        sys.exit(1)
        
    # 2. Load the candidate queue
    input_csv = "data/processed/commons_llm_results.csv"
    if not os.path.exists(input_csv):
        print(f"❌ Error: {input_csv} does not exist.")
        sys.exit(1)
        
    print(f"📋 Reading candidates from {input_csv}...")
    try:
        # Since the original has no headers, we read with header=None
        df = pd.read_csv(input_csv, header=None, names=["id", "text"] + TARGET_CATEGORIES)
        print(f"✅ Loaded {len(df)} candidates.")
    except Exception as e:
        print(f"❌ Failed to read CSV: {e}")
        sys.exit(1)
        
    # 3. Create Semaphore for concurrency control
    semaphore = asyncio.Semaphore(10)
    
    # 4. Define async function to classify single row
    async def process_row(index, row):
        text = str(row['text'])
        # Handle cases where text is empty
        if not text.strip():
            print(f"⚠️ Row index {index} has empty text. Skipping Vertex AI call.")
            return index, {cat: 0 for cat in TARGET_CATEGORIES}
            
        labels = await classify_comment_async(text, model, semaphore)
        return index, labels

    # 5. Run async classification tasks
    print("⚙️ Firing up async queue processing...")
    start_time = time.time()
    
    tasks = [process_row(idx, row) for idx, row in df.iterrows()]
    results = await asyncio.gather(*tasks)
    
    elapsed = time.time() - start_time
    print(f"⏳ Processed all {len(results)} items in {elapsed/60:.1f} minutes.")
    
    # 6. Apply classifications back to dataframe
    failed_count = 0
    for idx, labels in results:
        if labels is None or any(v is None for v in labels.values()):
            failed_count += 1
            # Fill with 0 or keep as None? Let's check: we want no nulls in the output, but let's see.
            # If a call actually failed, let's keep it as None so we can identify it, 
            # but we want to know if everything succeeded.
            if labels is None:
                labels = {cat: None for cat in TARGET_CATEGORIES}
        df.loc[idx, TARGET_CATEGORIES] = pd.Series(labels)
        
    print(f"📊 Completed run. Classification failures: {failed_count} / {len(df)}")
    
    # 7. Write to CSV with headers
    print(f"💾 Saving scores to {input_csv}...")
    df.to_csv(input_csv, index=False)
    print("✅ File saved successfully.")
    
    # 8. Run Verification & Metrics
    print("\n=== POST-RUN VALIDATION & METRICS ===")
    df_after = pd.read_csv(input_csv)
    print(f"Output shape: {df_after.shape}")
    
    null_counts = df_after[TARGET_CATEGORIES].isna().sum()
    print("Null counts per classification dimension:")
    print(null_counts)
    
    total_nulls = null_counts.sum()
    if total_nulls == 0:
        print("🎉 SUCCESS! No nulls/empty cells found in any classification columns.")
    else:
        print(f"⚠️ WARNING: Found {total_nulls} total null cells in classification columns.")
        
    print("\nPositive detection counts per category:")
    for cat in TARGET_CATEGORIES:
        pos_count = (df_after[cat] == 1).sum()
        pct = (pos_count / len(df_after)) * 100
        print(f"  {cat}: {pos_count} ({pct:.1f}%)")
    print("=====================================")

if __name__ == "__main__":
    asyncio.run(main())
