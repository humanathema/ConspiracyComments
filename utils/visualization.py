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

