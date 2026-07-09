"""
Python Script: PBI-Scope Database Exploration

This script connects to the PBI-Scope database using the pbi package
and generates exploration plots. It demonstrates how to use Python
with the PBI-Scope data.

Usage:
    python explore_phages.py

Prerequisites:
    - Python packages: pbi, duckdb, pandas, matplotlib, seaborn
    - The pbi-data Docker volume must be mounted at /data

Output:
    Plots are saved to ./output/ directory

This script is designed to run inside the custom R+Python container.
See Dockerfile and docker-compose.custom.yml for setup instructions.
"""

import os
from pathlib import Path

import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

# The pbi package provides quick_connect() for easy database access.
# It auto-detects the DATA_PATH environment variable and connects
# to the database and FASTA files automatically.
from pbi import quick_connect


def main():
    """Run the exploration analysis."""
    print("=== PBI-Scope Database Exploration (Python) ===\n")

    # Create output directory
    output_dir = Path("output")
    output_dir.mkdir(exist_ok=True)

    # Connect to database
    # quick_connect() reads DATA_PATH env var and resolves all file paths.
    # In Docker: DATA_PATH=/data/processed
    print("Connecting to database...")
    retriever = quick_connect()

    # --- Plot 1: Source Database Distribution ---------------------------------
    # Which public databases contribute the most phages?
    print("[1/6] Querying source database distribution...")
    source_dist = retriever.conn.execute("""
        SELECT Source_DB, COUNT(*) AS phage_count
        FROM fact_phages
        GROUP BY Source_DB
        ORDER BY phage_count DESC
    """).fetchdf()

    print("  Top sources:")
    print(source_dist.head().to_string(index=False))

    fig, ax = plt.subplots(figsize=(10, 6))
    source_dist.plot(
        kind="barh", x="Source_DB", y="phage_count", 
        ax=ax, legend=False, color="steelblue"
    )
    ax.set_title(f"Phages by Source Database\nTotal: {source_dist['phage_count'].sum():,} phages")
    ax.set_xlabel("Number of Phages")
    ax.set_ylabel(None)
    ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f"{x:,.0f}"))
    plt.tight_layout()
    fig.savefig(output_dir / "01_source_distribution.png", dpi=150)
    plt.close(fig)
    print("  Saved: output/01_source_distribution.png\n")

    # --- Plot 2: Genome Length Distribution -----------------------------------
    # Phage genome lengths vary widely (from ~2 kb to ~500 kb).
    print("[2/6] Querying genome length distribution...")
    lengths = retriever.conn.execute("""
        SELECT Length
        FROM fact_phages
        WHERE Length > 0 AND Length < 200000
    """).fetchdf()

    median_len = lengths["Length"].median()
    print(f"  Median: {median_len:,.0f} bp")
    print(f"  Mean: {lengths['Length'].mean():,.0f} bp")
    print(f"  Min: {lengths['Length'].min():,.0f} bp")
    print(f"  Max: {lengths['Length'].max():,.0f} bp\n")

    fig, ax = plt.subplots(figsize=(10, 6))
    lengths["Length"].div(1000).hist(
        bins=50, ax=ax, color="steelblue", edgecolor="white"
    )
    ax.axvline(median_len / 1000, color="red", linestyle="--", 
               linewidth=1.5, label=f"Median: {median_len/1000:,.0f} kb")
    ax.set_title("Phage Genome Length Distribution")
    ax.set_xlabel("Genome Length (kb)")
    ax.set_ylabel("Count")
    ax.legend()
    plt.tight_layout()
    fig.savefig(output_dir / "02_length_distribution.png", dpi=150)
    plt.close(fig)
    print("  Saved: output/02_length_distribution.png\n")

    # --- Plot 3: Lifestyle Distribution ---------------------------------------
    # Phages are classified as virulent (lytic) or temperate (lysogenic).
    print("[3/6] Querying lifestyle distribution...")
    lifestyle = retriever.conn.execute("""
        SELECT Lifestyle, COUNT(*) AS count
        FROM fact_phages
        WHERE Lifestyle IN ('virulent', 'temperate')
        GROUP BY Lifestyle
    """).fetchdf()

    total = lifestyle["count"].sum()
    for _, row in lifestyle.iterrows():
        pct = row["count"] / total * 100
        print(f"  {row['Lifestyle']}: {row['count']:,} ({pct:.1f}%)")

    fig, ax = plt.subplots(figsize=(8, 6))
    colors = {"virulent": "#E74C3C", "temperate": "#3498DB"}
    lifestyle.plot(
        kind="bar", x="Lifestyle", y="count", ax=ax, legend=False,
        color=[colors.get(x, "gray") for x in lifestyle["Lifestyle"]]
    )
    ax.set_title("Phage Lifestyle Distribution")
    ax.set_xlabel(None)
    ax.set_ylabel("Count")
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f"{x:,.0f}"))
    plt.xticks(rotation=0)
    plt.tight_layout()
    fig.savefig(output_dir / "03_lifestyle_distribution.png", dpi=150)
    plt.close(fig)
    print("  Saved: output/03_lifestyle_distribution.png\n")

    # --- Plot 4: Top Host Species ---------------------------------------------
    # Which bacterial species have the most known phages?
    print("[4/6] Querying top host species...")
    hosts = retriever.conn.execute("""
        SELECT h.Species_Name, COUNT(DISTINCT p.Phage_ID) AS phage_count
        FROM phage_host_associations pha
        JOIN fact_phages p ON pha.Phage_ID = p.Phage_ID
        JOIN dim_hosts h ON pha.Host_ID = h.Host_ID
        WHERE h.Species_Name IS NOT NULL
        GROUP BY h.Species_Name
        ORDER BY phage_count DESC
        LIMIT 20
    """).fetchdf()

    print("  Top 5 hosts:")
    print(hosts.head().to_string(index=False))

    fig, ax = plt.subplots(figsize=(10, 8))
    hosts.plot(
        kind="barh", x="Species_Name", y="phage_count", 
        ax=ax, legend=False, color="forestgreen"
    )
    ax.set_title("Top 20 Host Species by Number of Phages")
    ax.set_xlabel("Number of Phages")
    ax.set_ylabel(None)
    ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f"{x:,.0f}"))
    plt.tight_layout()
    fig.savefig(output_dir / "04_top_hosts.png", dpi=150)
    plt.close(fig)
    print("  Saved: output/04_top_hosts.png\n")

    # --- Plot 5: GC Content Comparison ----------------------------------------
    # Comparing GC content between phages and their hosts.
    print("[5/6] Querying GC content comparison...")
    gc_comparison = retriever.conn.execute("""
        SELECT 
            'Phage' AS type,
            GC_content AS GC
        FROM fact_phages
        WHERE GC_content > 0 AND GC_content < 100
        UNION ALL
        SELECT
            'Host' AS type,
            GC_Content AS GC
        FROM dim_hosts
        WHERE GC_Content > 0 AND GC_Content < 100
    """).fetchdf()

    for t in ["Phage", "Host"]:
        subset = gc_comparison[gc_comparison["type"] == t]
        print(f"  {t} GC: mean={subset['GC'].mean():.1f}%, median={subset['GC'].median():.1f}%")

    fig, ax = plt.subplots(figsize=(10, 6))
    for t, color in [("Phage", "#E74C3C"), ("Host", "#3498DB")]:
        subset = gc_comparison[gc_comparison["type"] == t]
        subset["GC"].plot.kde(ax=ax, color=color, alpha=0.5, label=t, linewidth=2)
    ax.set_title("GC Content Distribution: Phages vs Hosts")
    ax.set_xlabel("GC Content (%)")
    ax.set_ylabel("Density")
    ax.legend()
    plt.tight_layout()
    fig.savefig(output_dir / "05_gc_content_comparison.png", dpi=150)
    plt.close(fig)
    print("  Saved: output/05_gc_content_comparison.png\n")

    # --- Plot 6: Host Assembly Quality ----------------------------------------
    # The quality of host assemblies affects downstream analyses.
    print("[6/6] Querying host assembly quality...")
    assembly = retriever.conn.execute("""
        SELECT Assembly_Level, COUNT(*) AS count
        FROM dim_hosts
        GROUP BY Assembly_Level
        ORDER BY count DESC
    """).fetchdf()

    for _, row in assembly.iterrows():
        pct = row["count"] / assembly["count"].sum() * 100
        print(f"  {row['Assembly_Level']}: {row['count']:,} ({pct:.1f}%)")

    # Order by quality level
    level_order = ["Complete Genome", "Chromosome", "Scaffold", "Contig"]
    assembly["Assembly_Level"] = pd.Categorical(
        assembly["Assembly_Level"], categories=level_order, ordered=True
    )
    assembly = assembly.sort_values("Assembly_Level")

    fig, ax = plt.subplots(figsize=(10, 6))
    assembly.plot(
        kind="bar", x="Assembly_Level", y="count", ax=ax, legend=False,
        color=plt.cm.Set2(range(len(assembly)))
    )
    ax.set_title("Host Assembly Quality Distribution")
    ax.set_xlabel(None)
    ax.set_ylabel("Number of Hosts")
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f"{x:,.0f}"))
    plt.xticks(rotation=45, ha="right")
    plt.tight_layout()
    fig.savefig(output_dir / "06_assembly_quality.png", dpi=150)
    plt.close(fig)
    print("  Saved: output/06_assembly_quality.png\n")

    # Cleanup
    retriever.close()

    print("=== All plots saved to output/ ===")
    print("Files:")
    for f in sorted(output_dir.glob("*.png")):
        print(f"  - {f.name}")


if __name__ == "__main__":
    main()
