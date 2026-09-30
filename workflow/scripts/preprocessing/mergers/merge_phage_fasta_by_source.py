"""Snakemake script for merge_phage_fasta_by_source — always normalizes headers to canonical form.

Canonical: >Phage_ID Source_DB [rest]
This replaces the previous shell cp bypass which skipped normalization for single-file sources.
"""

import importlib.util
from pathlib import Path
import sys

# Load merge_fasta_files from sibling file without relying on sys.path
_spec = importlib.util.spec_from_file_location(
    "merge_phage_fasta", Path(__file__).with_name("merge_phage_fasta.py")
)
_mod = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(_mod)  # type: ignore[union-attr]
merge_fasta_files = _mod.merge_fasta_files

# Snakemake globals injected by Snakemake
source_dir = Path(snakemake.input.source_dir)  # noqa: F821
output_fasta = Path(snakemake.output.merged_fasta)  # noqa: F821
dataset = snakemake.wildcards.dataset  # noqa: F821
log_path = snakemake.log[0] if hasattr(snakemake, "log") and len(snakemake.log) else None  # noqa: F821

if log_path:
    Path(log_path).parent.mkdir(parents=True, exist_ok=True)

# Ensure output dir exists
output_fasta.parent.mkdir(parents=True, exist_ok=True)

# Check for fasta files
fasta_files = list(source_dir.rglob("*.fa")) + list(source_dir.rglob("*.fasta"))
fasta_files = [p for p in fasta_files if p.is_file()]

if not fasta_files:
    # Create empty file but warn (previous behavior)
    output_fasta.touch()
    msg = f"WARNING: No FASTA files found in {source_dir} - created empty {output_fasta}"
    print(msg, file=sys.stderr)
    if log_path:
        Path(log_path).write_text(msg)
else:
    # Always use canonical merge (even for single file)
    merge_fasta_files(source_dir, output_fasta)
    # Override source_db derived from output stem with wildcards.dataset to be explicit
    # Re-read and ensure Source_DB token is dataset (handles edge where output stem derived differently)
    # Our merge already uses source_dir.name as source_db, which equals dataset
    pass
