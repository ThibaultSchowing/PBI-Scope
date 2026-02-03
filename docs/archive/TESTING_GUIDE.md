# Testing Guide for Direct Data Access Implementation

This document provides step-by-step instructions for testing the new Analysis Service.

## Prerequisites

Before testing, ensure you have:
- Docker (≥20.10)
- Docker Compose (≥2.0)
- At least 4 GB free RAM (for testing)
- At least 5 GB free disk space (for Docker images)

## Test Plan

### Phase 1: Build and Startup Tests

#### Test 1.1: Build Analysis Container

**Objective**: Verify the analysis container builds successfully

```bash
cd /path/to/PBI
docker compose build analysis
```

**Expected Result**:
- Build completes without errors
- Image size approximately 2 GB
- All Python dependencies install correctly
- Jupyter Lab configuration created

**Success Criteria**:
- Exit code 0
- No error messages in build output
- Image appears in `docker images | grep pbi-analysis`

#### Test 1.2: Start Analysis Service

**Objective**: Verify the service starts correctly

```bash
docker compose up -d analysis
```

**Expected Result**:
- Container starts successfully
- Status shows "Up" in `docker ps`
- Port 8888 is exposed

**Success Criteria**:
- Container running: `docker ps | grep pbi-analysis`
- Logs show no errors: `docker logs pbi-analysis`
- Health check passes after 40 seconds

#### Test 1.3: Access Jupyter Lab

**Objective**: Verify Jupyter Lab is accessible

1. Open browser to http://localhost:8888
2. Should see Jupyter Lab interface (no password required)

**Expected Result**:
- Jupyter Lab interface loads
- No authentication prompt
- `/workspace` directory visible with notebooks

**Success Criteria**:
- HTTP 200 response
- Can navigate to notebooks directory
- No error messages in browser console

### Phase 2: Functional Tests

#### Test 2.1: Verify Data Volume Mount

**Objective**: Verify read-only access to data volume

In Jupyter Lab, create a new notebook and run:

```python
from pathlib import Path

# Check data paths exist
DB_PATH = Path("/data/processed/databases/phage_database_optimized.duckdb")
PHAGE_FASTA = Path("/data/processed/sequences/all_phages.fasta")

print(f"Database exists: {DB_PATH.exists()}")
print(f"Phage FASTA exists: {PHAGE_FASTA.exists()}")

# Try to write (should fail)
try:
    test_file = Path("/data/test_write.txt")
    test_file.write_text("test")
    print("❌ FAIL: Should not be able to write to /data")
except Exception as e:
    print(f"✅ PASS: Cannot write to /data (expected): {type(e).__name__}")
```

**Expected Result**:
- Database and FASTA files exist (if pipeline has run)
- Write operation fails with `PermissionError` or `OSError`

**Success Criteria**:
- Read operations succeed
- Write operations fail (proving read-only mount)

#### Test 2.2: Database Connection

**Objective**: Test read-only database connection

```python
import duckdb

DB_PATH = "/data/processed/databases/phage_database_optimized.duckdb"

# Test read-only connection
try:
    conn = duckdb.connect(DB_PATH, read_only=True)
    tables = conn.execute("SHOW TABLES").fetchdf()
    print(f"✅ Connected! Found {len(tables)} tables")
    print(tables)
    conn.close()
except Exception as e:
    print(f"❌ FAIL: {e}")
```

**Expected Result** (if pipeline has run):
- Connection succeeds
- Tables listed (fact_phages, fact_proteins, etc.)

