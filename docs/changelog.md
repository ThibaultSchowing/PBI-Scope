# Changelog

All notable changes to this project are documented here.

## [Unreleased]

### Added

- Optional `n8n` example container with BLAST-screening and API-watchdog workflows (`n8n/workflows/`); the API is n8n-compatible for custom workflows. See [n8n Workflows](guides/n8n-integration.md).
- API key authentication (`X-API-Key`, `PBI_API_KEY`) and async BLAST jobs (`POST /blast/jobs`).

### Changed

- Documentation: n8n is presented as an optional example separate from the core services; added the combined `ssh -L 8888:localhost:8886 -L 8000:localhost:8000 -L 5678:localhost:5678` tunnel command; fixed the analysis port in the Docker guide (8886 → 8888).

## [0.6.0] - 2026-09-09

### Added

- BLAST capacity: the pipeline now builds five BLAST databases (`phages`, `proteins`, `hosts`, `private`, `combined`) via `workflow/rules/blast.smk`, with private-vs-public duplicate detection.
- `BlastSearcher` class in the `pbi` package, `pbi blast-search` / `pbi blast-diagnose` CLI commands, and REST API endpoints (`POST /blast/search`, `GET /blast/databases`, `GET /blast/status`).
- `09_blast_search.ipynb` notebook demonstrating sequence similarity search.
- Restored `private_data/test_private/` synthetic example dataset so notebooks can demonstrate private-data ingestion end to end.

### Changed

- Documentation refreshed for v0.6.0: BLAST pipeline stage and outputs, first-run timing warnings (downloading, host resolution, file merging, BLAST database building), PBI-Scope naming consistency, and reference-page index.

## [0.5.0] - 2026-08-24

### Added

- GFF3 gene annotation retrieval: `GFF3Retriever` class, API endpoints, and `07_gff3_annotations.ipynb` notebook.
- Continuous integration pipeline with automated pipeline and `pbi` package tests (see [CI Tests](developer/ci-tests.md)).

## [0.4.0] - 2026-07-20

### Added

- Phage-only private data ingestion: the `hosts/` directory is now optional for private sources. When all `Host_ID` and `Host_name` values are `unknown`, the source is valid without host FASTA files.
- Detailed VS Code remote connection guide (SSH + Dev Containers) in [Analysis Container Guide](guides/analysis-guide.md).
- Security warning section in analysis-guide.md, installation.md, and docker-guide.md explaining the implications of `--ServerApp.disable_check_xsrf=True` and the broader lack of authentication.

### Changed

- Expanded `Dockerfile.analysis` CMD comment to explicitly document the security risks of disabling token auth, password auth, and XSRF protection, with guidance on hardening steps.
- Updated private data ingestion documentation with phage-only mode examples and updated directory structure requirements.

## [0.3.0] - 2026-04-20

### Changed

- Updated project naming consistency to **Phage Bacteria Interactions** across code/docs.
- Refreshed documentation structure and core pages for current infrastructure.
- Added one-read storytelling page describing end-to-end flow.
- Clarified private data ingestion behavior and mandatory host sequence requirements.
- Updated home/current-status sections with dedicated private-data status.
- Documented current API limitation (not supported for sequence-heavy retrieval).
- Added VS Code Dev Containers recommendation in analysis workflow docs.

## [0.2.0]

- Introduced private source ingestion and host mapping improvements.

## [0.1.0]

- Initial public release with pipeline, DuckDB integration, and API prototype.
