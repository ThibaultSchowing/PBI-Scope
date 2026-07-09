# =============================================================================
# R Script: PBI-Scope Database Exploration
# =============================================================================
# This script connects to the PBI-Scope DuckDB database and generates
# exploration plots. It demonstrates how to use R with the PBI-Scope data.
#
# Usage:
#   Rscript explore_phages.R
#
# Prerequisites:
#   - R packages: DBI, duckdb, dplyr, ggplot2, scales
#   - The pbi-data Docker volume must be mounted at /data
#
# Output:
#   Plots are saved to ./output/ directory
#
# This script is designed to run inside the custom R+Python container.
# See Dockerfile and docker-compose.custom.yml for setup instructions.
# =============================================================================

# --- Load Libraries -----------------------------------------------------------
# DBI: Database Interface - standard R interface for databases
# duckdb: DuckDB driver for DBI
# dplyr: Data manipulation grammar
# ggplot2: Grammar of graphics for visualization
# scales: Axis formatting utilities (comma labels, percent, etc.)
library(DBI)
library(duckdb)
library(dplyr)
library(ggplot2)
library(scales)

# --- Configuration ------------------------------------------------------------
# The database path is determined by the DATA_PATH environment variable.
# In Docker: DATA_PATH=/data/processed (set in docker-compose.yml)
# The database file is at: /data/processed/databases/phage_database_optimized.duckdb
db_path <- file.path(Sys.getenv("DATA_PATH", "/data/processed"),
                     "databases", "phage_database_optimized.duckdb")

# Output directory for plots
output_dir <- "output"
dir.create(output_dir, showWarnings = FALSE)

cat("=== PBI-Scope Database Exploration (R) ===\n\n")
cat("Database:", db_path, "\n")
cat("Output:", output_dir, "/\n\n")

# --- Connect to Database ------------------------------------------------------
# We open a read-only connection to prevent accidental modifications.
cat("Connecting to database...\n")
con <- dbConnect(duckdb(), dbdir = db_path, read_only = TRUE)

# List available tables
tables <- dbListTables(con)
cat("Available tables:", paste(tables, collapse = ", "), "\n\n")

