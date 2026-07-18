"""
Display and visualization utilities.
"""

from IPython.display import HTML, display
import pandas as pd
from typing import Optional


def setup_display_styles() -> None:
    """
    Configure IPython display settings for wide dataframes.
    Call once at notebook startup.
    """
    pd.set_option('display.max_colwidth', None)
    pd.set_option('display.max_columns', None)
    pd.set_option('display.max_rows', None)
    
    display(HTML("""
    <style>
        .dataframe td {
            white-space: normal !important;
            word-wrap: break-word;
            max-width: 300px;
        }
        .dataframe th {
            max-width: 300px;
            font-weight: bold;
        }
        .dataframe tr {
            height: auto;
        }
    </style>
    """))


def show_dataframe(
    df: pd.DataFrame,
    title: Optional[str] = None,
    max_rows: int = 10
) -> None:
    """
    Display a dataframe with optional title.
    
    Args:
        df: DataFrame to display.
        title: Optional section title.
        max_rows: Max rows to show.
    """
    if title:
        print(f"\n{'='*70}")
        print(f"  {title}")
        print(f"{'='*70}\n")
    
    with pd.option_context('display.max_rows', max_rows):
        display(df)


def format_number(n: int) -> str:
    """
    Format integer with commas.
    
    Args:
        n: Number to format.
        
    Returns:
        Formatted string (e.g., "1,234,567").
    """
    return f"{n:,}"


def print_section_header(title: str, level: int = 1) -> None:
    """
    Print a formatted section header.
    
    Args:
        title: Section title.
        level: Header level (1-3, affects size).
    """
    width = 70 - (level * 5)
    print(f"\n{'='*width}")
    print(f"{'  ' * level}{title}")
    print(f"{'='*width}\n")


def print_stats_table(
    stats_dict: dict,
    title: str = "Statistics",
    decimals: int = 2
) -> None:
    """
    Pretty-print a statistics dictionary.
    
    Args:
        stats_dict: Dict of {label: value} pairs.
        title: Table title.
        decimals: Decimal places for floats.
    """
    print(f"\n{title}")
    print("-" * 50)
    
    for key, value in stats_dict.items():
        if isinstance(value, float):
            value_str = f"{value:.{decimals}f}"
        elif isinstance(value, int):
            value_str = format_number(value)
        else:
            value_str = str(value)
        
        print(f"  {key:<30} {value_str:>15}")
    
    print("-" * 50)


def print_query_result(query: str, result_df: pd.DataFrame, title: Optional[str] = None) -> None:
    """
    Pretty-print a query result with metadata.
    
    Args:
        query: SQL query that was executed (for reference).
        result_df: Result DataFrame.
        title: Optional result title.
    """
    if title:
        print_section_header(title)
    
    print(f"Query returned {len(result_df)} rows, {len(result_df.columns)} columns\n")
    display(result_df)


def display_with_links(
    df: pd.DataFrame,
    url_col: str,
    text_col: Optional[str] = None,
    columns: Optional[list] = None,
) -> None:
    """
    Display a dataframe with `url_col` rendered as a clickable link.

    Args:
        df: DataFrame to display.
        url_col: Column holding the URL to link to.
        text_col: If given, this column's value becomes the clickable
            link text and `url_col` itself is dropped from the visible
            table. If omitted, the URL itself is the visible+clickable text.
        columns: Optional explicit column order/subset for the final
            visible table (after the link substitution above).
    """
    d = df.copy()
    if text_col:
        d[text_col] = [
            f'<a href="{u}" target="_blank">{t}</a>'
            for u, t in zip(d[url_col], d[text_col])
        ]
        if url_col != text_col:
            d = d.drop(columns=[url_col])
    else:
        d[url_col] = d[url_col].apply(lambda u: f'<a href="{u}" target="_blank">{u}</a>')

    if columns:
        d = d[columns]
    display(HTML(d.to_html(escape=False, index=False)))


import matplotlib.pyplot as plt
import seaborn as sns
import numpy as np

# --- Shared style: applied once at import time ---
NAVY, ORANGE, GREEN, PURPLE, RED, TEAL = '#2c3e50', '#e67e22', '#27ae60', '#8e44ad', '#c0392b', '#16a085'
PALETTE = [NAVY, ORANGE, GREEN, PURPLE, RED, TEAL]

