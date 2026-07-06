"""Model-vs-human validation for the epistemic strategy measures.

Ground truth comes from the human-labeled rows of labeled_2k_with_scores.csv,
identified by `{dim}_source == 'human_1'`. The `{dim}_best` columns must never
be used as ground truth: they are human-overridden where human labels exist and
model-derived elsewhere, so scoring against them is circular.

Outputs data/processed/classifier_performance_summary.csv.
"""
import pandas as pd
from sklearn.metrics import cohen_kappa_score, precision_recall_fscore_support

L2K = 'data/processed/labeled_2k_with_scores.csv'
HS_SPOT = 'data/processed/hedged_suspicion_final_hitl_scored.csv'
OUT = 'data/processed/classifier_performance_summary.csv'

DIMS = ['source_citation', 'hedged_suspicion', 'appeal_to_authority',
        'anti_establishment_stance']


def as_binary(s):
    if s.dtype == object:
        return s.astype(str).str.lower().isin(['1', '1.0', 'true', 'yes']).astype(int)
    return (s.fillna(0) > 0.5).astype(int)


def metrics_row(dimension, measure, y_true, y_pred):
    p, r, f1, _ = precision_recall_fscore_support(
        y_true, y_pred, average='binary', zero_division=0)
    return {
        'dimension': dimension,
        'measure': measure,
        'n_human': len(y_true),
        'base_rate': round(float(y_true.mean()), 3),
        'kappa': round(cohen_kappa_score(y_true, y_pred), 3),
        'precision': round(p, 3),
        'recall': round(r, 3),
        'f1': round(f1, 3),
    }


def main():
    rows = []
    df = pd.read_csv(L2K)

    for dim in DIMS:
        human = df[df[f'{dim}_source'] == 'human_1']
        if len(human) == 0:
            continue
        y_true = as_binary(human[f'{dim}_score'])
        y_pred = as_binary(human[dim])
        rows.append(metrics_row(dim, 'batch LLM label', y_true, y_pred))

    # Dedicated hedged_suspicion ML pipeline, independent spot check
    spot = pd.read_csv(HS_SPOT).dropna(subset=['human_label', 'hitl_probability'])
    y_true = spot['human_label'].astype(int)
    y_pred = (spot['hitl_probability'] >= 0.5).astype(int)
    rows.append(metrics_row('hedged_suspicion', 'dedicated ML pipeline (spot check)',
                            y_true, y_pred))

    out = pd.DataFrame(rows)
    out.to_csv(OUT, index=False)
    print(out.to_string(index=False))
    print(f'\nWritten to {OUT}')
    print('NOTE: rows with small n_human (e.g. anti_establishment_stance) are '
          'reported for transparency, not as validation evidence.')


if __name__ == '__main__':
    main()
