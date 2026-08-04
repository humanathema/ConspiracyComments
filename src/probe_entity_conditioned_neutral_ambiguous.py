"""probe_entity_conditioned_neutral_ambiguous.py

Quick local probe: can an entity-conditioned roberta-base fine-tune
distinguish neutral vs ambiguous meaningfully better than TF-IDF+LogReg
did (kappa 0.056-0.186 depending on correction pass)? TF-IDF structurally
can't do the entity-conditioned reasoning this task needs (e.g. "Jones is
not Bill Hicks" is neutral toward Hicks but the identical words could be
non-neutral toward a different target) -- this tests whether that's
actually the missing ingredient, using the same `[ENTITY: X]` prefix
convention already validated in production (entity-conditioning ablation,
+0.0548 kappa isolated).

Uses the thorough-correction label set (hand-review + Gemini v2 revised
prompt, 460 rows, 74 changed from original raw_label) -- not a full
5-fold CV like the TF-IDF check, just a single stratified 80/20 split,
to get a fast indicative number before deciding whether this is worth a
more rigorous run.
"""
import numpy as np
import pandas as pd
import torch
from sklearn.model_selection import train_test_split
from sklearn.metrics import cohen_kappa_score, classification_report
from transformers import AutoTokenizer, AutoModelForSequenceClassification, Trainer, TrainingArguments


def build_corrected_set():
    df = pd.read_parquet('data/processed/stance_classifier_training_data.parquet')
    human = df[df['is_human'] == True].copy()
    sub = human[human['raw_label'].isin(['neutral', 'ambiguous'])].copy()
    sub['corrected'] = sub['raw_label']

    def apply_hand_correction(row):
        t = row['text']
        if t.startswith('what kind of deal would that be for Assange'):
            return 'ambiguous'
        if t.startswith('Where is this leftist journalism'):
            return 'ambiguous'
        if t.startswith('"an attack on me is an attack on science"'):
            return 'DROP'
        if t.startswith("The one I'm finding most fascinating"):
            return 'ambiguous'
        if 'pizza dough' in t:
            return 'ambiguous'
        if t.startswith('Not really, just post a video of Bill Hicks'):
            return 'DROP'
        if t.startswith('How to verify the data yourself'):
            return 'neutral'
        return row['corrected']

    sub['corrected'] = sub.apply(apply_hand_correction, axis=1)

    for f in ['/tmp/batch1_v2_merged.csv', '/tmp/batch2_v2_merged.csv']:
        gm = pd.read_csv(f)
        gm = gm[gm['target_entity'].notna()]
        gm = gm[gm['verdict_v2'].isin(['neutral', 'ambiguous'])]
        text_to_verdict = dict(zip(gm['text'], gm['verdict_v2']))
        mask = sub['text'].isin(text_to_verdict) & (sub['corrected'] == sub['raw_label'])
        sub.loc[mask, 'corrected'] = sub.loc[mask, 'text'].map(text_to_verdict)

    sub = sub[sub['corrected'] != 'DROP']
    sub = sub[sub['corrected'].isin(['neutral', 'ambiguous'])]
    sub = sub[sub['target_entity'].notna()]  # drop the nan-target data-quality rows
    return sub


def main():
    device = "cpu"  # MPS was hitting out-of-memory errors on this machine even for this tiny dataset
    print(f"device: {device}", flush=True)

    sub = build_corrected_set()
    sub['text_cond'] = "[ENTITY: " + sub['target_entity'].astype(str) + "] " + sub['text'].astype(str)
    sub['y'] = (sub['corrected'] == 'neutral').astype(int)
    print(f"{len(sub)} rows, class balance: {sub['corrected'].value_counts().to_dict()}", flush=True)

    train_df, val_df = train_test_split(sub, test_size=0.2, stratify=sub['y'], random_state=42)
    print(f"train={len(train_df)} val={len(val_df)}", flush=True)

    tokenizer = AutoTokenizer.from_pretrained("roberta-base")

    def encode(texts):
        return tokenizer(list(texts), truncation=True, padding=True, max_length=256, return_tensors="pt")

    train_enc = encode(train_df['text_cond'])
    val_enc = encode(val_df['text_cond'])

    class DS(torch.utils.data.Dataset):
        def __init__(self, enc, labels):
            self.enc = enc
            self.labels = list(labels)

        def __len__(self):
            return len(self.labels)

        def __getitem__(self, idx):
            item = {k: v[idx] for k, v in self.enc.items()}
            item['labels'] = torch.tensor(self.labels[idx])
            return item

    train_ds = DS(train_enc, train_df['y'].tolist())
    val_ds = DS(val_enc, val_df['y'].tolist())

    model = AutoModelForSequenceClassification.from_pretrained("roberta-base", num_labels=2).to(device)

    # class weights, same inverse-frequency formula used in production
    counts = train_df['y'].value_counts().sort_index()
    class_weights = torch.tensor(
        [len(train_df) / (2 * counts.get(i, 1)) for i in range(2)], dtype=torch.float
    ).to(device)

    class WeightedTrainer(Trainer):
        def compute_loss(self, model, inputs, return_outputs=False, **kwargs):
            labels = inputs.pop("labels")
            outputs = model(**inputs)
            logits = outputs.logits
            loss = torch.nn.functional.cross_entropy(logits, labels, weight=class_weights)
            return (loss, outputs) if return_outputs else loss

    def compute_metrics(eval_pred):
        logits, labels = eval_pred
        preds = np.argmax(logits, axis=1)
        return {"kappa": cohen_kappa_score(labels, preds)}

    args = TrainingArguments(
        output_dir="/tmp/probe_neutral_ambiguous_checkpoints",
        num_train_epochs=6, per_device_train_batch_size=16, per_device_eval_batch_size=16,
        learning_rate=2e-5, weight_decay=0.01, eval_strategy="epoch", save_strategy="no",
        logging_steps=10, report_to=[],
    )
    trainer = WeightedTrainer(model=model, args=args, train_dataset=train_ds, eval_dataset=val_ds,
                               compute_metrics=compute_metrics)
    trainer.train()

    preds = trainer.predict(val_ds)
    pred_labels = np.argmax(preds.predictions, axis=1)
    kappa = cohen_kappa_score(val_df['y'].to_numpy(), pred_labels)
    print(f"\n=== Entity-conditioned roberta-base kappa: {kappa:.4f} ===", flush=True)
    print(classification_report(val_df['y'], pred_labels, target_names=['ambiguous', 'neutral']))


if __name__ == "__main__":
    main()