sns.set_theme(style='white', font='sans-serif')
plt.rcParams.update({
    'figure.facecolor': 'white',
    'axes.facecolor': 'white',
    'axes.titlesize': 15,
    'axes.titleweight': 'bold',
    'axes.titlepad': 14,
    'axes.labelsize': 11,
    'axes.edgecolor': '#888',
    'xtick.labelsize': 10,
    'ytick.labelsize': 10,
    'xtick.color': '#444',
    'ytick.color': '#444',
    'legend.frameon': False,
    'legend.fontsize': 10,
})


def _despine(ax=None, keep_left=True, keep_bottom=True):
    """Strip chart-junk spines, keep a light left/bottom axis by default."""
    sns.despine(ax=ax, left=not keep_left, bottom=not keep_bottom)


def _light_grid(ax=None, axis='y'):
    """A faint, single-axis gridline -- enough to read values off, not a cage."""
    (ax or plt.gca()).grid(True, axis=axis, alpha=0.25, linewidth=0.7, color='#999')
    (ax or plt.gca()).set_axisbelow(True)


def plot_lexical_divergence(flashpoint_scores, control_scores):
    plt.figure(figsize=(11, 5.5))
    sns.kdeplot(flashpoint_scores, color=RED, label='Flashpoint (Viral)', fill=True, alpha=0.25, linewidth=1.5)
    sns.kdeplot(control_scores, color=NAVY, label='Inward-Facing (Quiet)', fill=True, alpha=0.25, linewidth=1.5)
    plt.title("Lexical Divergence: Flashpoints vs. Inward-Facing Threads")
    _light_grid()
    _despine()
    plt.legend()
    plt.tight_layout()
    plt.show()

def plot_linguistic_gravity(df_rankings, target_month):
    plt.figure(figsize=(12, 6.5))
    sns.scatterplot(
        data=df_rankings,
        x='total_comment_volume',
        y='lexical_score',
        alpha=0.25,
        color=ORANGE,
        s=25,
        linewidth=0,
    )
    sns.regplot(
        data=df_rankings,
        x='total_comment_volume',
        y='lexical_score',
        scatter=False,
        color=NAVY,
        line_kws={'linewidth': 3},
    )
    plt.xscale('log')
    plt.title(f"The Linguistic Gravity of r/conspiracy ({target_month})\nDoes volume lead to convergence?")
    plt.xlabel("Total Comments Posted (Log Scale)")
    plt.ylabel("Lexical Convergence Score")
    _light_grid()
    _despine()
    plt.tight_layout()
    plt.show()

def plot_binned_linguistic_gravity(df_rankings, binned_data, target_month):
    plt.figure(figsize=(12, 6.5))
    sns.scatterplot(
        data=df_rankings,
        x='total_comment_volume',
        y='lexical_score',
        alpha=0.12,
        color=ORANGE,
        s=18,
        linewidth=0,
    )
    plt.plot(
        binned_data['bin_mid'],
        binned_data['lexical_score'],
        color=NAVY,
        linewidth=3,
        marker='o',
        markersize=9,
        label='Median Score per Activity Tier',
    )
    plt.xscale('log')
    plt.ylim(0, 1.0)
    plt.title(f"Actual Linguistic Convergence: Binned Median Activity ({target_month})")
    plt.xlabel("Total Comments Posted (Log Scale)")
    plt.ylabel("Lexical Convergence Score")
    _light_grid()
    _despine()
    plt.legend()
    plt.tight_layout()
    plt.show()

def plot_epistemic_impact(thread_significance):
    plt.figure(figsize=(9, 5.5))
    sc = sns.scatterplot(
        data=thread_significance,
        x='total_raw_upvotes',
        y='weighted_epistemic_impact',
        hue='insider_density',
        palette='viridis',
        linewidth=0,
        s=35,
    )
    sc.legend(title='Insider Density', frameon=False, bbox_to_anchor=(1.02, 1), loc='upper left')
    plt.title("Raw Upvotes vs. Weighted Epistemic Impact")
    plt.xlabel("Total Raw Upvotes")
    plt.ylabel("Significant Approval (Weighted)")
    _light_grid()
    _despine()
    plt.tight_layout()
    plt.show()

