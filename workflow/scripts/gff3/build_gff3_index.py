#!/usr/bin/env python3
"""
Build a JSON index mapping phage_id -> file location for fast GFF3 retrieval.

Called by Snakemake rule build_gff3_index.
Parses each GFF3 file, extracts sequence header lines containing seqhdr="Phage_ID",
and records byte offsets for each phage block.
"""

import json
import os
import re
import sys


def build_index(gff3_files):
    """
    Parse GFF3 files and build an index mapping phage_id to byte offsets.

    The index structure:
    {
        "phage_id": {
            "source_db": "PhagesDB",
            "file_path": "/data/processed/gff3/PhagesDB.gff3",
            "byte_offset": 1234,
            "byte_length": 5678
        }
    }
    """
    index = {}
    header_pattern = re.compile(r'seqhdr="([^"]+)"')
    duplicates = []

    for gff3_path in gff3_files:
        source_db = os.path.splitext(os.path.basename(gff3_path))[0]
        print(f"Processing {gff3_path} (source_db={source_db})")

        if not os.path.exists(gff3_path) or os.path.getsize(gff3_path) == 0:
            print(f"  Skipping empty or missing file: {gff3_path}")
            continue

        current_phage_id = None
        current_start = 0
        phage_count = 0

        with open(gff3_path, "r", encoding="utf-8") as f:
            while True:
                line_start = f.tell()
                line = f.readline()

                if not line:
                    # End of file - save last phage if exists
                    if current_phage_id:
                        byte_length = line_start - current_start
                        index[current_phage_id] = {
                            "source_db": source_db,
                            "file_path": gff3_path,
                            "byte_offset": current_start,
                            "byte_length": byte_length,
                        }
                        phage_count += 1
                    break

                # Check for sequence header line
                if line.startswith("# Sequence Data:"):
                    match = header_pattern.search(line)
                    if match:
                        # Save previous phage if exists
                        if current_phage_id:
                            byte_length = line_start - current_start
                            index[current_phage_id] = {
                                "source_db": source_db,
                                "file_path": gff3_path,
                                "byte_offset": current_start,
                                "byte_length": byte_length,
                            }
                            phage_count += 1

                        # Start new phage block
                        current_phage_id = match.group(1)
                        current_start = line_start

        print(f"  Indexed {phage_count} phages from {source_db}")

    # Check for duplicate phage IDs across sources
    seen = {}
    for phage_id, entry in index.items():
        if phage_id in seen:
            duplicates.append(
                f"  WARNING: Duplicate phage_id '{phage_id}' in "
                f"'{entry['source_db']}' and '{seen[phage_id]['source_db']}'"
            )
        seen[phage_id] = entry

    if duplicates:
        print(f"\nWARNING: Found {len(duplicates)} duplicate phage IDs:")
        for msg in duplicates[:10]:
            print(msg)
        if len(duplicates) > 10:
            print(f"  ... and {len(duplicates) - 10} more")

    return index


def main():
    # Snakemake inputs and outputs
    gff3_files = list(snakemake.input)
    output_index = str(snakemake.output.index)

    print(f"Building GFF3 index from {len(gff3_files)} files...")

    index = build_index(gff3_files)

    os.makedirs(os.path.dirname(output_index), exist_ok=True)
    with open(output_index, "w", encoding="utf-8") as f:
        json.dump(index, f, indent=2)

    print(f"\nBuilt index with {len(index)} phage entries")
    print(f"Index written to: {output_index}")


if __name__ == "__main__":
    main()
