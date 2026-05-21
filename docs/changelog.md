# Changelog

All notable changes to this project are documented here.

## [Unreleased]

### Added

- Detailed VS Code remote connection guide (SSH + Dev Containers) in [Analysis Container Guide](guides/analysis-guide.md).
- Security warning section in analysis-guide.md, installation.md, and docker-guide.md explaining the implications of `--ServerApp.disable_check_xsrf=True` and the broader lack of authentication.

### Changed

- Expanded `Dockerfile.analysis` CMD comment to explicitly document the security risks of disabling token auth, password auth, and XSRF protection, with guidance on hardening steps.

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