def plot_epistemic_strategy_correlation(corr_matrix):
    plt.figure(figsize=(7, 7))
    sns.heatmap(
        corr_matrix[['score']].sort_values(by='score', ascending=False),
        annot=True, fmt='.2f', cmap='RdBu_r', center=0,
        linewidths=0.6, linecolor='white', cbar_kws={'shrink': 0.7},
    )
    plt.title("Correlation: Epistemic Strategy vs. Upvotes")
    plt.tight_layout()
    plt.show()

def plot_archetype_performance(df_commenters):
    plt.figure(figsize=(12, 6.5))
    sns.scatterplot(
        data=df_commenters,
        x='rhetoric_norm',
        y='score',
        size='rhetoric_norm',
        alpha=0.5,
        sizes=(15, 160),
        color=ORANGE,
        linewidth=0,
        legend=False,
    )
    plt.yscale('symlog')
    plt.title("The Rhetoric/Adversarial Archetype: Does High-Mistrust Language Yield More Social Capital?")
    _light_grid()
    _despine()
    plt.tight_layout()
    plt.show()

def plot_corpus_size_funnel(raw: int, usable: int, threads: int) -> None:
    """
    Corpus-overview bar chart: raw usable comments vs. lexically-scored
    comments (thread count shown as an annotation since it's a different
    unit and doesn't belong on the same bar scale).
    """
    stages = ['Raw Usable Comments\n(no length filter)', 'Lexically Scored Comments\n(length > 100 chars)']
    values = [raw, usable]

    plt.figure(figsize=(9, 5.5))
    bars = plt.bar(stages, values, color=[NAVY, ORANGE], width=0.5)
    for bar, val in zip(bars, values):
        plt.text(bar.get_x() + bar.get_width() / 2, bar.get_height(),
                  f"{val:,}", ha='center', va='bottom', fontsize=12, fontweight='bold')

    plt.title(f"Corpus Size After Length Filtering  (across {threads:,} threads)")
    plt.ylabel("Comment Count")
    plt.ylim(0, max(values) * 1.15)
    _light_grid()
    _despine()
    plt.tight_layout()
    plt.show()


