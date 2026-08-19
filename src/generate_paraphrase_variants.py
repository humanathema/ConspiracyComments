"""generate_paraphrase_variants.py

First step of the confidently-wrong detection thread (2026-08-18 session
discussion): deterministic, meaning-preserving paraphrases of the
human-labeled training rows, to check whether the already-trained
classifier flips its prediction (especially confidently, away from the
known true label) under a semantic-preserving rewrite. No LLM calls, no
retraining -- reuses the existing checkpoint.

Two paraphrase methods, compared on a small sample before committing to
one for the full run (this corpus's informal register -- slang,
profanity, political shorthand -- may not suit WordNet's curated synsets
well, per the earlier session discussion):

1. WordNet synonym substitution: fully deterministic, no model needed.
   Replaces a bounded number of non-stopword tokens with a WordNet
   synonym (same POS-agnostic heuristic -- first synset's first lemma
   that isn't the original word), skipping the entity name itself and
   very short/common words.

2. Masked-LM fill-in substitution: mask one token at a time, take the
   local MLM's top-1 prediction (deterministic, no sampling). More
   context-aware, likely better suited to this corpus's informal
   register than WordNet's curated vocabulary.

Output: two CSVs (one per method) with original + paraphrased text,
target_entity, and true label, ready for a follow-up inference-comparison
pass (not done here -- this script only generates the paraphrases).
"""
import random
import re
import sys

sys.path.insert(0, "src")
import pandas as pd

random.seed(42)

MAX_SUBSTITUTIONS = 3
URL_RE = re.compile(r"https?://\S+")


def _url_spans(text):
    return [(m.start(), m.end()) for m in URL_RE.finditer(text)]


def _is_eligible_word(word, char_pos, url_spans):
    """False for words inside a URL, ALL-CAPS/acronym tokens (MSM, GLP,
    TPTB -- substituting these breaks domain-specific meaning), and
    anything too short to substitute safely."""
    if any(s <= char_pos < e for s, e in url_spans):
        return False
    if word.isupper() and len(word) <= 6:
        return False
    return True


def _is_antonym(word, candidate, wordnet_mod):
    """True if `candidate` is a WordNet-listed antonym of `word` -- the
    real, dangerous failure mode found 2026-08-18: "hide" -> "expose" is
    a semantic inversion, not a synonym, and would silently corrupt any
    downstream fragility check (a prediction change would reflect the
    paraphrase changing the actual meaning, not the classifier being
    fragile). Applied as a safety filter to BOTH methods, not just
    WordNet's own substitutions, since the MLM method has no inherent
    concept of antonymy at all."""
    for syn in wordnet_mod.synsets(word.lower()):
        for lemma in syn.lemmas():
            if lemma.name().lower() == word.lower():
                for ant in lemma.antonyms():
                    if ant.name().lower() == candidate.lower():
                        return True
    return False


STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "is", "are", "was", "were", "be",
    "been", "being", "have", "has", "had", "do", "does", "did", "will",
    "would", "could", "should", "of", "to", "in", "on", "at", "for", "with",
    "as", "by", "this", "that", "these", "those", "it", "its", "he", "she",
    "they", "we", "you", "i", "my", "your", "his", "her", "their", "our",
    "not", "no", "so", "if", "then", "than", "just", "very", "also", "too",
}


def _token_positions(tokens):
    """Char offset of each token's start, given the token list reconstructs
    the original text via "".join(tokens)."""
    positions = []
    pos = 0
    for t in tokens:
        positions.append(pos)
        pos += len(t)
    return positions


def wordnet_paraphrase(text, target_entity, wordnet_mod, max_subs=MAX_SUBSTITUTIONS):
    entity_words = set(str(target_entity).lower().split())
    url_spans = _url_spans(text)
    tokens = re.findall(r"\w+|\W+", text)
    positions = _token_positions(tokens)
    word_indices = [i for i, t in enumerate(tokens)
                    if re.match(r"^\w+$", t) and t.lower() not in STOPWORDS
                    and t.lower() not in entity_words and len(t) > 3
                    and _is_eligible_word(t, positions[i], url_spans)]
    random.shuffle(word_indices)
    n_subs = 0
    for idx in word_indices:
        if n_subs >= max_subs:
            break
        word = tokens[idx]
        synsets = wordnet_mod.synsets(word.lower())
        if not synsets:
            continue
        lemmas = [l.name().replace("_", " ") for l in synsets[0].lemmas()]
        candidates = [l for l in lemmas if l.lower() != word.lower()
                      and not _is_antonym(word, l, wordnet_mod)]
        if not candidates:
            continue
        replacement = candidates[0]
        if word[0].isupper():
            replacement = replacement.capitalize()
        tokens[idx] = replacement
        n_subs += 1
    return "".join(tokens), n_subs


