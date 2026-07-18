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

def plot_lexical_divergence(flashpoint_scores, control_scores):
    plt.figure(figsize=(12, 6))
    sns.kdeplot(flashpoint_scores, color='red', label='Flashpoint (Viral)', fill=True, alpha=0.2)
    sns.kdeplot(control_scores, color='blue', label='Inward-Facing (Quiet)', fill=True, alpha=0.2)
    plt.title("Lexical Divergence: Flashpoints vs. Inward-Facing Threads")
    plt.legend()
    plt.show()

def plot_linguistic_gravity(df_rankings, target_month):
    plt.figure(figsize=(14, 8))
    sns.set_style("whitegrid")
    sns.scatterplot(
        data=df_rankings, 
        x='total_comment_volume', 
        y='lexical_score', 
        alpha=0.3, 
        color='#e67e22',
        s=30
    )
    sns.regplot(
        data=df_rankings, 
        x='total_comment_volume', 
        y='lexical_score', 
        scatter=False, 
        color='#2c3e50', 
        line_kws={'linewidth': 3}
    )
    plt.xscale('log')
    plt.title(f"The Linguistic Gravity of r/conspiracy ({target_month})\\nDoes volume lead to convergence?", fontsize=16)
    plt.xlabel("Total Comments Posted (Log Scale)", fontsize=12)
    plt.ylabel("Lexical Convergence Score", fontsize=12)
    plt.tight_layout()
    plt.show()

def plot_binned_linguistic_gravity(df_rankings, binned_data, target_month):
    plt.figure(figsize=(14, 8))
    sns.scatterplot(
        data=df_rankings, 
        x='total_comment_volume', 
        y='lexical_score', 
        alpha=0.15, 
        color='#e67e22',
        s=20
    )
    plt.plot(
        binned_data['bin_mid'], 
        binned_data['lexical_score'], 
        color='#2c3e50', 
        linewidth=4, 
        marker='o', 
        markersize=10, 
        label='Median Score per Activity Tier'
    )
    plt.xscale('log')
    plt.ylim(0, 1.0)
    plt.title(f"Actual Linguistic Convergence: Binned Median Activity ({target_month})", fontsize=16)
    plt.xlabel("Total Comments Posted (Log Scale)", fontsize=12)
    plt.ylabel("Lexical Convergence Score", fontsize=12)
    plt.legend()
    plt.show()

def plot_epistemic_impact(thread_significance):
    plt.figure(figsize=(10, 6))
    sns.scatterplot(
        data=thread_significance, 
        x='total_raw_upvotes', 
        y='weighted_epistemic_impact', 
        hue='insider_density', 
        palette='viridis'
    )
    plt.title("Raw Upvotes vs. Weighted Epistemic Impact")
    plt.xlabel("Total Raw Upvotes")
    plt.ylabel("Significant Approval (Weighted)")
    plt.show()

def plot_epistemic_strategy_correlation(corr_matrix):
    plt.figure(figsize=(10, 8))
    sns.heatmap(corr_matrix[['score']].sort_values(by='score', ascending=False), annot=True, cmap='coolwarm')
    plt.title("Correlation: Epistemic Strategy vs. Upvotes")
    plt.show()

def plot_archetype_performance(df_commenters):
    plt.figure(figsize=(14, 8))
    sns.scatterplot(
        data=df_commenters, 
        x='rhetoric_norm', 
        y='score', 
        size='rhetoric_norm', 
        alpha=0.6, 
        sizes=(20, 200)
    )
    plt.yscale('symlog')
    plt.title("The Rhetoric/Adversarial Archetype: Does high-mistrust language yield more social capital?")
    plt.show()

def plot_corpus_size_funnel(raw: int, usable: int, threads: int) -> None:
    """
    Corpus-overview bar chart: raw usable comments vs. lexically-scored
    comments (thread count shown as an annotation since it's a different
    unit and doesn't belong on the same bar scale).
    """
    stages = ['Raw Usable Comments\n(no length filter)', 'Lexically Scored Comments\n(length > 100 chars)']
    values = [raw, usable]

    plt.figure(figsize=(10, 6))
    bars = plt.bar(stages, values, color=['#2c3e50', '#e67e22'], width=0.5)
    for bar, val in zip(bars, values):
        plt.text(bar.get_x() + bar.get_width() / 2, bar.get_height(),
                  f"{val:,}", ha='center', va='bottom', fontsize=12, fontweight='bold')

    plt.title(f"Corpus Size After Length Filtering  (across {threads:,} threads)", fontsize=16)
    plt.ylabel("Comment Count")
    plt.ylim(0, max(values) * 1.15)
    plt.tight_layout()
    plt.show()