**Expected Result** (if pipeline hasn't run):
- FileNotFoundError (expected)

**Success Criteria**:
- No database lock errors
- Read-only flag accepted
- Can query tables if database exists

#### Test 2.3: SequenceRetriever Initialization

**Objective**: Test sequence retrieval setup

```python
from pbi import SequenceRetriever

try:
    retriever = SequenceRetriever(
        db_path="/data/processed/databases/phage_database_optimized.duckdb",
        phage_fasta_path="/data/processed/sequences/all_phages.fasta",
        protein_fasta_path="/data/processed/sequences/all_proteins.fasta",
        preload=True
    )
    print(f"✅ SequenceRetriever initialized")
    print(f"   Has host data: {retriever.has_host_data()}")
except FileNotFoundError as e:
    print(f"⚠️  Data files not found (run pipeline first): {e}")
except Exception as e:
    print(f"❌ FAIL: {e}")
```

**Expected Result**:
- Initialization succeeds if files exist
- FASTA indexes load
- No errors

**Success Criteria**:
- No exceptions if data exists
- Graceful error if data doesn't exist

#### Test 2.4: Example Notebook

**Objective**: Verify example notebook runs

1. Open `notebooks/analysis_direct_access_guide.ipynb`
2. Run first 5 cells (setup, imports, path verification)

**Expected Result**:
- All imports succeed
- Paths exist (if pipeline has run)
- No errors in setup cells

**Success Criteria**:
- Kernel doesn't crash
- No import errors
- Clear error messages if data doesn't exist

### Phase 3: Integration Tests

#### Test 3.1: Full Workflow (Requires Pipeline Data)

**Prerequisite**: Pipeline must have run successfully

**Steps**:
1. Run full `analysis_direct_access_guide.ipynb` notebook
2. Verify all sections execute:
   - Setup ✓
   - Basic queries ✓
   - Sequence retrieval ✓
   - Batch processing ✓
   - Data export ✓
   - E. coli example ✓

**Expected Result**:
- All cells execute without errors
- Exports created in `/workspace/exports/`
- Plots generated successfully

**Success Criteria**:
- No kernel crashes
- All example queries return results
- Export files created
- Visualizations display correctly

#### Test 3.2: Performance Benchmark

**Objective**: Measure actual performance

In notebook, run:

```python
import time
import duckdb

DB_PATH = "/data/processed/databases/phage_database_optimized.duckdb"
conn = duckdb.connect(DB_PATH, read_only=True)

# Benchmark query
query = "SELECT * FROM fact_phages LIMIT 1000"

start = time.time()
df = conn.execute(query).fetchdf()
elapsed = time.time() - start

print(f"Query time: {elapsed*1000:.2f} ms")
print(f"Records retrieved: {len(df)}")
print(f"Records/second: {len(df)/elapsed:.0f}")

conn.close()
```

**Expected Result**:
- Query completes in <100 ms for 1000 records
- No database lock errors
- Results correct

**Success Criteria**:
- Performance is acceptable (<1 second for 1000 records)
- No errors or warnings

### Phase 4: Security Tests

#### Test 4.1: Network Exposure

**Objective**: Verify Jupyter is accessible only locally

```bash
# From same machine
curl http://localhost:8888/api

# Expected: HTTP 200 (Jupyter API responds)
```

**From different machine** (if applicable):
```bash
curl http://<server-ip>:8888/api

# Expected: Connection refused or timeout (not exposed)
```

**Success Criteria**:
- Accessible from localhost
- Not accessible from outside (unless Docker host is configured otherwise)

#### Test 4.2: Read-Only Volume

**Objective**: Verify cannot modify data

In Jupyter notebook:
```python
from pathlib import Path

# Try to modify database
try:
    Path("/data/processed/databases/test.db").touch()
    print("❌ FAIL: Should not be able to create files")
except Exception:
    print("✅ PASS: Cannot create files in /data")

# Try to modify FASTA
try:
    with open("/data/processed/sequences/all_phages.fasta", "a") as f:
        f.write("test")
    print("❌ FAIL: Should not be able to modify FASTA")
except Exception:
    print("✅ PASS: Cannot modify FASTA files")
```

**Expected Result**:
- All write operations fail
- Read operations succeed

**Success Criteria**:
- Read-only mount enforced
- No data can be modified

#### Test 4.3: Authentication Status

**Objective**: Verify Jupyter auth is disabled (expected for local dev)

```bash
curl http://localhost:8888/api | grep -i token
```

**Expected Result**:
- No token required (for local development)

**Success Criteria**:
- Matches documented behavior
- Security warning in documentation exists

### Phase 5: Resource Tests

#### Test 5.1: Memory Usage

**Objective**: Verify reasonable memory consumption

```bash
# Check container memory
docker stats pbi-analysis --no-stream
```

**Expected Result**:
- Base memory: ~500 MB - 1 GB (Jupyter + dependencies)
- Memory stable (not growing)

**Success Criteria**:
- Memory usage within reasonable bounds
- No memory leaks over time

#### Test 5.2: Batch Processing

**Objective**: Test memory-efficient batch processing

In notebook:
```python
import duckdb

conn = duckdb.connect("/data/processed/databases/phage_database_optimized.duckdb", 
                      read_only=True)

BATCH_SIZE = 1000
offset = 0
batch_count = 0

while batch_count < 5:  # Test 5 batches
    batch = conn.execute(
        f"SELECT * FROM fact_phages LIMIT {BATCH_SIZE} OFFSET {offset}"
    ).fetchdf()
    
    if len(batch) == 0:
        break
    
    print(f"Batch {batch_count}: {len(batch)} records")
    offset += BATCH_SIZE
    batch_count += 1

conn.close()
```

**Expected Result**:
- Processes batches without errors
- Memory stays constant (batch size controlled)

**Success Criteria**:
- No out-of-memory errors
- Batch processing works correctly

### Phase 6: Documentation Tests

#### Test 6.1: Documentation Accuracy

**Objective**: Verify documentation matches actual behavior

Checklist:
- [ ] Paths in docs match actual container paths
- [ ] Commands work as documented
- [ ] Examples are executable
- [ ] Troubleshooting guide is accurate
- [ ] Links work (mkdocs navigation)

#### Test 6.2: Build Documentation

**Objective**: Verify MkDocs builds correctly

```bash
cd /path/to/PBI
pip install mkdocs-material
mkdocs build
```

**Expected Result**:
- Builds without errors
- Analysis guide appears in navigation
- All links work

**Success Criteria**:
- Exit code 0
- No broken links
- Documentation site renders correctly

## Clean Up After Testing

```bash
# Stop analysis service
docker compose stop analysis

# Remove container (optional)
docker compose rm -f analysis

# Remove image (optional)
docker rmi pbi-analysis

# Remove test files
rm -rf notebooks/exports/
rm -rf notebooks/.cache/
```

## Test Matrix

| Test | Without Pipeline | With Pipeline | Expected Result |
|------|------------------|---------------|-----------------|
| Build | ✓ | ✓ | Success |
| Startup | ✓ | ✓ | Success |
| Jupyter Access | ✓ | ✓ | Success |
| DB Connection | Graceful error | Success | As expected |
| Sequence Retrieval | Graceful error | Success | As expected |
| Example Notebook | Partial (setup) | Full | As expected |
| Data Export | N/A | Success | As expected |

## Troubleshooting Tests

### If Build Fails

1. Check Docker version: `docker --version`
2. Check available disk space: `df -h`
3. Try clean build: `docker compose build --no-cache analysis`
4. Check logs for specific errors

### If Jupyter Not Accessible

1. Check container status: `docker ps | grep pbi-analysis`
2. Check logs: `docker logs pbi-analysis`
3. Verify port mapping: `docker port pbi-analysis`
4. Try restart: `docker compose restart analysis`

### If Database Connection Fails

1. Verify pipeline has run: `docker run --rm -v pbi-data:/data alpine ls -lh /data/processed/databases/`
2. Check file permissions
3. Verify read-only flag: `read_only=True`

## Success Criteria Summary

**Minimum for Approval**:
- [x] Dockerfile builds successfully
- [x] Container starts and runs
- [x] Jupyter Lab accessible at localhost:8888
- [x] Read-only mount works
- [x] Documentation complete and accurate
- [x] Code review issues addressed
- [x] Security warnings present

**Optional (Requires Pipeline Data)**:
- [ ] Database queries work
- [ ] Sequence retrieval works
- [ ] Full notebook executes
- [ ] Performance benchmarks pass

## Reporting Issues

If any test fails:
1. Document the exact error message
2. Include relevant logs: `docker logs pbi-analysis`
3. Note your environment (OS, Docker version)
4. List steps to reproduce
5. Open GitHub issue with details
