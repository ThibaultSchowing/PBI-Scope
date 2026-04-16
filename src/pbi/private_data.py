from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set

import duckdb
import pandas as pd


MANDATORY_COLUMNS = ["Phage_ID", "Host_ID", "Host_name", "Source_DB", "interaction"]
ALLOWED_INTERACTIONS = {"temperate", "virulent"}


@dataclass
class PrivateSourceValidation:
    source_dir: Path
    source_db: str
    errors: List[str]
    warnings: List[str]
    stats: Dict[str, int]
    metadata_df: Optional[pd.DataFrame] = None
    extra_columns: Optional[List[str]] = None

    @property
    def is_valid(self) -> bool:
        return len(self.errors) == 0


def _extract_fasta_identifier(header_line: str) -> str:
    header = header_line[1:].strip()
    return header.split()[0] if header else ""


def parse_fasta_ids(fasta_path: Path) -> tuple[Set[str], Set[str]]:
    ids: Set[str] = set()
    duplicates: Set[str] = set()

    with fasta_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.startswith(">"):
                continue
            seq_id = _extract_fasta_identifier(line)
            if not seq_id:
                continue
            if seq_id in ids:
                duplicates.add(seq_id)
            ids.add(seq_id)

    return ids, duplicates


def _required_files(source_dir: Path) -> Dict[str, Path]:
    return {
        "metadata.csv": source_dir / "metadata.csv",
        "phage.fasta": source_dir / "phage.fasta",
        "host.fasta": source_dir / "host.fasta",
    }


def validate_private_source(source_dir: Path, include_dataframe: bool = False) -> PrivateSourceValidation:
    source_dir = Path(source_dir)
    source_db = source_dir.name
    errors: List[str] = []
    warnings: List[str] = []
    stats: Dict[str, int] = {"rows": 0, "unique_phages": 0, "unique_hosts": 0, "extra_attributes": 0}

    required = _required_files(source_dir)
    missing = [name for name, path in required.items() if not path.exists()]
    if missing:
        errors.append(f"Missing required files: {', '.join(missing)}")
        return PrivateSourceValidation(source_dir, source_db, errors, warnings, stats)

    try:
        df = pd.read_csv(required["metadata.csv"], dtype=str, keep_default_na=False)
    except Exception as exc:
        errors.append(f"metadata.csv cannot be parsed: {exc}")
        return PrivateSourceValidation(source_dir, source_db, errors, warnings, stats)

    missing_columns = [col for col in MANDATORY_COLUMNS if col not in df.columns]
    if missing_columns:
        errors.append(f"metadata.csv missing required columns: {missing_columns}")
        return PrivateSourceValidation(source_dir, source_db, errors, warnings, stats)

    df = df.copy()
    for col in df.columns:
        df[col] = df[col].map(lambda x: x.strip() if isinstance(x, str) else x)

    stats["rows"] = len(df)
    if len(df) == 0:
        errors.append("metadata.csv is empty")

    for col in MANDATORY_COLUMNS:
        invalid_rows = df.index[df[col].astype(str).str.len() == 0].tolist()
        if invalid_rows:
            errors.append(
                f"metadata.csv column '{col}' has empty values at rows {[row + 2 for row in invalid_rows[:20]]}"
            )

    unique_sources = sorted(set(v for v in df["Source_DB"].astype(str).tolist() if v))
    if unique_sources != [source_db]:
        errors.append(
            f"Source_DB mismatch: expected only '{source_db}', found {unique_sources or ['<empty>']}"
        )

    normalized_interactions = df["interaction"].astype(str).str.lower()
    invalid_interaction_mask = ~normalized_interactions.isin(ALLOWED_INTERACTIONS)
    if invalid_interaction_mask.any():
        invalid_rows = (df.index[invalid_interaction_mask] + 2).tolist()
        invalid_values = sorted(set(df.loc[invalid_interaction_mask, "interaction"].tolist()))
        errors.append(
            "Invalid interaction values "
            f"{invalid_values}. Allowed values: {sorted(ALLOWED_INTERACTIONS)}. Rows: {invalid_rows[:20]}"
        )
    df["interaction"] = normalized_interactions

    phage_ids, phage_duplicates = parse_fasta_ids(required["phage.fasta"])
    host_ids, host_duplicates = parse_fasta_ids(required["host.fasta"])

    if phage_duplicates:
        errors.append(f"Duplicate FASTA identifiers in phage.fasta: {sorted(phage_duplicates)[:20]}")
    if host_duplicates:
        errors.append(f"Duplicate FASTA identifiers in host.fasta: {sorted(host_duplicates)[:20]}")

    csv_phage_ids = set(df["Phage_ID"].tolist())
    csv_host_ids = set(df["Host_ID"].tolist())

    missing_phages = sorted(csv_phage_ids - phage_ids)
    missing_hosts = sorted(csv_host_ids - host_ids)
    if missing_phages:
        errors.append(f"Phage_ID not found in phage.fasta: {missing_phages[:20]}")
    if missing_hosts:
        errors.append(f"Host_ID not found in host.fasta: {missing_hosts[:20]}")

    duplicated_rows = int(df.duplicated(subset=["Phage_ID", "Host_ID", "Source_DB"]).sum())
    if duplicated_rows:
        warnings.append(
            f"Found {duplicated_rows} duplicated (Phage_ID, Host_ID, Source_DB) rows; they will be deduplicated"
        )

    stats["unique_phages"] = int(df["Phage_ID"].nunique())
    stats["unique_hosts"] = int(df["Host_ID"].nunique())
    extra_columns = [col for col in df.columns if col not in MANDATORY_COLUMNS]
    stats["extra_attributes"] = int((df[extra_columns] != "").sum().sum()) if extra_columns else 0

    return PrivateSourceValidation(
        source_dir=source_dir,
        source_db=source_db,
        errors=errors,
        warnings=warnings,
        stats=stats,
        metadata_df=df if include_dataframe else None,
        extra_columns=extra_columns,
    )


