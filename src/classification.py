import vertexai
from vertexai.generative_models import GenerativeModel
import asyncio
import pandas as pd
import random
import time

# --- CONFIGURATION ---
TARGET_CATEGORIES = [
    "anti_establishment_stance", "hedged_suspicion", "personal_experience",
    "source_citation", "appeal_to_authority", "procedural_skepticism", "maverick_authority"
]

SYSTEM_INSTRUCTION = (
    "You are an expert qualitative coder. Analyze the provided Reddit comment and list any of the following "
    "rhetorical strategies present: anti_establishment_stance, hedged_suspicion, personal_experience, "
    "source_citation, appeal_to_authority, procedural_skepticism, maverick_authority. "
    "If none are present, output 'none'."
)

def init_vertex_ai(project_id="conspiracycomments-499821", location="us-central1"):
    vertexai.init(project=project_id, location=location)

def get_model(endpoint="projects/216825947633/locations/us-central1/endpoints/8723006835042287616"):
    return GenerativeModel(endpoint)

def classify_comment_sync(text, model):
    prompt = f"System: {SYSTEM_INSTRUCTION}\n\nUser: {text}"
    max_retries = 6
    wait = 1.5
    
    for attempt in range(max_retries):
        try:
            response = model.generate_content(prompt)
            raw_output = response.text.strip().lower()
            
            results = {cat: 0 for cat in TARGET_CATEGORIES}
            if "none" not in raw_output:
                for cat in TARGET_CATEGORIES:
                    if cat in raw_output:
                        results[cat] = 1
            return results
            
        except Exception as e:
            if '429' in str(e) and attempt < max_retries - 1:
                jitter = random.uniform(0.1, 1.0)
                time.sleep(wait + jitter)
                wait *= 2
            else:
                return {cat: None for cat in TARGET_CATEGORIES}

async def classify_comment_async(text, model, semaphore):
    prompt = f"System: {SYSTEM_INSTRUCTION}\n\nUser: {text}"
    
    async with semaphore:
        for attempt in range(6):
            try:
                response = await asyncio.to_thread(model.generate_content, prompt)
                raw_output = response.text.strip().lower()
                
                results = {cat: 0 for cat in TARGET_CATEGORIES}
                if "none" not in raw_output:
                    for cat in TARGET_CATEGORIES:
                        if cat in raw_output:
                            results[cat] = 1
                return results
                
            except Exception as e:
                if '429' in str(e):
                    await asyncio.sleep(2 ** attempt + random.uniform(0.1, 1.0))
                else:
                    return {cat: None for cat in TARGET_CATEGORIES}

async def run_cascade_batch_async(df_target, model, output_csv, processed_ids, concurrent_requests=10):
    batch_size = 50 
    semaphore = asyncio.Semaphore(concurrent_requests)
    
    records_to_save = []
    start_time = time.time()
    
    print(f"⚙️ Firing up the ASYNC engine at {concurrent_requests} concurrent requests...")
    
    for index, row in df_target.iterrows():
        task = classify_comment_async(row['text'], model, semaphore)
        labels = await task
        
        output_row = {'id': row['id'], 'text': row['text']}
        output_row.update(labels)
        records_to_save.append(output_row)
        
        if len(records_to_save) >= batch_size:
            pd.DataFrame(records_to_save).to_csv(output_csv, mode='a', header=False, index=False)
            total = len(processed_ids) + index + 1
            print(f"💾 Saved {total:,} records... (Time: {(time.time() - start_time)/60:.1f} min)")
            records_to_save = []

    if records_to_save:
        pd.DataFrame(records_to_save).to_csv(output_csv, mode='a', header=False, index=False)

def pre_flight_cost_estimate(df, text_column, model_type="flash"):
    prices = {
        "flash": {"input": 0.075, "output": 0.30},
        "pro":   {"input": 3.50,  "output": 10.50}
    }
    
    est_output_tokens_per_row = 75 
    
    total_text_chars = df[text_column].astype(str).apply(len).sum()
    total_prompt_chars = len(SYSTEM_INSTRUCTION) * len(df)
    
    est_input_tokens = (total_text_chars + total_prompt_chars) / 4
    est_output_tokens = est_output_tokens_per_row * len(df)
    
    input_cost = (est_input_tokens / 1_000_000) * prices[model_type]["input"]
    output_cost = (est_output_tokens / 1_000_000) * prices[model_type]["output"]
    total_cost = input_cost + output_cost
    
    print("=== PRE-FLIGHT COST ESTIMATE ===")
    print(f"Dataset Size:   {len(df):,} rows")
    print(f"Model Selected: Gemini 1.5 {model_type.upper()}")
    print("-" * 35)
    print(f"Est. Input Tokens:  {est_input_tokens:,.0f} tokens")
    print(f"Est. Output Tokens: {est_output_tokens:,.0f} tokens")
    print("-" * 35)
    print(f"Est. Input Cost:  ${input_cost:.4f}")
    print(f"Est. Output Cost: ${output_cost:.4f}")
    print(f"TOTAL EST. COST:  ${total_cost:.4f}")
    print("===================================")
