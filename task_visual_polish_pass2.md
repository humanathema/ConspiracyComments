# Task: Second visual-polish pass on ConspiracyMaster_Refactored.ipynb

**Status: Done (2026-07-18, same-day Claude session).** All 4 pieces
verified complete in the current notebook: Piece 1's spot-check cell
already uses `LIMIT 8`/`text[:250]` and is wrapped in a scrollable box;
Piece 2's `---` dividers exist before every `### 9.N`/`#### 9.N` header
except 9.1 (as intended); Piece 3's `plot_top_citations_bar` exists in
`utils/visualization.py` and is called for all 6 citation tables
(Wikipedia, PubMed, mainstream news, alt media, YouTube, WikiLeaks),
now executed with real output; Piece 4's top-level section intros are
all present. This file is kept for reference only — no further action
needed.

## Context — read this first

Reviewing the live GitHub Pages export
(https://kahatahi.co.nz/ConspiracyComments/) surfaced four concrete
presentation problems that survived the first polish pass. This task
fixes those four, in order of impact. Do not touch anything else —
no re-running cells with different logic, no changing any query, no
altering any finding or number.

**Guardrails** (same as every other task in this repo):
- Read-only on all `src/`, `utils/`, `data/` — this task only edits
  `ConspiracyMaster_Refactored.ipynb` and (for one item) appends to
  `utils/visualization.py`.
- Validate the notebook is valid JSON/nbformat after every edit
  (`python3 -c "import nbformat; nbformat.read(open('ConspiracyMaster_Refactored.ipynb'), as_version=4)"`)
  before moving to the next piece.
- Execute every cell you touch for real and visually inspect the output
  before considering it done — same standard as prior sessions (don't
  trust that code "should" work).
- Commit each of the 4 pieces separately, not as one giant commit, so
  each is independently revertable if something looks wrong.
- Regenerate the GitHub Pages export after each commit (same
  `scripts/postprocess_notebook_html.py` step used in prior sessions —
  check recent git log for the exact command if unsure).
- Report back after each piece rather than waiting until all 4 are done.

## Piece 1 (highest priority): truncate the Section 3 raw-output wall

**The problem**: the cell in Section 3 that prints ~100 individual
spaCy-attribution examples (`Type: ... / Text: ... / ---`, the one
iterating `spot_checks.iterrows()` over
`ORDER BY RANDOM() LIMIT 100`) produces a huge unbroken wall of raw
printed text — the single worst offender for "unrelieved text" in the
whole notebook. It's a leftover that should have been caught by the
"truncate large raw-output dumps" instruction in
`handoff/task_notebook_and_repo_polish.md` but wasn't.

**Fix**: change the query's `LIMIT 100` to `LIMIT 8`, and change the
per-row truncation from `text[:400]` to `text[:250]`. Do not change
anything else about the query (same filters, same columns). This
keeps the spot-check genuinely useful (a reader can still see real
examples of each attribution type) without the wall-of-text problem.

Find the cell via:
```
grep -n "spot_checks = con.execute" ConspiracyMaster_Refactored.ipynb
```

## Piece 2: horizontal-rule dividers between Section 9.x subsections

Section 9 has 12 subsections (9.1 through 9.12) that currently run
together with only a `###`/`####` markdown header and no visual break.

**Fix**: for every markdown cell whose header matches `### 9.\d` or
`#### 9.\d`, prepend a horizontal rule (`---`) as its own line before
the header, UNLESS it's the very first one (9.1, which follows directly
after the "9. ..." top-level section header and doesn't need a
redundant break). This is a pure markdown-text edit — find each
matching markdown cell's `source` list and insert `"---\n"` and `"\n"`
before the existing header line.

Verify with:
```
grep -c '^---$' <(jupyter nbconvert --to markdown --stdout ConspiracyMaster_Refactored.ipynb)
```
should increase by roughly 11 (9.2 through 9.12) after the edit.

## Piece 3: small bar chart for the Section 4 citation tables

