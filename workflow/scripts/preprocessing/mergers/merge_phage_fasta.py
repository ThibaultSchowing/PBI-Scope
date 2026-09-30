#!/usr/bin/env python

import sys
from pathlib import Path


def merge_fasta_files(source_dir: Path, output_file: Path):
    source_dir = Path(source_dir)
    # Source_DB is the dataset name = output filename stem (e.g. RefSeq.fasta -> RefSeq)
    # This is more reliable than source_dir name for synthetic tests where source_dir is temp.
    source_db = output_file.stem if output_file.stem else source_dir.name

    with output_file.open('w') as out_f:
        for fasta_file in sorted(source_dir.rglob("*.fa")) + sorted(source_dir.rglob("*.fasta")):
            if not fasta_file.is_file():
                continue
            with fasta_file.open('r') as in_f:
                for line in in_f:
                    if line.startswith('>'):
                        raw = line.rstrip('\n\r')
                        # Canonical: >Phage_ID Source_DB [rest]
                        toks = raw[1:].strip().split()
                        if not toks:
                            continue
                        phage_id = toks[0]
                        if not phage_id or any(c.isspace() for c in phage_id):
                            raise ValueError(f"Invalid phage header contains whitespace: {raw!r}")
                        rest = " ".join(" ".join(toks[1:]).split())
                        if rest:
                            out_f.write(f">{phage_id} {source_db} {rest}\n")
                        else:
                            out_f.write(f">{phage_id} {source_db}\n")
                    else:
                        out_f.write(line)

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: merge_fastas.py <source_dir> <output_file>", file=sys.stderr)
        sys.exit(1)

    src_dir = Path(sys.argv[1])
    out_file = Path(sys.argv[2])
    merge_fasta_files(src_dir, out_file)
