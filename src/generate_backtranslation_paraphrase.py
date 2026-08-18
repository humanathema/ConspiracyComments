"""generate_backtranslation_paraphrase.py

Sentence-level paraphrase generation via back-translation (English ->
German -> English, MarianMT/opus-mt), compared against the word-
substitution methods in generate_paraphrase_variants.py. Nash's point
(2026-08-18): a document-level embedding model (MiniLM etc.) can't
GENERATE text -- it's encoder-only, no trained decoder to reconstruct
fluent text from a vector, only useful for scoring similarity, not
producing a paraphrase. Back-translation is the right tool for actual
generation: translation models are trained to preserve meaning across
languages, so round-tripping naturally rewords a whole sentence rather
than making isolated word swaps that can each subtly corrupt local
meaning (the "hide"->"expose" inversion, "Torlonia family"->"Owl
brothers" garbage found earlier testing word-substitution).

Deterministic (greedy decoding, no sampling) -- same constraint as the
word-substitution methods, no LLM API calls.
"""
import re
import sys

sys.path.insert(0, "src")
import pandas as pd
import torch
from transformers import MarianMTModel, MarianTokenizer

from clean_reddit_markdown import (
    clean_reddit_markdown, protect_links_for_translation, restore_links_after_translation,
)

EN_DE = "Helsinki-NLP/opus-mt-en-de"
DE_EN = "Helsinki-NLP/opus-mt-de-en"

URL_RE = re.compile(r"https?://\S+")
MIN_PROSE_WORDS = 8


def is_too_thin_to_translate(text):
    """True if there isn't enough real prose left to meaningfully
    translate, once URLs are stripped out. Found 2026-08-19: MarianMT
    hallucinates completely unrelated content when fed a bare URL or a
    near-empty comment plus a link ("Source?" + a link -> "The data will
    be published in the European Commission database") -- the model
    tries to translate URL text as if it were prose. Different failure
    trigger than stance_window_utils.py's is_list_or_link_dump_window()
    (which needs 2+ URLs specifically) -- this catches the single-URL,
    near-empty-prose case that one doesn't."""
    no_urls = URL_RE.sub("", str(text))
    return len(no_urls.split()) < MIN_PROSE_WORDS


def translate_batch(texts, tokenizer, model, device, batch_size=8, max_length=768):
    outputs = []
    for i in range(0, len(texts), batch_size):
        batch = [str(t)[:4000] for t in texts[i:i + batch_size]]  # cap input length, avoid pathological long comments -- 4000 chars comfortably covers max_length=768 tokens
        enc = tokenizer(batch, return_tensors="pt", truncation=True, padding=True, max_length=max_length).to(device)
        with torch.no_grad():
            # no_repeat_ngram_size=3: found 2026-08-19 that markdown/formatting-
            # heavy text (headers, bold, long dash separators) sends greedy
            # decoding into degenerate repetition loops ("usually usually
            # usually...", "==References==External links=="=x5) -- these
            # already get caught by the downstream semantic-similarity gate
            # (all scored <=0.157), but preventing the loop in the first
            # place recovers rows that would otherwise be wasted compute.
            gen = model.generate(**enc, max_length=max_length, num_beams=1, do_sample=False, no_repeat_ngram_size=3)
        outputs.extend(tokenizer.batch_decode(gen, skip_special_tokens=True))
    return outputs


import os

FULL_RUN = os.environ.get("FULL_RUN", "0") == "1"
OUT_PATH = "outputs/reinfer_probs/paraphrase_backtranslation_full.csv" if FULL_RUN \
    else "outputs/reinfer_probs/paraphrase_sample_backtranslation.csv"