def plot_monthly_volume(df_monthly) -> None:
    """
    Area chart of comment volume per month across the corpus's time range.

    Args:
        df_monthly: DataFrame with columns ['month', 'n_comments'].
    """
    plt.figure(figsize=(13, 5.5))
    plt.fill_between(df_monthly['month'], df_monthly['n_comments'], color=ORANGE, alpha=0.25)
    plt.plot(df_monthly['month'], df_monthly['n_comments'], color=NAVY, linewidth=1.8)
    plt.title("Comment Volume by Month, Full Corpus")
    plt.xlabel("Month")
    plt.ylabel("Comment Count")
    every_nth = max(1, len(df_monthly) // 20)
    plt.gca().set_xticks(df_monthly['month'][::every_nth])
    plt.xticks(rotation=45, ha='right')
    _light_grid()
    _despine()
    plt.tight_layout()
    plt.show()


def plot_upvote_tier_distribution(df_tiers) -> None:
    """
    Bar chart of comment count per upvote tier.

    Args:
        df_tiers: DataFrame with columns ['upvote_tier', 'n'].
    """
    plt.figure(figsize=(9, 5.5))
    plt.bar(df_tiers['upvote_tier'], df_tiers['n'], color=NAVY, width=0.6)
    plt.title("Comment Distribution Across Upvote Tiers")
    plt.xlabel("Upvote Tier")
    plt.ylabel("Comment Count")
    plt.yscale('log')
    _despine()
    plt.tight_layout()
    plt.show()


def plot_spam_bot_top_authors(df_top) -> None:
    """
    Horizontal bar chart of text-reuse ratio for the most duplicative authors,
    colored by detected category (bot vs. repeat poster).

    Args:
        df_top: DataFrame with columns ['author', 'dup_ratio', 'is_likely_bot'].
    """
    colors = [RED if is_bot else ORANGE for is_bot in df_top['is_likely_bot']]
    plt.figure(figsize=(9, max(4, 0.35 * len(df_top))))
    plt.barh(df_top['author'], df_top['dup_ratio'], color=colors)
    plt.gca().invert_yaxis()
    plt.xscale('log')
    plt.xlabel("Comments / Distinct Texts (dup_ratio, log scale)")
    plt.title("Most Duplicative Authors: Bots (red) vs. Repeat Posters (orange)")
    _despine()
    plt.tight_layout()
    plt.show()


def plot_near_duplicate_cluster_sizes(df_clusters) -> None:
    """
    Histogram of near-duplicate cluster sizes (log-log), split by whether
    the cluster spans multiple authors.

    Args:
        df_clusters: one row per cluster, columns ['cluster_size', 'n_distinct_authors'].
    """
    single = df_clusters[df_clusters['n_distinct_authors'] == 1]['cluster_size']
    cross = df_clusters[df_clusters['n_distinct_authors'] > 1]['cluster_size']

    plt.figure(figsize=(9, 5.5))
    bins = np.logspace(np.log10(2), np.log10(max(df_clusters['cluster_size'].max(), 3)), 25)
    plt.hist([single, cross], bins=bins, stacked=True, color=[ORANGE, RED],
              label=['Single author', 'Cross-author'])
    plt.xscale('log')
    plt.yscale('log')
    plt.xlabel("Cluster Size (near-duplicate comments)")
    plt.ylabel("Number of Clusters")
    plt.title("Near-Duplicate Cluster Size Distribution")
    _despine()
    plt.legend()
    plt.tight_layout()
    plt.show()


def plot_yearly_lexical_trends(df_yearly) -> None:
    """
    Multi-line chart of the 5 core lexical dimension averages by year.

    Args:
        df_yearly: columns ['year', 'avg_hedge', 'avg_certainty',
            'avg_evidence', 'avg_authority', 'avg_rhetorical'].
    """
    dims = ['avg_hedge', 'avg_certainty', 'avg_evidence', 'avg_authority', 'avg_rhetorical']

    plt.figure(figsize=(12, 5.5))
    for dim, color in zip(dims, PALETTE):
        plt.plot(df_yearly['year'], df_yearly[dim], marker='o', markersize=4, color=color,
                  label=dim.replace('avg_', '').capitalize(), linewidth=2)
    plt.title("Epistemic Dimension Averages by Year")
    plt.xlabel("Year")
    plt.ylabel("Average Score per Comment")
    _light_grid()
    _despine()
    plt.legend(bbox_to_anchor=(1.02, 1), loc='upper left')
    plt.tight_layout()
    plt.show()


def plot_domain_type_citations(type_summary) -> None:
    """
    Bar chart of total citation volume by epistemic domain type.

    Args:
        type_summary: columns ['epistemic_type', 'total_citations', ...].
    """
    df = type_summary.sort_values('total_citations', ascending=True)
    plt.figure(figsize=(9, 6.5))
    plt.barh(df['epistemic_type'], df['total_citations'], color=ORANGE)
    plt.xscale('log')
    plt.xlabel("Total Citations (log scale)")
    plt.title("Citation Volume by Source Domain Type")
    _despine()
    plt.tight_layout()
    plt.show()


def plot_tier_signature_shifts(df_brigade_test) -> None:
    """
    Dual-panel bar chart: controversiality and expertise-vocabulary usage
    across upvote tiers.

    Args:
        df_brigade_test: columns ['upvote_tier', 'avg_controversiality',
            'expertise_talk_percentage'].
    """
    fig, axes = plt.subplots(1, 2, figsize=(13, 5.5))

    axes[0].bar(df_brigade_test['upvote_tier'], df_brigade_test['avg_controversiality'], color=NAVY, width=0.6)
    axes[0].set_title("Avg. Controversiality by Tier")
    axes[0].tick_params(axis='x', rotation=20)
    _light_grid(axes[0])
    _despine(axes[0])

    axes[1].bar(df_brigade_test['upvote_tier'], df_brigade_test['expertise_talk_percentage'], color=ORANGE, width=0.6)
    axes[1].set_title("% Mentioning Expertise Vocabulary")
    axes[1].tick_params(axis='x', rotation=20)
    _light_grid(axes[1])
    _despine(axes[1])

    plt.suptitle("Structural Signature Shifts Across Upvote Tiers", fontweight='bold')
    plt.tight_layout()
    plt.show()


def plot_insider_segment_profile(df_insider_matrix) -> None:
    """
    Heatmap of epistemic dimension averages across insider segments.

    Args:
        df_insider_matrix: columns ['insider_segment', 'avg_evidence',
            'avg_adversarial', 'avg_hedge', 'avg_certainty', 'avg_pattern',
            'avg_meta'] (plus others, ignored).
    """
    dims = ['avg_evidence', 'avg_adversarial', 'avg_hedge', 'avg_certainty', 'avg_pattern', 'avg_meta']
    heat_data = df_insider_matrix.set_index('insider_segment')[dims]

    plt.figure(figsize=(10, 3.8))
    sns.heatmap(heat_data, annot=True, fmt='.4f', cmap='YlOrRd', linewidths=0.6, linecolor='white',
                 cbar_kws={'label': 'Avg. score', 'shrink': 0.85})
    plt.title("Insider-Only Epistemic Profile by Segment")
    plt.ylabel("")
    plt.xlabel("")
    plt.tight_layout()
    plt.show()


def plot_source_category_totals(totals: dict) -> None:
    """
    Bar chart comparing total reference/citation volume across the
    source-type tables built in Section 4.1 (Wikipedia, PubMed, mainstream
    news, alt media, YouTube, WikiLeaks).

    Args:
        totals: dict {category_label: total_count}.
    """
    labels = list(totals.keys())
    values = list(totals.values())
    order = sorted(range(len(values)), key=lambda i: values[i])

    plt.figure(figsize=(9, 5.5))
    plt.barh([labels[i] for i in order], [values[i] for i in order], color=NAVY)
    plt.xlabel("Total References (top-N shown per category)")
    plt.title("Source Citation Volume by Category")
    _despine()
    plt.tight_layout()
    plt.show()


def plot_epistemic_stance_heatmap(matrix) -> None:
    """
    Heatmap of epistemic-move x human-stance annotation counts (HITL queue).

    Args:
        matrix: crosstab DataFrame with a 'Total' row/column to exclude.
    """
    heat = matrix.drop(index='Total', errors='ignore').drop(columns='Total', errors='ignore')
    plt.figure(figsize=(9, 5.5))
    sns.heatmap(heat, annot=True, fmt='d', cmap='YlGnBu', linewidths=0.6, linecolor='white',
                 cbar_kws={'shrink': 0.85})
    plt.title("Epistemic Move × Human Stance (HITL Annotations)")
    plt.tight_layout()
    plt.show()


def plot_hitl_queue_progress(df_progress) -> None:
    """
    Stacked horizontal bar: labeled vs. remaining rows per HITL queue.

    Args:
        df_progress: columns ['queue', 'labeled', 'remaining'].
    """
    df = df_progress.sort_values('labeled', ascending=True)
    plt.figure(figsize=(9, 4.5))
    plt.barh(df['queue'], df['labeled'], color=GREEN, label='Labeled')
    plt.barh(df['queue'], df['remaining'], left=df['labeled'], color='#e4e4e4', label='Remaining')
    plt.xlabel("Rows")
    plt.title("HITL Queue Progress")
    _despine()
    plt.legend()
    plt.tight_layout()
    plt.show()


def plot_hitl_label_distributions(dist_by_queue: dict) -> None:
    """
    Grouped bar chart comparing label distributions across completed
    HITL queues that share the same label vocabulary.

    Args:
        dist_by_queue: dict {queue_name: pandas Series of label -> count}.
    """
    df = pd.DataFrame(dist_by_queue).fillna(0)
    ax = df.plot(kind='bar', figsize=(10, 5.5), color=[NAVY, ORANGE, GREEN])
    plt.title("Label Distribution by Queue (Completed Queues)")
    plt.ylabel("Count")
    plt.xticks(rotation=20)
    _light_grid(ax)
    _despine(ax)
    plt.legend(title='Queue')
    plt.tight_layout()
    plt.show()


def plot_zscore_power_users(df_power_users, dim_cols):
    fig, axes = plt.subplots(2, 5, figsize=(20, 10), sharey=True)
    axes = axes.flatten()

    for i, dim in enumerate(dim_cols):
        ax = axes[i]
        sns.scatterplot(
            data=df_power_users,
            x=dim,
            y='score',
            alpha=0.5,
            size=dim,
            sizes=(15, 160),
            ax=ax,
            color=ORANGE,
            linewidth=0,
            legend=False,
        )
        ax.set_title(f"{dim.replace('_count', '').capitalize()} (Z-Score)", fontsize=12)
        ax.set_yscale('symlog')
        ax.set_xlabel("Deviation from Mean (Z-Score)")
        _despine(ax)
        if i == 0: ax.set_ylabel("Total Upvotes Earned")

    plt.tight_layout()
    plt.show()


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

