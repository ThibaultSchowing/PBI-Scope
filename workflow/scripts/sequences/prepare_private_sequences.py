#!/usr/bin/env python

import json
import logging
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO)

REPO_ROOT = Path(__file__).resolve().parents[3]
SRC_PATH = REPO_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from pbi.private_data import prepare_private_sequence_artifacts  # noqa: E402


def main():
    manifest_path = Path(snakemake.input.manifest)  # noqa: F821
    private_phage_fasta = Path(snakemake.output.private_phages)  # noqa: F821
    private_host_mapping = Path(snakemake.output.private_host_mapping)  # noqa: F821
    private_host_dir = Path(snakemake.params.private_host_dir)  # noqa: F821

    if not manifest_path.exists():
        manifest = {"sources": []}
    else:
        with manifest_path.open("r", encoding="utf-8") as handle:
            manifest = json.load(handle) or {"sources": []}

    stats = prepare_private_sequence_artifacts(
        manifest=manifest,
        private_phage_fasta_path=private_phage_fasta,
        private_host_dir=private_host_dir,
        private_host_mapping_path=private_host_mapping,
    )

    logging.info("✅ Prepared private sequence artifacts")
    for key, value in stats.items():
        logging.info("   %s: %s", key, value)


if __name__ == "__main__":
    main()