def main():
    device = "mps" if torch.backends.mps.is_available() else "cpu"
    print(f"Using device: {device}, FULL_RUN={FULL_RUN}", flush=True)

    df = pd.read_parquet("data/processed/stance_classifier_training_data_round10_truncation_fixed.parquet")
    human = df[df["is_human"] == True].copy()
    if FULL_RUN:
        sample = human
    else:
        sample = human.sample(n=min(80, len(human)), random_state=42)  # same sample as the word-substitution comparison
    print(f"{len(sample)} candidate rows before filtering", flush=True)

    too_thin = sample["text"].apply(is_too_thin_to_translate)
    print(f"{too_thin.sum()} rows excluded as too URL-heavy/thin to translate meaningfully", flush=True)
    sample = sample[~too_thin].reset_index(drop=True)

    # Protect links (markdown + bare URLs) with prime placeholders BEFORE
    # any other cleaning -- must run first, on the raw text, since
    # clean_reddit_markdown's own link-handling would otherwise collapse
    # them to "anchor (domain)" before we get a chance to preserve the
    # full original link for restoration after translation. Once links
    # are swapped for plain numbers, clean_reddit_markdown's link regex
    # simply finds nothing left to touch, so running it second is safe --
    # it only strips headers/bold/separators/bullets at that point.
    too_many_links = pd.Series(False, index=sample.index)
    protected_texts, mappings = [], []
    for idx, text in sample["text"].items():
        try:
            protected, mapping = protect_links_for_translation(str(text))
        except ValueError:
            too_many_links[idx] = True
            protected, mapping = str(text), {}
        protected_texts.append(clean_reddit_markdown(protected))
        mappings.append(mapping)
    print(f"{too_many_links.sum()} rows excluded as having more links than the placeholder pool covers", flush=True)
    sample = sample[~too_many_links.values].reset_index(drop=True)
    protected_texts = [t for t, excl in zip(protected_texts, too_many_links) if not excl]
    mappings = [m for m, excl in zip(mappings, too_many_links) if not excl]
    print(f"{len(sample)} rows remaining for translation", flush=True)

    print("Loading en->de model...", flush=True)
    tok_ende = MarianTokenizer.from_pretrained(EN_DE)
    model_ende = MarianMTModel.from_pretrained(EN_DE).to(device).eval()

    print("Translating en->de...", flush=True)
    de_texts = translate_batch(protected_texts, tok_ende, model_ende, device)

    del model_ende
    if device == "mps":
        torch.mps.empty_cache()

    print("Loading de->en model...", flush=True)
    tok_deen = MarianTokenizer.from_pretrained(DE_EN)
    model_deen = MarianMTModel.from_pretrained(DE_EN).to(device).eval()

    print("Translating de->en (back)...", flush=True)
    back_texts = translate_batch(de_texts, tok_deen, model_deen, device)

    restored_texts = [restore_links_after_translation(t, m) for t, m in zip(back_texts, mappings)]
    links_dropped = sum(
        1 for t, m in zip(back_texts, mappings) for prime in m if prime not in t
    )
    print(f"placeholder primes not found after round-trip (link lost): {links_dropped}", flush=True)

    out = pd.DataFrame({
        "text": sample["text"].values,
        "paraphrase": restored_texts,
        "target_entity": sample["target_entity"].values,
        "label": sample["label"].values,
    })
    out.to_csv(OUT_PATH, index=False)
    print(f"\nSaved {len(out)} rows to {OUT_PATH}", flush=True)

    print("\nScoring semantic similarity...", flush=True)
    from sentence_transformers import SentenceTransformer, util
    embed_model = SentenceTransformer("all-MiniLM-L6-v2")
    orig_emb = embed_model.encode(out["text"].astype(str).tolist(), convert_to_tensor=True, show_progress_bar=False)
    para_emb = embed_model.encode(out["paraphrase"].astype(str).tolist(), convert_to_tensor=True, show_progress_bar=False)
    sims = util.cos_sim(orig_emb, para_emb).diagonal().cpu().numpy()
    out["semantic_similarity"] = sims
    out.to_csv(OUT_PATH, index=False)
    print(f"backtranslation: mean similarity={sims.mean():.4f}, min={sims.min():.4f}, "
          f"pct below 0.85={(sims < 0.85).mean():.1%}, pct below 0.90={(sims < 0.90).mean():.1%}", flush=True)


if __name__ == "__main__":
    main()
