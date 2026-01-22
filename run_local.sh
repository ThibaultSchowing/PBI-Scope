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

# Set environment to use local relative paths
export PBI_DATA_DIR="data"

echo "✅ Environment configured:"
echo "   PBI_DATA_DIR = $PBI_DATA_DIR"
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

# Run snakemake from project root
snakemake \
  --directory workflow \
  --snakefile workflow/Snakefile \
  --cores 4 \
  --use-conda \
  --printshellcmds \
  --cache

echo ""
echo "✅ Pipeline complete!"
echo "📊 Check outputs in ./data/processed/"
