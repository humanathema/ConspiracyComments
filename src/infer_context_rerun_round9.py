"""infer_context_rerun_round9.py — VM script

Re-score escalation candidates with submission context prepended.
Reads escalation candidates from round 9 inference output.
Builds text_with_context by joining with local post data.

Outputs:
  ~/outputs/round9/escalation_context_rerun_round9.parquet
    columns: id, target_entity, orig_margin, ctx_margin, ctx_pred_label, resolved

Usage (on VM, after SCP of posts data):
  python3 ~/infer_context_rerun_round9.py
"""

import os, json, gzip
os.environ.setdefault("CUDA_VISIBLE_DEVICES", "0")

import numpy as np
import pandas as pd
import torch
import torch.nn.functional as F
from pathlib import Path
from transformers import AutoTokenizer, AutoModelForSequenceClassification

CKPT_ROOT   = Path(os.path.expanduser("~/outputs/round8/checkpoints_twostage"))
ESC_FILE    = Path(os.path.expanduser("~/outputs/round9/batch_escalation_candidates_round9.csv"))
POSTS_FILES = [
    Path(os.path.expanduser("~/r_conspiracy_posts.jsonl")),
    Path(os.path.expanduser("~/r_conspiracy_posts2.jsonl.gz")),
]
OUT_DIR     = Path(os.path.expanduser("~/outputs/round9"))
MAX_LENGTH  = 768
INFER_BATCH = 64
MARGIN_THR  = 0.45

MODELS = [
    ("r7v1", "baseline"),
    ("r5v2", "baseline"),
    ("r7v3", "baseline"),
]

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
print(f"Device: {device}")


def build_context_texts(df, posts_files):
    """Pull submission titles and prepend as context."""
    # Get post IDs from link_id (t3_xxxxx -> xxxxx)
    # We need to fetch link_id from empath_scores — it's not in the escalation CSV
    # Fall back to title-only context if link_id not available
    needed_ids = set()
    if 'link_id' in df.columns:
        for lid in df['link_id'].dropna():
            lid = str(lid)
            needed_ids.add(lid[3:] if lid.startswith('t3_') else lid)

    post_titles = {}
    for pf in posts_files:
        if not pf.exists():
            continue
        opener = gzip.open if str(pf).endswith('.gz') else open
        with opener(pf, 'rt', encoding='utf-8', errors='replace') as f:
            for line in f:
                obj = json.loads(line.strip())
                pid = str(obj.get('id', ''))
                if pid in needed_ids:
                    post_titles[pid] = obj.get('title', '')[:400]
        print(f"  {pf.name}: {len(post_titles)} titles found")
        if len(post_titles) >= len(needed_ids):
            break

    texts_with_context = []
    for _, row in df.iterrows():
        lid = str(row.get('link_id', '') or '')
        pid = lid[3:] if lid.startswith('t3_') else lid
        title = post_titles.get(pid, '')
        if title:
            ctx = f"[SUBMISSION: {title}] "
        else:
            ctx = ""
        texts_with_context.append(
            "[ENTITY: " + str(row['target_entity']) + "] "
            + ctx + str(row['text'])
        )
    return texts_with_context


def load_model(path):
    return AutoModelForSequenceClassification.from_pretrained(
        str(path), torch_dtype=torch.float16
    ).to(device).eval()


def score_texts(tokenizer, model, texts):
    probs = []
    with torch.no_grad():
        for i in range(0, len(texts), INFER_BATCH):
            batch = list(texts[i:i + INFER_BATCH])
            enc = tokenizer(batch, max_length=MAX_LENGTH, truncation=True,
                            padding=True, return_tensors="pt")
            enc = {k: v.to(device) for k, v in enc.items()}
            probs.append(F.softmax(model(**enc).logits, dim=-1).cpu().float().numpy())
    return np.concatenate(probs, axis=0)


