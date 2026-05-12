#!/usr/bin/env python3

import csv
import json
import logging
import os
import shutil
import subprocess
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version

logging.basicConfig(level=logging.INFO)
LOGGER = logging.getLogger(__name__)


def _to_utc_iso(ts: datetime | None = None) -> str:
    now = ts or datetime.now(timezone.utc)
    return now.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _safe_git_commit() -> str:
    try:
        git_bin = shutil.which("git")
        if not git_bin:
            return ""
        result = subprocess.run(
            [git_bin, "rev-parse", "HEAD"],
            check=True,
            text=True,
            capture_output=True,
        )
        return result.stdout.strip()
    except Exception:
        return ""


def _safe_pbi_version() -> str:
    try:
        return version("pbi")
    except PackageNotFoundError:
        return ""


def _write_csv(path: str, rows: list[dict], fieldnames: list[str]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({name: row.get(name, "") for name in fieldnames})


def main():
    provenance_cfg = snakemake.config.get("public_data_provenance", {})
    provider_cfg = snakemake.config.get("public_data_provider", {})

    # Each input is a per-download sidecar JSON emitted by download_public_file.py.
    # We merge all sidecars into one run-level provenance manifest.
    records = []
    for sidecar_path in sorted(str(path) for path in snakemake.input):
        if not os.path.exists(sidecar_path) or os.path.getsize(sidecar_path) == 0:
            continue
        with open(sidecar_path, "r", encoding="utf-8") as handle:
            payload = json.load(handle) or {}
        records.append(payload)

    manifest_json = str(snakemake.output.manifest_json)
    manifest_csv = str(snakemake.output.manifest_csv)
    run_json = str(snakemake.output.pipeline_run_json)
    run_csv = str(snakemake.output.pipeline_run_csv)

    os.makedirs(os.path.dirname(manifest_json), exist_ok=True)
    with open(manifest_json, "w", encoding="utf-8") as handle:
        json.dump(records, handle, indent=2)
        handle.write("\n")

    # Flatten list-like fields for CSV storage while preserving JSON output fidelity.
    csv_rows = []
    for record in records:
        row = dict(record)
        row["detected_tabular_columns"] = json.dumps(record.get("detected_tabular_columns", []) or [])
        csv_rows.append(row)

    manifest_fieldnames = [
        "provider_name",
        "provider_release",
        "provider_snapshot_date",
        "provider_schema_profile",
        "feature",
        "source_key",
        "normalized_source_db",
        "source_url",
        "local_path",
        "retrieved_at",
        "file_size",
        "sha256",
        "etag",
        "last_modified",
        "detected_tabular_columns",
        "schema_fingerprint",
        "status",
        "error_message",
    ]
    _write_csv(manifest_csv, csv_rows, manifest_fieldnames)

    # Run-level pinning snapshot: ties the downloaded manifest to a specific
    # provider config and pipeline/package revision.
    run_record = {
        "pipeline_run_timestamp": _to_utc_iso(),
        "provider_name": provider_cfg.get("name", "PhageScope"),
        "provider_release": provider_cfg.get("release", ""),
        "provider_snapshot_date": provider_cfg.get("snapshot_date", ""),
        "provider_schema_profile": provider_cfg.get("schema_profile", ""),
        "provider_api_base_url": provider_cfg.get("api_base_url", ""),
        "provider_provenance_mode": provider_cfg.get("provenance_mode", ""),
        "pbi_version": _safe_pbi_version(),
        "git_commit": _safe_git_commit(),
        "download_records_count": len(records),
    }

    with open(run_json, "w", encoding="utf-8") as handle:
        json.dump(run_record, handle, indent=2)
        handle.write("\n")

    _write_csv(
        run_csv,
        [run_record],
        [
            "pipeline_run_timestamp",
            "provider_name",
            "provider_release",
            "provider_snapshot_date",
            "provider_schema_profile",
            "provider_api_base_url",
            "provider_provenance_mode",
            "pbi_version",
            "git_commit",
            "download_records_count",
        ],
    )
    LOGGER.info("Wrote public data provenance manifest with %d records", len(records))


if __name__ == "__main__":
    main()
