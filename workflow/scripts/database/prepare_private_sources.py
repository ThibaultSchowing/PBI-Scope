#!/usr/bin/env python

import logging
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO)

REPO_ROOT = Path(__file__).resolve().parents[3]
SRC_PATH = REPO_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from pbi.private_data import build_private_manifest, write_private_manifest  # noqa: E402


def main():
    output_path = Path(snakemake.output[0])

    # Single root directory — each immediate subdirectory is one private source_db.
    # An empty or missing root simply produces an empty manifest (no ingestion).
    raw_root = snakemake.config.get("private_data_root", "")
    root_path = Path(raw_root) if raw_root else None

    if not root_path or not root_path.is_dir():
        manifest = {
            "roots": [str(root_path)] if root_path else [],
            "sources_found": 0,
            "sources_valid": 0,
            "sources_invalid": 0,
            "sources": [],
        }
        write_private_manifest(manifest, output_path)
        logging.info(
            "Private data root '%s' is absent or empty; wrote empty manifest",
            root_path,
        )
        return

    manifest = build_private_manifest([str(root_path)])
    write_private_manifest(manifest, output_path)
    logging.info(
        "Prepared private manifest with %d sources (%d valid, %d invalid)",
        manifest["sources_found"],
        manifest["sources_valid"],
        manifest["sources_invalid"],
    )


if __name__ == "__main__":
    main()
