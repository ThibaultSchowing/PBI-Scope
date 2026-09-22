"""Snakemake script for merge_protein_fasta_by_source — always normalizes headers.

Canonical Variant B + Source: >Phage_ID Protein_ID Source_DB [rest]
"""

import importlib.util
from pathlib import Path
import sys

_spec = importlib.util.spec_from_file_location(
    "merge_protein_fasta", Path(__file__).with_name("merge_protein_fasta.py")
)
_mod = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(_mod)  # type: ignore[union-attr]
merge_fasta_files = _mod.merge_fasta_files

source_dir = Path(snakemake.input.source_dir)  # noqa: F821
output_fasta = Path(snakemake.output.merged_fasta)  # noqa: F821

output_fasta.parent.mkdir(parents=True, exist_ok=True)

fasta_files = list(source_dir.rglob("*.fa")) + list(source_dir.rglob("*.fasta"))
fasta_files = [p for p in fasta_files if p.is_file()]

if not fasta_files:
    output_fasta.touch()
    print(f"WARNING: No FASTA files found in {source_dir} - created empty {output_fasta}", file=sys.stderr)
else:
    merge_fasta_files(source_dir, output_fasta)
