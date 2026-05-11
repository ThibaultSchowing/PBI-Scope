#!/usr/bin/env python3

import csv
import hashlib
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

logging.basicConfig(level=logging.INFO)
LOGGER = logging.getLogger(__name__)


def _to_utc_iso(ts: datetime | None = None) -> str:
    now = ts or datetime.now(timezone.utc)
    return now.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _normalize_source_db(source_key: str) -> str:
    if not source_key:
        return ""
    return source_key.split("_", 1)[0]


def _sha256_file(path: str) -> str:
    sha = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            sha.update(chunk)
    return sha.hexdigest()


def _read_tsv_header(path: str) -> list[str]:
    try:
        with open(path, "r", encoding="utf-8", newline="") as handle:
            reader = csv.reader(handle, delimiter="\t")
            header = next(reader, [])
            return [column.strip() for column in header if str(column).strip()]
    except Exception:
        return []


def _schema_fingerprint(columns: list[str]) -> str:
    payload = "|".join(columns).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:16] if columns else ""


def _load_previous_fingerprint(manifest_path: str, feature: str, source_key: str) -> str:
    if not manifest_path or not os.path.exists(manifest_path):
        return ""
    try:
        with open(manifest_path, "r", encoding="utf-8") as handle:
            records = json.load(handle) or []
        for record in reversed(records):
            if (
                record.get("feature") == feature
                and record.get("source_key") == source_key
                and record.get("status") == "success"
                and record.get("schema_fingerprint")
            ):
                return str(record.get("schema_fingerprint"))
    except Exception as exc:
        LOGGER.warning("Could not read previous manifest '%s': %s", manifest_path, exc)
    return ""


def _download(url: str, output_path: str) -> tuple[dict, int]:
    request = Request(url, headers={"User-Agent": "PBI-public-download/1.0"})
    with urlopen(request, timeout=120) as response:  # nosec B310 - trusted configured URLs
        body = response.read()
        headers = {
            "etag": response.headers.get("ETag"),
            "last_modified": response.headers.get("Last-Modified"),
            "content_type": response.headers.get("Content-Type"),
        }
    tmp_path = f"{output_path}.tmp"
    with open(tmp_path, "wb") as handle:
        handle.write(body)
    os.replace(tmp_path, output_path)
    return headers, len(body)


def main():
    config = snakemake.config
    provider_cfg = config.get("public_data_provider", {})
    provenance_cfg = config.get("public_data_provenance", {})

    output_tsv = str(snakemake.output.tsv)
    output_sidecar = str(snakemake.output.provenance_sidecar)
    feature = str(snakemake.wildcards.feature)
    source_key = str(snakemake.wildcards.source)
    source_url = str(snakemake.params.url)

    provider_release = str(provider_cfg.get("release", "") or "")
    provider_snapshot = str(provider_cfg.get("snapshot_date", "") or "")
    require_release_or_snapshot = bool(provenance_cfg.get("require_release_or_snapshot", False))

    if require_release_or_snapshot and not (provider_release or provider_snapshot):
        raise ValueError(
            "public_data_provenance.require_release_or_snapshot is enabled but neither "
            "public_data_provider.release nor public_data_provider.snapshot_date is set."
        )

    os.makedirs(os.path.dirname(output_tsv), exist_ok=True)

    retrieved_at = _to_utc_iso()
    status = "success"
    response_headers = {}
    detected_columns: list[str] = []
    schema_fingerprint = ""
    file_size = 0
    sha256 = ""
    error_message = ""

    try:
        response_headers, file_size = _download(source_url, output_tsv)
        detected_columns = _read_tsv_header(output_tsv) if output_tsv.endswith(".tsv") else []
        schema_fingerprint = _schema_fingerprint(detected_columns)
        if provenance_cfg.get("capture_checksums", True):
            sha256 = _sha256_file(output_tsv)
    except Exception as exc:
        status = "failed"
        error_message = str(exc)
        LOGGER.warning("Failed download for %s/%s from %s: %s", feature, source_key, source_url, exc)
        if not os.path.exists(output_tsv):
            Path(output_tsv).touch()

    previous_fingerprint = _load_previous_fingerprint(
        str(provenance_cfg.get("manifest_json_output", "") or ""),
        feature,
        source_key,
    )
    if schema_fingerprint and previous_fingerprint and schema_fingerprint != previous_fingerprint:
        message = (
            f"Schema fingerprint changed for {feature}/{source_key}: "
            f"{previous_fingerprint} -> {schema_fingerprint}"
        )
        if provenance_cfg.get("fail_on_schema_mismatch", False):
            raise ValueError(message)
        LOGGER.warning(message)

    record = {
        "provider_name": provider_cfg.get("name", "PhageScope"),
        "provider_release": provider_release,
        "provider_snapshot_date": provider_snapshot,
        "provider_schema_profile": provider_cfg.get("schema_profile", ""),
        "feature": feature,
        "source_key": source_key,
        "normalized_source_db": _normalize_source_db(source_key),
        "source_url": source_url,
        "local_path": output_tsv,
        "retrieved_at": retrieved_at,
        "file_size": file_size,
        "sha256": sha256,
        "etag": response_headers.get("etag") if provenance_cfg.get("capture_response_headers", True) else "",
        "last_modified": response_headers.get("last_modified")
        if provenance_cfg.get("capture_response_headers", True)
        else "",
        "detected_tabular_columns": detected_columns,
        "schema_fingerprint": schema_fingerprint,
        "status": status,
        "error_message": error_message,
    }

    os.makedirs(os.path.dirname(output_sidecar), exist_ok=True)
    with open(output_sidecar, "w", encoding="utf-8") as handle:
        json.dump(record, handle, indent=2)
        handle.write("\n")


if __name__ == "__main__":
    main()
