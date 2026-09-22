"""
Exhaustive tests for Variant B + Source_DB FASTA header scheme across all 26 PhageScope sources.

Covers:
- Representative Phage_ID per Source_DB (clean and dirty naming patterns)
- phage_key / protein_key extraction (Variant B: token1 for proteins)
- normalize_phage_header / normalize_protein_header
- Source provenance tokens
- Deduplication on canonical keys (including IMGVR↔MetaVR cross-source Phage_ID duplicate)
- pyfaidx round-trip with canonical keys (no Duplicate key error)
- Merge script integration (single-file canonical guarantee)

These tests are SYNTHETIC and run without the full pipeline or Docker, so they
validate that *any* of the 26 sources would work if the full pipeline ran.
CI itself only downloads 2 sources (RefSeq+PhagesDB) for speed; this suite
covers the remaining 24 naming conventions offline.

See workflow/scripts/preprocessing/mergers/merge_{phage,protein}_fasta.py and
workflow/scripts/sequences/index_sequences.py for the implementation under test.
"""

import tempfile
from pathlib import Path
import sys

import pytest

# Make workflow scripts importable for direct tests
sys.path.insert(0, str(Path(__file__).parent.parent / "workflow" / "scripts" / "sequences"))
sys.path.insert(0, str(Path(__file__).parent.parent / "workflow" / "scripts" / "preprocessing" / "mergers"))

from pbi.fasta_ids import (
    phage_key,
    protein_key,
    source_of_phage_header,
    source_of_protein_header,
    normalize_phage_header,
    normalize_protein_header,
)

# ---------------------------------------------------------------------------
# Representative Phage_ID per Source_DB — taken from live fact_phages sample
# (ROW_NUMBER() OVER (PARTITION BY Source_DB) query, Sep 2026) + config.yaml
# ---------------------------------------------------------------------------
REPRESENTATIVE_PHAGE_IDS = {
    "BAPS": "Accumulibacter_sp.__GCA_016712935.1_-_ASM1671293v1__JADJQC010000007.1__91__2053492",
    "CHVD": "SAMEA1906416_a1_ct135852_vs1",
    "DDBJ": "AB009866.2",
    "ELGV": "VIBRANT_ERR1600426_k141_1560_flag=1_multi=30.0000_len=51938_fragment_1",
    "EMBL": "AJ006589.3",
    "GOV2": "6982.1.58137.GGACC_Malaspina_NODE_215_length_24696_cov_5.994151",
    "GPD": "ivig_1",
    "GSV": "2124908027.a:MRS2a_Contig_206",
    "GVD": "Broecker_Sample_ID29-1191-0_NODE_1524_length_7254_cov_8.926043",
    "Genbank": "AF009630.1",
    "HPGC": "huge_phage_100",
    "IGVD": "OTU_100",
    "IMGVR": "IMGVR_UViG_2020627000_000021|2020627000|VrWwEF_contig52410",
    "MGV": "MGV-GENOME-0000594",
    "MetaVR": "IMGVR_UViG_2029527003_000023|2029527003|APTF_contig46037|167350-219702",
    "OPD": "OPD_100",
    "OVD": "Altabtbaei_2021_03.k141_103957",
    "PhagesDB": "Arthrobacter_phage_Abba",
    "RefSeq": "NC_000867.1",
    "STV": "biochar_0",
    "SVD": "1111525849475064:k141_1333017_length_3534_cov_29.0000",
    "TYMEFLIES": "3300033816__vRhyme_111",
    "TemPhD": "TemPhD_cluster_10",
    "UHGV": "UHGV-0000018",
    "URPC": "Buffalo_1000",
    "VMGC": "v0003",
    # Extra edge patterns not in sample but from raw naming logic
    "ELGV_fragment": "VIBRANT_ERR1600426_k141_1547_flag=1_multi=29.0087_len=6951",
}

