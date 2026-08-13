"""Train 5-model ensemble on full training data, score 25k unlabeled batch.

This Kaggle kernel:
1. Loads stance_classifier_training_data.parquet
2. Trains 5 ModernBERT models (same config as validation ensemble)
3. Scores unlabeled_batch_round8.parquet
4. Filters for uncertain rows (margin < 0.45)
5. Outputs escalation candidates for frontier judge

Designed for Kaggle GPU (P100 or better).
"""
import numpy as np
import pandas as pd
import torch
from transformers import AutoTokenizer, AutoModelForSequenceClassification
from torch.utils.data import DataLoader, TensorDataset
from tqdm import tqdm

# Hyperparams (match validation training)
MODEL_NAME = "answerdotai/ModernBERT-large"
BATCH_SIZE = 4
MAX_LENGTH = 768
NUM_EPOCHS = 2
LEARNING_RATE = 2e-5

LABEL_MAP = {'hostile': 0, 'endorsement': 1, 'other': 2}
ID_TO_LABEL = {v: k for k, v in LABEL_MAP.items()}

print("=== Round 8: Train Ensemble + Score Batch ===\n")

# Load training data
print("Loading training data...")
train_data = pd.read_parquet('/kaggle/input/stance-round8-training/stance_classifier_training_data.parquet')
print(f"  Loaded {len(train_data)} rows")

# Load batch to score
print("Loading unlabeled batch...")
batch = pd.read_parquet('/kaggle/input/stance-round8-batch/unlabeled_batch_round8.parquet')
print(f"  Loaded {len(batch):,} rows")

# Map entity keywords to canonical formal names in memory
ENTITY_MAP = {
    'assange': 'Julian Assange',
    'snowden': 'Edward Snowden',
    'greenwald': 'Glenn Greenwald',
    'swartz': 'Aaron Swartz',
    'wikileaks': 'WikiLeaks',
    'fauci': 'Anthony Fauci',
    'gates': 'Bill Gates',
    'cdc': 'CDC',
    'who': 'WHO',
    'jones': 'Alex Jones',
    'carlson': 'Tucker Carlson',
    'stone': 'Roger Stone',
    'gaetz': 'Matt Gaetz'
}
if 'target_entity' in batch.columns:
    batch['target_entity'] = batch['target_entity'].astype(str).str.lower().str.strip().map(ENTITY_MAP).fillna(batch['target_entity'])

# Prepare training data with entity-conditioning prefix
X_train = ("[ENTITY: " + train_data["target_entity"].fillna("the subject").astype(str) + "] " + train_data["text"].astype(str)).values
y_train = train_data["label"].map(LABEL_MAP).values
print(f"\nLabel distribution in training data:")
for label_id, label_name in ID_TO_LABEL.items():
    count = (y_train == label_id).sum()
    pct = count / len(y_train) * 100
    print(f"  {label_name}: {count} ({pct:.1f}%)")

# Tokenize training data
print("\nTokenizing training data...")
tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
encodings_train = tokenizer(
    list(X_train),
    max_length=MAX_LENGTH,
    truncation=True,
    padding='max_length',
    return_tensors='pt'
)

# Create dataset
train_dataset = TensorDataset(
    encodings_train['input_ids'],
    encodings_train['attention_mask'],
    torch.tensor(y_train, dtype=torch.long)
)
train_loader = DataLoader(train_dataset, batch_size=BATCH_SIZE, shuffle=True)

print(f"Training data prepared: {len(train_dataset)} rows")

# Train 5 models
model_names = ['r7v2_split', 'r7v1_baseline', 'r5v2_baseline', 'r5v2_split', 'r7v3_baseline']
all_predictions = []

device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
print(f"\nUsing device: {device}\n")

