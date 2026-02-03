# Archive

> **Note**: This archive has been removed from the main documentation navigation to maintain clarity and focus. The content here represents historical documentation and development notes. For current information, please refer to the [main documentation](https://thibaultschowing.github.io/PBI/).

This directory contains older documentation files that have been replaced or reorganized. These files are kept for reference and will be reviewed for potential removal.

## Archived Documentation

### Previous Structure

The original documentation structure has been reorganized for clarity. The old files are preserved here:

- **[DESCRIPTION.md](DESCRIPTION.md)** - Original detailed project description (content merged into Database Overview and index)
- **[api-reference.md](api-reference.md)** - Original API reference (replaced by api/overview.md)
- **[changelog.md](changelog.md)** - Original changelog (to be updated and moved back)

### Archived Directories

- **[getting-started/](getting-started/)** - Original getting started guide (replaced by guides/)
  - `overview.md` - Project overview (content merged into index.md and database/overview.md)
  - `installation.md` - Installation guide (replaced by guides/installation.md)

- **[user-guide/](user-guide/)** - Original user guide (content merged into guides/ and reference/)
  - `data-preparation.md` - Data preparation steps
  - `running-pbi.md` - Running the pipeline (merged into guides/installation.md)
  - `analyzing-results.md` - Result analysis examples

- **[development/](development/)** - Development documentation
  - `fixes/` - Historical fix documentation (CSV parsing, OOM issues, etc.)
    - `CSV_COLUMN_CONSISTENCY_FIX.md`
    - `CSV_PARSING_FIX_SUMMARY.md`
    - `CSV_TOKENIZATION_FIX.md`
    - `OOM_FIX_SUMMARY.md`
    - `SOLUTION_SUMMARY.md`
    - `README.md`

## What Happened to This Content?

The documentation was reorganized to be more user-friendly:

1. **Welcoming Index**: New homepage with clear status and quick links
2. **Guides**: Separated Docker and local installation into clear, focused guides
3. **Database**: Comprehensive database documentation with schema details
4. **API**: Dedicated API documentation with work-in-progress status
5. **Reference**: Command cheatsheet for quick reference

## Review Status

⏳ **Pending Review** - These files will be reviewed to determine if:
- Content should be integrated into new documentation
- Files should be kept as historical reference
- Files can be safely deleted

## Notes

If you need information from these archived files, please check the new documentation structure first:
- [Home](../index.md)
- [Guides](../guides/overview.md)
- [Database](../database/overview.md)
- [API](../api/overview.md)
- [Command Reference](../reference/commands.md)
