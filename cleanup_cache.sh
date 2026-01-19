#!/bin/bash
# Cleanup script for PBI Docker cache volume
# This script removes the Snakemake cache volume to free up space
# while preserving the main data volume

set -e

echo "PBI Cache Cleanup Tool"
echo "====================="
echo ""
echo "This script will remove the pbi-cache Docker volume."
echo "This volume contains:"
echo "  - Snakemake metadata and workflow state"
echo "  - Conda environments (~2 GB)"
echo ""
echo "The main data volume (pbi-data) with your database will NOT be affected."
echo ""

# Check if volume exists
if ! docker volume inspect pbi-cache >/dev/null 2>&1; then
    echo "✓ Cache volume 'pbi-cache' does not exist or is already removed."
    exit 0
fi

# Check if volume is in use
if docker ps -q -f volume=pbi-cache | grep -q .; then
    echo "⚠ Warning: The cache volume is currently in use by running containers."
    echo ""
    echo "Running containers using pbi-cache:"
    docker ps --filter volume=pbi-cache --format "table {{.Names}}\t{{.Status}}\t{{.Image}}"
    echo ""
    read -p "Do you want to stop these containers? (y/N): " -n 1 -r
    echo ""
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo "Stopping containers..."
        docker compose down
    else
        echo "Aborted. Please stop the containers manually and try again."
        exit 1
    fi
fi

# Confirm deletion
read -p "Are you sure you want to delete the cache volume? (y/N): " -n 1 -r
echo ""
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Aborted."
    exit 0
fi

# Remove the volume
echo "Removing cache volume..."
docker volume rm pbi-cache

echo "✓ Cache volume removed successfully!"
echo ""
echo "Next steps:"
echo "  - Run 'docker compose run --rm pipeline' to rebuild the cache"
echo "  - The first run will re-download conda packages (~2 GB)"
echo "  - Subsequent runs will be faster as the cache is rebuilt"
