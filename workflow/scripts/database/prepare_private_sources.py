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


def _normalize_roots(raw_roots):
    if raw_roots is None:
        return []
    if isinstance(raw_roots, str):
        return [r.strip() for r in raw_roots.split(",") if r.strip()]
    if isinstance(raw_roots, (list, tuple)):
        roots = []
        for item in raw_roots:
            if isinstance(item, str):
                roots.extend([r.strip() for r in item.split(",") if r.strip()])
        return roots
    return []


def main():
    output_path = Path(snakemake.output[0])
    enabled = bool(snakemake.config.get("private_ingestion_enabled", False))
    roots = _normalize_roots(snakemake.config.get("private_data_roots", []))

    if not enabled:
        manifest = {
            "roots": roots,
            "sources_found": 0,
            "sources_valid": 0,
            "sources_invalid": 0,
            "sources": [],
            "enabled": False,
        }
        write_private_manifest(manifest, output_path)
        logging.info("Private ingestion disabled; wrote empty manifest")
        return

    manifest = build_private_manifest(roots)
    manifest["enabled"] = True
    write_private_manifest(manifest, output_path)
    logging.info(
        "Prepared private manifest with %d sources (%d valid, %d invalid)",
        manifest["sources_found"],
        manifest["sources_valid"],
        manifest["sources_invalid"],
    )


if __name__ == "__main__":
    main()
