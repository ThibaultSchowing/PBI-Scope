#!/usr/bin/env python

import gzip
import json
import logging
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path
from typing import Dict, Optional

logging.basicConfig(level=logging.INFO)

REPO_ROOT = Path(__file__).resolve().parents[3]
SRC_PATH = REPO_ROOT / "src"
SCRIPTS_SEQUENCES_PATH = REPO_ROOT / "workflow" / "scripts" / "sequences"

for _p in (str(SRC_PATH), str(SCRIPTS_SEQUENCES_PATH)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from pbi.private_data import prepare_private_sequence_artifacts  # noqa: E402


def _download_host_genome_by_name(
    host_id: str,
    host_name: str,
    output_dir: Path,
    ncbi_email: str,
    ncbi_api_key: Optional[str] = None,
) -> Optional[Path]:
    """Resolve *host_name* via NCBI and download the best genomic FASTA.

    Returns the path to the decompressed FASTA file written as
    ``output_dir/{host_id}.fna``, or ``None`` when resolution or download fails.

    Reuses the existing :class:`assembly_resolver.AssemblyResolver` so the
    same NCBI resolution logic is applied as for the main PhageScope pipeline.
    """
    try:
        from assembly_resolver import AssemblyResolver  # noqa: PLC0415 — runtime import
    except ImportError:
        logging.warning(
            "⚠️  Could not import assembly_resolver — NCBI host fallback skipped for %s (%s)",
            host_id,
            host_name,
        )
        return None

    output_dir.mkdir(parents=True, exist_ok=True)
    dest = output_dir / f"{host_id}.fna"
    if dest.exists() and dest.stat().st_size > 0:
        logging.info("   ✓ %s already present, reusing %s", host_id, dest.name)
        return dest

    logging.warning(
        "⚠️  host.fasta missing for %s (%s) — attempting NCBI retrieval",
        host_id,
        host_name,
    )

    resolver = AssemblyResolver(email=ncbi_email, api_key=ncbi_api_key)
    try:
        assemblies = resolver.resolve_with_fallback(host_name, prefer_refseq=True, max_results=1)
    except Exception as exc:
        logging.warning("⚠️  NCBI resolution failed for '%s': %s", host_name, exc)
        return None

    if not assemblies:
        logging.warning("⚠️  No assembly found for host '%s' (%s)", host_name, host_id)
        return None

    best = max(assemblies, key=lambda a: a.get_quality_score())
    ftp_path = best.ftp_path
    if not ftp_path:
        logging.warning(
            "⚠️  Assembly %s for '%s' has no FTP path", best.assembly_accession, host_name
        )
        return None

    base_name = ftp_path.rstrip("/").split("/")[-1]
    gz_url = f"{ftp_path}/{base_name}_genomic.fna.gz"
    tmp_gz = dest.with_suffix(".fna.gz.tmp")

    try:
        logging.info(
            "   Downloading %s for %s (%s)…",
            best.assembly_accession,
            host_id,
            host_name,
        )
        time.sleep(0.34)
        urllib.request.urlretrieve(gz_url, tmp_gz)
        with gzip.open(tmp_gz, "rt", encoding="utf-8") as gz_in, dest.open("w", encoding="utf-8") as out:
            out.write(gz_in.read())
        tmp_gz.unlink(missing_ok=True)
        logging.info(
            "   ✅ Downloaded host genome for %s → %s (%.1f KB)",
            host_id,
            dest.name,
            dest.stat().st_size / 1024,
        )
        return dest
    except Exception as exc:
        logging.warning("⚠️  Download failed for '%s' (%s): %s", host_name, host_id, exc)
        for _tmp in (tmp_gz, dest):
            if _tmp.exists():
                _tmp.unlink(missing_ok=True)
        return None


def main():
    manifest_path = Path(snakemake.input.manifest)  # noqa: F821
    private_phage_fasta = Path(snakemake.output.private_phages)  # noqa: F821
    private_host_mapping = Path(snakemake.output.private_host_mapping)  # noqa: F821
    private_host_dir = Path(snakemake.params.private_host_dir)  # noqa: F821

    ncbi_email = snakemake.config.get("ncbi_email", "phage.pipeline@example.com")  # noqa: F821
    ncbi_api_key: Optional[str] = snakemake.config.get("ncbi_api_key") or None  # noqa: F821

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
        if key != "missing_host_names":
            logging.info("   %s: %s", key, value)

    missing_host_names: Dict[str, str] = stats.get("missing_host_names", {})
    if missing_host_names:
        logging.warning(
            "⚠️  %d private host(s) have no host.fasta — falling back to NCBI retrieval",
            len(missing_host_names),
        )
        # Load existing mapping to avoid overwriting already-downloaded hosts
        with private_host_mapping.open("r", encoding="utf-8") as handle:
            host_mapping: Dict[str, str] = json.load(handle)

        downloaded_count = 0
        failed_count = 0
        for host_id, host_name in missing_host_names.items():
            if host_id in host_mapping:
                # Already resolved by a different source that provided host.fasta
                continue
            genome_path = _download_host_genome_by_name(
                host_id=host_id,
                host_name=host_name,
                output_dir=private_host_dir,
                ncbi_email=ncbi_email,
                ncbi_api_key=ncbi_api_key,
            )
            if genome_path is not None:
                host_mapping[host_id] = str(genome_path)
                downloaded_count += 1
            else:
                failed_count += 1

        # Persist updated mapping
        private_host_mapping.write_text(
            json.dumps(dict(sorted(host_mapping.items())), indent=2),
            encoding="utf-8",
        )
        logging.info(
            "NCBI host fallback: %d downloaded, %d failed",
            downloaded_count,
            failed_count,
        )


if __name__ == "__main__":
    main()

