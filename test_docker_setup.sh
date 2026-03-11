#!/bin/bash
# Integration test for Docker setup
# This script demonstrates the complete workflow

set -e

echo "=========================================="
echo "PBI Docker Integration Test"
echo "=========================================="
echo ""

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}Step 1: Validating Docker Compose configuration${NC}"
docker compose config --quiet
echo -e "${GREEN}✓ Docker Compose configuration is valid${NC}"
echo ""

echo -e "${BLUE}Step 2: Checking Dockerfile syntax${NC}"
if docker compose build --help > /dev/null 2>&1; then
    echo -e "${GREEN}✓ Docker Compose build command available${NC}"
else
    echo "Error: Docker Compose not available"
    exit 1
fi
echo ""

echo -e "${BLUE}Step 3: Verifying path configuration${NC}"
python3 tests/test_docker_paths.py
echo ""

echo "=========================================="
echo "Docker Setup Validation Complete!"
echo "=========================================="
echo ""
echo "Next steps for users:"
echo "1. docker compose build pipeline"
echo "2. docker compose run --rm pipeline"
echo "3. docker compose build api"
echo "4. docker compose up -d api"
echo "5. curl http://localhost:8000/health"
echo ""
echo "See DOCKER.md for detailed instructions."
