#!/usr/bin/env bash
# Helper script for running the pipeline locally

set -e

echo "🚀 PBI Pipeline - Local Development Mode"
echo "========================================="

# Create data directory structure if it doesn't exist
echo "📁 Creating data directories..."
mkdir -p data/raw/{phage_fasta_compressed,phage_fasta_extracted,protein_fasta_compressed,protein_fasta_extracted}
mkdir -p data/intermediate/{csv/merged,fasta/phages,fasta/proteins}
mkdir -p data/processed/{databases,sequences,reports}
mkdir -p pipeline_logs/{logs,reports}
mkdir -p private_data/phages

# Set environment to use local relative paths
export PBI_DATA_DIR="data"
export PBI_PRIVATE_DATA_DIR="private_data"
export PBI_LOGS_DIR="pipeline_logs"

echo "✅ Environment configured:"
echo "   PBI_DATA_DIR = $PBI_DATA_DIR"
echo "   PBI_PRIVATE_DATA_DIR = $PBI_PRIVATE_DATA_DIR"
echo "   PBI_LOGS_DIR = $PBI_LOGS_DIR"
echo ""

# Check if conda environment is activated
if [[ -z "$CONDA_DEFAULT_ENV" ]]; then
    echo "⚠️  Warning: No conda environment detected"
    echo "   Please activate your environment first:"
    echo "   conda activate pbi-pipeline"
    echo ""
    exit 1
fi

echo "🔄 Running Snakemake pipeline..."
echo "================================"

# Get number of cores from environment or default to 4
CORES=${PBI_CORES:-4}
echo "Using $CORES cores (set PBI_CORES to override)"
echo ""

# Run snakemake from project root
snakemake \
  --directory workflow \
  --cores $CORES \
  --use-conda \
  --printshellcmds \
  --cache

echo ""
echo "✅ Pipeline complete!"
echo "📊 Check outputs in ./data/processed/"
