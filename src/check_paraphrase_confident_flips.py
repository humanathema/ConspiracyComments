"""check_paraphrase_confident_flips.py

The actual motivating goal of the whole paraphrase/back-translation thread
(2026-08-18/19): run the trained classifier on both the original text and
its quality-gated back-translation paraphrase
(outputs/reinfer_probs/paraphrase_backtranslation_full.csv, 2,839 rows,
mean semantic similarity 0.951), and flag cases where the model flips a
CONFIDENT prediction on a meaning-preserving rewrite -- a real signal that
it latched onto surface phrasing rather than the underlying signal, not
just noise.

Deliberately targets the OTHER-vs-STANCE gate, not hostile/endorsement
polarity -- per Nash 2026-08-19: polarity is already solid (~0.71-0.74
kappa, established and re-confirmed repeatedly this project), it's the
"is there a stance at all" gate that has been the actual weak point this
whole project has fought (historically kappa 0.22-0.37 across every
intervention tried). Uses the same model+method already validated for
this specific task in the 2026-08-18 session
(handoff/task_2026-08-18_session_handoff_full_entity_pool_and_cascade_design.md):
binconf_other015's DeVries-Taylor self-assessed confidence head,
thresholded at 0.5, as a stand-in for the old explicit has-stance-vs-other
gate (measured there at kappa=0.348 on the original val set -- this script
first reproduces that on the paraphrase set's ORIGINAL side as a sanity
check that we're using the right model + method, then checks whether the
SAME gate flips on the paraphrased rewrite).
"""
import sys

sys.path.insert(0, "src")
import numpy as np
import pandas as pd
import torch
import torch.nn.functional as F
from sklearn.metrics import cohen_kappa_score
from transformers import AutoTokenizer

from train_binary_confidence import ConfidenceModel, MODEL_NAME

CHECKPOINT_DIR = "outputs/checkpoints/binconf_other015_binary_confidence"
IN_PATH = "outputs/reinfer_probs/paraphrase_backtranslation_full.csv"
OUT_PATH = "outputs/reinfer_probs/paraphrase_confident_flips_stage1_gate.csv"
MAX_LENGTH = 768
BATCH_SIZE = 8
CONF_THRESHOLD = 0.5  # matches the established stage1-proxy method (kappa=0.348 there)


def run_inference(model, tokenizer, texts, device):
    all_conf = []
    with torch.no_grad():
        for i in range(0, len(texts), BATCH_SIZE):
            batch = texts[i:i + BATCH_SIZE]
            enc = tokenizer(batch, truncation=True, padding=True, max_length=MAX_LENGTH, return_tensors="pt").to(device)
            _, conf = model(**enc)
            all_conf.append(conf.cpu())
    return torch.cat(all_conf).numpy()


def main():
    device = "cuda" if torch.cuda.is_available() else ("mps" if torch.backends.mps.is_available() else "cpu")
    print(f"Using device: {device}", flush=True)

    df = pd.read_csv(IN_PATH)
    print(f"{len(df)} rows, label counts: {dict(df['label'].value_counts())}", flush=True)
    true_has_stance = df["label"].isin(["hostile", "endorsement"]).to_numpy()

    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
    model = ConfidenceModel(MODEL_NAME).to(device)
    state = torch.load(f"{CHECKPOINT_DIR}/model_state.pt", map_location=device)
    model.load_state_dict(state)
    model.eval()

    orig_texts = ("[ENTITY: " + df["target_entity"].fillna("unknown").astype(str) + "] " + df["text"].astype(str)).tolist()
    para_texts = ("[ENTITY: " + df["target_entity"].fillna("unknown").astype(str) + "] " + df["paraphrase"].astype(str)).tolist()

    print("Running inference on original text...", flush=True)
    orig_conf = run_inference(model, tokenizer, orig_texts, device)
    print("Running inference on paraphrase text...", flush=True)
    para_conf = run_inference(model, tokenizer, para_texts, device)

    orig_gate = orig_conf >= CONF_THRESHOLD  # predicted "has stance"
    para_gate = para_conf >= CONF_THRESHOLD

    # Sanity check first: does this reproduce the known ~0.348 kappa on
    # THIS set's original text, confirming right model + right method
    # before trusting anything about the flip analysis below.
    kappa_orig = cohen_kappa_score(true_has_stance, orig_gate)
    print(f"\n=== sanity check: stage1-gate-proxy kappa on ORIGINAL text ===", flush=True)
    print(f"kappa={kappa_orig:.4f} (established baseline: 0.348 -- should be in the same range)", flush=True)

    kappa_para = cohen_kappa_score(true_has_stance, para_gate)
    print(f"\n=== same gate, applied to PARAPHRASE text ===", flush=True)
    print(f"kappa={kappa_para:.4f}", flush=True)

    flipped = orig_gate != para_gate
    print(f"\nGate flip rate (orig vs paraphrase): {flipped.mean():.1%} ({flipped.sum()}/{len(df)})", flush=True)

    # The real question: among rows the gate was CONFIDENT about on the
    # original (self-confidence far from the 0.5 threshold), how often
    # does the paraphrase flip it anyway? That's fragility, not noise.
    orig_dist_from_threshold = np.abs(orig_conf - CONF_THRESHOLD)
    hi_certainty = orig_dist_from_threshold >= np.median(orig_dist_from_threshold)
    print(f"\nFlip rate when orig gate was CONFIDENT (far from 0.5 threshold, >=median): "
          f"{flipped[hi_certainty].mean():.1%} (n={hi_certainty.sum()})", flush=True)
    print(f"Flip rate when orig gate was UNCERTAIN (close to 0.5 threshold, <median):  "
          f"{flipped[~hi_certainty].mean():.1%} (n={(~hi_certainty).sum()})", flush=True)

    orig_correct = orig_gate == true_has_stance
    confidently_right_but_flips = hi_certainty & orig_correct & flipped
    print(f"\nGate was CONFIDENT + CORRECT on original, but flips on paraphrase: "
          f"{confidently_right_but_flips.sum()} rows ({confidently_right_but_flips.mean():.1%} of all rows)", flush=True)

    out = pd.DataFrame({
        "text": df["text"], "paraphrase": df["paraphrase"], "target_entity": df["target_entity"],
        "true_label": df["label"], "true_has_stance": true_has_stance,
        "semantic_similarity": df["semantic_similarity"],
        "orig_confidence": orig_conf, "orig_gate_has_stance": orig_gate,
        "para_confidence": para_conf, "para_gate_has_stance": para_gate,
        "flipped": flipped, "orig_gate_correct": orig_correct,
        "confidently_right_but_flips": confidently_right_but_flips,
    })
    out.to_csv(OUT_PATH, index=False)
    print(f"\nSaved full comparison to {OUT_PATH}", flush=True)


if __name__ == "__main__":
    main()