def discover_private_sources(roots: Iterable[str]) -> List[Path]:
    discovered: List[Path] = []
    seen: Set[Path] = set()
    for root in roots:
        root_path = Path(root).expanduser()
        if not root_path.exists() or not root_path.is_dir():
            continue
        for child in sorted(root_path.iterdir()):
            if child.is_dir() and child not in seen:
                discovered.append(child)
                seen.add(child)
    return discovered


def validate_private_roots(roots: Iterable[str], include_dataframe: bool = False) -> Dict:
    sources = discover_private_sources(roots)
    duplicate_names = {}
    for src in sources:
        duplicate_names[src.name] = duplicate_names.get(src.name, 0) + 1

    validations: List[PrivateSourceValidation] = []
    for src in sources:
        result = validate_private_source(src, include_dataframe=include_dataframe)
        if duplicate_names[src.name] > 1:
            result.errors.append(
                f"Duplicate source directory name '{src.name}' across roots is not allowed"
            )
        validations.append(result)

    return {
        "roots": [str(Path(r).expanduser()) for r in roots],
        "sources_found": len(sources),
        "sources_valid": sum(1 for v in validations if v.is_valid),
        "sources_invalid": sum(1 for v in validations if not v.is_valid),
        "sources": validations,
    }


def _source_fingerprint(source_dir: Path) -> str:
    hasher = hashlib.sha256()
    for file_name in ("metadata.csv", "phage.fasta", "host.fasta"):
        path = source_dir / file_name
        if not path.exists():
            continue
        hasher.update(file_name.encode("utf-8"))
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                hasher.update(chunk)
    return hasher.hexdigest()


def build_private_manifest(roots: Iterable[str]) -> Dict:
    summary = validate_private_roots(roots, include_dataframe=False)
    manifest_sources = []
    for src in summary["sources"]:
        manifest_sources.append(
            {
                "source_db": src.source_db,
                "source_dir": str(src.source_dir),
                "is_valid": src.is_valid,
                "errors": src.errors,
                "warnings": src.warnings,
                "stats": src.stats,
                "fingerprint": _source_fingerprint(src.source_dir),
            }
        )

    return {
        "roots": summary["roots"],
        "sources_found": summary["sources_found"],
        "sources_valid": summary["sources_valid"],
        "sources_invalid": summary["sources_invalid"],
        "sources": manifest_sources,
    }


def write_private_manifest(manifest: Dict, output_path: Path) -> None:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")


