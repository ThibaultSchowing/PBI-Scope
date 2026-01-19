#!/bin/bash
# Cleanup script for PBI Docker cache volume
# This script removes the Snakemake cache volume to free up space
# while preserving the main data volume
#
# Make executable with: chmod +x cleanup_cache.sh

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
# Note: Docker Compose prefixes volumes with project name (e.g., pbi_pbi-cache)
VOLUME_NAME=$(docker volume ls --format '{{.Name}}' | grep -E '(^|_)pbi-cache$' | head -1)

if [ -z "$VOLUME_NAME" ]; then
    echo "✓ Cache volume 'pbi-cache' does not exist or is already removed."
    exit 0
fi

echo "Found cache volume: $VOLUME_NAME"
echo ""

# Check if volume is in use
CONTAINERS_USING_CACHE=$(docker ps -q | xargs -r docker inspect --format "{{.Name}}{{range .Mounts}}{{if eq .Name \"$VOLUME_NAME\"}} USES_CACHE{{end}}{{end}}" 2>/dev/null | grep "USES_CACHE" | cut -d' ' -f1 || true)

if [ -n "$CONTAINERS_USING_CACHE" ]; then
    echo "⚠ Warning: The cache volume is currently in use by running containers."
    echo ""
    echo "Containers using pbi-cache:"
    echo "$CONTAINERS_USING_CACHE"
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
echo "Removing cache volume $VOLUME_NAME..."
docker volume rm "$VOLUME_NAME"

echo "✓ Cache volume removed successfully!"
echo ""
echo "Next steps:"
echo "  - Run 'docker compose run --rm pipeline' to rebuild the cache"
echo "  - The first run will re-download conda packages (~2 GB)"
echo "  - Subsequent runs will be faster as the cache is rebuilt"