def run_twostage(tokenizer, s1_model, s2_model, texts):
    N = len(texts)
    s1 = score_texts(tokenizer, s1_model, texts)
    preds = np.full(N, 2, dtype=int)
    stance_mask = s1[:, 1] >= 0.5
    if stance_mask.sum() == 0:
        return preds
    stance_texts = [texts[i] for i in np.where(stance_mask)[0]]
    s2 = score_texts(tokenizer, s2_model, stance_texts)
    s2_pred = np.argmax(s2, axis=1)
    preds[np.where(stance_mask)[0]] = s2_pred
    return preds


def main():
    df = pd.read_csv(ESC_FILE)
    print(f"Escalation candidates: {len(df):,}")

    # Try to get link_id from the full scores parquet
    full_scores = OUT_DIR / "batch_ensemble_scores_round9.parquet"
    if full_scores.exists():
        meta = pd.read_parquet(full_scores, columns=['id', 'link_id'] if 'link_id' in pd.read_parquet(full_scores, columns=['id']).columns else ['id'])
        if 'link_id' in meta.columns:
            df = df.merge(meta[['id', 'link_id']], on='id', how='left')

    print("Building context texts ...")
    texts = build_context_texts(df, POSTS_FILES)

    all_preds = []
    for tag, arm in MODELS:
        s1_path = CKPT_ROOT / tag / arm / "stage1"
        s2_path = CKPT_ROOT / tag / arm / "stage2"
        if not s1_path.exists():
            print(f"MISSING {tag}/{arm} — skipping")
            continue
        print(f"\n[{tag}_{arm}] context re-inference ...")
        tokenizer = AutoTokenizer.from_pretrained(str(s1_path))
        s1 = load_model(s1_path)
        s2 = load_model(s2_path)
        preds = run_twostage(tokenizer, s1, s2, texts)
        all_preds.append(preds)
        del s1, s2
        torch.cuda.empty_cache()

    arr = np.stack(all_preds, axis=1)
    ensemble_pred = np.array([np.bincount(row, minlength=3).argmax() for row in arr])

    ctx_margins = []
    for row in arr:
        h, e = (row == 0).sum(), (row == 1).sum()
        total = h + e
        ctx_margins.append(abs(h / total - 0.5) if total > 0 else np.nan)
    ctx_margins = np.array(ctx_margins)

    id_to_label = {0: "hostile", 1: "endorsement", 2: "other"}
    df["ctx_ensemble_pred"] = ensemble_pred
    df["ctx_pred_label"]    = pd.Series(ensemble_pred).map(id_to_label).values
    df["ctx_margin"]        = ctx_margins
    df["resolved"]          = ctx_margins >= MARGIN_THR

    resolved = df["resolved"].sum()
    print(f"\nResolved (epistemic) with context: {resolved} / {len(df)} ({resolved/len(df)*100:.1f}%)")
    print(f"Still uncertain (aleatoric):        {len(df)-resolved} ({(len(df)-resolved)/len(df)*100:.1f}%)")

    out_path = OUT_DIR / "escalation_context_rerun_round9.parquet"
    df[["id", "target_entity", "margin", "ctx_margin", "ctx_pred_label", "resolved"]].to_parquet(out_path, index=False)
    print(f"\nSaved to {out_path}")

    # Summary for sign-off before frontier judge
    epistemic = df[df["resolved"]]
    aleatoric = df[~df["resolved"]]
    print(f"\n=== SIGN-OFF NEEDED before frontier judge ===")
    print(f"Epistemic (context resolved): {len(epistemic):,} rows → send to frontier judge")
    print(f"  Estimated Gemini cost: ~${len(epistemic) * 10 / 1_000_000 * 0.10:.2f} (rough: 10 tokens/row, $0.10/1M)")
    print(f"Aleatoric (still uncertain): {len(aleatoric):,} rows → HITL queue")


if __name__ == "__main__":
    main()