# Ensure we actually cover all 26 dataset keys from config
EXPECTED_SOURCES = {
    "Genbank", "RefSeq", "DDBJ", "EMBL", "PhagesDB", "GPD", "GVD", "MGV", "TemPhD",
    "CHVD", "IGVD", "IMGVR", "GOV2", "STV", "GSV", "UHGV", "HPGC", "URPC", "ELGV",
    "OVD", "VMGC", "OPD", "BAPS", "SVD", "TYMEFLIES", "MetaVR",
}


def test_all_sources_covered():
    assert set(REPRESENTATIVE_PHAGE_IDS.keys()) >= EXPECTED_SOURCES or EXPECTED_SOURCES.issubset(set(REPRESENTATIVE_PHAGE_IDS.keys()).union({"ELGV_fragment"}))
    # allow ELGV_fragment alias; check real sources present
    missing = EXPECTED_SOURCES - set(REPRESENTATIVE_PHAGE_IDS.keys())
    assert not missing, f"Missing representative IDs for: {missing}"


@pytest.mark.parametrize("source, phage_id", list(REPRESENTATIVE_PHAGE_IDS.items()))
def test_phage_key_no_whitespace(source, phage_id):
    assert " " not in phage_id and "\t" not in phage_id, f"{source} ID contains whitespace: {phage_id!r}"
    hdr = normalize_phage_header(phage_id, source)
    assert phage_key(hdr) == phage_id
    assert source_of_phage_header(hdr) == source
    # full header round-trip: token0 still DB Phage_ID
    assert hdr.startswith(f">{phage_id} {source}")


@pytest.mark.parametrize("source, phage_id", list(REPRESENTATIVE_PHAGE_IDS.items()))
def test_phage_header_with_description(source, phage_id):
    raw = f"{phage_id} some description with spaces"
    hdr = normalize_phage_header(raw, source)
    # rest collapsed
    assert hdr == f">{phage_id} {source} some description with spaces"
    assert phage_key(hdr) == phage_id
    assert source_of_phage_header(hdr) == source


@pytest.mark.parametrize("source, phage_id", list(REPRESENTATIVE_PHAGE_IDS.items()))
def test_protein_header_variant_b(source, phage_id):
    protein_id = f"{phage_id.split('|')[0].split(':')[0][:20]}_1".replace(" ", "_") if len(phage_id) > 30 else f"{source}_prot_001"
    # Use clean protein accession style for a subset to mimic real data
    if source in ("RefSeq", "Genbank", "DDBJ", "EMBL"):
        protein_id = "NP_049616.1" if source == "RefSeq" else "AAF39720.1"
    raw = protein_id  # original file bare header
    hdr = normalize_protein_header(raw, phage_id, source)
    assert protein_key(hdr) == protein_id
    assert phage_key(hdr) == phage_id
    assert source_of_protein_header(hdr) == source
    assert hdr.startswith(f">{phage_id} {protein_id} {source}")


def test_protein_header_with_rest():
    hdr = normalize_protein_header("AAF39720.1 hypothetical protein", "AE002163.1", "Genbank")
    assert hdr == ">AE002163.1 AAF39720.1 Genbank hypothetical protein"
    assert protein_key(hdr) == "AAF39720.1"
    assert phage_key(hdr) == "AE002163.1"
    assert source_of_protein_header(hdr) == "Genbank"


def test_cross_source_duplicate_phage_id_imgvr_metavr():
    # Same Phage_ID appears in IMGVR and MetaVR — real case from fact_phages
    pid = "IMGVR_UViG_2029527003_000023|2029527003|APTF_contig46037|167350-219702"
    hdr_imgvr = normalize_phage_header(pid, "IMGVR")
    hdr_metavr = normalize_phage_header(pid, "MetaVR")
    assert phage_key(hdr_imgvr) == phage_key(hdr_metavr) == pid
    assert source_of_phage_header(hdr_imgvr) == "IMGVR"
    assert source_of_phage_header(hdr_metavr) == "MetaVR"
    # Canonical dedup key same → would be considered duplicate; provenance differs
    assert hdr_imgvr != hdr_metavr  # full headers differ by source token


