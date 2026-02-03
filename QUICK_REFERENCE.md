# Quick Reference: ModuleNotFoundError Fix

## Problem Solved
Fixed `ModuleNotFoundError` when importing workflow scripts in Jupyter notebooks.

## What Changed
1. **setup.py** - Added dependencies: pyyaml, aiohttp, aiofiles
2. **Dockerfile.analysis** - Copy entire project, set PYTHONPATH=/app
3. **docker-compose.yml** - Mount workflow and src directories, set PYTHONPATH=/app
4. **notebooks/expl_7_hostgenomes.ipynb** - Use proper import path
5. **workflow/** - Added __init__.py files to make it a Python package

## Quick Start

### Test the Fix
```bash
./test_module_import_fix.sh
```

### Manual Testing
```bash
# Build and start
docker compose build analysis
docker compose up -d analysis

# Access Jupyter Lab
# Open http://localhost:8888 in browser
# Open notebooks/expl_7_hostgenomes.ipynb
# Run the import cell - should succeed

# Clean up
docker compose down
```

### Verify Imports Work
```bash
docker exec pbi-analysis python3 -c "
from workflow.scripts.sequences.download_host_genomes_optimized import OptimizedHostGenomeDownloader
print('✅ Import successful!')
"
```

## New Import Pattern

### Before (❌ Don't use this)
```python
import sys
from pathlib import Path
project_root = Path.cwd().parent
sys.path.insert(0, str(project_root / 'workflow' / 'scripts' / 'sequences'))
from download_host_genomes_optimized import OptimizedHostGenomeDownloader
```

### After (✅ Use this)
```python
from workflow.scripts.sequences.download_host_genomes_optimized import OptimizedHostGenomeDownloader, load_config
```

## Files Modified
- setup.py (3 new dependencies)
- Dockerfile.analysis (COPY . /app/, PYTHONPATH)
- docker-compose.yml (volume mounts, PYTHONPATH env)
- notebooks/expl_7_hostgenomes.ipynb (proper imports)

## Files Created
- workflow/__init__.py (+ 6 more in subdirectories)
- test_module_import_fix.sh
- MODULE_FIX_DOCUMENTATION.md
- QUICK_REFERENCE.md (this file)

## Documentation
See `MODULE_FIX_DOCUMENTATION.md` for detailed information.

## Troubleshooting

### Import still fails?
1. Ensure container is rebuilt: `docker compose build analysis`
2. Check PYTHONPATH is set: `docker exec pbi-analysis env | grep PYTHONPATH`
3. Verify workflow is mounted: `docker exec pbi-analysis ls /app/workflow`

### Container won't start?
1. Check logs: `docker logs pbi-analysis`
2. Rebuild: `docker compose build --no-cache analysis`
3. Clean restart: `docker compose down && docker compose up -d analysis`

## Support
- Full documentation: MODULE_FIX_DOCUMENTATION.md
- Automated tests: ./test_module_import_fix.sh
- Issue tracking: GitHub Issues
