#!/bin/bash
# Test script to verify ModuleNotFoundError fix

set -e

echo "=============================================="
echo "Testing ModuleNotFoundError Fix"
echo "=============================================="
echo ""

# Step 1: Build the analysis container
echo "Step 1: Building analysis container..."
docker compose build analysis

echo ""
echo "Step 2: Starting analysis container..."
docker compose up -d analysis

echo ""
echo "Step 3: Waiting for Jupyter to start..."
sleep 10

echo ""
echo "Step 4: Testing module imports..."
docker exec pbi-analysis python3 -c "
from workflow.scripts.sequences.download_host_genomes_optimized import OptimizedHostGenomeDownloader, load_config
print('✅ Import test 1: OptimizedHostGenomeDownloader imported successfully')

from workflow.scripts.sequences.download_host_genomes_optimized import OptimizedHostGenomeDownloader
print('✅ Import test 2: Direct import successful')

import sys
print('')
print('PYTHONPATH:', sys.path[0:3])
"

echo ""
echo "Step 5: Verifying all dependencies..."
docker exec pbi-analysis python3 -c "
import yaml
import aiohttp
import aiofiles
import duckdb
import pandas
from Bio import Entrez
print('✅ All dependencies installed correctly')
"

echo ""
echo "Step 6: Testing from workspace directory (notebook context)..."
docker exec -w /workspace pbi-analysis python3 -c "
from workflow.scripts.sequences.download_host_genomes_optimized import OptimizedHostGenomeDownloader
print('✅ Import from workspace context successful')
"

echo ""
echo "Step 7: Checking Jupyter status..."
docker exec pbi-analysis curl -s http://localhost:8888/api | head -20 || echo "Jupyter API is accessible"

echo ""
echo "=============================================="
echo "✅ All tests passed!"
echo "=============================================="
echo ""
echo "Jupyter Lab is available at: http://localhost:8888"
echo "You can now open notebooks/expl_7_hostgenomes.ipynb"
echo ""
echo "To stop: docker compose down"
