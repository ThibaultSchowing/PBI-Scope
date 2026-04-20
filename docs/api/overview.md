# API Status

!!! warning "Limited support"
    The REST API is currently **not supported for sequence-heavy retrieval**.

    It is kept for lightweight metadata/database exploration only, and will be redesigned later.

## Current position

- Basic endpoints exist (`/health`, `/stats`, `/query`)
- Sequence endpoints are not recommended for large workloads
- Main supported interface remains the analysis container + `pbi` package

## Version

Current API version: `0.3.0`

## Recommendation

For practical analysis and ML workflows, use:

1. [Installation guide](../guides/installation.md)
2. [Analysis container](../guides/analysis-guide.md)
3. [PBI package guide](../guides/pbi-package.md)
