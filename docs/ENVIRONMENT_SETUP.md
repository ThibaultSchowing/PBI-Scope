# Environment Setup Guide

This guide provides step-by-step instructions for setting up the environment variables and dependencies required for the PBI pipeline, particularly for FASTA downloads.

## Table of Contents

1. [Quick Setup](#quick-setup)
2. [NCBI Credentials](#ncbi-credentials)
3. [System Dependencies](#system-dependencies)
4. [Conda Environment](#conda-environment)
5. [Docker Environment](#docker-environment)
6. [Verification](#verification)

## Quick Setup

### Minimal Setup (Required)

```bash
# Set NCBI email (required by NCBI API)
export NCBI_EMAIL="your.email@example.com"
```

### Recommended Setup

```bash
# Set NCBI credentials
export NCBI_EMAIL="your.email@example.com"
export NCBI_API_KEY="your_api_key_here"

# Make persistent (add to ~/.bashrc or ~/.zshrc)
echo 'export NCBI_EMAIL="your.email@example.com"' >> ~/.bashrc
echo 'export NCBI_API_KEY="your_api_key_here"' >> ~/.bashrc
source ~/.bashrc
```

## NCBI Credentials

### Why NCBI Credentials are Required

**NCBI Email** (Required):
- NCBI requires an email for all API requests
- Used for identification and rate limiting
- NCBI may contact you if there are issues with your requests

**NCBI API Key** (Recommended):
- Increases rate limit from 3 to 10 requests/second
- Reduces download time by ~70%
- Free to obtain from NCBI

### How to Get NCBI API Key

#### Step 1: Create NCBI Account

1. Go to https://www.ncbi.nlm.nih.gov/account/
2. Click "Register for an NCBI account"
3. Fill in registration form with your details
4. Verify your email address

#### Step 2: Generate API Key

1. Log in to your NCBI account
2. Go to https://www.ncbi.nlm.nih.gov/account/settings/
3. Scroll to "API Key Management" section
4. Click "Create an API Key"
5. Copy the generated key (you won't be able to see it again!)

#### Step 3: Set API Key

**Linux/macOS**:
```bash
export NCBI_API_KEY="your_api_key_here"

# Make permanent
echo 'export NCBI_API_KEY="your_api_key_here"' >> ~/.bashrc
source ~/.bashrc
```

**Windows (PowerShell)**:
```powershell
$env:NCBI_API_KEY = "your_api_key_here"

# Make permanent
setx NCBI_API_KEY "your_api_key_here"
```

**Windows (Command Prompt)**:
```cmd
set NCBI_API_KEY=your_api_key_here

:: Make permanent
setx NCBI_API_KEY "your_api_key_here"
```

### Verify NCBI Credentials

```bash
# Check if variables are set
echo "NCBI Email: $NCBI_EMAIL"
echo "NCBI API Key: ${NCBI_API_KEY:0:10}..."  # Show only first 10 chars

# Test NCBI connection
python -c "
from Bio import Entrez
import os

Entrez.email = os.getenv('NCBI_EMAIL')
Entrez.api_key = os.getenv('NCBI_API_KEY')

if Entrez.api_key:
    print('✅ API Key detected - 10 req/sec rate limit')
else:
    print('⚠️  No API Key - 3 req/sec rate limit')

# Test search
handle = Entrez.esearch(db='assembly', term='Escherichia coli', retmax=1)
result = Entrez.read(handle)
handle.close()

if result['IdList']:
    print('✅ NCBI connection successful')
else:
    print('❌ NCBI connection failed')
"
```

## System Dependencies

### NCBI Datasets CLI (Optional but Recommended)

The NCBI datasets command-line tool provides faster and more reliable downloads.

#### Installation Methods

**Via Conda** (Recommended):
```bash
conda install -c conda-forge ncbi-datasets-cli
```

**Via Direct Download**:

**Linux**:
```bash
curl -o datasets 'https://ftp.ncbi.nlm.nih.gov/pub/datasets/command-line/LATEST/linux-amd64/datasets'
chmod +x datasets
sudo mv datasets /usr/local/bin/
```

**macOS**:
```bash
curl -o datasets 'https://ftp.ncbi.nlm.nih.gov/pub/datasets/command-line/LATEST/mac/datasets'
chmod +x datasets
sudo mv datasets /usr/local/bin/
```

**Windows**:
Download from: https://ftp.ncbi.nlm.nih.gov/pub/datasets/command-line/LATEST/windows-amd64/
Add to PATH

#### Verify Installation

```bash
datasets version
# Output: datasets version: 16.x.x
```

### Other Required Tools

**Python packages** (installed via conda/pip):
- biopython >= 1.79
- pandas >= 1.3.0
- pyfaidx >= 0.6.0

**System tools**:
- wget or curl (for downloads)
- tar, gzip (for archive extraction)
- sqlite3 (for cache database)

## Conda Environment

### Creating the Environment

**From environment file**:
```bash
# Navigate to repository
cd /path/to/PBI

# Create environment
conda env create -f workflow/envs/base_environment.yaml

# Activate environment
conda activate snakemake_base
```

**Manual creation**:
```bash
# Create environment
conda create -n pbi_env python=3.9

# Activate
conda activate pbi_env

# Install dependencies
conda install -c conda-forge -c bioconda \
    snakemake \
    biopython \
    pandas \
    pyfaidx \
    ncbi-datasets-cli \
    duckdb \
    pyyaml

# Install PBI package
pip install -e .
```

### Environment Activation

**Every session**:
```bash
conda activate snakemake_base  # or pbi_env
```

**Auto-activation** (optional):
```bash
echo 'conda activate snakemake_base' >> ~/.bashrc
```

### Verify Environment

```bash
# Check Python version
python --version  # Should be 3.9+

# Check key packages
python -c "
import Bio
import pandas as pd
import pyfaidx
import yaml
print('✅ All key packages installed')
print(f'Biopython version: {Bio.__version__}')
print(f'Pandas version: {pd.__version__}')
"

# Check command-line tools
which snakemake
which datasets
```

## Docker Environment

### Using Docker Compose

Docker provides the easiest setup with all dependencies pre-installed.

**Set environment variables in `.env` file**:
```bash
# Create .env file in repository root
cat > .env << EOF
NCBI_EMAIL=your.email@example.com
NCBI_API_KEY=your_api_key_here
EOF
```

**Run pipeline**:
```bash
# Build and run
docker compose build pipeline
docker compose run --rm pipeline
```

**Environment variables are automatically loaded** from `.env` file.

### Using Plain Docker

**Set environment variables**:
```bash
docker run --rm \
  -e NCBI_EMAIL="your.email@example.com" \
  -e NCBI_API_KEY="your_api_key_here" \
  -v $(pwd)/data:/data \
  pbi-pipeline
```

### Verify Docker Environment

```bash
# Test environment in container
docker compose run --rm pipeline bash -c "
echo 'NCBI Email:' \$NCBI_EMAIL
echo 'API Key set:' \${NCBI_API_KEY:+Yes}
python -c 'import Bio; print(\"Biopython:\", Bio.__version__)'
datasets version
"
```

## Verification

### Complete Verification Script

```bash
#!/bin/bash
# verify_setup.sh

echo "=== PBI Environment Verification ==="
echo ""

# 1. Check environment variables
echo "1. Environment Variables:"
if [ -n "$NCBI_EMAIL" ]; then
    echo "   ✅ NCBI_EMAIL is set: $NCBI_EMAIL"
else
    echo "   ❌ NCBI_EMAIL is NOT set"
fi

if [ -n "$NCBI_API_KEY" ]; then
    echo "   ✅ NCBI_API_KEY is set: ${NCBI_API_KEY:0:10}..."
else
    echo "   ⚠️  NCBI_API_KEY is NOT set (optional but recommended)"
fi
echo ""

# 2. Check conda environment
echo "2. Conda Environment:"
if command -v conda &> /dev/null; then
    echo "   ✅ Conda is installed"
    echo "   Current environment: $CONDA_DEFAULT_ENV"
else
    echo "   ❌ Conda is NOT installed"
fi
echo ""

# 3. Check Python packages
echo "3. Python Packages:"
python -c "
try:
    import Bio
    print(f'   ✅ Biopython {Bio.__version__}')
except ImportError:
    print('   ❌ Biopython NOT installed')

try:
    import pandas as pd
    print(f'   ✅ Pandas {pd.__version__}')
except ImportError:
    print('   ❌ Pandas NOT installed')

try:
    import pyfaidx
    print(f'   ✅ pyfaidx installed')
except ImportError:
    print('   ❌ pyfaidx NOT installed')

try:
    import yaml
    print(f'   ✅ PyYAML installed')
except ImportError:
    print('   ❌ PyYAML NOT installed')
"
echo ""

# 4. Check command-line tools
echo "4. Command-line Tools:"
if command -v datasets &> /dev/null; then
    echo "   ✅ NCBI datasets CLI: $(datasets version | head -n 1)"
else
    echo "   ⚠️  NCBI datasets CLI NOT installed (optional but recommended)"
fi

if command -v snakemake &> /dev/null; then
    echo "   ✅ Snakemake: $(snakemake --version)"
else
    echo "   ❌ Snakemake NOT installed"
fi
echo ""

# 5. Test NCBI connection
echo "5. NCBI Connection Test:"
python -c "
import os
from Bio import Entrez

Entrez.email = os.getenv('NCBI_EMAIL', 'test@example.com')
Entrez.api_key = os.getenv('NCBI_API_KEY')

try:
    handle = Entrez.esearch(db='assembly', term='Escherichia coli', retmax=1)
    result = Entrez.read(handle)
    handle.close()
    
    if result['IdList']:
        print('   ✅ NCBI connection successful')
        if Entrez.api_key:
            print('   ✅ Using API key (10 req/sec)')
        else:
            print('   ⚠️  No API key (3 req/sec)')
    else:
        print('   ⚠️  NCBI returned no results')
except Exception as e:
    print(f'   ❌ NCBI connection failed: {e}')
"
echo ""

echo "=== Verification Complete ==="
```

**Run verification**:
```bash
chmod +x verify_setup.sh
./verify_setup.sh
```

### Quick Tests

**Test 1: Environment Variables**
```bash
env | grep NCBI
```

**Test 2: Python Import**
```bash
python -c "from Bio import Entrez; print('✅ Biopython OK')"
```

**Test 3: NCBI Connection**
```bash
python -c "
from Bio import Entrez
import os
Entrez.email = os.getenv('NCBI_EMAIL', 'test@example.com')
handle = Entrez.esearch(db='assembly', term='test', retmax=1)
Entrez.read(handle)
handle.close()
print('✅ NCBI OK')
"
```

**Test 4: Datasets CLI**
```bash
datasets summary genome taxon "Escherichia coli" --limit 1
```

## Troubleshooting

### Issue: NCBI_EMAIL not set

**Error**: 
```
ValueError: NCBI requires you to set Entrez.email
```

**Solution**:
```bash
export NCBI_EMAIL="your.email@example.com"
```

### Issue: API key not detected

**Symptoms**: Slow downloads (3 req/sec instead of 10)

**Solution**:
```bash
# Set API key
export NCBI_API_KEY="your_api_key_here"

# Verify
python -c "import os; print('API Key set:', bool(os.getenv('NCBI_API_KEY')))"
```

### Issue: Command not found: datasets

**Solution**:
```bash
# Install via conda
conda install -c conda-forge ncbi-datasets-cli

# Or download directly (see installation section above)
```

### Issue: Module not found: Bio

**Solution**:
```bash
# Activate conda environment
conda activate snakemake_base

# Or install Biopython
pip install biopython
```

### Issue: Permission denied on Docker

**Solution**:
```bash
# Add user to docker group
sudo usermod -aG docker $USER

# Log out and log back in, or
newgrp docker
```

## Best Practices

1. **Always set NCBI_EMAIL** - Required by NCBI API
2. **Use NCBI API key** - 3x faster downloads
3. **Use conda environments** - Isolates dependencies
4. **Verify setup before running** - Saves time debugging later
5. **Keep credentials secure** - Don't commit to git
6. **Update regularly** - Keep datasets CLI and Biopython current

## Related Documentation

- [FASTA Download Guide](FASTA_DOWNLOAD_GUIDE.md)
- [Genome Download Quickstart](../GENOME_DOWNLOAD_QUICKSTART.md)
- [Local Setup Guide](../LOCAL_SETUP.md)
- [Docker Documentation](../DOCKER.md)