def mlm_paraphrase(text, target_entity, tokenizer, model, device, wordnet_mod, max_subs=MAX_SUBSTITUTIONS):
    import torch
    entity_words = set(str(target_entity).lower().split())
    url_spans = _url_spans(text)
    tokens = re.findall(r"\w+|\W+", text)
    positions = _token_positions(tokens)
    word_indices = [i for i, t in enumerate(tokens)
                    if re.match(r"^\w+$", t) and t.lower() not in STOPWORDS
                    and t.lower() not in entity_words and len(t) > 3
                    and _is_eligible_word(t, positions[i], url_spans)]
    random.shuffle(word_indices)
    n_subs = 0
    for idx in word_indices[:max_subs * 3]:  # try a few extra in case some fail
        if n_subs >= max_subs:
            break
        word = tokens[idx]
        masked_tokens = tokens.copy()
        masked_tokens[idx] = tokenizer.mask_token
        masked_text = "".join(masked_tokens)
        enc = tokenizer(masked_text, return_tensors="pt", truncation=True, max_length=256).to(device)
        mask_positions = (enc["input_ids"][0] == tokenizer.mask_token_id).nonzero(as_tuple=True)[0]
        if len(mask_positions) == 0:
            continue
        with torch.no_grad():
            out = model(**enc).logits
        top_id = out[0, mask_positions[0]].argmax().item()
        replacement = tokenizer.decode([top_id]).strip()
        if replacement and _is_antonym(word, replacement, wordnet_mod):
            continue
        if not replacement or replacement.lower() == word.lower() or not replacement.isalnum():
            continue
        if word[0].isupper():
            replacement = replacement.capitalize()
        tokens[idx] = replacement
        n_subs += 1
    return "".join(tokens), n_subs


def main():
    import nltk
    nltk.download("wordnet", quiet=True)
    nltk.download("omw-1.4", quiet=True)
    from nltk.corpus import wordnet

    df = pd.read_parquet("data/processed/stance_classifier_training_data_round10_truncation_fixed.parquet")
    human = df[df["is_human"] == True].copy()
    print(f"{len(human)} human-labeled rows", flush=True)

    sample = human.sample(n=min(80, len(human)), random_state=42)

    print("Generating WordNet paraphrases...", flush=True)
    wn_results = []
    for _, row in sample.iterrows():
        para, n_subs = wordnet_paraphrase(str(row["text"]), row["target_entity"], wordnet)
        wn_results.append({"text": row["text"], "paraphrase": para, "n_subs": n_subs,
                            "target_entity": row["target_entity"], "label": row["label"]})
    wn_df = pd.DataFrame(wn_results)
    wn_df.to_csv("outputs/reinfer_probs/paraphrase_sample_wordnet.csv", index=False)
    print(f"  mean substitutions: {wn_df['n_subs'].mean():.2f}", flush=True)

    print("Loading local MLM (distilbert-base-uncased) for fill-in substitution...", flush=True)
    import torch
    from transformers import AutoTokenizer, AutoModelForMaskedLM
    device = "mps" if torch.backends.mps.is_available() else "cpu"
    mlm_tokenizer = AutoTokenizer.from_pretrained("distilbert-base-uncased")
    mlm_model = AutoModelForMaskedLM.from_pretrained("distilbert-base-uncased").to(device)
    mlm_model.eval()

    print("Generating MLM paraphrases...", flush=True)
    mlm_results = []
    for i, (_, row) in enumerate(sample.iterrows()):
        para, n_subs = mlm_paraphrase(str(row["text"]), row["target_entity"], mlm_tokenizer, mlm_model, device, wordnet)
        mlm_results.append({"text": row["text"], "paraphrase": para, "n_subs": n_subs,
                             "target_entity": row["target_entity"], "label": row["label"]})
        if i % 20 == 0:
            print(f"  {i}/{len(sample)}", flush=True)
    mlm_df = pd.DataFrame(mlm_results)
    mlm_df.to_csv("outputs/reinfer_probs/paraphrase_sample_mlm.csv", index=False)
    print(f"  mean substitutions: {mlm_df['n_subs'].mean():.2f}", flush=True)

    print("\nSaved both samples to outputs/reinfer_probs/ for eyeball comparison.")

    # Semantic-similarity quality gate: sentence embeddings for original
    # vs. paraphrase, per Nash's point (2026-08-18) -- antonym-checking
    # alone doesn't catch broader meaning drift ("Torlonia family" ->
    # "Owl brothers" isn't an antonym relationship, just garbage). Given
    # the eventual scope here is small (3,582 human-labeled rows, further
    # narrowed to polar-vs-other errors specifically), a proper embedding
    # model is cheap enough to use as a real quality gate, not just eyeball
    # a sample and hope.
    print("\nLoading sentence embedding model (all-MiniLM-L6-v2) for semantic-similarity gate...", flush=True)
    from sentence_transformers import SentenceTransformer, util
    embed_model = SentenceTransformer("all-MiniLM-L6-v2")

    for name, d in [("wordnet", wn_df), ("mlm", mlm_df)]:
        orig_emb = embed_model.encode(d["text"].astype(str).tolist(), convert_to_tensor=True, show_progress_bar=False)
        para_emb = embed_model.encode(d["paraphrase"].astype(str).tolist(), convert_to_tensor=True, show_progress_bar=False)
        sims = util.cos_sim(orig_emb, para_emb).diagonal().cpu().numpy()
        d["semantic_similarity"] = sims
        print(f"\n{name}: mean similarity={sims.mean():.4f}, min={sims.min():.4f}, "
              f"pct below 0.85={(sims < 0.85).mean():.1%}, pct below 0.90={(sims < 0.90).mean():.1%}", flush=True)

    wn_df.to_csv("outputs/reinfer_probs/paraphrase_sample_wordnet.csv", index=False)
    mlm_df.to_csv("outputs/reinfer_probs/paraphrase_sample_mlm.csv", index=False)
    print("\nRe-saved both samples with semantic_similarity column.")


if __name__ == "__main__":
    main()