# --- Query 1: Source Database Distribution ------------------------------------
# Which public databases contribute the most phages?
# This helps understand data composition and potential biases.
cat("[1/6] Querying source database distribution...\n")
source_dist <- dbGetQuery(con, "
    SELECT Source_DB, COUNT(*) AS phage_count
    FROM fact_phages
    GROUP BY Source_DB
    ORDER BY phage_count DESC
")

cat("  Top sources:\n")
head(source_dist, 5) %>% 
    mutate(phage_count = comma(phage_count)) %>%
    print()

p1 <- ggplot(source_dist, aes(x = reorder(Source_DB, phage_count), y = phage_count)) +
    geom_bar(stat = "identity", fill = "steelblue") +
    coord_flip() +
    scale_y_continuous(labels = comma) +
    labs(
        title = "Phages by Source Database",
        subtitle = paste("Total:", comma(sum(source_dist$phage_count)), "phages"),
        x = NULL,
        y = "Number of Phages"
    ) +
    theme_minimal(base_size = 12)

ggsave(file.path(output_dir, "01_source_distribution.png"), p1, 
       width = 10, height = 6, dpi = 150)
cat("  Saved: output/01_source_distribution.png\n\n")

# --- Query 2: Genome Length Distribution -------------------------------------
# Phage genome lengths vary widely (from ~2 kb to ~500 kb).
# This distribution helps identify unusual phages and set filtering thresholds.
cat("[2/6] Querying genome length distribution...\n")
lengths <- dbGetQuery(con, "
    SELECT Length
    FROM fact_phages
    WHERE Length > 0 AND Length < 200000
")

cat("  Summary:\n")
cat("    Median:", comma(round(median(lengths$Length))), "bp\n")
cat("    Mean:", comma(round(mean(lengths$Length))), "bp\n")
cat("    Min:", comma(min(lengths$Length)), "bp\n")
cat("    Max:", comma(max(lengths$Length)), "bp\n\n")

p2 <- ggplot(lengths, aes(x = Length / 1000)) +
    geom_histogram(bins = 50, fill = "steelblue", color = "white") +
    geom_vline(xintercept = median(lengths$Length) / 1000, 
               linetype = "dashed", color = "red", linewidth = 1) +
    scale_x_continuous(labels = comma) +
    labs(
        title = "Phage Genome Length Distribution",
        subtitle = paste("Median:", comma(round(median(lengths$Length) / 1000)), "kb"),
        x = "Genome Length (kb)",
        y = "Count"
    ) +
    theme_minimal(base_size = 12)

ggsave(file.path(output_dir, "02_length_distribution.png"), p2, 
       width = 10, height = 6, dpi = 150)
cat("  Saved: output/02_length_distribution.png\n\n")

# --- Query 3: Lifestyle Distribution -----------------------------------------
# Phages are classified as virulent (lytic) or temperate (lysogenic).
# This is a key biological variable for many analyses.
cat("[3/6] Querying lifestyle distribution...\n")
lifestyle <- dbGetQuery(con, "
    SELECT Lifestyle, COUNT(*) AS count
    FROM fact_phages
    WHERE Lifestyle IN ('virulent', 'temperate')
    GROUP BY Lifestyle
")

cat("  Distribution:\n")
lifestyle %>%
    mutate(percentage = paste0(round(count / sum(count) * 100, 1), "%")) %>%
    print()

p3 <- ggplot(lifestyle, aes(x = Lifestyle, y = count, fill = Lifestyle)) +
    geom_bar(stat = "identity") +
    scale_y_continuous(labels = comma) +
    scale_fill_manual(values = c("virulent" = "#E74C3C", "temperate" = "#3498DB")) +
    labs(
        title = "Phage Lifestyle Distribution",
        x = NULL,
        y = "Count"
    ) +
    theme_minimal(base_size = 12) +
    theme(legend.position = "none")

ggsave(file.path(output_dir, "03_lifestyle_distribution.png"), p3, 
       width = 8, height = 6, dpi = 150)
cat("  Saved: output/03_lifestyle_distribution.png\n\n")

# --- Query 4: Top Host Species ------------------------------------------------
# Which bacterial species have the most known phages?
# This reveals sampling bias in phage research.
cat("[4/6] Querying top host species...\n")
hosts <- dbGetQuery(con, "
    SELECT h.Species_Name, COUNT(DISTINCT p.Phage_ID) AS phage_count
    FROM phage_host_associations pha
    JOIN fact_phages p ON pha.Phage_ID = p.Phage_ID
    JOIN dim_hosts h ON pha.Host_ID = h.Host_ID
    WHERE h.Species_Name IS NOT NULL
    GROUP BY h.Species_Name
    ORDER BY phage_count DESC
    LIMIT 20
")

cat("  Top 5 hosts:\n")
head(hosts, 5) %>%
    mutate(phage_count = comma(phage_count)) %>%
    print()

p4 <- ggplot(hosts, aes(x = reorder(Species_Name, phage_count), y = phage_count)) +
    geom_bar(stat = "identity", fill = "forestgreen") +
    coord_flip() +
    scale_y_continuous(labels = comma) +
    labs(
        title = "Top 20 Host Species by Number of Phages",
        x = NULL,
        y = "Number of Phages"
    ) +
    theme_minimal(base_size = 12)

ggsave(file.path(output_dir, "04_top_hosts.png"), p4, 
       width = 10, height = 8, dpi = 150)
cat("  Saved: output/04_top_hosts.png\n\n")

# --- Query 5: GC Content Comparison ------------------------------------------
# Comparing GC content between phages and their hosts can reveal
# co-evolution patterns and horizontal gene transfer.
cat("[5/6] Querying GC content comparison...\n")
gc_comparison <- dbGetQuery(con, "
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
")

cat("  Summary:\n")
gc_comparison %>%
    group_by(type) %>%
    summarise(
        mean_gc = round(mean(GC), 1),
        median_gc = round(median(GC), 1),
        .groups = "drop"
    ) %>%
    print()

p5 <- ggplot(gc_comparison, aes(x = GC, fill = type)) +
    geom_density(alpha = 0.5) +
    scale_fill_manual(values = c("Phage" = "#E74C3C", "Host" = "#3498DB")) +
    labs(
        title = "GC Content Distribution: Phages vs Hosts",
        x = "GC Content (%)",
        y = "Density",
        fill = "Type"
    ) +
    theme_minimal(base_size = 12)

ggsave(file.path(output_dir, "05_gc_content_comparison.png"), p5, 
       width = 10, height = 6, dpi = 150)
cat("  Saved: output/05_gc_content_comparison.png\n\n")

# --- Query 6: Host Assembly Quality -------------------------------------------
# The quality of host assemblies affects downstream analyses.
# This plot shows the distribution of assembly levels.
cat("[6/6] Querying host assembly quality...\n")
assembly <- dbGetQuery(con, "
    SELECT Assembly_Level, COUNT(*) AS count
    FROM dim_hosts
    GROUP BY Assembly_Level
    ORDER BY count DESC
")

cat("  Distribution:\n")
assembly %>%
    mutate(percentage = paste0(round(count / sum(count) * 100, 1), "%")) %>%
    print()

# Order assembly levels by quality
assembly$Assembly_Level <- factor(assembly$Assembly_Level, 
    levels = c("Complete Genome", "Chromosome", "Scaffold", "Contig"))

p6 <- ggplot(assembly, aes(x = Assembly_Level, y = count, fill = Assembly_Level)) +
    geom_bar(stat = "identity") +
    scale_y_continuous(labels = comma) +
    scale_fill_brewer(palette = "Set2") +
    labs(
        title = "Host Assembly Quality Distribution",
        x = NULL,
        y = "Number of Hosts"
    ) +
    theme_minimal(base_size = 12) +
    theme(legend.position = "none",
          axis.text.x = element_text(angle = 45, hjust = 1))

ggsave(file.path(output_dir, "06_assembly_quality.png"), p6, 
       width = 10, height = 6, dpi = 150)
cat("  Saved: output/06_assembly_quality.png\n\n")

# --- Disconnect ---------------------------------------------------------------
dbDisconnect(con, shutdown = TRUE)

cat("=== All plots saved to output/ ===\n")
cat("Files:\n")
list.files(output_dir, pattern = "\\.png$") %>%
    paste0("  - ", .) %>%
    cat(sep = "\n")