def plot_monthly_volume(df_monthly) -> None:
    """
    Area chart of comment volume per month across the corpus's time range.

    Args:
        df_monthly: DataFrame with columns ['month', 'n_comments'].
    """
    plt.figure(figsize=(14, 6))
    plt.fill_between(df_monthly['month'], df_monthly['n_comments'], color='#e67e22', alpha=0.3)
    plt.plot(df_monthly['month'], df_monthly['n_comments'], color='#2c3e50', linewidth=2)
    plt.title("Comment Volume by Month, Full Corpus", fontsize=16)
    plt.xlabel("Month")
    plt.ylabel("Comment Count")
    every_nth = max(1, len(df_monthly) // 20)
    plt.gca().set_xticks(df_monthly['month'][::every_nth])
    plt.xticks(rotation=45, ha='right')
    plt.tight_layout()
    plt.show()


def plot_upvote_tier_distribution(df_tiers) -> None:
    """
    Bar chart of comment count per upvote tier.

    Args:
        df_tiers: DataFrame with columns ['upvote_tier', 'n'].
    """
    plt.figure(figsize=(10, 6))
    plt.bar(df_tiers['upvote_tier'], df_tiers['n'], color='#2c3e50')
    plt.title("Comment Distribution Across Upvote Tiers", fontsize=16)
    plt.xlabel("Upvote Tier")
    plt.ylabel("Comment Count")
    plt.yscale('log')
    plt.tight_layout()
    plt.show()


def plot_spam_bot_top_authors(df_top) -> None:
    """
    Horizontal bar chart of text-reuse ratio for the most duplicative authors,
    colored by detected category (bot vs. repeat poster).

    Args:
        df_top: DataFrame with columns ['author', 'dup_ratio', 'is_likely_bot'].
    """
    colors = ['#c0392b' if is_bot else '#e67e22' for is_bot in df_top['is_likely_bot']]
    plt.figure(figsize=(10, max(4, 0.35 * len(df_top))))
    plt.barh(df_top['author'], df_top['dup_ratio'], color=colors)
    plt.gca().invert_yaxis()
    plt.xscale('log')
    plt.xlabel("Comments / Distinct Texts (dup_ratio, log scale)")
    plt.title("Most Duplicative Authors: Bots (red) vs. Repeat Posters (orange)", fontsize=14)
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

    plt.figure(figsize=(10, 6))
    bins = np.logspace(np.log10(2), np.log10(max(df_clusters['cluster_size'].max(), 3)), 25)
    plt.hist([single, cross], bins=bins, stacked=True, color=['#e67e22', '#c0392b'],
              label=['Single author', 'Cross-author'])
    plt.xscale('log')
    plt.yscale('log')
    plt.xlabel("Cluster Size (near-duplicate comments)")
    plt.ylabel("Number of Clusters")
    plt.title("Near-Duplicate Cluster Size Distribution", fontsize=14)
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
    colors = ['#2c3e50', '#e67e22', '#27ae60', '#8e44ad', '#c0392b']

    plt.figure(figsize=(13, 6))
    for dim, color in zip(dims, colors):
        plt.plot(df_yearly['year'], df_yearly[dim], marker='o', color=color,
                  label=dim.replace('avg_', '').capitalize(), linewidth=2)
    plt.title("Epistemic Dimension Averages by Year", fontsize=16)
    plt.xlabel("Year")
    plt.ylabel("Average Score per Comment")
    plt.legend()
    plt.tight_layout()
    plt.show()


def plot_domain_type_citations(type_summary) -> None:
    """
    Bar chart of total citation volume by epistemic domain type.

    Args:
        type_summary: columns ['epistemic_type', 'total_citations', ...].
    """
    df = type_summary.sort_values('total_citations', ascending=True)
    plt.figure(figsize=(10, 7))
    plt.barh(df['epistemic_type'], df['total_citations'], color='#e67e22')
    plt.xscale('log')
    plt.xlabel("Total Citations (log scale)")
    plt.title("Citation Volume by Source Domain Type", fontsize=16)
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
    fig, axes = plt.subplots(1, 2, figsize=(14, 6))

    axes[0].bar(df_brigade_test['upvote_tier'], df_brigade_test['avg_controversiality'], color='#2c3e50')
    axes[0].set_title("Avg. Controversiality by Tier")
    axes[0].tick_params(axis='x', rotation=20)

    axes[1].bar(df_brigade_test['upvote_tier'], df_brigade_test['expertise_talk_percentage'], color='#e67e22')
    axes[1].set_title("% Mentioning Expertise Vocabulary")
    axes[1].tick_params(axis='x', rotation=20)

    plt.suptitle("Structural Signature Shifts Across Upvote Tiers", fontsize=16)
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

    plt.figure(figsize=(11, 4))
    sns.heatmap(heat_data, annot=True, fmt='.4f', cmap='YlOrRd', cbar_kws={'label': 'Avg. score'})
    plt.title("Insider-Only Epistemic Profile by Segment", fontsize=14)
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

    plt.figure(figsize=(10, 6))
    plt.barh([labels[i] for i in order], [values[i] for i in order], color='#2c3e50')
    plt.xlabel("Total References (top-N shown per category)")
    plt.title("Source Citation Volume by Category", fontsize=16)
    plt.tight_layout()
    plt.show()


def plot_epistemic_stance_heatmap(matrix) -> None:
    """
    Heatmap of epistemic-move x human-stance annotation counts (HITL queue).

    Args:
        matrix: crosstab DataFrame with a 'Total' row/column to exclude.
    """
    heat = matrix.drop(index='Total', errors='ignore').drop(columns='Total', errors='ignore')
    plt.figure(figsize=(10, 6))
    sns.heatmap(heat, annot=True, fmt='d', cmap='YlGnBu')
    plt.title("Epistemic Move × Human Stance (HITL Annotations)", fontsize=14)
    plt.tight_layout()
    plt.show()


def plot_zscore_power_users(df_power_users, dim_cols):
    fig, axes = plt.subplots(2, 5, figsize=(22, 12), sharey=True)
    axes = axes.flatten()

    for i, dim in enumerate(dim_cols):
        ax = axes[i]
        sns.scatterplot(
            data=df_power_users, 
            x=dim, 
            y='score', 
            alpha=0.6, 
            size=dim, 
            sizes=(20, 200), 
            ax=ax, 
            color='#e67e22'
        )
        
        ax.set_title(f"{dim.replace('_count', '').capitalize()} (Z-Score)")
        ax.set_yscale('symlog')
        ax.set_xlabel("Deviation from Mean (Z-Score)")
        if i == 0: ax.set_ylabel("Total Upvotes Earned")

    plt.tight_layout()
    plt.show()

