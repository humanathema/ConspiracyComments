"""graph_pilot_build_contrastive_pairs.py

Extracts the training pairs for contrastive fine-tuning of a projection
head on top of Gemini's comment embeddings -- Nash's direction 2026-08-02
(late/night): use the trustworthy, exact-match structural layers
(citation, entity, reply) as supervision to teach the embedding space
what topic-level similarity should look like, rather than continuing to
work around its raw geometry.

Positive pairs: comments connected by citation_comention_domain,
citation_comention_url, entity_comention, or reply -- the layers that
never showed the compression/degeneracy problems tonight, chosen
specifically because they're exact-match and verifiable (two comments
citing the same paper, or replying to each other, are genuinely
topic-related, no ambiguity). Excludes author/temporal/topic_lineage --
those are either noisy (temporal, dropped earlier tonight) or
structural-but-not-precise (author identity isn't the same as topic).

Output: data/processed/graph_pilot_top200_depth/contrastive_positive_pairs.csv
  (id_a, id_b) -- deduped, no weight/layer info, just the pair
"""
import pandas as pd

PILOT_DIR = "data/processed/graph_pilot_top200_depth"
TRUSTED_LAYERS = ["citation_comention_domain", "citation_comention_url", "entity_comention", "reply"]


def main():
    edges = pd.read_csv(f"{PILOT_DIR}/multilayer_edges.csv")
    pos = edges[edges["layer"].isin(TRUSTED_LAYERS)][["id_a", "id_b"]].drop_duplicates()
    pos.to_csv(f"{PILOT_DIR}/contrastive_positive_pairs.csv", index=False)
    print(f"{len(pos):,} unique positive pairs saved to {PILOT_DIR}/contrastive_positive_pairs.csv", flush=True)


if __name__ == "__main__":
    main()
