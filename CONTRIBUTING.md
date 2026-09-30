# Contributing to PBI-Scope

## Development setup

Pipeline execution is performed on a remote server. Development and unit testing are done on a local machine without Docker containers.

```bash
# Clone and enter
git clone https://github.com/ThibaultSchowing/PBI-Scope.git
cd PBI-Scope

# Install package in editable mode with dev dependencies
python -m pip install -e ".[dev]"

# Run tests (no Docker needed)
python -m pytest tests/ -v

# Run a single test file
python -m pytest tests/test_fasta_ids_and_naming.py -v
```

For pipeline execution on a remote server:

```bash
cp .env.example .env  # fill NCBI_EMAIL, UID, GID
docker compose build pipeline
docker compose run --rm pipeline
```

## Testing expectations

- **Unit tests:** No Docker, no network, <1s each. Use `tmp_path` fixtures.
- **Integration tests:** May use `tmp_path` fixtures, still no Docker.
- **CI smoke tests:** Run inside a Docker container against real pipeline output. See `docs/developer/ci-tests.md`.
- **CI subset:** 2 of 26 sources (RefSeq + PhagesDB) to keep runtime under 40 minutes.

## Pull request process

1. Fork/branch from `main`
2. Make changes + add tests
3. Run: `python -m pytest tests/ -v`
4. Run: `docker compose build pipeline` (verify image builds)
5. Open PR with filled template

## Code style

- Python: type hints on public API, docstrings on public classes
- Tests: pytest, one test file per module
- Commits: conventional commits (`feat:`, `fix:`, `docs:`, `test:`, `refactor:`)

## Schema contract changes

See `docs/developer/code-structure.md#schema-contracts` for the change matrix. When adding/removing/renaming columns, update the contract YAML first, then `create_duckdb.py`, then tests.

## AI assistants

If you're an AI assistant (Cursor, Copilot, Claude, Codex, etc.), start with `AGENTS.md` in the repo root. It contains the repository map, critical rules, and common pitfalls.
