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

Beam search (num_beams=4), not greedy -- Nash confirmed 2026-08-19 exact
computational reproducibility isn't required (publishing the generated
paraphrase set + method is enough for others to verify), so there's no
determinism reason to stay on greedy, and beam search recovered a real
content-loss bug greedy had (see translate_batch). No LLM API calls.
"""
import gc
import re
import sys

sys.path.insert(0, "src")
import pandas as pd
import torch
from transformers import MarianMTModel, MarianTokenizer

from clean_reddit_markdown import (
    clean_reddit_markdown, protect_links_for_translation, protect_entities_for_translation,
    restore_links_after_translation,
)

EN_DE = "Helsinki-NLP/opus-mt-en-de"
DE_EN = "Helsinki-NLP/opus-mt-de-en"

URL_RE = re.compile(r"https?://\S+")
MIN_PROSE_WORDS = 8

# Found 2026-08-19: placeholder-prime survival degrades with link density
# per translation CALL, not per comment -- a comment with 8 links sent as
# one whole-document translation lost 3/8 primes, but the exact same text
# split into paragraph-level chunks (or sentence-level) and translated
# independently, then rejoined, survived 8/8. Doesn't fight the placeholder
# scheme's job of surviving within-chunk word-order shifts -- chunks are
# reassembled in their original order, never reordered relative to each
# other, so cross-chunk positional drift (the thing placeholders exist to
# handle) never comes up; only within-chunk order can shift, which is
# exactly what the primes already tolerate. Also directly resolves Nash's
# "just a list of links" case for free: a pure link-dump comment naturally
# splits into many tiny single-link paragraphs under this same rule,
# rather than needing special-case handling.
MAX_LINKS_PER_CHUNK = 3
SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


def chunk_protected_text(protected_text: str, mapping: dict):
    """Splits protected (prime-placeholder) text into chunks safe to
    translate independently: paragraph-level first, and any paragraph that
    still has more than MAX_LINKS_PER_CHUNK primes gets further split by
    sentence. Returns a list of (chunk_text, joiner_after) pairs where
    joiner_after is the whitespace to reinsert after that chunk when
    reassembling ("\n\n" between paragraphs, " " between sentences)."""
    primes_in = lambda s: sum(1 for p in mapping if p in s)
    paragraphs = protected_text.split("\n\n")
    chunks = []
    for pi, para in enumerate(paragraphs):
        para_joiner = "\n\n" if pi < len(paragraphs) - 1 else ""
        if primes_in(para) <= MAX_LINKS_PER_CHUNK:
            chunks.append((para, para_joiner))
            continue
        sentences = [s for s in SENTENCE_SPLIT_RE.split(para) if s.strip()]
        for si, sent in enumerate(sentences):
            sent_joiner = " " if si < len(sentences) - 1 else para_joiner
            chunks.append((sent, sent_joiner))
    return chunks


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


def translate_batch(texts, tokenizer, model, device, batch_size=4, max_length=512):
    outputs = []
    for batch_num, i in enumerate(range(0, len(texts), batch_size)):
        # Found 2026-08-19 (real near-OOM, caught by Nash checking Activity
        # Monitor -- top's RSIZE showed 10GB resident, ps's RSS badly
        # undercounted it): MPS's allocator cache grows across many
        # generate() calls in this loop when never cleared. Clearing every
        # 20 batches looked sufficient in a small 60-batch test (flat
        # ~2GB) but still grew to 7GB+ over the real ~1,371-batch full
        # run -- a hard safety-monitor kill caught it before OOM. Variable
        # input lengths (different padded shapes each batch) are the
        # likely driver on MPS, not just allocator fragmentation, so
        # clearing every batch plus a real gc.collect() (drops any
        # lingering Python-side references to prior batches' tensors
        # before MPS can reclaim them) is the safer version of the same
        # fix, verified 2026-08-19 at full-run batch-count scale before
        # relying on it again.
        if device == "mps":
            gc.collect()
            torch.mps.empty_cache()
        elif device == "cuda":
            torch.cuda.empty_cache()
        batch = [str(t)[:2600] for t in texts[i:i + batch_size]]  # cap input length, avoid pathological long comments -- 2600 chars comfortably covers max_length=512 tokens
        enc = tokenizer(batch, return_tensors="pt", truncation=True, padding=True, max_length=max_length).to(device)
        with torch.no_grad():
            # no_repeat_ngram_size=3: found 2026-08-19 that markdown/formatting-
            # heavy text (headers, bold, long dash separators) sends greedy
            # decoding into degenerate repetition loops ("usually usually
            # usually...", "==References==External links=="=x5) -- these
            # already get caught by the downstream semantic-similarity gate
            # (all scored <=0.157), but preventing the loop in the first
            # place recovers rows that would otherwise be wasted compute.
            #
            # num_beams=4 (was 1/greedy): found 2026-08-19 greedy decoding
            # silently dropped an entire opening sentence ("Watergate
            # changed the country.") from a 6-sentence comment -- confirmed
            # via isolated re-run that beam search recovers it, greedy
            # doesn't, regardless of no_repeat_ngram_size. Not a speed-vs-
            # quality tradeoff we need to avoid: Nash already established
            # (2026-08-19) exact reproducibility isn't required here, only
            # that the method + generated set both get published, so
            # there's no determinism reason to stay on greedy.
            gen = model.generate(**enc, max_length=max_length, num_beams=4, do_sample=False, no_repeat_ngram_size=3)
        outputs.extend(tokenizer.batch_decode(gen, skip_special_tokens=True))
    return outputs


import os

FULL_RUN = os.environ.get("FULL_RUN", "0") == "1"
OUT_PATH = "outputs/reinfer_probs/paraphrase_backtranslation_full.csv" if FULL_RUN \
    else "outputs/reinfer_probs/paraphrase_sample_backtranslation.csv"


def main():
    device = "cuda" if torch.cuda.is_available() else ("mps" if torch.backends.mps.is_available() else "cpu")
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

    # Protect the row's own known target_entity (case-insensitive) so the
    # exact entity a training label is ABOUT can't get corrupted by
    # back-translation ("KKK"->"CCC"-class errors). Deliberately NOT using
    # general spaCy NER protection here -- tried it 2026-08-19, found it
    # over-fires on dense conspiracy-comment text (NIH/FDA/PCR/dates all
    # getting tagged ORG/etc and swapped for numbers), which guts whole
    # sentences down to strings of digits, defeats the actual point of
    # back-translation (natural rewording, not word-substitution), AND
    # recreates the exact "isolated placeholder, no surrounding context"
    # hallucination bug already fixed once for links (a paragraph reduced
    # to nothing but one bare number). Corrupting a NON-target proper noun
    # is low-stakes phrasing drift; only the target_entity itself is worth
    # this protection given that asymmetry -- runs AFTER clean_reddit_markdown
    # and link protection so its prime allocation can't collide with
    # already-placed link primes.
    entity_protected_texts = []
    for text, mapping, target_entity in zip(protected_texts, mappings, sample["target_entity"].values):
        entity_protected, entity_mapping = protect_entities_for_translation(
            text, nlp=None, target_entity=str(target_entity) if pd.notna(target_entity) else None,
            exclude_primes=set(mapping),
        )
        entity_protected_texts.append(entity_protected)
        mapping.update(entity_mapping)
    protected_texts = entity_protected_texts

    # Chunk each row (paragraph-level, sentence-level fallback for
    # link-dense paragraphs) and flatten into one list of translation
    # units so batching still spans across rows efficiently. row_chunk_map
    # tracks which flattened-chunk indices belong to which row, in order,
    # so rows can be reassembled after translation.
    row_chunk_map = []
    flat_chunks = []
    flat_joiners = []
    for protected in protected_texts:
        chunks = chunk_protected_text(protected, {})
        start = len(flat_chunks)
        for chunk_text, joiner in chunks:
            flat_chunks.append(chunk_text)
            flat_joiners.append(joiner)
        row_chunk_map.append((start, len(flat_chunks)))
    print(f"{len(flat_chunks)} chunks across {len(sample)} rows "
          f"(mean {len(flat_chunks)/max(1,len(sample)):.1f} chunks/row)", flush=True)

    # batch_size=4 is tuned for the 8GB-shared-memory MPS machine (see
    # translate_batch's own memory-safety notes) -- on a CUDA GPU with
    # dedicated VRAM (not shared with host RAM the way MPS unified memory
    # is), that's needlessly conservative. 24 was picked directly against
    # this VM's actual free VRAM (nvidia-smi: 23GB, 0 used before this job)
    # -- 2026-08-19.
    gpu_batch_size = 24 if device == "cuda" else 4

    print("Loading en->de model...", flush=True)
    tok_ende = MarianTokenizer.from_pretrained(EN_DE)
    model_ende = MarianMTModel.from_pretrained(EN_DE).to(device).eval()

    print("Translating en->de...", flush=True)
    de_chunks = translate_batch(flat_chunks, tok_ende, model_ende, device, batch_size=gpu_batch_size)

    del model_ende
    if device == "mps":
        torch.mps.empty_cache()
    elif device == "cuda":
        torch.cuda.empty_cache()

    print("Loading de->en model...", flush=True)
    tok_deen = MarianTokenizer.from_pretrained(DE_EN)
    model_deen = MarianMTModel.from_pretrained(DE_EN).to(device).eval()

    print("Translating de->en (back)...", flush=True)
    back_chunks = translate_batch(de_chunks, tok_deen, model_deen, device, batch_size=gpu_batch_size)

    back_texts = []
    for start, end in row_chunk_map:
        pieces = []
        for i in range(start, end):
            pieces.append(back_chunks[i])
            pieces.append(flat_joiners[i])
        back_texts.append("".join(pieces))

    restored_texts = [restore_links_after_translation(t, m) for t, m in zip(back_texts, mappings)]
    # Drop, not just count, any row where a placeholder didn't survive --
    # found 2026-08-19 that MarianMT can silently drop an isolated
    # placeholder mid-sentence even with chunking+beam search (rare, ~1.3%
    # of rows), and the one observed case was the row's own target_entity
    # ("funded by Bill Gates through JEFFREY EPSTEIN" -> "funded by JEFFREY
    # EPSTEIN", quietly erasing the entity the label is about). A rare
    # failure like this is fine to just exclude from the output set --
    # not fine to silently keep as a corrupted training-augmentation row.
    placeholder_ok = [all(prime in t for prime in m) for t, m in zip(back_texts, mappings)]
    dropped_placeholder = len(placeholder_ok) - sum(placeholder_ok)
    print(f"{dropped_placeholder} rows dropped: a placeholder (link or target_entity) "
          f"didn't survive the round-trip", flush=True)

    out = pd.DataFrame({
        "text": sample["text"].values,
        "paraphrase": restored_texts,
        "target_entity": sample["target_entity"].values,
        "label": sample["label"].values,
    })
    out = out[placeholder_ok].reset_index(drop=True)

    print("\nScoring semantic similarity...", flush=True)
    from sentence_transformers import SentenceTransformer, util
    embed_model = SentenceTransformer("all-MiniLM-L6-v2")
    orig_emb = embed_model.encode(out["text"].astype(str).tolist(), convert_to_tensor=True, show_progress_bar=False)
    para_emb = embed_model.encode(out["paraphrase"].astype(str).tolist(), convert_to_tensor=True, show_progress_bar=False)
    sims = util.cos_sim(orig_emb, para_emb).diagonal().cpu().numpy()
    out["semantic_similarity"] = sims
    print(f"pre-threshold: {len(out)} rows, mean similarity={sims.mean():.4f}, min={sims.min():.4f}, "
          f"pct below 0.85={(sims < 0.85).mean():.1%}, pct below 0.90={(sims < 0.90).mean():.1%}", flush=True)

    # Quality gate: drop rows below the 0.85 similarity bar used as the
    # quality threshold throughout this diagnostic, rather than keep
    # meaning-drifted paraphrases in the augmentation-candidate set.
    SIMILARITY_THRESHOLD = 0.85
    dropped_similarity = (sims < SIMILARITY_THRESHOLD).sum()
    out = out[sims >= SIMILARITY_THRESHOLD].reset_index(drop=True)
    out.to_csv(OUT_PATH, index=False)
    print(f"{dropped_similarity} rows dropped below similarity {SIMILARITY_THRESHOLD}", flush=True)
    print(f"\nSaved {len(out)} final rows to {OUT_PATH} "
          f"(mean similarity={out['semantic_similarity'].mean():.4f})", flush=True)


if __name__ == "__main__":
    main()