for i, model_name in enumerate(model_names):
    print(f"Training model {i+1}/5: {model_name}")

    # Load model
    model = AutoModelForSequenceClassification.from_pretrained(
        MODEL_NAME,
        num_labels=3,
        torch_dtype=torch.float16 if 'cuda' in device.type else torch.float32
    )
    model.to(device)

    # Training loop
    optimizer = torch.optim.AdamW(model.parameters(), lr=LEARNING_RATE)

    for epoch in range(NUM_EPOCHS):
        model.train()
        total_loss = 0

        for batch_idx, (input_ids, attention_mask, labels) in enumerate(tqdm(train_loader, desc=f"Epoch {epoch+1}/{NUM_EPOCHS}")):
            input_ids = input_ids.to(device)
            attention_mask = attention_mask.to(device)
            labels = labels.to(device)

            outputs = model(input_ids, attention_mask=attention_mask, labels=labels)
            loss = outputs.loss

            loss.backward()
            optimizer.step()
            optimizer.zero_grad()

            total_loss += loss.item()

        avg_loss = total_loss / len(train_loader)
        print(f"  Epoch {epoch+1}: loss={avg_loss:.4f}")

    # Score batch
    print(f"  Scoring batch...")
    model.eval()

    # Tokenize batch with entity-conditioning prefix
    batch_texts = "[ENTITY: " + batch["target_entity"].fillna("the subject").astype(str) + "] " + batch["text"].astype(str)
    encodings_batch = tokenizer(
        list(batch_texts.values),
        max_length=MAX_LENGTH,
        truncation=True,
        padding='max_length',
        return_tensors='pt'
    )

    batch_dataset = TensorDataset(
        encodings_batch['input_ids'],
        encodings_batch['attention_mask']
    )
    batch_loader = DataLoader(batch_dataset, batch_size=BATCH_SIZE, shuffle=False)

    predictions = []
    with torch.no_grad():
        for input_ids, attention_mask in batch_loader:
            input_ids = input_ids.to(device)
            attention_mask = attention_mask.to(device)
            outputs = model(input_ids, attention_mask=attention_mask)
            preds = torch.argmax(outputs.logits, dim=1).cpu().numpy()
            predictions.extend(preds)

    all_predictions.append(np.array(predictions))
    print(f"  ✓ {model_name} scored")

# Ensemble voting
print("\nEnsemble voting...")
all_predictions = np.stack(all_predictions, axis=1)
ensemble_preds = np.array([np.bincount(row).argmax() for row in all_predictions])

# Calculate margins
print("Computing margins...")
margins = []
for i, row_votes in enumerate(all_predictions):
    hostile_count = (row_votes == 0).sum()
    endorse_count = (row_votes == 1).sum()
    total_stance = hostile_count + endorse_count

    if total_stance > 0:
        p_hostile_norm = hostile_count / total_stance
        margin = abs(p_hostile_norm - 0.5)
    else:
        margin = np.nan

    margins.append(margin)

margins = np.array(margins)

# Filter uncertain (margin < 0.45)
print("Filtering uncertain rows (margin < 0.45)...")
uncertain_mask = margins < 0.45
n_uncertain = uncertain_mask.sum()

escalation_batch = batch[uncertain_mask].copy()
escalation_batch['ensemble_pred'] = ensemble_preds[uncertain_mask]
escalation_batch['margin'] = margins[uncertain_mask]
escalation_batch['pred_label'] = escalation_batch['ensemble_pred'].map(ID_TO_LABEL)

print(f"  Uncertain rows: {n_uncertain}/{len(batch)} ({n_uncertain/len(batch)*100:.1f}%)")

# Save results
print(f"\nSaving outputs...")
batch_scores = batch.copy()
batch_scores['ensemble_pred'] = ensemble_preds
batch_scores['margin'] = margins
batch_scores.to_parquet('/kaggle/working/batch_ensemble_scores_round8.parquet', index=False)

escalation_batch.to_csv('/kaggle/working/batch_escalation_candidates_round8.csv', index=False)

print(f"✓ batch_ensemble_scores_round8.parquet ({len(batch_scores)} rows)")
print(f"✓ batch_escalation_candidates_round8.csv ({len(escalation_batch)} rows)")
print("\nDone!")