Section 4's three drilldown tables (top Wikipedia articles by reference
count, top PubMed studies by reference count, and — check whether a
third "top alt/mainstream media articles" table exists further down in
4.1, per the earlier session's "Alternative Media subsection added,
mainstream-news drilldown expanded to 63-domain taxonomy" note — include
that one too if present) are currently pure HTML tables via
`viz.display_with_links(...)`, no accompanying chart.

**Fix**: add one new function to `utils/visualization.py`, following
the exact style/signature convention of the other `plot_*` functions
already in that file (e.g. `plot_source_category_totals`,
`plot_domain_type_citations` — read those two first as the closest
existing templates):

```python
def plot_top_citations_bar(df, label_col, count_col, title, top_n=15):
    """
    Horizontal bar chart of the top-N rows in a citation/reference table
    by count_col, for a quick-glance companion to the full HTML table.

    Args:
        df: DataFrame already sorted descending by count_col (as the
            existing citation tables are).
        label_col: column to use as the bar label (e.g. 'title').
        count_col: column to use as the bar length (e.g. 'reference_count').
        title: chart title.
        top_n: how many rows to show (default 15).
    """
    d = df.head(top_n).sort_values(count_col, ascending=True)
    plt.figure(figsize=(10, max(4, 0.35 * len(d))))
    plt.barh(d[label_col].astype(str).str.slice(0, 60), d[count_col], color='#2c3e50')
    plt.xlabel(count_col.replace('_', ' ').title())
    plt.title(title, fontsize=14)
    plt.tight_layout()
    plt.show()
```

Then, in the notebook, immediately after each of the existing
`viz.display_with_links(df_wiki, ...)` / `viz.display_with_links(df_pubmed, ...)`
calls (and the alt/mainstream-media equivalent if it exists), insert
a new cell calling this function, e.g.:

```python
viz.plot_top_citations_bar(df_wiki, 'title', 'reference_count',
                            'Top 15 Wikipedia Articles by Citation Count')
```

Match `label_col`/`count_col` to each table's actual column names (they
differ slightly per table — check the `postprocess` function above each
`cached_query_csv` call to confirm exact column names before writing
each cell, e.g. `df_pubmed` uses `title`/`reference_count` too but
verify against the live dataframe, don't assume).

No new queries — this reuses the dataframes already loaded by the
existing cells, just adds a visualization on top.

## Piece 4: short intro paragraph for major sections lacking one

Compare against the existing "research map" table at the very top of
the notebook (Section 0) — every top-level section number in that table
should have a 1-2 sentence markdown paragraph immediately under its
`## N. ...` header stating what question the section answers and what
it's about to do, BEFORE the first code cell. Some sections already have
this (e.g. Section 2's "Five dimensions scored via SQL LIKE pattern
matching..." line); others don't.

**Fix**: for any top-level section (`## N. ...` headers only, not the
9.x subsections — those are covered by Piece 2) that currently has no
descriptive text between its header and its first code cell, add one.
Keep it to 1-2 sentences, factual, matching the tone of the existing
ones that already have this (see Section 2 and Section 3's existing
intro lines as the template) — do not invent findings, just state the
question/method, pulling language from the research-map table's
"Question" column where useful.

## What NOT to do in this task

- Do not touch the entity_final_review.csv staleness flag from the
  prior systematic pass — separate, unrelated, still awaiting Nash's
  decision.
- Do not add colour to markdown text (inline HTML) — this was
  deliberately decided against in the first polish pass since GitHub
  Pages' renderer strips most inline HTML styling anyway. If this
  should be revisited, that's Nash's call, not something to add here.
- Do not modify, re-run with different parameters, or re-derive any
  actual finding, number, or query result — this task is presentation
  only.
- Do not touch Sections 1, 2, or 9.11/9.12 — cited here only as
  examples of the existing good patterns to match, not sections that
  need further changes themselves.

## When done

Report back per-piece as you finish each one (per the main handoff
guardrail 6 — don't chain into the next piece based on your own
judgement that the prior one looks good enough). If anything in the
notebook doesn't match what this task file assumes (e.g. the Section 4
alt-media table doesn't exist, or column names differ from what's
described above), flag it and ask rather than guessing.