def ingest_private_sources_into_db(conn: duckdb.DuckDBPyConnection, source_dirs: Iterable[str]) -> Dict:
    ingested = []
    skipped = []

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS private_entity_attributes (
            source_db VARCHAR,
            source_type VARCHAR,
            entity_type VARCHAR,
            entity_id VARCHAR,
            attribute_key VARCHAR,
            attribute_value VARCHAR,
            value_type VARCHAR
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS private_interactions (
            Phage_ID VARCHAR,
            Host_ID VARCHAR,
            Host_name VARCHAR,
            interaction VARCHAR,
            Source_DB VARCHAR,
            source_type VARCHAR
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS private_phage_host_associations (
            Phage_ID VARCHAR,
            Host_ID VARCHAR
        )
        """
    )

    for source_dir_str in source_dirs:
        source_dir = Path(source_dir_str)
        validation = validate_private_source(source_dir, include_dataframe=True)
        if not validation.is_valid or validation.metadata_df is None:
            skipped.append(
                {
                    "source_db": validation.source_db,
                    "source_dir": str(validation.source_dir),
                    "errors": validation.errors,
                }
            )
            continue

        df = validation.metadata_df.drop_duplicates(subset=["Phage_ID", "Host_ID", "Source_DB"]).copy()
        df["source_type"] = "private"

        private_phages = (
            df[["Phage_ID", "Source_DB", "Host_name", "interaction", "source_type"]]
            .drop_duplicates(subset=["Phage_ID", "Source_DB"])
            .rename(columns={"Host_name": "Host", "interaction": "Lifestyle"})
        )
        private_phages["Length"] = pd.NA
        private_phages["GC_content"] = pd.NA
        private_phages["Taxonomy"] = pd.NA
        private_phages["Completeness"] = pd.NA
        private_phages["Cluster"] = pd.NA
        private_phages["Subcluster"] = pd.NA
        private_phages = private_phages[
            [
                "Phage_ID",
                "Source_DB",
                "Length",
                "GC_content",
                "Taxonomy",
                "Completeness",
                "Host",
                "Lifestyle",
                "Cluster",
                "Subcluster",
                "source_type",
            ]
        ]
        conn.register("private_phages_df", private_phages)
        conn.execute(
            """
            INSERT INTO fact_phages
            SELECT * FROM private_phages_df
            """
        )

        if "dim_hosts" not in set(conn.execute("SHOW TABLES").fetchnumpy()["name"]):
            conn.execute(
                """
                CREATE TABLE dim_hosts (
                    Host_ID VARCHAR,
                    Species_Name VARCHAR,
                    Strain_Name VARCHAR,
                    Assembly_Accession VARCHAR,
                    Assembly_Name VARCHAR,
                    Assembly_Level VARCHAR,
                    Genome_Length BIGINT,
                    GC_Content DOUBLE,
                    RefSeq_Category VARCHAR,
                    Download_Date VARCHAR,
                    Source VARCHAR,
                    source_type VARCHAR
                )
                """
            )

        private_hosts = df[["Host_ID", "Host_name"]].drop_duplicates().rename(columns={"Host_name": "Species_Name"})
        private_hosts["Strain_Name"] = pd.NA
        private_hosts["Assembly_Accession"] = pd.NA
        private_hosts["Assembly_Name"] = pd.NA
        private_hosts["Assembly_Level"] = pd.NA
        private_hosts["Genome_Length"] = pd.NA
        private_hosts["GC_Content"] = pd.NA
        private_hosts["RefSeq_Category"] = pd.NA
        private_hosts["Download_Date"] = pd.NA
        private_hosts["Source"] = "private"
        private_hosts["source_type"] = "private"
        private_hosts = private_hosts[
            [
                "Host_ID",
                "Species_Name",
                "Strain_Name",
                "Assembly_Accession",
                "Assembly_Name",
                "Assembly_Level",
                "Genome_Length",
                "GC_Content",
                "RefSeq_Category",
                "Download_Date",
                "Source",
                "source_type",
            ]
        ]
        conn.register("private_hosts_df", private_hosts)
        conn.execute(
            """
            INSERT INTO dim_hosts
            SELECT * FROM private_hosts_df
            """
        )

        private_associations = df[["Phage_ID", "Host_ID"]].drop_duplicates()
        conn.register("private_associations_df", private_associations)
        conn.execute(
            """
            INSERT INTO private_phage_host_associations
            SELECT * FROM private_associations_df
            """
        )

        private_interactions = df[
            ["Phage_ID", "Host_ID", "Host_name", "interaction", "Source_DB", "source_type"]
        ].copy()
        conn.register("private_interactions_df", private_interactions)
        conn.execute(
            """
            INSERT INTO private_interactions
            SELECT * FROM private_interactions_df
            """
        )

        extra_columns = validation.extra_columns or []
        if extra_columns:
            attrs = df[["Phage_ID", "Host_ID", "Source_DB"] + extra_columns].copy()
            attrs = attrs.melt(
                id_vars=["Phage_ID", "Host_ID", "Source_DB"],
                value_vars=extra_columns,
                var_name="attribute_key",
                value_name="attribute_value",
            )
            attrs = attrs[attrs["attribute_value"].astype(str).str.len() > 0].copy()
            attrs["source_type"] = "private"
            attrs["entity_type"] = "interaction"
            attrs["entity_id"] = attrs["Phage_ID"] + "|" + attrs["Host_ID"]
            attrs["value_type"] = "string"
            attrs = attrs[
                [
                    "Source_DB",
                    "source_type",
                    "entity_type",
                    "entity_id",
                    "attribute_key",
                    "attribute_value",
                    "value_type",
                ]
            ].rename(columns={"Source_DB": "source_db"})
            if not attrs.empty:
                conn.register("private_attrs_df", attrs)
                conn.execute(
                    """
                    INSERT INTO private_entity_attributes
                    SELECT * FROM private_attrs_df
                    """
                )

        ingested.append(
            {
                "source_db": validation.source_db,
                "source_dir": str(validation.source_dir),
                "rows": validation.stats["rows"],
                "unique_phages": validation.stats["unique_phages"],
                "unique_hosts": validation.stats["unique_hosts"],
            }
        )

    return {"ingested": ingested, "skipped": skipped}
