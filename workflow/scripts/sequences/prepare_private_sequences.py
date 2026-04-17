#!/usr/bin/env python

import json
import logging
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO)

SNAKEMAKE_SCRIPTDIR = Path(getattr(snakemake, "scriptdir", Path(__file__).resolve().parent)).resolve()  # noqa: F821
REPO_ROOT = SNAKEMAKE_SCRIPTDIR.parents[2]
SRC_PATH = REPO_ROOT / "src"
SCRIPTS_SEQUENCES_PATH = REPO_ROOT / "workflow" / "scripts" / "sequences"

for module_path in (SRC_PATH, SCRIPTS_SEQUENCES_PATH):
    module_path_str = str(module_path)
    if module_path_str not in sys.path:
        sys.path.insert(0, module_path_str)

from pbi.private_data import prepare_private_sequence_artifacts  # noqa: E402


def main():
    manifest_path = Path(snakemake.input.manifest)  # noqa: F821
    private_phage_mapping = Path(snakemake.output.private_phage_mapping)  # noqa: F821
    private_host_mapping = Path(snakemake.output.private_host_mapping)  # noqa: F821
    private_host_dir = Path(snakemake.params.private_host_dir)  # noqa: F821
    private_phage_dir = Path(snakemake.params.private_phage_dir)  # noqa: F821

    if not manifest_path.exists():
        manifest = {"sources": []}
    else:
        with manifest_path.open("r", encoding="utf-8") as handle:
            manifest = json.load(handle) or {"sources": []}

    stats = prepare_private_sequence_artifacts(
        manifest=manifest,
        private_phage_dir=private_phage_dir,
        private_phage_mapping_path=private_phage_mapping,
        private_host_dir=private_host_dir,
        private_host_mapping_path=private_host_mapping,
    )

    logging.info("✅ Prepared private sequence artifacts")
    for key, value in stats.items():
        logging.info("   %s: %s", key, value)


if __name__ == "__main__":
    main()
