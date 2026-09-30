#!/usr/bin/env python

import sys
from pathlib import Path

def merge_fasta_files(source_dir: Path, output_file: Path):
    source_dir = Path(source_dir)
    source_db = output_file.stem if output_file.stem else source_dir.name
    with output_file.open('w') as out_f:
        for fasta_file in sorted(source_dir.rglob("*.fa")) + sorted(source_dir.rglob("*.fasta")):
            if not fasta_file.is_file():
                continue
            phage = fasta_file.parent.name
            if not phage or any(c.isspace() for c in phage):
                raise ValueError(f"Invalid phage dir name contains whitespace: {phage!r}")
            with fasta_file.open('r') as in_f:
                for line in in_f:
                    if line.startswith('>'):
                        raw = line.rstrip('\n\r')
                        toks = raw[1:].strip().split()
                        if not toks:
                            continue
                        protein_id = toks[0]
                        if not protein_id or any(c.isspace() for c in protein_id):
                            raise ValueError(f"Invalid protein header: {raw!r}")
                        rest = " ".join(" ".join(toks[1:]).split())
                        # Canonical Variant B + Source: >Phage_ID Protein_ID Source_DB [rest]
                        if rest:
                            out_f.write(f">{phage} {protein_id} {source_db} {rest}\n")
                        else:
                            out_f.write(f">{phage} {protein_id} {source_db}\n")
                    else:
                        out_f.write(line)

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: merge_fastas.py <source_dir> <output_file>", file=sys.stderr)
        sys.exit(1)

    src_dir = Path(sys.argv[1])
    out_file = Path(sys.argv[2])
    merge_fasta_files(src_dir, out_file)
