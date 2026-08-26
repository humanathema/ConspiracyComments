"""build_aboutness_features.py

Rebuilds the aboutness/entity-salience feature (validated on 2026-08-20,
original script never promoted from scratchpad, not recoverable -- this
is a fresh implementation of the same documented method) for a genuinely
different FP-detector task design: is the target entity actually the
grammatical subject of the strongest evaluative language in the comment,
or just co-occurring with it.

Method (two-tier, per the original validation):
  1. Locate the sentence with the strongest evaluative language anywhere
     in the whole comment (VADER compound score, max absolute value) --
     not assumed to be the entity's own local sentence.
  2. Check whether the target entity co-occurs with that sentence, and
     whether it (or its dependency-chain ancestor) is the grammatical
     subject there (spaCy dependency parse).

Deterministic, no API calls, no GPU needed.
"""
import re
import sys
import pandas as pd
import spacy
from nltk.sentiment.vader import SentimentIntensityAnalyzer

nlp = spacy.load("en_core_web_sm")
sia = SentimentIntensityAnalyzer()


def entity_tokens_in_sent(sent, entity_words):
    """Return spaCy tokens in `sent` whose lowercased text matches any word of the entity."""
    return [tok for tok in sent if tok.text.lower() in entity_words]


def is_subject_or_ancestor_subject(tok):
    """True if tok is nsubj/nsubjpass, or any ancestor up the dep tree is."""
    cur = tok
    seen = set()
    while cur is not None and id(cur) not in seen:
        seen.add(id(cur))
        if cur.dep_ in ("nsubj", "nsubjpass"):
            return True
        if cur.head == cur:
            break
        cur = cur.head
    return False


def compute_features(text, entity):
    if not isinstance(text, str) or not text.strip() or not isinstance(entity, str) or not entity.strip():
        return None
    entity_words = set(w.lower() for w in re.findall(r"[a-zA-Z']+", entity) if len(w) > 2)
    if not entity_words:
        return None

    # 2026-08-23 fix: spaCy's default sentencizer fails to split on paragraph
    # breaks (blank lines) when there's no terminal punctuation before them --
    # common in informal Reddit text -- which was merging unrelated content
    # into one "sentence" and falsely inflating entity/evaluative-sentence
    # co-occurrence. Pre-split on blank lines first, sentence-segment each
    # paragraph separately, then treat the concatenated result as the
    # sentence sequence.
    paragraphs = [p for p in re.split(r"\n\s*\n", text[:3000]) if p.strip()]
    sents = []
    for para in paragraphs:
        doc = nlp(para)
        sents.extend(list(doc.sents))
    if not sents:
        return None

    sent_scores = []
    for s in sents:
        vs = sia.polarity_scores(s.text)
        sent_scores.append(vs["compound"])

    max_idx = max(range(len(sents)), key=lambda i: abs(sent_scores[i]))
    max_sent = sents[max_idx]
    max_score = sent_scores[max_idx]

    # which sentences does the entity appear in at all
    entity_sent_idxs = [i for i, s in enumerate(sents) if entity_tokens_in_sent(s, entity_words)]

    entity_in_max_sent = max_idx in entity_sent_idxs
    entity_is_subject_in_max_sent = False
    if entity_in_max_sent:
        for tok in entity_tokens_in_sent(max_sent, entity_words):
            if is_subject_or_ancestor_subject(tok):
                entity_is_subject_in_max_sent = True
                break

    if entity_sent_idxs:
        dist_to_max_eval_sent = min(abs(i - max_idx) for i in entity_sent_idxs)
        entity_own_sent_scores = [sent_scores[i] for i in entity_sent_idxs]
        entity_own_max_abs_score = max(entity_own_sent_scores, key=abs)
    else:
        dist_to_max_eval_sent = len(sents)  # entity never explicitly mentioned in any sentence (span match failed)
        entity_own_max_abs_score = 0.0

    return {
        "n_sentences": len(sents),
        "max_eval_compound": max_score,
        "entity_in_max_eval_sentence": int(entity_in_max_sent),
        "entity_is_subject_of_max_eval_sentence": int(entity_is_subject_in_max_sent),
        "dist_entity_to_max_eval_sentence": dist_to_max_eval_sent,
        "entity_own_sentence_max_abs_compound": entity_own_max_abs_score,
        "entity_mentioned_at_all": int(len(entity_sent_idxs) > 0),
    }


def main():
    input_path = sys.argv[1]
    output_path = sys.argv[2]
    text_col = sys.argv[3] if len(sys.argv) > 3 else "text"
    entity_col = sys.argv[4] if len(sys.argv) > 4 else "target_entity"

    df = pd.read_csv(input_path)
    print(f"{len(df)} rows to featurize", flush=True)

    feats = []
    for i, row in df.iterrows():
        f = compute_features(row[text_col], row[entity_col])
        feats.append(f if f is not None else {})
        if i % 50 == 0:
            print(f"  {i}/{len(df)}", flush=True)

    feat_df = pd.DataFrame(feats)
    out = pd.concat([df.reset_index(drop=True), feat_df], axis=1)
    out.to_csv(output_path, index=False)
    print(f"Saved {output_path}", flush=True)


if __name__ == "__main__":
    main()