def test_merge_phage_single_file_canonical():
    """Single-file source must still emit Source_DB token (cp bypass fixed)."""
    from merge_phage_fasta import merge_fasta_files
    with tempfile.TemporaryDirectory() as td:
        src = Path(td) / "src"
        src.mkdir()
        # Simulate single extracted file containing one phage
        f = src / "a.fasta"
        f.write_text(">NC_000867.1\nATGCATGC\n")
        out = Path(td) / "RefSeq.fasta"
        merge_fasta_files(src, out)
        txt = out.read_text()
        assert ">NC_000867.1 RefSeq" in txt
        # Ensure not bare >NC_000867.1 without source
        assert txt.count(">NC_000867.1 RefSeq") == 1


def test_merge_protein_single_file_canonical():
    from merge_protein_fasta import merge_fasta_files
    with tempfile.TemporaryDirectory() as td:
        src = Path(td) / "src"
        sub = src / "NC_000867.1"
        sub.mkdir(parents=True)
        f = sub / "prot.fasta"
        f.write_text(">NP_049616.1\nMKTII\n")
        out = Path(td) / "RefSeq.fasta"
        merge_fasta_files(src, out)
        txt = out.read_text()
        assert ">NC_000867.1 NP_049616.1 RefSeq" in txt


def test_index_dedup_protein_variant_b_no_duplicate_key_error():
    """Protein FASTA with many proteins sharing same Phage must not raise Duplicate key."""
    try:
        from pyfaidx import Fasta
    except ImportError:
        pytest.skip("pyfaidx not installed")
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "all_proteins.fasta"
        # 3 proteins same phage, different Protein_IDs
        p.write_text(
            ">AE002163.1 AAF39720.1 Genbank\nATGC\n"
            ">AE002163.1 AAF39721.1 Genbank\nATGC\n"
            ">AE002163.1 AAF39722.1 Genbank\nATGC\n"
        )
        # Variant B: protein_key = token1 → 3 distinct keys → no Duplicate key
        # Requires split_char='\x00' so full header is passed to key_function
        f = Fasta(str(p), key_function=protein_key, read_long_names=True, split_char="\x00", rebuild=True)
        assert len(f.keys()) == 3
        assert set(f.keys()) == {"AAF39720.1", "AAF39721.1", "AAF39722.1"}
        f.close()
        # Old phage-key on same file would have raised Duplicate key (3 proteins same phage)
        # Need to remove existing index first then try phage_key
        fai = Path(str(p) + ".fai")
        if fai.exists():
            fai.unlink()
        with pytest.raises(ValueError, match="Duplicate key"):
            Fasta(str(p), key_function=phage_key, read_long_names=True, split_char="\x00", rebuild=True)


def test_index_dedup_phage_pipe_and_colon():
    """Pipe and colon IDs must survive pyfaidx key extraction."""
    try:
        from pyfaidx import Fasta
    except ImportError:
        pytest.skip("pyfaidx not installed")
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "all_phages.fasta"
        p.write_text(
            ">IMGVR_UViG_2020627000_000021|2020627000|VrWwEF_contig52410 IMGVR\nATGC\n"
            ">2124908027.a:MRS2a_Contig_206 GSV\nATGC\n"
            ">VIBRANT_ERR1600426_k141_1560_flag=1_multi=30.0000_len=51938_fragment_1 ELGV\nATGC\n"
        )
        f = Fasta(str(p), key_function=phage_key, read_long_names=True, split_char="\x00", rebuild=True)
        assert "IMGVR_UViG_2020627000_000021|2020627000|VrWwEF_contig52410" in f.keys()
        assert "2124908027.a:MRS2a_Contig_206" in f.keys()
        assert "VIBRANT_ERR1600426_k141_1560_flag=1_multi=30.0000_len=51938_fragment_1" in f.keys()
        f.close()


def test_normalize_rejects_whitespace_in_id():
    # phage_id param with space should be rejected (direct validation)
    with pytest.raises(ValueError):
        normalize_protein_header("NP_049616.1", "bad phage id", "RefSeq")
    # empty header should raise
    with pytest.raises(ValueError):
        normalize_phage_header("", "RefSeq")
    with pytest.raises(ValueError):
        normalize_phage_header("   ", "RefSeq")
