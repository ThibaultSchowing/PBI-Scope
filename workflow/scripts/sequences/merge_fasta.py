#!/usr/bin/env python3
"""
Merge multiple per-source FASTA files into a single combined FASTA.

Used by the ``merge_phage_fasta`` and ``merge_protein_fasta`` Snakemake rules.
"""

import logging
import os
import sys
import time
from pathlib import Path


def _setup_logging(log_file: str, also_stderr: bool = True) -> None:
    """Route root-logger output to *log_file* and optionally stderr."""
    try:
        _common = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'common')
        if _common not in sys.path:
            sys.path.insert(0, _common)
        from logging_utils import setup_logging  # noqa: PLC0415
        setup_logging(log_file, also_stderr=also_stderr)
    except Exception:
        Path(log_file).parent.mkdir(parents=True, exist_ok=True)
        fmt = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
        root = logging.getLogger()
        root.handlers.clear()
        root.setLevel(logging.INFO)
        fh = logging.FileHandler(log_file)
        fh.setFormatter(fmt)
        root.addHandler(fh)
        if also_stderr:
            sh = logging.StreamHandler(sys.stderr)
            sh.setFormatter(fmt)
            root.addHandler(sh)


def merge_fasta_files(
    input_files: list,
    output_file: str,
    sequence_type: str = "FASTA",
) -> None:
    """Merge *input_files* into *output_file*, skipping empty/missing files.

    Args:
        input_files:   Ordered list of input FASTA paths.
        output_file:   Destination path for the merged FASTA.
        sequence_type: Human-readable label used in log messages (e.g.
                       ``"phage"`` or ``"protein"``).

    Raises:
        ValueError: if no valid (non-empty) input files are found.
    """
    t0 = time.time()
    n_total = len(input_files)

    logging.info("=" * 70)
    logging.info(f"🚀 Starting {sequence_type} FASTA merge")
    logging.info(f"   Expected inputs : {n_total}")
    logging.info(f"   Output          : {output_file}")

    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    valid_files = []
    skipped_files = []
    for fasta_file in input_files:
        if os.path.exists(fasta_file) and os.path.getsize(fasta_file) > 0:
            valid_files.append(fasta_file)
        else:
            # Delete stale empty files from previous failed runs so that
            # Snakemake re-runs the download/extract chain on next execution.
            if os.path.exists(fasta_file) and os.path.getsize(fasta_file) == 0:
                os.remove(fasta_file)
                logging.warning(f"🗑️  Deleted stale empty file: {fasta_file}")
            skipped_files.append(fasta_file)
            logging.warning(f"⚠️  Skipping empty or missing file: {fasta_file}")

    if not valid_files:
        raise ValueError(f"❌ No valid {sequence_type} FASTA files found for merging!")

    logging.info(f"   Valid inputs    : {len(valid_files)}/{n_total}")
    if skipped_files:
        logging.warning(f"   Skipped         : {len(skipped_files)} file(s)")

    with open(output_file, 'w') as outfile:
        for fasta_file in valid_files:
            with open(fasta_file, 'r') as infile:
                content = infile.read()
                if content.strip():
                    outfile.write(content)
                    if not content.endswith('\n'):
                        outfile.write('\n')

    output_size = os.path.getsize(output_file)
    elapsed = time.time() - t0

    logging.info(f"✅ Merged {len(valid_files)}/{n_total} {sequence_type} FASTA files")
    logging.info(f"   Output size     : {output_size:,} bytes")
    logging.info(f"   Elapsed         : {elapsed:.1f}s")
    logging.info("=" * 70)


if __name__ == "__main__":
    # Snakemake integration
    _setup_logging(snakemake.log[0])  # noqa: F821

    # ``snakemake.params.sequence_type`` is optional; default to "FASTA"
    seq_type = getattr(snakemake.params, "sequence_type", "FASTA")  # noqa: F821

    merge_fasta_files(
        input_files=list(snakemake.input),  # noqa: F821
        output_file=snakemake.output[0],    # noqa: F821
        sequence_type=seq_type,
    )
