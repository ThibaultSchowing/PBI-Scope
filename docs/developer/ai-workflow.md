# AI Agent Workflow

## How to use this guide

This file is for AI assistants (OpenCode, Copilot, Claude, Codex, Cursor) and new contributors.
For architecture details, see `code-structure.md`. For CI, see `ci-tests.md`.

## Change matrix

| Change | Files to edit | Tests to add |
|--------|--------------|--------------|
| New PhageScope source | `config.yaml` (URLs), `phagescope.smk` | `test_fasta_ids_and_naming.py` |
| New metadata column | `workflow/schemas/*.yaml`, `create_duckdb.py` | `test_schema_contracts.py` |
| New pbi method | `src/pbi/sequence_retrieval.py` | `test_sequence_retrieval.py` |
| New API endpoint | `api/app.py` | `test_api.py` |
| New private data field | `src/pbi/private_data.py` | `test_private_data_ingestion.py` |

## Common tasks

### Adding a new PhageScope data source

1. Add URLs to `workflow/config/config.yaml` (`phage_fasta_urls`, `protein_fasta_urls`, `phage_metadata_urls`, `phage_GFF3_urls`)
2. No `.smk` changes needed — rules iterate over config keys
3. Add representative ID to `tests/test_fasta_ids_and_naming.py` `REPRESENTATIVE_PHAGE_IDS`
4. Run: `python -m pytest tests/test_fasta_ids_and_naming.py -v`

### Modifying schema contracts

1. Edit `workflow/schemas/<name>_merged.yaml`
2. Update change matrix in `docs/developer/code-structure.md`
3. Run: `python -m pytest tests/test_schema_contracts.py -v`

### Adding a pbi method

1. Add method to `src/pbi/sequence_retrieval.py` (or new module if splitting)
2. Add type hints + docstring
3. Add test to `tests/`
4. Run: `python -m pytest tests/ -v`

### Debugging pipeline failures

1. Check `/pipeline-logs/logs/*.log` for the failing rule
2. Check `/pipeline-logs/reports/*.html` for validation reports
3. Run single rule: `docker compose run --rm pipeline snakemake --cores 2 --use-conda -p <rule_name>`
4. Check host cache TTL: `/pipeline-logs/csv/host_token_resolution_cache.json` mtime

## Pitfalls

- **FASTA key extraction:** use `src/pbi/fasta_ids.py`, never reimplement
- **Phage_ID uniqueness:** `(Phage_ID, Source_DB)` is the key, not `Phage_ID` alone
- **Protein headers:** token1 is Protein_ID, except old Prodigal headers where `token1 == '#'`
- **Host resolution cache:** 120-day TTL, delete to force refresh
- **genome_stats:** 60s timeout per file, daemon threads prevent hangs
- **Private data:** use `PBI_DATA_DIR`/`PBI_PRIVATE_DATA_DIR` env vars, never hardcode paths

## Local development without Docker

```bash
python -m pip install -e ".[dev]"
export DATA_PATH=/path/to/processed
python -m pytest tests/ -v
```

For integration tests: `docker compose run --rm pipeline` (full pipeline on remote server).

## CI tests

CI tests run inside a Docker container against real pipeline output. The CI subset uses 2 of 26 sources (RefSeq + PhagesDB) to keep runtime under 40 minutes. See `docs/developer/ci-tests.md` for details.
